"""Deterministic adapter fixtures: no live Pangram or human-authorship claims."""
import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from checking import Checking
from expression import Expression
from faculty import Faculty
from model import Graph
from pangram_check import DEFAULT_CONFIGURATION, HTTPReply, PangramCheck, validate_configuration
from providers import SuppliedResearch
from test_checking import Reviewer
from test_construction_closure import ClosureReasoner, close_fixture_plan


CONFIG = dict(DEFAULT_CONFIGURATION, expected_version='4.1')
TEXT = ' '.join(['fixture'] * 60) + '.'


def result_for(text, label='Human Written', version='4.1'):
    labels = {'Human Written': 'human', 'AI-Assisted': 'ai_assisted', 'AI-Generated': 'ai'}
    selected = labels[label]
    result = {'stage': 'STAGE_SUCCESS', 'text': text, 'version': version,
              'windows': [{'text': text, 'label': label, 'confidence': 'High',
                           'start_index': 0, 'end_index': len(text)}]}
    for kind in labels.values():
        result['fraction_' + kind] = 1.0 if kind == selected else 0.0
        result['num_' + kind + '_segments'] = 1 if kind == selected else 0
    return result


class Writer:
    def __init__(self, text=TEXT):
        self.text = text
    def realize(self, context):
        return {'status': 'draft', 'sentences': [{'text': self.text, 'acts': context['acts']}]}


class PangramTests(unittest.TestCase):
    def setUp(self):
        self.g = Graph()
        self.addCleanup(self.g.db.close)
        faculty = Faculty(self.g, ClosureReasoner(), SuppliedResearch())
        self.plan = faculty.build('Test only; no manuscript generation')
        close_fixture_plan(faculty, self.plan)
        self.writer = Writer()
        self.expression = Expression(self.g, self.writer)
        self.checking = Checking(self.g, Reviewer())
        self.calls, self.responses = [], []
        self.gate = PangramCheck(self.g, self.expression, self.checking, configuration=CONFIG, transport=self.transport)
        self.run, self.assessment = self.paragraph()

    def paragraph(self):
        acts = self.expression.context(self.plan)['acts']
        run = self.expression.run(self.plan, paragraph={'id': 'fixture-p1', 'index': 0, 'acts': acts, 'prior_paragraphs': []})
        return run, self.checking.assess(run)

    def transport(self, request):
        self.calls.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(request) if callable(item) else item

    def start(self):
        return self.gate.start(self.run, self.assessment, mode='fixture')

    def complete(self, result=None):
        self.responses[:] = [{'task_id': 'fixture-task'}, result or result_for(TEXT)]
        ident = self.start()
        self.gate.advance(ident)
        return ident, self.gate.advance(ident)

    def test_submission_is_recorded_before_transport_and_one_call_per_advance(self):
        ident = self.start()
        self.assertFalse(self.calls)
        self.assertEqual(self.gate.inspect(ident)['state'], 'prepared')
        def submit(request):
            state = self.gate.inspect(ident)
            self.assertEqual(state['events'][-1]['state'], 'request_prepared')
            self.assertEqual(state['events'][-1]['detail']['body'].encode(), request.data)
            self.assertEqual(json.loads(request.data), {'text': TEXT, 'model': 'pangram-4', 'public_dashboard_link': False})
            self.assertNotIn('fixture-only-pangram-key', json.dumps(state))
            return {'task_id': 'fixture-task'}
        self.responses[:] = [submit, {'stage': 'STAGE_PROCESSING'}, result_for(TEXT)]
        first = self.gate.advance(ident)
        self.assertEqual(first['state'], 'pending')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.gate.start(self.run, self.assessment, mode='fixture'), ident)
        self.assertEqual(self.gate.advance(ident)['state'], 'pending')
        self.assertEqual(len(self.calls), 2)
        final = self.gate.advance(ident)
        self.assertEqual(final['state'], 'passed')
        self.assertEqual(final['text_sha256'], self.expression.inspect(self.run)['text_sha256'])
        self.assertEqual(final['paragraph_id'], 'fixture-p1')
        self.assertEqual([request.get_method() for request in self.calls], ['POST', 'GET', 'GET'])
        self.assertEqual(final['version'], '4.1')
        self.assertEqual(self.gate.advance(ident)['state'], 'passed')
        self.assertEqual(len(self.calls), 3)

    def test_pending_task_resumes_without_resubmission(self):
        self.responses[:] = [{'task_id': 'fixture-task'}, result_for(TEXT)]
        ident = self.start()
        self.gate.advance(ident)
        resumed = PangramCheck(self.g, self.expression, self.checking, configuration=CONFIG, transport=self.transport)
        self.assertEqual(resumed.advance(ident)['state'], 'passed')
        self.assertEqual([request.get_method() for request in self.calls], ['POST', 'GET'])

    def test_prepared_request_without_response_is_not_resubmitted(self):
        ident = self.start()
        self.gate._event(ident, 'request_prepared', {'request_id': 'simulated-interruption', 'method': 'POST'})
        self.assertEqual(self.gate.advance(ident)['state'], 'pending')
        self.assertFalse(self.calls)

    def test_flagged_and_ai_assisted_results_stop_progression(self):
        for label in ('AI-Generated', 'AI-Assisted'):
            with self.subTest(label=label):
                self.run, self.assessment = self.paragraph()
                _, result = self.complete(result_for(TEXT, label))
                self.assertEqual(result['state'], 'flagged')
                self.assertEqual(result['full_result']['windows'][0]['label'], label)

    def test_short_paragraph_is_unscorable_without_padding_or_submission(self):
        self.writer.text = 'A short fixture.'
        self.run, self.assessment = self.paragraph()
        ident = self.start()
        current = self.gate.advance(ident)
        self.assertEqual(current['state'], 'unscorable')
        self.assertEqual(current['text'], self.writer.text)
        self.assertFalse(self.calls)

    def test_version_mismatch_preserves_result_and_fails_closed(self):
        _, current = self.complete(result_for(TEXT, version='4.0'))
        self.assertEqual(current['state'], 'error')
        self.assertEqual(current['version'], '4.0')
        self.assertIn('version', current['reason'])

    def test_malformed_result_or_different_text_never_passes(self):
        mutations = [
            lambda value: value.update(text=TEXT + ' changed'),
            lambda value: value.pop('windows'),
            lambda value: value['windows'][0].update(end_index=10),
            lambda value: value.update(num_human_segments=2),
            lambda value: value.update(fraction_ai=float('nan')),
            lambda value: value['windows'][0].update(label='Unknown'),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.run, self.assessment = self.paragraph()
                response = result_for(TEXT)
                mutate(response)
                _, current = self.complete(response)
                self.assertEqual(current['state'], 'error')

    def test_failed_stage_and_http_errors_are_recorded(self):
        ident, failed = self.complete({'stage': 'STAGE_FAILED', 'message': 'Fixture service failure'})
        self.assertEqual(failed['state'], 'error')
        self.assertEqual(failed['full_result']['stage'], 'STAGE_FAILED')
        self.run, self.assessment = self.paragraph()
        self.responses[:] = [HTTPReply(402, b'{"error":"fixture quota"}')]
        ident = self.start()
        current = self.gate.advance(ident)
        self.assertEqual(current['state'], 'error')
        self.assertEqual(current['events'][-1]['detail']['http_status'], 402)
        self.assertEqual(current['events'][-1]['detail']['raw_response']['format'], 'base64')

    def test_network_error_never_resubmits_uncertain_submission(self):
        self.responses[:] = [OSError('fixture-only-pangram-key')]
        ident = self.start()
        current = self.gate.advance(ident)
        self.assertEqual(current['state'], 'error')
        self.assertNotIn('fixture-only-pangram-key', json.dumps(current))
        self.assertEqual(self.gate.advance(ident)['state'], 'error')
        self.assertEqual(len(self.calls), 1)

    def test_stale_text_assessment_and_config_invalidate_prior_pass(self):
        ident, current = self.complete()
        self.assertEqual(current['state'], 'passed')
        sentence = self.expression.inspect(self.run)['sentences'][0]
        self.g.revise(sentence['id'], dict(sentence['payload'], text=TEXT + ' revised'))
        self.assertEqual(self.gate.inspect(ident)['state'], 'stale')
        self.assertEqual(self.gate.advance(ident)['state'], 'stale')
        self.assertEqual(len(self.calls), 2)
        self.run, self.assessment = self.paragraph()
        ident, _ = self.complete()
        self.gate.configuration['expected_version'] = '4.2'
        self.assertEqual(self.gate.inspect(ident)['state'], 'stale')

    def test_change_during_response_is_preserved_but_not_accepted(self):
        def response(request):
            sentence = self.expression.inspect(self.run)['sentences'][0]
            self.g.revise(sentence['id'], dict(sentence['payload'], text=TEXT + ' changed'))
            return result_for(TEXT)
        self.responses[:] = [{'task_id': 'fixture-task'}, response]
        ident = self.start()
        self.gate.advance(ident)
        current = self.gate.advance(ident)
        self.assertEqual(current['state'], 'stale')
        self.assertEqual(current['full_result']['text'], TEXT)

    def test_four_layer_check_must_pass_for_exact_same_run(self):
        other_run, other_assessment = self.paragraph()
        with self.assertRaises(ValueError): self.gate.start(self.run, other_assessment, mode='fixture')
        failed_checking = Checking(self.g, Reviewer('linguistic'))
        failed = failed_checking.assess(self.run)
        with self.assertRaises(ValueError): self.gate.start(self.run, failed, mode='fixture')
        self.assertFalse(self.calls)

    def test_secret_echo_even_json_escaped_is_omitted(self):
        content = json.dumps({'task_id': 'fixture-task', 'echo': 'fixture-only-pangram-key'}).replace('fixture-only', '\\u0066ixture-only')
        self.responses[:] = [content]
        current = self.gate.advance(self.start())
        self.assertEqual(current['state'], 'error')
        self.assertNotIn('fixture-only-pangram-key', json.dumps(current))
        self.assertIsNone(current['full_result'])
        self.assertNotIn('raw_response', current['events'][-1]['detail'])

    def test_records_are_append_only_and_inspect_is_read_only(self):
        ident, _ = self.complete()
        before = self.g.db.total_changes
        self.gate.inspect(ident)
        self.assertEqual(self.g.db.total_changes, before)
        for table in ('pangram_scan', 'pangram_event'):
            with self.assertRaises(sqlite3.IntegrityError):
                with self.g.db: self.g.db.execute('DELETE FROM ' + table)
        self.assertEqual(self.gate.inspect(ident)['state'], 'passed')

    def test_explicit_version_private_results_and_minimum_required(self):
        for mutation in ({'expected_version': None}, {'minimum_words': 49}, {'public_dashboard_link': True},
                         {'endpoint': 'https://example.invalid'}, {'policy': 'ignore-flags'}):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError): validate_configuration(dict(CONFIG, **mutation))

    def test_preflight_blocks_missing_live_credential_and_fixture_http(self):
        config = copy.deepcopy(CONFIG)
        class Binding:
            id = 'fixture-bound-config'
            def inspect(self): return {'mode': 'live', 'pangram': config}
            def verify(self): return self.inspect()
        gate = PangramCheck(self.g, self.expression, self.checking, binding=Binding(), configuration=CONFIG)
        with patch.dict('os.environ', {}, clear=True):
            result = gate.preflight(mode='live')
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(result['code'], 'missing_credential')
        self.assertEqual(gate.preflight(mode='fixture')['state'], 'blocked')
        self.assertFalse(self.calls)


if __name__ == '__main__':
    unittest.main()
