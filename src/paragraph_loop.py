"""One paragraph of work per advance, with a detector gate before the next.

Execution remains the only scheduler. This loop records paragraph work and
returns its state; it does not autonomously retry, bypass closure, or rewrite
prose in response to detector scores.
"""
import hashlib
import json
from pathlib import Path

from editing import Editing
from run_binding import digest, paragraph_addendum, PARAGRAPH_RETRY_ADDENDUM, PARAGRAPH_OVER99_ADDENDUM


FRESH_EXPRESSION_POLICY = 'author-authorized-v1'


def validate_fresh_retry(policy, max_retries, max_attempts):
    if (policy not in (None, FRESH_EXPRESSION_POLICY)
            or type(max_retries) is not int or max_retries < 0
            or (policy is None and max_retries != 0)
            or (policy is not None and not 0 < max_retries < max_attempts)):
        raise ValueError('Fresh expression retry requires explicit opt-in and a positive limit within the total attempt budget')


def _copy(value):
    return json.loads(json.dumps(value))


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class ParagraphLoop:
    def __init__(self, graph, expression, checking, pangram, *, paragraph_groups=None,
                 max_attempts=3, fresh_expression_retry=None, max_fresh_retries=0):
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError('A positive per-paragraph attempt budget is required')
        validate_fresh_retry(fresh_expression_retry, max_fresh_retries, max_attempts)
        self.g, self.expression, self.checking, self.pangram = graph, expression, checking, pangram
        self.paragraph_groups = _copy(paragraph_groups)
        self.max_attempts = max_attempts
        self.fresh_expression_retry = fresh_expression_retry
        self.max_fresh_retries = max_fresh_retries
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

    def _save(self, progress, state, *, expected_revision=None, **fields):
        with self.g.db:
            if expected_revision is not None:
                self.g.db.execute('BEGIN IMMEDIATE')
            revision = self.g.db.execute(
                'SELECT COALESCE(MAX(revision),0)+1 FROM paragraph_checkpoint WHERE execution_id=?',
                (progress['execution_id'],),
            ).fetchone()[0]
            if expected_revision is not None and revision != expected_revision + 1:
                raise ValueError('Paragraph checkpoint changed before the authorized fresh operation')
            progress.update(state=state, **fields)
            progress['revision'] = revision
            self.g.db.execute('INSERT INTO paragraph_checkpoint VALUES(?,?,?)',
                              (progress['execution_id'], revision, json.dumps(progress, sort_keys=True)))
        return _copy(progress)

    def _bound_contract(self, mode):
        if mode != 'live':
            return
        binding = getattr(self.pangram, 'binding', None)
        if binding is None:
            raise ValueError('Live paragraph execution requires a bound detector')
        manifest = binding.verify()
        configuration = json.loads(Path(manifest['configuration']['path']).read_text(encoding='utf-8'))
        if (configuration.get('paragraph_groups') != self.paragraph_groups
                or configuration.get('max_attempts', 3) != self.max_attempts
                or configuration.get('fresh_expression_retry') != self.fresh_expression_retry
                or configuration.get('max_fresh_retries', 0) != self.max_fresh_retries):
            raise ValueError('Paragraph grouping or retry budgets differ from committed configuration')
        if self.fresh_expression_retry and paragraph_addendum(configuration)[0] not in {PARAGRAPH_RETRY_ADDENDUM, PARAGRAPH_OVER99_ADDENDUM}:
            raise ValueError('Fresh expression retries require the separately bound v0.2 addendum')

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
        single_paragraph = groups == 'all_acts_one_paragraph'
        if single_paragraph:
            groups = [list(range(len(acts)))]
        elif default:
            groups = [[index] for index in range(len(acts))]
        if (not isinstance(groups, list) or not groups
                or any(not isinstance(group, list) or not group for group in groups)
                or any(type(index) is not int for group in groups for index in group)
                or [index for group in groups for index in group] != list(range(len(acts)))):
            raise ValueError('Paragraph groups must cover every closed-plan act once, in order')
        self._bound_contract(mode)
        progress = {
            'execution_id': execution_id, 'plan': plan, 'mode': mode, 'active_index': 0,
            'grouping_policy': ('one_act_per_paragraph_default_unvalidated' if default
                                else 'all_closed_acts_in_one_paragraph' if single_paragraph
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
        if self.fresh_expression_retry is not None:
            progress.update(fresh_expression_retry=self.fresh_expression_retry,
                            max_fresh_retries=self.max_fresh_retries)
        return self._save(progress, 'ready', unresolved=None)

    def continue_expression(self, execution_id, parent, reference, *, actor=None):
        """Prepare the next normal editing attempt, preserving the source work ID."""
        if actor != 'author':
            raise PermissionError('Explicit author authorization required for continuation')
        if (digest(parent) != reference['source_progress_sha256']
                or parent['execution_id'] != reference['source_execution_id']
                or parent['state'] != 'budget_exhausted'
                or len(parent['paragraphs']) != 1 or parent['active_index'] != 0
                or self.max_attempts <= parent['max_attempts_per_paragraph']):
            raise ValueError('Exact exhausted paragraph evidence and an extended total budget required')
        paragraph = parent['paragraphs'][0]
        assessment = self.editing._current(paragraph['run'], paragraph['assessment'])
        progress = self.prepare(execution_id, parent['plan'], mode=parent['mode'])
        if progress['act_groups'] != parent['act_groups']:
            raise ValueError('Continuation cannot change paragraph grouping')
        # Paragraph identity describes the same closed intellectual work. New
        # execution, binding, editing attempt, expression and assessment IDs are
        # recorded separately; no prior checkpoint or attempt is relabeled.
        progress['paragraphs'] = _copy(parent['paragraphs'])
        progress['continuation'] = _copy(reference)
        return self._save(progress, 'expression_repair_required',
                          pending_action='editing', unresolved=assessment['findings'])

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

    def _flagged_source(self, progress, paragraph):
        """A detector flag authorizes no repair diagnosis; verify its exact witness."""
        if (self.fresh_expression_retry != FRESH_EXPRESSION_POLICY
                or progress.get('fresh_expression_retry') != self.fresh_expression_retry
                or progress.get('max_fresh_retries') != self.max_fresh_retries
                or progress.get('max_attempts_per_paragraph') != self.max_attempts):
            raise ValueError('Fresh expression retry is not enabled by this frozen paragraph configuration')
        self._bound_contract(progress['mode'])
        draft = self.expression.inspect(paragraph['run'])
        assessment = self.checking.inspect(paragraph['assessment'])
        scan = self.pangram.inspect(paragraph['scan'])
        if (draft['state'] != 'draft_unvalidated' or draft['plan'] != progress['plan']
                or (draft.get('input') or {}).get('paragraph') != self._scope(progress, paragraph)
                or assessment['run'] != paragraph['run'] or assessment['state'] != 'checks_passed'
                or len(assessment['findings']) != 4
                or {item['layer']: item['status'] for item in assessment['findings']} != {
                    'conceptual': 'pass', 'epistemic': 'pass', 'rhetorical': 'pass', 'linguistic': 'pass'}
                or scan['state'] != 'flagged' or scan['run'] != paragraph['run']
                or scan.get('plan') != progress['plan']
                or scan['assessment'] != paragraph['assessment']
                or scan.get('paragraph_id') != paragraph['id']
                or scan.get('assessment_snapshot_sha256') != assessment['snapshot_sha256']
                or scan['text_sha256'] != draft['text_sha256']
                or paragraph['text_sha256'] != draft['text_sha256']):
            raise ValueError('Fresh retry requires the current exact four-layer-passing, detector-flagged paragraph')
        return {'plan': progress['plan'], 'paragraph_id': paragraph['id'],
                'run': paragraph['run'], 'assessment': paragraph['assessment'], 'scan': paragraph['scan'],
                'text_sha256': draft['text_sha256'],
                'assessment_snapshot_sha256': assessment['snapshot_sha256'],
                'actor': 'author', 'policy': self.fresh_expression_retry}

    def _fresh_budget(self, progress, paragraph):
        if len(paragraph['attempts']) >= progress['max_attempts_per_paragraph']:
            return self._save(progress, 'budget_exhausted', expected_revision=progress['revision'],
                              unresolved='Per-paragraph attempt limit reached; no closure granted')
        count = sum(item['operation'] == 'fresh_expression' for item in paragraph['attempts'])
        if count >= self.max_fresh_retries:
            return self._save(progress, 'fresh_retry_exhausted', expected_revision=progress['revision'],
                              unresolved='Committed fresh-expression retry limit reached; no closure granted')
        return None

    def retry_fresh_expression(self, execution_id, *, actor=None):
        if actor != 'author':
            raise PermissionError('Explicit author authorization required for fresh expression')
        progress = self.inspect(execution_id)
        if progress['state'] != 'detector_flagged':
            raise ValueError('Only a completed flagged paragraph can request fresh expression')
        paragraph = progress['paragraphs'][progress['active_index']]
        witness = self._flagged_source(progress, paragraph)
        exhausted = self._fresh_budget(progress, paragraph)
        if exhausted is not None:
            return exhausted
        return self._save(progress, 'fresh_expression_required', expected_revision=progress['revision'],
                          fresh_retry_source=witness, pending_action='fresh_expression',
                          unresolved='Authorized fresh candidate from the unchanged closed construction')

    def advance(self, execution_id, actor=None):
        progress = self.inspect(execution_id)
        state = progress['state']
        if state in {'stale', 'complete', 'budget_exhausted', 'fresh_retry_exhausted', 'detector_flagged',
                     'detector_unscorable', 'construction_required', 'author_review_required'}:
            raise ValueError('Paragraph execution requires review or is not runnable: ' + state)
        paragraph = progress['paragraphs'][progress['active_index']]
        if state in {'detector_pending', 'detector_error'}:
            return self._scan(progress, paragraph)
        if state == 'checking_error':
            return self._check(progress, paragraph)
        fresh = state == 'fresh_expression_required' or (
            state == 'detector_blocked' and progress.get('pending_action') == 'fresh_expression') or (
            state == 'generation_error' and paragraph['attempts']
            and paragraph['attempts'][-1]['operation'] == 'fresh_expression')
        editing = state == 'expression_repair_required' or (
            state == 'detector_blocked' and progress.get('pending_action') == 'editing') or (
            state == 'generation_error' and paragraph['attempts']
            and paragraph['attempts'][-1]['operation'] == 'editing')
        if state not in {'ready', 'ready_for_next_paragraph', 'expression_repair_required',
                         'fresh_expression_required', 'detector_blocked', 'generation_error'}:
            raise ValueError('Unresolved interrupted paragraph operation; inspect its evidence')
        if (editing or fresh or state == 'generation_error') and actor != 'author':
            raise PermissionError('Explicit author authorization required for a paragraph retry')
        if fresh:
            witness = self._flagged_source(progress, paragraph)
            if progress.get('fresh_retry_source') != witness:
                raise ValueError('The authorized fresh-expression source witness changed')
            exhausted = self._fresh_budget(progress, paragraph)
            if exhausted is not None:
                return exhausted
        # This check precedes every writer invocation, including expression repair.
        availability = self.pangram.preflight(mode=progress['mode'])
        if availability.get('state') != 'ready':
            return self._save(progress, 'detector_blocked', unresolved=availability,
                              expected_revision=progress['revision'] if fresh else None,
                              pending_action='fresh_expression' if fresh else 'editing' if editing else 'expression')
        if fresh and self._flagged_source(progress, paragraph) != witness:
            raise ValueError('Fresh-expression source changed during preflight')
        if len(paragraph['attempts']) >= progress['max_attempts_per_paragraph']:
            return self._save(progress, 'budget_exhausted',
                              unresolved='Per-paragraph attempt limit reached; no closure granted')
        scope = self._scope(progress, paragraph)
        attempt = {'number': len(paragraph['attempts']) + 1,
                   'operation': 'fresh_expression' if fresh else 'editing' if editing else 'expression', 'state': 'running'}
        if fresh:
            attempt['fresh_retry_source'] = _copy(witness)
        paragraph['attempts'].append(attempt)
        self._save(progress, 'generating', pending_action=None, unresolved=None,
                   expected_revision=progress['revision'] if fresh else None)
        try:
            if fresh and self._flagged_source(progress, paragraph) != witness:
                raise ValueError('Fresh-expression source changed before generation')
            run = (self.editing.run(paragraph['run'], paragraph['assessment'], actor=actor)
                   if editing else self.expression.run(progress['plan'], paragraph=scope))
            attempt['run'] = run
            if fresh and self._flagged_source(progress, paragraph) != witness:
                raise ValueError('Fresh-expression source changed during generation')
            paragraph.update(run=run, assessment=None, scan=None, state='generated', text_sha256=None)
            progress.pop('fresh_retry_source', None)
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
