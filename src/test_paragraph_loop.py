"""Fixture evidence that no next paragraph is written before the detector gate."""
import copy
import unittest

from checking import Checking
from execution import Execution
from expression import Expression
from faculty import Faculty
from model import Graph
from paragraph_loop import ParagraphLoop
from test_checking import Reviewer
from test_faculty import Research
from test_helpers import FixtureConstructionReviewer, close_fixture_plan
from pangram_check import PangramCheck, DEFAULT_CONFIGURATION
from test_pangram_check import result_for


class TwoActReasoner:
    def propose(self, context):
        return {
            'claims': [
                {'key': 'c' + str(index), 'text': 'Fixture claim ' + str(index),
                 'origin': 'agent_hypothesis', 'evidence': ['intent']}
                for index in range(2)
            ],
            'acts': [{'purpose': 'Fixture act ' + str(index), 'claims': ['c' + str(index)]}
                     for index in range(2)],
        }


class ParagraphWriter:
    def __init__(self):
        self.calls = []

    def realize(self, context):
        self.calls.append(copy.deepcopy(context))
        return {'status': 'draft', 'sentences': [
            {'text': 'Fixture paragraph ' + str(context['paragraph']['index']) + '.',
             'acts': context['acts']}
        ]}


class PipelineReviewer(Reviewer, FixtureConstructionReviewer):
    pass


class FixtureDetector:
    """No API or network; recorded outcomes control the scheduling test."""
    def __init__(self, expression, checking, outcomes):
        self.expression, self.checking = expression, checking
        self.outcomes = list(outcomes)
        self.records = {}
        self.calls = []
        self.ready = True
        self.binding = None

    def preflight(self, mode='fixture'):
        return {'state': 'ready' if self.ready else 'blocked', 'reason': 'Fixture availability'}

    def start(self, run, assessment, mode='fixture'):
        self.calls.append(('start', run))
        draft = self.expression.inspect(run)
        ident = 'scan-' + str(len(self.records))
        self.records[ident] = {
            'id': ident, 'state': 'prepared', 'run': run, 'assessment': assessment,
            'text': draft['text'], 'text_sha256': draft['text_sha256'],
            'paragraph_id': draft['input']['paragraph']['id'],
        }
        return ident

    def advance(self, scan):
        self.calls.append(('advance', scan))
        self.records[scan]['state'] = self.outcomes.pop(0) if self.outcomes else 'pending'
        return self.inspect(scan)

    def inspect(self, scan):
        result = copy.deepcopy(self.records[scan])
        if (self.expression.inspect(result['run'])['state'] == 'stale'
                or self.checking.inspect(result['assessment'])['state'] != 'checks_passed'):
            result['state'] = 'stale'
        return result


class ParagraphLoopTests(unittest.TestCase):
    def setUp(self):
        self.g = Graph()
        self.addCleanup(self.g.db.close)

    def engine(self, outcomes, *, fail=None, groups=None, max_attempts=3):
        faculty = Faculty(self.g, TwoActReasoner(), Research())
        writer = ParagraphWriter()
        expression = Expression(self.g, writer)
        checking = Checking(self.g, PipelineReviewer(fail))
        detector = FixtureDetector(expression, checking, outcomes)
        loop = ParagraphLoop(self.g, expression, checking, detector,
                             paragraph_groups=groups, max_attempts=max_attempts)
        engine = Execution(self.g, faculty, expression, checking, paragraph_loop=loop)
        started = engine.start('Fixture chapter intent', max_attempts=max_attempts, mode='fixture')
        ready = engine.close_construction(started['id'], actor='author')
        return engine, loop, writer, detector, ready

    def test_pending_first_paragraph_never_starts_the_next_writer(self):
        engine, loop, writer, detector, ready = self.engine(['pending', 'pending', 'passed', 'passed'])
        first = engine.advance(ready['id'])
        self.assertEqual(first['state'], 'suspended_detector_pending')
        self.assertEqual(len(writer.calls), 1)
        again = engine.advance(ready['id'])
        self.assertEqual(again['state'], 'suspended_detector_pending')
        self.assertEqual(len(writer.calls), 1)
        passed = engine.advance(ready['id'])
        self.assertEqual(passed['state'], 'ready_for_next_paragraph')
        self.assertEqual(len(writer.calls), 1)
        complete = engine.advance(ready['id'])
        self.assertEqual(complete['state'], 'awaiting_approval')
        self.assertEqual(len(writer.calls), 2)
        self.assertEqual(sum(call[0] == 'start' for call in detector.calls), 2)
        self.assertEqual([call['paragraph']['index'] for call in writer.calls], [0, 1])
        self.assertEqual(len(writer.calls[0]['acts']), 1)
        self.assertEqual(len(writer.calls[1]['acts']), 1)
        self.assertEqual(loop.validate_complete(ready['id'])['state'], 'complete')

    def test_real_adapter_fixture_polls_each_paragraph_before_next_writer(self):
        class LongFixtureWriter(ParagraphWriter):
            def realize(self, context):
                result = super().realize(context)
                result['sentences'][0]['text'] = ' '.join(['fixture'] * 60) + '.'
                return result
        faculty = Faculty(self.g, TwoActReasoner(), Research())
        writer = LongFixtureWriter()
        expression = Expression(self.g, writer)
        checking = Checking(self.g, PipelineReviewer())
        requests, submitted = [], []
        def transport(request):
            import json
            requests.append(request.get_method())
            if request.get_method() == 'POST':
                submitted.append(json.loads(request.data)['text'])
                return {'task_id': 'fixture-task-' + str(len(submitted))}
            return result_for(submitted[-1])
        detector = PangramCheck(self.g, expression, checking,
                               configuration=dict(DEFAULT_CONFIGURATION, expected_version='4.1'),
                               transport=transport)
        loop = ParagraphLoop(self.g, expression, checking, detector)
        engine = Execution(self.g, faculty, expression, checking, paragraph_loop=loop)
        started = engine.start('Fixture chapter only', mode='fixture')
        engine.close_construction(started['id'], actor='author')
        self.assertEqual(engine.advance(started['id'])['state'], 'suspended_detector_pending')
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(engine.advance(started['id'])['state'], 'ready_for_next_paragraph')
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(engine.advance(started['id'])['state'], 'suspended_detector_pending')
        self.assertEqual(len(writer.calls), 2)
        self.assertEqual(engine.advance(started['id'])['state'], 'awaiting_approval')
        self.assertEqual(requests, ['POST', 'GET', 'POST', 'GET'])
        self.assertEqual(len(submitted), 2)

    def test_flag_error_and_unscorable_stop_after_first_paragraph(self):
        for outcome in ('flagged', 'error', 'unscorable'):
            with self.subTest(outcome=outcome):
                engine, loop, writer, detector, ready = self.engine([outcome])
                result = engine.advance(ready['id'])
                self.assertEqual(result['state'], 'suspended_detector_' + outcome)
                self.assertEqual(len(writer.calls), 1)
                self.assertNotIn('text', result)
                if outcome != 'error':
                    with self.assertRaises(ValueError):
                        engine.advance(ready['id'], actor='author')
                else:
                    detector.outcomes = ['error']
                    engine.advance(ready['id'])
                self.assertEqual(len(writer.calls), 1)
                with self.assertRaises(ValueError):
                    engine.approve(ready['id'], 'author')

    def test_detector_readiness_is_checked_before_the_writer(self):
        engine, loop, writer, detector, ready = self.engine(['passed'])
        detector.ready = False
        result = engine.advance(ready['id'])
        self.assertEqual(result['state'], 'suspended_detector_blocked')
        self.assertEqual(writer.calls, [])
        self.assertEqual(detector.calls, [])
        detector.ready = True
        result = engine.advance(ready['id'])
        self.assertEqual(result['state'], 'ready_for_next_paragraph')
        self.assertEqual(len(writer.calls), 1)

    def test_stale_prior_text_or_scan_blocks_the_second_writer(self):
        for change in ('text', 'scan'):
            with self.subTest(change=change):
                engine, loop, writer, detector, ready = self.engine(['passed', 'passed'])
                first = engine.advance(ready['id'])
                paragraph = first['paragraph_progress']['paragraphs'][0]
                if change == 'text':
                    sentence = engine.e.inspect(paragraph['run'])['sentences'][0]['id']
                    self.g.revise(sentence, {'text': 'Changed fixture paragraph.'})
                else:
                    detector.records[paragraph['scan']]['text_sha256'] = 'incorrect'
                with self.assertRaises(ValueError):
                    engine.advance(ready['id'])
                self.assertEqual(len(writer.calls), 1)
                self.assertEqual(engine.inspect(ready['id'])['state'], 'stale')

    def test_assembly_preserves_exact_checked_paragraphs_and_requires_author(self):
        engine, loop, writer, detector, ready = self.engine(['passed', 'passed'])
        first = engine.advance(ready['id'])
        self.assertEqual(first['state'], 'ready_for_next_paragraph')
        final = engine.advance(ready['id'])
        paragraphs = final['paragraph_progress']['paragraphs']
        expected = '\n\n'.join(engine.e.inspect(item['run'])['text'] for item in paragraphs)
        self.assertEqual(final['text'], expected)
        self.assertEqual(final['chapter_semantic_check'], 'pending')
        with self.assertRaises(PermissionError):
            engine.approve(ready['id'], 'agent')
        approved = engine.approve(ready['id'], 'author')
        self.assertEqual(approved['state'], 'closed')
        self.assertEqual(approved['chapter_semantic_check'], 'pending')
        self.assertEqual(approved['authorial_validation'], 'approved')
        self.assertEqual(len(writer.calls), 2)
        self.assertTrue(all('repair' not in call for call in writer.calls))

    def test_four_layer_failure_prevents_detector_and_next_paragraph(self):
        engine, loop, writer, detector, ready = self.engine(['passed'], fail='linguistic', max_attempts=2)
        failed = engine.advance(ready['id'])
        self.assertEqual(failed['state'], 'suspended_reopen')
        self.assertEqual(failed['route'], 'expression')
        self.assertEqual(detector.calls, [])
        with self.assertRaises(PermissionError):
            engine.advance(ready['id'])
        engine.advance(ready['id'], actor='author')
        self.assertEqual([call['paragraph']['index'] for call in writer.calls], [0, 0])
        self.assertIn('repair', writer.calls[-1])
        self.assertNotIn('pangram', writer.calls[-1]['repair'])
        self.assertEqual(detector.calls, [])
        exhausted = engine.advance(ready['id'], actor='author')
        self.assertEqual(exhausted['state'], 'budget_exhausted')
        self.assertEqual(exhausted['attempt_budget_scope'], 'per_paragraph')
        self.assertEqual(len(writer.calls), 2)

    def test_default_and_explicit_grouping_are_recorded_and_invalid_groups_rejected(self):
        engine, loop, writer, detector, ready = self.engine(['passed', 'passed'])
        progress = loop.inspect(ready['id'])
        self.assertEqual(progress['act_groups'], [[0], [1]])
        self.assertEqual(progress['grouping_policy'], 'one_act_per_paragraph_default_unvalidated')
        for index, groups in enumerate(([[0], [0]], [[1], [0]], [[False], [1]], [[]], [[0]])):
            invalid = ParagraphLoop(self.g, engine.e, engine.c, detector, paragraph_groups=groups)
            with self.subTest(groups=groups), self.assertRaises(ValueError):
                invalid.prepare('invalid-' + str(index), ready['plan'], mode='fixture')
        combined = ParagraphLoop(self.g, engine.e, engine.c, detector, paragraph_groups=[[0, 1]])
        prepared = combined.prepare('explicit-group', ready['plan'], mode='fixture')
        self.assertEqual(prepared['grouping_policy'], 'explicit_ordered_act_groups')
        self.assertEqual(len(prepared['paragraphs']), 1)


if __name__ == '__main__':
    unittest.main()
