"""The existing execution coordinator, with explicit gates and versioned checkpoints.

This is the single scheduler. Loop owners perform their own work. Integration
with the external platform canonical interface remains an explicit requirement.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from editing import Editing
from run_binding import PARAGRAPH_ADDENDUM, PARAGRAPH_ADDENDUM_ID

OWNERS = {'construction': 'src/faculty.py', 'expression': 'src/expression.py',
          'checking': 'src/checking.py', 'editing': 'src/editing.py',
          'validation': 'src/execution.py', 'paragraph': 'src/paragraph_loop.py',
          'detector': 'src/pangram_check.py'}


class Execution:
    def __init__(self, g, faculty, expression, checking, binding=None, paragraph_loop=None,
                 max_voice_repairs=0):
        self.g, self.f, self.e, self.c = g, faculty, expression, checking
        self.binding = binding
        if type(max_voice_repairs) is not int or max_voice_repairs < 0:
            raise ValueError('Nonnegative voice repair budget required')
        self.max_voice_repairs = max_voice_repairs
        self.paragraph_loop = paragraph_loop
        if paragraph_loop is not None and (
                paragraph_loop.g is not g or paragraph_loop.expression is not expression
                or paragraph_loop.checking is not checking):
            raise ValueError('Paragraph loop must use this execution graph and faculties')
        self.editing = Editing(g, expression, checking)
        g.db.executescript('''
            CREATE TABLE IF NOT EXISTS execution(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS execution_revision(
                execution_id TEXT NOT NULL, revision INTEGER NOT NULL,
                recorded_at TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY(execution_id, revision));
            CREATE TRIGGER IF NOT EXISTS execution_revision_no_update
                BEFORE UPDATE ON execution_revision BEGIN
                SELECT RAISE(ABORT, 'Execution history is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS execution_revision_no_delete
                BEFORE DELETE ON execution_revision BEGIN
                SELECT RAISE(ABORT, 'Execution history is append-only'); END;
        ''')

    def save(self, x):
        with self.g.db:
            revision = self.g.db.execute(
                'SELECT COALESCE(MAX(revision),0)+1 FROM execution_revision WHERE execution_id=?',
                (x['id'],)).fetchone()[0]
            x['revision'] = revision
            data = json.dumps(x, sort_keys=True)
            self.g.db.execute('INSERT INTO execution_revision VALUES(?,?,?,?)',
                (x['id'], revision, datetime.now(timezone.utc).isoformat(), data))
            self.g.db.execute('INSERT OR REPLACE INTO execution VALUES(?,?)', (x['id'], data))

    def _binding_current(self, x):
        if x.get('binding_id'):
            if self.binding is None or self.binding.id != x['binding_id']:
                raise ValueError('Load the original execution binding before resuming')
            self._bound_components(self.binding.verify(), intent=x.get('intent'),
                                   max_attempts=x.get('max_attempts'))
        elif x.get('mode') != 'fixture':
            raise ValueError('A verified run binding is required')

    def _bound_components(self, manifest, *, intent=None, max_attempts=None):
        """The coordinator cannot claim one binding while its workers use another.

        Providers remain interchangeable, but a bound run requires the same
        journal/configuration contract at every model boundary. Explicit unbound
        fixture execution does not claim these production provenance guarantees.
        """
        if self.binding.g is not self.g:
            raise ValueError('Execution binding must belong to the execution graph')
        for role, provider in (
            ('construction', self.f.reasoner),
            ('expression', self.e.writer),
            ('checking', self.c.reviewer),
        ):
            journal = getattr(provider, 'journal', None)
            provider_binding = getattr(journal, 'binding', None)
            if (journal is None or getattr(journal, 'g', None) is not self.g
                    or provider_binding is None
                    or getattr(provider_binding, 'g', None) is not self.g
                    or getattr(provider_binding, 'id', None) != self.binding.id
                    or getattr(journal, 'provider_role', None) != role):
                raise ValueError('Provider must use its declared role and original execution binding: ' + role)
            configuration = getattr(provider, 'configuration', None)
            templates = getattr(provider, 'prompt_templates', None)
            if (not callable(configuration) or not callable(templates)
                    or configuration() != manifest['providers'].get(role)
                    or templates() != manifest['prompt_templates']):
                raise ValueError('Provider configuration or prompts differ from the execution binding: ' + role)
        if self.f.baseline_digest != manifest['ledger']['sha256']:
            raise ValueError('Construction must select rules from the bound ledger')
        if manifest['mode'] == 'live':
            if self.paragraph_loop is None:
                raise ValueError('Live execution requires the paragraph detector gate')
            config = (manifest.get('configuration') or {}).get('contents')
            if not isinstance(config, dict) or config.get('paragraph_mode') != 'pangram-gated-v1':
                raise ValueError('Live execution requires its committed paragraph configuration')
            if config.get('procedure_addenda') != [PARAGRAPH_ADDENDUM]:
                raise ValueError('Live execution must declare the paragraph Pangram addendum')
            addenda = manifest.get('procedure_addenda', [])
            expected_path = (Path(manifest['repository']['root']) / PARAGRAPH_ADDENDUM).resolve()
            if (len(addenda) != 1 or Path(addenda[0]['path']).resolve() != expected_path
                    or addenda[0].get('identity', {}).get('id') != PARAGRAPH_ADDENDUM_ID
                    or addenda[0].get('identity', {}).get('version') != '0.1'):
                raise ValueError('The declared paragraph addendum must be bound as an exact committed artifact')
            if self.f.rule_ids != config.get('selected_rule_ids'):
                raise ValueError('Rule selection differs from the committed configuration')
            if getattr(self.f, 'execution_profile', None) != config.get('execution_profile'):
                raise ValueError('Construction profile differs from the committed configuration')
            if self.max_voice_repairs != config.get('max_voice_repairs', 0):
                raise ValueError('Voice repair budget differs from the committed configuration')
            if getattr(self.f, 'written_calibration', []) != config.get('written_calibration', []):
                raise ValueError('Written calibration differs from the committed configuration')
            if self.paragraph_loop.paragraph_groups != config.get('paragraph_groups'):
                raise ValueError('Paragraph grouping differs from the committed configuration')
            if self.paragraph_loop.max_attempts != config.get('max_attempts', 3):
                raise ValueError('Paragraph attempt budget differs from the committed configuration')
            if intent is not None and intent != config.get('intent'):
                raise ValueError('Author intent differs from the committed configuration')
            if max_attempts is not None and max_attempts != config.get('max_attempts', 3):
                raise ValueError('Execution attempt budget differs from the committed configuration')
            scanner = self.paragraph_loop.pangram
            if scanner.configuration != config.get('pangram'):
                raise ValueError('Detector configuration differs from the committed configuration')
            detector_binding = getattr(scanner, 'binding', None)
            if (detector_binding is None or detector_binding.id != self.binding.id
                    or detector_binding.g is not self.g):
                raise ValueError('Paragraph detector must use the original execution binding')

    def inspect(self, ident):
        row = self.g.db.execute('SELECT data FROM execution WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        x = json.loads(row[0])
        if x.get('execution_scope') == 'paragraphs' and self.paragraph_loop is not None and x.get('paragraph_progress'):
            progress = self.paragraph_loop.inspect(ident)
            x['paragraph_progress'] = progress
            if progress['state'] == 'stale':
                x.update(state='stale', unresolved=progress['unresolved'])
        if x.get('assessment') and self.c.inspect(x['assessment'])['state'] == 'stale':
            x.update(state='stale', unresolved='Expression or construction changed')
        elif x.get('closure'):
            try:
                self.e.c.require_closed(x['plan'])
            except (ValueError, KeyError):
                x.update(state='stale', unresolved='Construction closure is no longer current')
        return x

    def history(self, ident):
        return [json.loads(row[0]) for row in self.g.db.execute(
            'SELECT data FROM execution_revision WHERE execution_id=? ORDER BY revision', (ident,))]

    def _checkpoint(self, x, state, loop, **details):
        x.update(state=state, active_loop=loop, loop_owner=OWNERS.get(loop), **details)
        x['history'].append({key: x.get(key) for key in (
            'attempts', 'plan', 'construction_review', 'closure', 'run',
            'assessment', 'state', 'active_loop', 'route', 'paragraph_index', 'scan')})
        self.save(x)
        return x

    def start(self, intent, max_attempts=3, *, mode='live'):
        if not isinstance(intent, str) or not intent.strip() or type(max_attempts) is not int or max_attempts < 1:
            raise ValueError('Intent and a positive attempt budget are required')
        if mode not in {'live', 'fixture'}:
            raise ValueError('Declare live or fixture execution')
        if self.paragraph_loop is not None and max_attempts != self.paragraph_loop.max_attempts:
            raise ValueError('Execution budget must match the per-paragraph attempt budget')
        if self.binding is None and mode != 'fixture':
            raise ValueError('Live execution requires an immutable run binding')
        if self.binding is not None:
            manifest = self.binding.verify()
            if manifest['mode'] != mode:
                raise ValueError('Execution mode must match its binding')
            self._bound_components(manifest, intent=intent, max_attempts=max_attempts)
        if mode == 'live' and self.paragraph_loop is not None:
            availability = self.paragraph_loop.pangram.preflight(mode=mode)
            if availability.get('state') != 'ready':
                raise ValueError('Pangram must be configured and available before live execution')
        x = dict(id=str(uuid.uuid4()), intent=intent, max_attempts=max_attempts,
                 attempts=0, state='constructing', history=[], mode=mode,
                 voice_repair_attempts=0, max_voice_repairs=self.max_voice_repairs,
                 binding_id=self.binding.id if self.binding else None,
                 execution_scope='paragraphs' if self.paragraph_loop else 'whole_plan_legacy',
                 active_loop='construction', loop_owner=OWNERS['construction'])
        self.save(x)
        try:
            x['plan'] = self.f.build(intent)
        except Exception as exc:
            return self._checkpoint(x, 'suspended_error', 'construction', error=type(exc).__name__)
        self._checkpoint(x, 'awaiting_construction_review', 'construction',
                         unresolved='Construction must be reviewed and closed before expression')
        if hasattr(self.c.reviewer, 'assess_construction'):
            return self.review_construction(x['id'])
        return x

    def review_construction(self, ident, reviewer=None):
        if self.binding is not None and reviewer is not None and reviewer is not self.c.reviewer:
            raise ValueError('Bound execution must use its declared checking provider')
        x = self.inspect(ident)
        if x['state'] not in {'awaiting_construction_review', 'construction_review_required'}:
            raise ValueError('Construction is not awaiting review')
        self._binding_current(x)
        try:
            x['construction_review'] = self.f.review(x['plan'], reviewer or self.c.reviewer)
            finding = self.f.inspect_review(x['construction_review'])
            passed = all(item['status'] == 'pass' for item in finding['findings'])
            return self._checkpoint(x,
                'awaiting_construction_closure' if passed else 'construction_review_required',
                'construction', unresolved='Explicit construction closure required' if passed
                else 'Construction findings remain unresolved')
        except Exception as exc:
            return self._checkpoint(x, 'suspended_error', 'construction', error=type(exc).__name__)

    def close_construction(self, ident, actor=None):
        x = self.inspect(ident)
        if x['state'] != 'awaiting_construction_closure':
            raise ValueError('Current passing construction review required')
        self._binding_current(x)
        x['closure'] = self.f.close(x['plan'], x['construction_review'], actor)
        if self.paragraph_loop is not None:
            try:
                progress = self.paragraph_loop.prepare(x['id'], x['plan'], mode=x['mode'])
            except Exception as exc:
                return self._checkpoint(x, 'suspended_error', 'paragraph', error=type(exc).__name__)
            return self._paragraph_checkpoint(x, progress)
        return self._checkpoint(x, 'ready', 'expression', unresolved=None, route=None)

    def repair_voice(self, ident, actor=None):
        """Repair reviewed bindings under the existing construction owner."""
        if actor != 'author':
            raise PermissionError('Explicit authorization required for voice binding repair')
        x = self.inspect(ident)
        if x['state'] != 'construction_review_required' or x.get('closure'):
            raise ValueError('Voice binding repair requires an unclosed construction with failed review')
        self._binding_current(x)
        if (getattr(self.f, 'execution_profile', None) != 'resolved-voice-v1'
                or self.max_voice_repairs < 1
                or x.get('max_voice_repairs', 0) != self.max_voice_repairs):
            raise ValueError('A committed resolved-profile voice repair budget is required')
        review = self.f.inspect_review(x['construction_review'])
        status = {finding['layer']: finding['status'] for finding in review['findings']}
        if (review['state'] != 'review_required' or review['plan'] != x['plan']
                or status != {'conceptual': 'pass', 'epistemic': 'pass', 'rhetorical_plan': 'fail'}):
            raise ValueError('Only a definite voice-plan defect with current meaning checks passed may be repaired')
        if x.get('voice_repair_attempts', 0) >= self.max_voice_repairs:
            return self._checkpoint(x, 'construction_review_required', 'construction', route='voice',
                                    unresolved='Voice binding repair budget exhausted; no closure granted')
        x['voice_repair_attempts'] = x.get('voice_repair_attempts', 0) + 1
        self._checkpoint(x, 'revising_voice', 'construction', route='voice',
                         unresolved='Repairing bindings; claims and intellectual act order remain fixed')
        from faculty import VoiceRepairReopen
        try:
            plan = self.f.repair_voice(x['plan'], x['construction_review'], actor=actor)
        except VoiceRepairReopen as exc:
            return self._checkpoint(x, 'construction_review_required', 'construction', route='construction',
                                    unresolved={'reason': exc.reason, 'layer': exc.layer,
                                                'voice_repair_attempt': exc.attempt})
        except Exception as exc:
            return self._checkpoint(x, 'suspended_error', 'construction', error=type(exc).__name__,
                                    unresolved='Voice binding repair did not produce an accepted plan')
        self._checkpoint(x, 'awaiting_construction_review', 'construction', plan=plan,
                         construction_review=None, closure=None, route=None,
                         unresolved='Revised bindings require a fresh construction review')
        return self.review_construction(ident)

    def _paragraph_checkpoint(self, x, progress):
        state = progress['state']
        mapping = {
            'ready': 'ready', 'ready_for_next_paragraph': 'ready_for_next_paragraph',
            'complete': 'awaiting_approval', 'detector_pending': 'suspended_detector_pending',
            'detector_error': 'suspended_detector_error', 'detector_flagged': 'suspended_detector_flagged',
            'detector_unscorable': 'suspended_detector_unscorable',
            'detector_blocked': 'suspended_detector_blocked',
            'expression_repair_required': 'suspended_reopen',
            'construction_required': 'suspended_reopen', 'author_review_required': 'suspended_reopen',
            'budget_exhausted': 'budget_exhausted', 'stale': 'stale',
            'generation_error': 'suspended_error', 'checking_error': 'suspended_error',
        }
        current = progress['paragraphs'][progress['active_index']]
        route = {'expression_repair_required': 'expression', 'construction_required': 'construction',
                 'author_review_required': 'author_review'}.get(state)
        loop = ('detector' if state.startswith('detector_') else
                'validation' if state == 'complete' else 'paragraph')
        x.update(paragraph_progress=progress, paragraph_index=progress['active_index'],
                 attempts=sum(len(item['attempts']) for item in progress['paragraphs']),
                 attempt_budget_scope='per_paragraph', run=current['run'],
                 assessment=current['assessment'], scan=current['scan'],
                 chapter_semantic_check=progress['chapter_semantic_check'])
        if state == 'complete':
            x.update(text=progress['text'], text_sha256=progress['text_sha256'])
        return self._checkpoint(x, mapping.get(state, 'suspended_error'), loop, route=route,
                                unresolved=progress.get('unresolved'))

    def advance(self, ident, actor=None):
        x = self.inspect(ident)
        if x.get('execution_scope') == 'paragraphs':
            if self.paragraph_loop is None:
                raise ValueError('Resume requires the original paragraph loop')
            self._binding_current(x)
            if x['state'] in {'closed', 'awaiting_approval', 'stale'}:
                raise ValueError('Paragraph execution is not runnable')
            return self._paragraph_checkpoint(x, self.paragraph_loop.advance(ident, actor=actor))
        if x['state'] not in {'ready', 'suspended_reopen'}:
            raise ValueError('Execution is not ready for expression or a permitted repair')
        self._binding_current(x)
        self.e.c.require_closed(x['plan'])
        retry = x['state'] == 'suspended_reopen'
        if retry:
            if actor != 'author':
                raise PermissionError('Explicit author authorization required for repair')
            if x.get('route') != 'expression':
                raise ValueError('Construction or author review required, not expression repair')
        if x['attempts'] >= x['max_attempts']:
            return self._checkpoint(x, 'budget_exhausted', 'editing' if retry else 'expression',
                                    unresolved='Attempt limit reached; no closure granted')
        prior_run, prior_assessment = x.get('run'), x.get('assessment')
        x['attempts'] += 1
        self._checkpoint(x, 'running', 'editing' if retry else 'expression')
        try:
            x['run'] = (self.editing.run(prior_run, prior_assessment, actor=actor)
                        if retry else self.e.run(x['plan']))
            x.pop('assessment', None)
            self._checkpoint(x, 'running', 'expression')
            draft = self.e.inspect(x['run'])
            if draft['state'] == 'reopen_requested':
                return self._checkpoint(x, 'suspended_reopen', 'construction',
                    route='construction', unresolved=draft['detail'])
            self._checkpoint(x, 'running', 'checking')
            x['assessment'] = self.c.assess(x['run'])
            result = self.c.inspect(x['assessment'])
            routes = {ticket['route'] for ticket in result['tickets']}
            route = ('author_review' if 'author_review' in routes else
                     'construction' if 'construction' in routes else
                     'expression' if routes else None)
            return self._checkpoint(x, 'suspended_reopen' if routes else 'awaiting_approval',
                'checking' if routes else 'validation', route=route,
                unresolved=result['findings'] if routes else None)
        except Exception as exc:
            # Provider errors are recorded separately; raw text may contain secrets.
            return self._checkpoint(x, 'suspended_error', x['active_loop'], error=type(exc).__name__)

    def approve(self, ident, actor):
        if actor != 'author':
            raise PermissionError('Author required')
        x = self.inspect(ident)
        self._binding_current(x)
        if x.get('execution_scope') == 'paragraphs':
            if self.paragraph_loop is None or x['state'] != 'awaiting_approval':
                raise ValueError('Current completed paragraph execution required')
            self.paragraph_loop.validate_complete(ident)
            return self._checkpoint(x, 'closed', 'validation', approved_by=actor,
                                    closure_authority='author', authorial_validation='approved',
                                    unresolved=None, chapter_semantic_check='pending')
        if x['state'] != 'awaiting_approval' or self.c.inspect(x['assessment'])['state'] != 'checks_passed':
            raise ValueError('Current passing assessment required')
        self.e.c.require_closed(x['plan'])
        return self._checkpoint(x, 'closed', 'validation', approved_by=actor,
                                closure_authority='author', unresolved=None)
