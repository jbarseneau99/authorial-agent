"""Bounded fresh candidates under deterministic providers; no live calls."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from checking import Checking
from execution import Execution
from expression import Expression
from faculty import Faculty
from model import Graph
from paragraph_loop import FRESH_EXPRESSION_POLICY, ParagraphLoop
from pangram_check import PangramCheck
from run_agent import validate_configuration
from run_binding import PARAGRAPH_RETRY_ADDENDUM, PARAGRAPH_RETRY_ADDENDUM_ID, ProviderJournal
from test_checking import Reviewer
from test_faculty import Research
import test_full_voice_corpus as corpus_fixture
from test_helpers import FixtureConstructionReviewer
from test_pangram_check import CONFIG, result_for
import test_paragraph_cli as cli_fixture
from test_paragraph_loop import TwoActReasoner
from test_providers import completion
from test_resolved_checking_editing import criterion_findings


FAILED_TEXT = 'REJECTED_CANDIDATE_SENTINEL ' + ' '.join(['fixture'] * 60) + '.'


class CountedWriter:
    def __init__(self):
        self.contexts = []
        self.raise_next = False
        self.mutate = None
        self.short = False

    def realize(self, context):
        self.contexts.append(copy.deepcopy(context))
        if self.raise_next:
            self.raise_next = False
            raise RuntimeError('Synthetic writer failure')
        if self.mutate:
            self.mutate()
            self.mutate = None
        index = len(self.contexts)
        text = FAILED_TEXT if index == 1 else ('Candidate ' + str(index) + ' ' + ' '.join(['fixture'] * 60) + '.')
        if self.short:
            text = 'Too short for the fixture detector.'
        return {'status': 'draft', 'sentences': [{'text': text, 'acts': context['acts']}]}


class CountedReviewer(Reviewer, FixtureConstructionReviewer):
    def __init__(self, fail_first=False):
        self.contexts, self.fail_first = [], fail_first

    def assess(self, context):
        self.contexts.append(copy.deepcopy(context))
        return Reviewer('linguistic' if self.fail_first and len(self.contexts) == 1 else None).assess(context)


def fixture_scanner(graph, expression, checking, outcomes, binding=None):
    tasks, calls = {}, []
    labels = list(outcomes)

    def transport(request):
        calls.append(request.get_method())
        if request.get_method() == 'POST':
            text = json.loads(request.data)['text']
            task = 'fixture-task-' + str(len(tasks))
            tasks[task] = (text, labels.pop(0) if labels else 'Human Written')
            return {'task_id': task}
        text, label = tasks[request.full_url.rsplit('/', 1)[1]]
        if label == 'error':
            return result_for(text, version='9.9')
        return result_for(text, label=label)

    return PangramCheck(graph, expression, checking, configuration=CONFIG,
                        binding=binding, transport=transport), calls


class FreshRetryTests(unittest.TestCase):
    def engine(self, outcomes=('AI-Generated', 'Human Written'), *, enabled=True,
               budget=4, fresh_limit=2, groups='all_acts_one_paragraph', fail_first=False, short=False):
        graph = Graph()
        self.addCleanup(graph.db.close)
        writer, reviewer = CountedWriter(), CountedReviewer(fail_first)
        writer.short = short
        expression, checking = Expression(graph, writer), Checking(graph, reviewer)
        scanner, http_calls = fixture_scanner(graph, expression, checking, outcomes)
        loop = ParagraphLoop(graph, expression, checking, scanner, paragraph_groups=groups,
                             max_attempts=budget,
                             fresh_expression_retry=FRESH_EXPRESSION_POLICY if enabled else None,
                             max_fresh_retries=fresh_limit if enabled else 0)
        engine = Execution(graph, Faculty(graph, TwoActReasoner(), Research()), expression,
                           checking, paragraph_loop=loop)
        current = engine.start('Synthetic fresh candidate test', max_attempts=budget, mode='fixture')
        current = engine.close_construction(current['id'], actor='author')
        return engine, writer, reviewer, scanner, http_calls, current

    def scan(self, engine, current):
        while current['state'] == 'suspended_detector_pending':
            current = engine.advance(current['id'])
        return current

    def flagged(self, *args, **kwargs):
        values = self.engine(*args, **kwargs)
        engine, writer, reviewer, scanner, calls, current = values
        current = self.scan(engine, engine.advance(current['id']))
        self.assertEqual(current['state'], 'suspended_detector_flagged')
        return engine, writer, reviewer, scanner, calls, current

    def test_fresh_candidate_retains_failed_evidence_and_rechecks_before_acceptance(self):
        engine, writer, reviewer, scanner, _, old = self.flagged()
        old_draft = engine.e.inspect(old['run'])
        old_assessment = engine.c.inspect(old['assessment'])
        old_scan = scanner.inspect(old['scan'])
        closed = engine.e.c.snapshot(old['plan'])
        history = engine.paragraph_loop.history(old['id'])
        for actor in (None, 'agent'):
            with self.assertRaises(PermissionError):
                engine.retry_fresh_expression(old['id'], actor=actor)
        queued = engine.retry_fresh_expression(old['id'], actor='author')
        self.assertEqual(queued['state'], 'ready_for_fresh_expression')
        self.assertEqual(queued['attempts'], 1)
        self.assertEqual(len(writer.contexts), 1)
        with self.assertRaises(ValueError):
            engine.retry_fresh_expression(old['id'], actor='author')
        with self.assertRaises(PermissionError):
            engine.advance(old['id'])
        pending = engine.advance(old['id'], actor='author')
        self.assertEqual(pending['state'], 'suspended_detector_pending')
        self.assertEqual(pending['paragraph_index'], 0)
        complete = self.scan(engine, pending)
        self.assertEqual(complete['state'], 'awaiting_approval')
        self.assertEqual(complete['paragraph_progress']['authorial_validation'], 'pending')
        attempts = complete['paragraph_progress']['paragraphs'][0]['attempts']
        self.assertEqual([item['operation'] for item in attempts], ['expression', 'fresh_expression'])
        self.assertEqual(attempts[0]['scan'], old['scan'])
        self.assertEqual(attempts[1]['fresh_retry_source']['run'], old['run'])
        self.assertNotEqual(complete['run'], old['run'])
        self.assertNotEqual(complete['assessment'], old['assessment'])
        self.assertNotEqual(complete['scan'], old['scan'])
        self.assertEqual(len(reviewer.contexts), 2)
        request = writer.contexts[-1]
        self.assertNotIn('repair', request)
        self.assertNotIn('REJECTED_CANDIDATE_SENTINEL', json.dumps(request))
        self.assertNotIn('fresh_retry_source', request)
        self.assertNotIn(old['scan'], json.dumps(request))
        self.assertEqual(engine.e.inspect(old['run']), old_draft)
        self.assertEqual(engine.c.inspect(old['assessment']), old_assessment)
        self.assertEqual(scanner.inspect(old['scan']), old_scan)
        self.assertEqual(engine.e.c.snapshot(old['plan']), closed)
        self.assertEqual(engine.paragraph_loop.history(old['id'])[:len(history)], history)

    def test_no_next_paragraph_before_fresh_candidate_review_and_scan_pass(self):
        engine, writer, _, _, _, old = self.flagged(groups=[[0], [1]])
        engine.retry_fresh_expression(old['id'], actor='author')
        pending = engine.advance(old['id'], actor='author')
        self.assertEqual([item['paragraph']['index'] for item in writer.contexts], [0, 0])
        passed = self.scan(engine, pending)
        self.assertEqual(passed['state'], 'ready_for_next_paragraph')
        current = engine.advance(old['id'])
        self.assertEqual([item['paragraph']['index'] for item in writer.contexts], [0, 0, 1])
        prior = writer.contexts[-1]['prior_paragraphs'][0]
        self.assertEqual(prior['run'], passed['paragraph_progress']['paragraphs'][0]['run'])
        self.assertNotIn('REJECTED_CANDIDATE_SENTINEL', json.dumps(writer.contexts[-1]))
        self.assertEqual(self.scan(engine, current)['state'], 'awaiting_approval')

    def test_legacy_default_keeps_detector_flag_terminal(self):
        engine, writer, _, _, _, old = self.flagged(enabled=False)
        with self.assertRaises(ValueError):
            engine.retry_fresh_expression(old['id'], actor='author')
        with self.assertRaises(ValueError):
            engine.advance(old['id'], actor='author')
        self.assertEqual(len(writer.contexts), 1)

    def test_both_budgets_stop_without_resetting_existing_attempts(self):
        engine, writer, _, _, _, old = self.flagged(
            outcomes=('AI-Generated', 'AI-Generated'), budget=4, fresh_limit=1)
        engine.retry_fresh_expression(old['id'], actor='author')
        flagged = self.scan(engine, engine.advance(old['id'], actor='author'))
        self.assertEqual(flagged['attempts'], 2)
        exhausted = engine.retry_fresh_expression(old['id'], actor='author')
        self.assertEqual(exhausted['state'], 'fresh_retry_exhausted')
        self.assertEqual(len(writer.contexts), 2)
        engine, writer, _, _, _, current = self.engine(
            outcomes=('AI-Generated', 'AI-Generated'), budget=3, fresh_limit=2, fail_first=True)
        failed = engine.advance(current['id'])
        self.assertEqual(failed['state'], 'suspended_reopen')
        flagged = self.scan(engine, engine.advance(current['id'], actor='author'))
        self.assertEqual(flagged['attempts'], 2)
        engine.retry_fresh_expression(current['id'], actor='author')
        flagged = self.scan(engine, engine.advance(current['id'], actor='author'))
        self.assertEqual(flagged['attempts'], 3)
        exhausted = engine.retry_fresh_expression(current['id'], actor='author')
        self.assertEqual(exhausted['state'], 'budget_exhausted')
        self.assertEqual([item['operation'] for item in exhausted['paragraph_progress']['paragraphs'][0]['attempts']],
                         ['expression', 'editing', 'fresh_expression'])
        self.assertEqual(len(writer.contexts), 3)

    def test_pending_error_unscorable_and_stale_results_cannot_retry(self):
        for scenario in ('pending', 'error', 'unscorable', 'stale'):
            with self.subTest(scenario=scenario):
                engine, writer, _, _, _, current = self.engine(
                    outcomes=('error' if scenario == 'error' else 'AI-Generated',),
                    short=scenario == 'unscorable')
                current = engine.advance(current['id'])
                if scenario not in {'pending', 'unscorable'}:
                    current = self.scan(engine, current)
                if scenario == 'stale':
                    sentence = engine.e.inspect(current['run'])['sentences'][0]
                    engine.g.revise(sentence['id'], dict(sentence['payload'], text='Changed fixture paragraph.'))
                with self.assertRaises(ValueError):
                    engine.retry_fresh_expression(current['id'], actor='author')
                self.assertEqual(len(writer.contexts), 1)

    def test_blocked_preflight_preserves_witness_and_requires_authorized_resume(self):
        engine, writer, _, scanner, _, old = self.flagged()
        queued = engine.retry_fresh_expression(old['id'], actor='author')
        witness = queued['paragraph_progress']['fresh_retry_source']
        with patch.object(scanner, 'preflight', return_value={'state': 'blocked', 'reason': 'Fixture unavailable'}):
            paused = engine.advance(old['id'], actor='author')
        self.assertEqual(paused['state'], 'suspended_detector_blocked')
        self.assertEqual(paused['attempts'], 1)
        self.assertEqual(paused['paragraph_progress']['pending_action'], 'fresh_expression')
        self.assertEqual(paused['paragraph_progress']['fresh_retry_source'], witness)
        self.assertEqual(len(writer.contexts), 1)
        with self.assertRaises(PermissionError):
            engine.advance(old['id'])
        self.assertEqual(self.scan(engine, engine.advance(old['id'], actor='author'))['state'], 'awaiting_approval')

    def test_generation_error_preserves_witness_and_consumes_both_limits(self):
        engine, writer, _, _, _, old = self.flagged(budget=4, fresh_limit=2)
        queued = engine.retry_fresh_expression(old['id'], actor='author')
        writer.raise_next = True
        failed = engine.advance(old['id'], actor='author')
        self.assertEqual(failed['state'], 'suspended_error')
        self.assertEqual(failed['attempts'], 2)
        self.assertEqual(failed['paragraph_progress']['fresh_retry_source'], queued['paragraph_progress']['fresh_retry_source'])
        with self.assertRaises(PermissionError):
            engine.advance(old['id'])
        complete = self.scan(engine, engine.advance(old['id'], actor='author'))
        self.assertEqual(complete['state'], 'awaiting_approval')
        attempts = complete['paragraph_progress']['paragraphs'][0]['attempts']
        self.assertEqual([item['operation'] for item in attempts], ['expression', 'fresh_expression', 'fresh_expression'])
        self.assertEqual(attempts[1]['state'], 'unresolved')
        self.assertEqual(attempts[1]['fresh_retry_source'], attempts[2]['fresh_retry_source'])

    def test_changed_source_during_preflight_never_consumes_or_invokes_writer(self):
        engine, writer, _, scanner, _, old = self.flagged()
        engine.retry_fresh_expression(old['id'], actor='author')
        sentence = engine.e.inspect(old['run'])['sentences'][0]
        def preflight(mode):
            engine.g.revise(sentence['id'], dict(sentence['payload'], text='Changed during preflight.'))
            return {'state': 'ready'}
        with patch.object(scanner, 'preflight', side_effect=preflight), self.assertRaises(ValueError):
            engine.advance(old['id'], actor='author')
        self.assertEqual(len(writer.contexts), 1)
        self.assertEqual(engine.inspect(old['id'])['state'], 'stale')
        self.assertEqual(len(engine.paragraph_loop.inspect(old['id'])['paragraphs'][0]['attempts']), 1)

    def test_source_mutation_during_generation_retains_output_without_review_or_scan(self):
        engine, writer, reviewer, _, calls, old = self.flagged()
        engine.retry_fresh_expression(old['id'], actor='author')
        sentence = engine.e.inspect(old['run'])['sentences'][0]
        writer.mutate = lambda: engine.g.revise(sentence['id'], dict(sentence['payload'], text='Changed during generation.'))
        failed = engine.advance(old['id'], actor='author')
        self.assertEqual(failed['state'], 'suspended_error')
        attempt = failed['paragraph_progress']['paragraphs'][0]['attempts'][-1]
        self.assertEqual(attempt['state'], 'unresolved')
        self.assertNotEqual(attempt['run'], old['run'])
        self.assertEqual(engine.e.inspect(attempt['run'])['state'], 'draft_unvalidated')
        self.assertEqual(len(reviewer.contexts), 1)
        self.assertEqual(calls, ['POST', 'GET'])
        self.assertEqual(engine.inspect(old['id'])['state'], 'stale')

    def test_stale_callers_cannot_claim_another_fresh_operation(self):
        engine, writer, _, _, _, old = self.flagged()
        loop = engine.paragraph_loop
        stale_flagged = loop.inspect(old['id'])
        engine.retry_fresh_expression(old['id'], actor='author')
        queued = loop.inspect(old['id'])
        with patch.object(loop, 'inspect', return_value=copy.deepcopy(stale_flagged)), self.assertRaisesRegex(ValueError, 'checkpoint changed'):
            loop.retry_fresh_expression(old['id'], actor='author')
        self.assertEqual(len(writer.contexts), 1)
        self.scan(engine, engine.advance(old['id'], actor='author'))
        with patch.object(loop, 'inspect', return_value=copy.deepcopy(queued)), self.assertRaisesRegex(ValueError, 'checkpoint changed'):
            loop.advance(old['id'], actor='author')
        self.assertEqual(len(writer.contexts), 2)

    def test_wrong_scan_identity_or_layer_findings_are_rejected(self):
        for mutation in ('plan', 'paragraph_id', 'text_sha256', 'assessment_snapshot_sha256', 'findings'):
            with self.subTest(mutation=mutation):
                engine, writer, _, scanner, _, old = self.flagged()
                if mutation == 'findings':
                    original = engine.c.inspect(old['assessment'])
                    changed = dict(original, findings=original['findings'][:-1])
                    target, method, value = engine.c, 'inspect', changed
                else:
                    changed = scanner.inspect(old['scan'])
                    changed[mutation] = 'not-the-current-identity'
                    target, method, value = scanner, 'inspect', changed
                with patch.object(target, method, return_value=changed), self.assertRaises(ValueError):
                    engine.retry_fresh_expression(old['id'], actor='author')
                self.assertEqual(len(writer.contexts), 1)


class FreshRetryConfigurationTests(unittest.TestCase):
    def test_version_opt_in_and_typed_limits_are_all_required(self):
        base = cli_fixture.live_configuration()
        validate_configuration(base)
        new = dict(base, procedure_addenda=[PARAGRAPH_RETRY_ADDENDUM])
        validate_configuration(new)  # v0.2 alone does not enable anything.
        for change in ({'fresh_expression_retry': FRESH_EXPRESSION_POLICY, 'max_fresh_retries': 1},
                       {'max_fresh_retries': 1}):
            with self.assertRaises(ValueError):
                validate_configuration(dict(base, **change))
        enabled = dict(new, fresh_expression_retry=FRESH_EXPRESSION_POLICY, max_fresh_retries=1)
        validate_configuration(enabled)
        for limit in (True, 0, -1, 3, '1'):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                validate_configuration(dict(enabled, max_fresh_retries=limit))
        for policy in (True, {}, [], 'unregistered'):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                validate_configuration(dict(enabled, fresh_expression_retry=policy))
        for addenda in ([{}], [[]], [PARAGRAPH_RETRY_ADDENDUM, PARAGRAPH_RETRY_ADDENDUM]):
            with self.subTest(addenda=addenda), self.assertRaises(ValueError):
                validate_configuration(dict(enabled, procedure_addenda=addenda))

    def test_bound_workers_cannot_change_retry_policy_or_addendum(self):
        engine, manifest = cli_fixture.ParagraphCLITests.live_components_fixture(self)
        config = manifest['configuration']['contents']
        config.update(procedure_addenda=[PARAGRAPH_RETRY_ADDENDUM],
                      fresh_expression_retry=FRESH_EXPRESSION_POLICY, max_fresh_retries=1)
        manifest['procedure_addenda'][0].update(
            path=str(Path(manifest['repository']['root']) / PARAGRAPH_RETRY_ADDENDUM),
            identity={'id': PARAGRAPH_RETRY_ADDENDUM_ID, 'version': '0.2'})
        loop = engine.paragraph_loop
        loop.fresh_expression_retry, loop.max_fresh_retries = FRESH_EXPRESSION_POLICY, 1
        engine._bound_components(manifest)
        for attribute, value in (('fresh_expression_retry', None), ('max_fresh_retries', 2)):
            original = getattr(loop, attribute)
            setattr(loop, attribute, value)
            with self.assertRaises(ValueError):
                engine._bound_components(manifest)
            setattr(loop, attribute, original)
        manifest['procedure_addenda'][0]['identity']['version'] = '0.1'
        with self.assertRaises(ValueError):
            engine._bound_components(manifest)
        self.assertEqual(engine.g.db.execute('SELECT count(*) FROM provider_invocation').fetchone()[0], 0)


class FreshRetryJournalTests(unittest.TestCase):
    records = corpus_fixture.FullVoiceCorpusTests.records

    def setUp(self):
        corpus_fixture.FullVoiceCorpusTests.setUp(self)
        self.writer_requests = []
        self.enterContext(patch.dict('os.environ', {'TEST_KEY': 'fixture-secret-key'}))

    def transport(self, role, request):
        record = self.journals[role].inspect()[-1]
        self.assertEqual(record['state'], 'invoking')
        self.assertEqual(record['request'].encode(), request.data)
        context = json.loads(json.loads(request.data)['messages'][1]['content'])
        if record['operation'] == 'construction':
            result = corpus_fixture.CorpusReasoner().propose(context)
        elif record['operation'] == 'construction_review':
            result = {'findings': [{'layer': layer, 'status': 'pass', 'reason': 'Synthetic construction review.'}
                                  for layer in ('conceptual', 'epistemic', 'rhetorical_plan')]}
        elif record['operation'] == 'expression':
            self.writer_requests.append(copy.deepcopy(context))
            text = FAILED_TEXT if len(self.writer_requests) == 1 else 'FRESH_CANDIDATE ' + ' '.join(['fixture'] * 60) + '.'
            result = {'status': 'draft', 'sentences': [{'text': text, 'acts': context['acts']}]}
        elif record['operation'] == 'checking':
            result = {'findings': criterion_findings(context)}
        else:
            self.fail('Unexpected fixture operation')
        return completion(json.dumps(result))

    def test_actual_journaled_fresh_request_uses_same_examples_without_failed_prose_or_scores(self):
        faculty = corpus_fixture.FullVoiceCorpusTests.faculty(self)
        expression = Expression(self.graph, self.models['expression'])
        checking = Checking(self.graph, self.models['checking'])
        scanner, http_calls = fixture_scanner(self.graph, expression, checking,
                                            ['AI-Generated', 'Human Written'], self.binding)
        loop = ParagraphLoop(self.graph, expression, checking, scanner,
                             paragraph_groups='all_acts_one_paragraph', max_attempts=3,
                             fresh_expression_retry=FRESH_EXPRESSION_POLICY, max_fresh_retries=1)
        engine = Execution(self.graph, faculty, expression, checking,
                           binding=self.binding, paragraph_loop=loop)
        current = engine.start('Synthetic full-corpus retry test', max_attempts=3, mode='fixture')
        engine.close_construction(current['id'], actor='author')
        current = engine.advance(current['id'])
        current = engine.advance(current['id'])
        self.assertEqual(current['state'], 'suspended_detector_flagged')
        previous = copy.deepcopy(current)
        engine.retry_fresh_expression(current['id'], actor='author')
        engine.advance(current['id'], actor='author')
        complete = engine.advance(current['id'])
        self.assertEqual(complete['state'], 'awaiting_approval')
        self.assertEqual(http_calls, ['POST', 'GET', 'POST', 'GET'])
        self.assertEqual(len(self.writer_requests), 2)
        first, fresh = self.writer_requests
        self.assertEqual(first, fresh)
        self.assertEqual(len(fresh['voice_exemplars']), 84)
        serialized = json.dumps(fresh)
        for forbidden in ('REJECTED_CANDIDATE_SENTINEL', 'fraction_ai', 'fraction_human',
                          'fresh_retry_source', previous['scan'], previous['run']):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(scanner.inspect(previous['scan'])['state'], 'flagged')
        self.assertEqual(scanner.inspect(complete['scan'])['state'], 'passed')
        writer_calls = self.journals['expression'].inspect()
        self.assertEqual(len(writer_calls), 2)
        self.assertTrue(all(record['state'] == 'succeeded' for record in writer_calls))
        checking_calls = self.journals['checking'].inspect()
        self.assertEqual(sum(record['operation'] == 'checking' for record in checking_calls), 2)


if __name__ == '__main__':
    unittest.main()
