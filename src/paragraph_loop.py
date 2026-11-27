"""One paragraph of work per advance, with a detector gate before the next.

Execution remains the only scheduler. This loop records paragraph work and
returns its state; it does not autonomously retry, bypass closure, or rewrite
prose in response to detector scores.
"""
import hashlib
import json
from pathlib import Path

from editing import Editing


def _copy(value):
    return json.loads(json.dumps(value))


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class ParagraphLoop:
    def __init__(self, graph, expression, checking, pangram, *, paragraph_groups=None,
                 max_attempts=3):
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError('A positive per-paragraph attempt budget is required')
        self.g, self.expression, self.checking, self.pangram = graph, expression, checking, pangram
        self.paragraph_groups = _copy(paragraph_groups)
        self.max_attempts = max_attempts
        self.editing = Editing(graph, expression, checking)
        graph.db.executescript('''
            CREATE TABLE IF NOT EXISTS paragraph_checkpoint(
                execution_id TEXT NOT NULL, revision INTEGER NOT NULL,
                data TEXT NOT NULL, PRIMARY KEY(execution_id, revision));
            CREATE TRIGGER IF NOT EXISTS paragraph_checkpoint_no_update
                BEFORE UPDATE ON paragraph_checkpoint BEGIN
                SELECT RAISE(ABORT, 'Paragraph evidence is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS paragraph_checkpoint_no_delete
                BEFORE DELETE ON paragraph_checkpoint BEGIN
                SELECT RAISE(ABORT, 'Paragraph evidence is append-only'); END;
        ''')

    def _save(self, progress, state, **fields):
        progress.update(state=state, **fields)
        with self.g.db:
            revision = self.g.db.execute(
                'SELECT COALESCE(MAX(revision),0)+1 FROM paragraph_checkpoint WHERE execution_id=?',
                (progress['execution_id'],),
            ).fetchone()[0]
            progress['revision'] = revision
            self.g.db.execute('INSERT INTO paragraph_checkpoint VALUES(?,?,?)',
                              (progress['execution_id'], revision, json.dumps(progress, sort_keys=True)))
        return _copy(progress)

    def prepare(self, execution_id, plan, *, mode='live'):
        if mode not in {'live', 'fixture'}:
            raise ValueError('Explicit paragraph execution mode required')
        if self.g.db.execute('SELECT 1 FROM paragraph_checkpoint WHERE execution_id=?',
                             (execution_id,)).fetchone():
            raise ValueError('Paragraph execution already prepared; preserve its grouping')
        context = self.expression.context(plan)
        acts = context['acts']
        groups = self.paragraph_groups
        default = groups is None
        if default:
            groups = [[index] for index in range(len(acts))]
        if (not isinstance(groups, list) or not groups
                or any(not isinstance(group, list) or not group for group in groups)
                or any(type(index) is not int for group in groups for index in group)
                or [index for group in groups for index in group] != list(range(len(acts)))):
            raise ValueError('Paragraph groups must cover every closed-plan act once, in order')
        binding = getattr(self.pangram, 'binding', None)
        if mode == 'live':
            if binding is None:
                raise ValueError('Live paragraph execution requires a bound detector')
            manifest = binding.verify()
            configuration = json.loads(Path(manifest['configuration']['path']).read_text(encoding='utf-8'))
            if (configuration.get('paragraph_groups') != self.paragraph_groups
                    or configuration.get('max_attempts', 3) != self.max_attempts):
                raise ValueError('Paragraph grouping or budget differs from committed configuration')
        progress = {
            'execution_id': execution_id, 'plan': plan, 'mode': mode, 'active_index': 0,
            'grouping_policy': ('one_act_per_paragraph_default_unvalidated' if default
                                else 'explicit_ordered_act_groups'),
            'act_groups': _copy(groups), 'max_attempts_per_paragraph': self.max_attempts,
            'chapter_semantic_check': 'pending', 'authorial_validation': 'pending',
            'paragraphs': [
                {'id': execution_id + ':paragraph:' + str(index), 'index': index,
                 'acts': [acts[act] for act in group], 'state': 'waiting',
                 'attempts': [], 'run': None, 'assessment': None, 'scan': None,
                 'text_sha256': None}
                for index, group in enumerate(groups)
            ],
        }
        return self._save(progress, 'ready', unresolved=None)

    def inspect(self, execution_id):
        row = self.g.db.execute(
            'SELECT data FROM paragraph_checkpoint WHERE execution_id=? ORDER BY revision DESC LIMIT 1',
            (execution_id,),
        ).fetchone()
        if row is None:
            raise KeyError(execution_id)
        progress = json.loads(row[0])
        try:
            self.expression.c.require_closed(progress['plan'])
            for paragraph in progress['paragraphs']:
                if paragraph['run']:
                    draft = self.expression.inspect(paragraph['run'])
                    if draft['state'] == 'stale':
                        raise ValueError('Paragraph expression is stale')
                if paragraph['state'] == 'passed':
                    self._validate_passed(paragraph)
        except (KeyError, ValueError):
            progress.update(state='stale', unresolved='Construction, prior paragraph or detector evidence is no longer current')
        return progress

    def history(self, execution_id):
        return [json.loads(row[0]) for row in self.g.db.execute(
            'SELECT data FROM paragraph_checkpoint WHERE execution_id=? ORDER BY revision',
            (execution_id,),
        )]

    def _validate_passed(self, paragraph):
        draft = self.expression.inspect(paragraph['run'])
        assessment = self.checking.inspect(paragraph['assessment'])
        scan = self.pangram.inspect(paragraph['scan'])
        if (draft['state'] != 'draft_unvalidated'
                or assessment['run'] != paragraph['run'] or assessment['state'] != 'checks_passed'
                or scan['state'] != 'passed' or scan['run'] != paragraph['run']
                or scan['assessment'] != paragraph['assessment']
                or draft['text_sha256'] != paragraph['text_sha256']
                or scan['text_sha256'] != paragraph['text_sha256']):
            raise ValueError('Current passing paragraph evidence required')
        return draft['text']

    def _scope(self, progress, paragraph):
        prior = progress['paragraphs'][:paragraph['index']]
        for previous in prior:
            if previous['state'] != 'passed':
                raise ValueError('Previous paragraph has not passed its checks')
            self._validate_passed(previous)
        return {'id': paragraph['id'], 'index': paragraph['index'], 'acts': paragraph['acts'],
                'prior_paragraphs': [{key: previous[key] for key in ('run', 'assessment', 'text_sha256')}
                                     for previous in prior]}

    def advance(self, execution_id, actor=None):
        progress = self.inspect(execution_id)
        state = progress['state']
        if state in {'stale', 'complete', 'budget_exhausted', 'detector_flagged',
                     'detector_unscorable', 'construction_required', 'author_review_required'}:
            raise ValueError('Paragraph execution requires review or is not runnable: ' + state)
        paragraph = progress['paragraphs'][progress['active_index']]
        if state in {'detector_pending', 'detector_error'}:
            return self._scan(progress, paragraph)
        if state == 'checking_error':
            return self._check(progress, paragraph)
        editing = state == 'expression_repair_required' or (
            state == 'detector_blocked' and progress.get('pending_action') == 'editing') or (
            state == 'generation_error' and paragraph['attempts']
            and paragraph['attempts'][-1]['operation'] == 'editing')
        if state not in {'ready', 'ready_for_next_paragraph', 'expression_repair_required',
                         'detector_blocked', 'generation_error'}:
            raise ValueError('Unresolved interrupted paragraph operation; inspect its evidence')
        if (editing or state == 'generation_error') and actor != 'author':
            raise PermissionError('Explicit author authorization required for a paragraph retry')
        # This check precedes every writer invocation, including expression repair.
        availability = self.pangram.preflight(mode=progress['mode'])
        if availability.get('state') != 'ready':
            return self._save(progress, 'detector_blocked', unresolved=availability,
                              pending_action='editing' if editing else 'expression')
        if len(paragraph['attempts']) >= progress['max_attempts_per_paragraph']:
            return self._save(progress, 'budget_exhausted',
                              unresolved='Per-paragraph attempt limit reached; no closure granted')
        scope = self._scope(progress, paragraph)
        attempt = {'number': len(paragraph['attempts']) + 1,
                   'operation': 'editing' if editing else 'expression', 'state': 'running'}
        paragraph['attempts'].append(attempt)
        self._save(progress, 'generating', pending_action=None, unresolved=None)
        try:
            run = (self.editing.run(paragraph['run'], paragraph['assessment'], actor=actor)
                   if editing else self.expression.run(progress['plan'], paragraph=scope))
            attempt['run'] = run
            paragraph.update(run=run, assessment=None, scan=None, state='generated', text_sha256=None)
            self._save(progress, 'checking')
            return self._check(progress, paragraph)
        except Exception as exc:
            attempt.update(state='unresolved', error_type=type(exc).__name__)
            return self._save(progress, 'generation_error', unresolved=type(exc).__name__)

    def _check(self, progress, paragraph):
        attempt = paragraph['attempts'][-1]
        try:
            draft = self.expression.inspect(paragraph['run'])
            if draft['state'] == 'reopen_requested':
                attempt['state'] = 'construction_required'
                return self._save(progress, 'construction_required', unresolved=draft['detail'])
            if draft['state'] != 'draft_unvalidated':
                raise ValueError('Current paragraph draft required')
            assessment_id = self.checking.assess(paragraph['run'])
            paragraph['assessment'] = assessment_id
            attempt['assessment'] = assessment_id
            assessment = self.checking.inspect(assessment_id)
            if assessment['state'] != 'checks_passed':
                routes = {ticket['route'] for ticket in assessment['tickets']}
                state = ('author_review_required' if 'author_review' in routes else
                         'construction_required' if 'construction' in routes else
                         'expression_repair_required' if routes == {'expression'} else 'checking_error')
                attempt['state'] = state
                return self._save(progress, state, unresolved=assessment['findings'])
            paragraph['text_sha256'] = draft['text_sha256']
            scan = self.pangram.start(paragraph['run'], assessment_id, mode=progress['mode'])
            paragraph['scan'] = scan
            attempt.update(scan=scan, state='detector_pending')
            self._save(progress, 'detector_pending', unresolved=None)
            return self._scan(progress, paragraph)
        except Exception as exc:
            attempt.update(state='unresolved', error_type=type(exc).__name__)
            return self._save(progress, 'checking_error', unresolved=type(exc).__name__)

    def _scan(self, progress, paragraph):
        attempt = paragraph['attempts'][-1]
        try:
            scan = self.pangram.advance(paragraph['scan'])
            if (scan['run'] != paragraph['run'] or scan['assessment'] != paragraph['assessment']
                    or scan['text_sha256'] != paragraph['text_sha256']):
                raise ValueError('Detector evidence does not match the checked paragraph')
        except Exception as exc:
            attempt.update(state='detector_error', error_type=type(exc).__name__)
            return self._save(progress, 'detector_error', unresolved=type(exc).__name__)
        detector_state = scan['state']
        if detector_state != 'passed':
            state = {'prepared': 'detector_pending', 'pending': 'detector_pending',
                     'flagged': 'detector_flagged', 'unscorable': 'detector_unscorable',
                     'error': 'detector_error', 'stale': 'stale'}.get(detector_state, 'detector_error')
            attempt['state'] = state
            paragraph['state'] = state
            return self._save(progress, state, unresolved={'scan': paragraph['scan'], 'state': detector_state})
        try:
            self._validate_passed(paragraph)
        except (KeyError, ValueError) as exc:
            return self._save(progress, 'stale', unresolved=type(exc).__name__)
        paragraph['state'] = 'passed'
        attempt['state'] = 'passed'
        if progress['active_index'] + 1 < len(progress['paragraphs']):
            progress['active_index'] += 1
            return self._save(progress, 'ready_for_next_paragraph', unresolved=None)
        text = '\n\n'.join(self._validate_passed(item) for item in progress['paragraphs'])
        return self._save(progress, 'complete', text=text, text_sha256=_sha(text), unresolved=None,
                          chapter_semantic_check='pending', authorial_validation='pending')

    def validate_complete(self, execution_id):
        progress = self.inspect(execution_id)
        if progress['state'] != 'complete':
            raise ValueError('Every paragraph requires current four-layer and detector checks')
        text = '\n\n'.join(self._validate_passed(item) for item in progress['paragraphs'])
        if progress['text'] != text or progress['text_sha256'] != _sha(text):
            raise ValueError('Assembled chapter differs from checked paragraphs')
        return progress
