"""Synthetic worked-example projection tests; no actual author text or providers."""
import copy
import hashlib
import json
import unittest

from expression import Expression
from test_voice_expression import fixture_context, node, SUBJECT


class WorkedVoiceExampleTests(unittest.TestCase):
    def setUp(self):
        self.context = fixture_context()

    def test_each_act_pairs_its_rule_with_actual_selected_examples(self):
        before = copy.deepcopy(self.context)
        packet = Expression.writer_context(self.context)
        self.assertIn('Write prose structured like these examples.', packet['instruction'])
        self.assertEqual([len(act['worked_examples']) for act in packet['intellectual_plan']], [1, 2])
        for act in packet['intellectual_plan']:
            canonical = self.context['nodes'][act['id']]['node']['payload']['voice_bindings']
            self.assertEqual(act['voice_bindings'], canonical)
            for index, (binding, worked) in enumerate(zip(canonical, act['worked_examples'])):
                self.assertEqual(worked['criterion_id'], f'binding:{act["id"]}:{index}')
                self.assertEqual(worked['rule']['id'], binding['rule_id'])
                self.assertEqual(worked['rule']['key'], binding['rule_key'])
                self.assertEqual(worked['structure_to_model'], binding['application'])
                self.assertEqual(worked['acceptance_criterion'], binding['criterion'])
                self.assertEqual(worked['rule']['authority'], 'advisory_only')
                for ident, example in zip(binding['exemplar_ids'], worked['examples']):
                    authentic = next(e for e in self.context['authentic_exemplars'] if e['id'] == ident)
                    self.assertEqual(example['example_text'], authentic['node']['payload']['Exact excerpt'])
                    self.assertEqual(example['authority'], authentic['authority'])
                    self.assertEqual(example['exemplar_type'], 'Original spoken')
                    self.assertEqual(example['written_validation'], 'Not validated for writing')
                    self.assertEqual(example['source_context_refs'], ['voice-source'])
        self.assertEqual(self.context, before)
        self.assertNotIn(SUBJECT, json.dumps(packet))

    def test_unselected_exemplar_and_subject_body_do_not_enter_worked_examples(self):
        unrelated = self.context['authentic_exemplars'][2]
        unrelated_text = 'Separate unrelated exemplar which no act selected.'
        unrelated['node']['payload']['Exact excerpt'] = unrelated_text
        unrelated['sources'] = [node('unselected-source', 'evidence', {
            'Source ID': 'unselected-source-key',
            'User transcript (segments joined)': unrelated_text})['node']]
        packet = Expression.writer_context(self.context)
        serialized = json.dumps(packet)
        self.assertNotIn('exemplar-3', serialized)
        self.assertNotIn(unrelated_text, serialized)
        self.assertNotIn('unselected-source', serialized)
        self.assertNotIn(SUBJECT, serialized)
        examples = [example for act in packet['intellectual_plan']
                    for worked in act['worked_examples'] for example in worked['examples']]
        self.assertEqual({example['id'] for example in examples}, {'exemplar-1', 'exemplar-2'})

    def test_approved_written_example_is_exact_and_remains_separate_once(self):
        packet = Expression.writer_context(self.context)
        calibration = self.context['written_calibration'][0]
        self.assertEqual(packet['written_calibration'], self.context['written_calibration'])
        self.assertEqual(json.dumps(packet).count(calibration['text']), 1)
        self.assertIn('worked examples of paragraph', packet['written_calibration_usage'])
        self.assertIn('passage_only', packet['written_calibration_usage'])
        self.assertEqual(packet['written_calibration'][0]['author_judgment'], calibration['author_judgment'])
        self.assertEqual(packet['written_calibration'][0]['source_path'], calibration['source_path'])
        self.assertEqual(packet['written_calibration'][0]['sha256'],
                         hashlib.sha256(calibration['text'].encode()).hexdigest())
        self.assertNotIn(calibration['id'], json.dumps(packet['intellectual_plan']))

    def test_repair_keeps_the_same_act_specific_worked_examples(self):
        before = Expression.writer_context(self.context)
        text = 'A synthetic prior expression.'
        self.context['repair'] = {
            'editing_attempt': 'fixture-repair', 'previous_run': 'fixture-run',
            'assessment': 'fixture-assessment', 'affected_sentences': ['sentence-1'],
            'affected_acts': ['act-1', 'act-2'],
            'findings': [{'layer': 'linguistic', 'status': 'fail',
                          'reason': 'A synthetic clause-order defect.'}],
            'instruction': 'Repair the diagnosed clause order using the selected examples.',
            'prior_draft': {
                'plan': 'fixture-plan', 'text': text,
                'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                'sentences': [{'id': 'sentence-1', 'payload': {'text': text}}],
                'detail': {'sentences': [{'text': text, 'acts': ['act-1', 'act-2']}]},
                'input': copy.deepcopy(self.context),
            },
        }
        repaired = Expression.writer_context(self.context)
        self.assertEqual(repaired['intellectual_plan'], before['intellectual_plan'])
        self.assertEqual(repaired['written_calibration'], before['written_calibration'])
        self.assertEqual(repaired['repair']['prior_draft']['text'], text)
        self.assertNotIn('input', repaired['repair']['prior_draft'])
        self.assertNotIn(SUBJECT, json.dumps(repaired))


if __name__ == '__main__':
    unittest.main()
