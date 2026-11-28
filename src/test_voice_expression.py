"""Synthetic compact voice inputs; no provider calls or authorship claims."""
import copy
import hashlib
import json
import unittest

from expression import Expression
from voice_expression import PROFILE, compact_writer_context, resolved_criteria


SUBJECT = 'SUBJECT BODY: a distinctive original passage kept only for independent checking.'
TRANSCRIPT = 'A fixture comparison. A fixture qualification. Unrelated surrounding transcript context.'


def node(ident, kind, payload, edges=()):
    return {'node': {'id': ident, 'kind': kind, 'revision': 1, 'status': 'draft', 'payload': payload},
            'edges': list(edges)}


def fixture_context():
    rules, exemplars, voice_nodes = [], [], {}
    source = node('voice-source', 'evidence', {
        'Source ID': 'S-fixture', 'User transcript (segments joined)': TRANSCRIPT})['node']
    for index, layer, excerpt in ((1, 'rhetorical', 'A fixture comparison.'),
                                   (2, 'linguistic', 'A fixture qualification.'),
                                   (3, 'linguistic', 'Unrelated surrounding transcript context.')):
        rule_id, exemplar_id = f'rule-{index}', f'exemplar-{index}'
        payload = {'Rule ID': f'R{index}', 'Layer': layer.title(),
                   'Candidate rule': f'Apply fixture rule {index}', 'Status': 'Unconfirmed',
                   'Applicability': 'Spoken; written untested', 'activation': 'candidate_only'}
        rules.append({'id': rule_id, 'payload': payload, 'authority': 'advisory_only'})
        voice_nodes[rule_id] = node(rule_id, 'rule', payload, [('grounded_in', exemplar_id)])
        exemplar_node = node(exemplar_id, 'evidence', {
            'Exemplar ID': f'E{index}', 'Source ID': 'S-fixture', 'Layer': layer.title(),
            'Intellectual act': 'Fixture act', 'Exemplar type': 'Original spoken',
            'Exact excerpt': excerpt, 'Written validation': 'Not validated for writing'})['node']
        exemplars.append({'id': exemplar_id, 'node': exemplar_node, 'sources': [source],
                          'authority': 'original_spoken; written validation remains as recorded'})
    def binding(index, layer):
        return {'rule_id': f'rule-{index}', 'rule_key': f'R{index}',
                'exemplar_ids': [f'exemplar-{index}'], 'exemplar_keys': [f'E{index}'],
                'layer': layer, 'application': 'Apply the fixture instruction to this act.',
                'criterion': f'This act satisfies fixture criterion {index}.'}
    nodes = {
        'intent': node('intent', 'intent', {'text': 'Express two ordered fixture acts.'}),
        'subject': node('subject', 'evidence', {'text': SUBJECT, 'origin': 'retrieved_unverified',
                                               'source': 'fixture-subject.txt', 'metadata': {'text': SUBJECT}}),
        'claim': node('claim', 'claim', {'text': 'A constructed fixture proposition.',
                                        'origin': 'external', 'verified': False}, [('supports', 'subject')]),
        'act-1': node('act-1', 'act', {'purpose': 'Compare the fixture cases.',
                                      'voice_bindings': [binding(1, 'rhetorical')]}, [('asserts', 'claim')]),
        'act-2': node('act-2', 'act', {'purpose': 'Qualify the fixture distinction.',
                                      'voice_bindings': [binding(1, 'rhetorical'), binding(2, 'linguistic')]},
                      [('asserts', 'claim')]),
    }
    calibration_text = 'An explicitly approved synthetic calibration passage.'
    return {'execution_profile': PROFILE, 'intent': 'intent', 'acts': ['act-1', 'act-2'],
            'nodes': nodes, 'baseline_digest': 'fixture-ledger', 'voice_candidates': rules,
            'voice_evidence': voice_nodes, 'authentic_exemplars': exemplars,
            'selection_status': 'per_act_bindings_validated; relevance_requires_review',
            'written_calibration': [{'id': 'calibration-1', 'source_path': 'fixture-calibration.txt',
                                     'text': calibration_text,
                                     'sha256': hashlib.sha256(calibration_text.encode()).hexdigest(),
                                     'authority': 'generated_author_approved_passage', 'scope': 'passage_only',
                                     'author_judgment': 'Explicit synthetic fixture approval.'}],
            'construction_closure': {'id': 'fixture-closure'},
            'paragraph': {'id': 'fixture-p1', 'index': 0, 'acts': ['act-1', 'act-2'], 'prior_paragraphs': []},
            'prior_paragraphs': [], 'instruction': 'Legacy full-context instruction.'}


class VoiceExpressionTests(unittest.TestCase):
    def setUp(self):
        self.context = fixture_context()

    def test_actual_writer_projection_excludes_source_body_and_deduplicates_selection(self):
        original = copy.deepcopy(self.context)
        packet = Expression.writer_context(self.context)
        self.assertNotIn(SUBJECT, json.dumps(packet))
        self.assertNotIn('nodes', packet)
        self.assertNotIn('voice_evidence', packet)
        self.assertEqual(packet['acts'], ['act-1', 'act-2'])
        self.assertEqual(len(packet['claims']), 1)
        self.assertEqual(len(packet['source_references']), 1)
        self.assertEqual(packet['source_references'][0]['text_sha256'], hashlib.sha256(SUBJECT.encode()).hexdigest())
        self.assertEqual([item['id'] for item in packet['voice_rules']], ['rule-1', 'rule-2'])
        self.assertEqual([item['id'] for item in packet['voice_exemplars']], ['exemplar-1', 'exemplar-2'])
        self.assertEqual(packet['source_contexts'], [{'id': 'voice-source', 'source_key': 'S-fixture', 'transcript': TRANSCRIPT}])
        self.assertEqual(self.context, original)

    def test_every_binding_has_stable_scoped_criterion_and_shared_base_criteria(self):
        packet = compact_writer_context(self.context)
        criteria = packet['criteria']
        self.assertEqual(criteria, resolved_criteria(self.context))
        self.assertEqual([c['id'] for c in criteria[:4]],
                         ['base:conceptual', 'base:epistemic', 'base:rhetorical', 'base:linguistic'])
        self.assertEqual([c['id'] for c in criteria[4:]],
                         ['binding:act-1:0', 'binding:act-2:0', 'binding:act-2:1'])
        self.assertEqual(criteria[-1], {'id': 'binding:act-2:1', 'layer': 'linguistic',
                                      'act_ids': ['act-2'], 'rule_ids': ['rule-2'],
                                      'exemplar_ids': ['exemplar-2'],
                                      'criterion': 'This act satisfies fixture criterion 2.'})
        self.context['acts'] = ['act-2']
        scoped = resolved_criteria(self.context)
        self.assertEqual(len(scoped), 6)
        self.assertTrue(all(c['act_ids'] == ['act-2'] for c in scoped))
        self.assertEqual(scoped[-1], criteria[-1])

    def test_calibration_remains_generated_passage_only_and_candidates_remain_advisory(self):
        packet = compact_writer_context(self.context)
        self.assertEqual(packet['written_calibration'], self.context['written_calibration'])
        self.assertTrue(all(r['authority'] == 'advisory_only' and r['activation'] == 'candidate_only'
                            for r in packet['voice_rules']))
        self.assertTrue(all(e['exemplar_type'] == 'Original spoken' for e in packet['voice_exemplars']))
        self.assertNotIn('calibration-1', [e['id'] for e in packet['voice_exemplars']])
        for key, value in [('scope', 'general_voice_rule'), ('authority', 'author_written'), ('sha256', 'wrong')]:
            context = copy.deepcopy(self.context)
            context['written_calibration'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                compact_writer_context(context)

    def test_unknown_profile_missing_bindings_and_unrelated_evidence_are_rejected(self):
        mutations = [
            lambda c: c.update(execution_profile='unknown-profile'),
            lambda c: c['nodes']['act-1']['node']['payload'].update(voice_bindings=[]),
            lambda c: c['nodes']['act-1']['node']['payload']['voice_bindings'][0].update(rule_key='unrelated'),
            lambda c: c['nodes']['act-1']['node']['payload']['voice_bindings'][0].update(layer='epistemic'),
            lambda c: c['nodes']['act-1']['node']['payload']['voice_bindings'][0].update(exemplar_ids=['exemplar-2'], exemplar_keys=['E2']),
        ]
        for change in mutations:
            context = copy.deepcopy(self.context)
            change(context)
            with self.subTest(change=change), self.assertRaises(ValueError):
                Expression.writer_context(context)

    def test_context_carries_frozen_profile_and_calibration_without_mutating_snapshot(self):
        snapshot = copy.deepcopy(self.context)
        class Gate:
            def require_closed(self, plan):
                return {'id': 'fixture-closure'}
            def snapshot(self, plan):
                return snapshot
        expression = object.__new__(Expression)
        expression.c = Gate()
        context = expression.context('fixture-plan')
        self.assertEqual(context['execution_profile'], PROFILE)
        self.assertEqual(context['written_calibration'], snapshot['written_calibration'])
        context['written_calibration'][0]['text'] = 'Caller mutation'
        self.assertNotEqual(context['written_calibration'], snapshot['written_calibration'])

    def test_compact_repair_preserves_exact_draft_and_mapping_without_nested_source_context(self):
        text = 'First synthetic sentence. Second synthetic sentence.'
        self.context['repair'] = {
            'editing_attempt': 'fixture-repair', 'previous_run': 'fixture-run', 'assessment': 'fixture-assessment',
            'affected_sentences': ['sentence-2'], 'affected_acts': ['act-2'],
            'findings': [{'layer': 'linguistic', 'status': 'fail', 'reason': 'A specific fixture defect.'}],
            'local_repair_policy': {'version': 1, 'mode': 'replace_affected_sentence_text_only',
                                    'sentence_count': 2, 'affected_positions': [1],
                                    'preserved_sentences': [{'id': 'sentence-1', 'text': 'First synthetic sentence.',
                                                             'acts': ['act-1']}]},
            'prior_draft': {'plan': 'fixture-plan', 'text': text, 'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
                            'sentences': [
                                {'id': 'sentence-1', 'payload': {'text': 'First synthetic sentence.'}},
                                {'id': 'sentence-2', 'payload': {'text': 'Second synthetic sentence.'}}],
                            'detail': {'sentences': [
                                {'text': 'First synthetic sentence.', 'acts': ['act-1']},
                                {'text': 'Second synthetic sentence.', 'acts': ['act-2']}]},
                            'input': copy.deepcopy(self.context)},
        }
        packet = compact_writer_context(self.context)
        repair = packet['repair']
        self.assertNotIn(SUBJECT, json.dumps(packet))
        self.assertEqual(repair['prior_draft']['text'], text)
        self.assertEqual(repair['prior_draft']['sentences'][1],
                         {'id': 'sentence-2', 'text': 'Second synthetic sentence.', 'acts': ['act-2']})
        self.assertEqual(repair['affected_sentences'], ['sentence-2'])
        self.assertEqual(repair['local_repair_policy'], self.context['repair']['local_repair_policy'])
        self.assertNotIn('input', repair['prior_draft'])


if __name__ == '__main__':
    unittest.main()
