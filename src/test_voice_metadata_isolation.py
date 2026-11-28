"""Fixture transports exercise recorded prompts; no live calls or voice claims.

The review note and experiment fields reproduce the audited metadata leak.
All utterances, claims, provider responses and approvals below are synthetic.
"""
import copy
import json
import unittest
from functools import partial
from unittest.mock import patch

from checking import Checking, LAYERS
from editing import Editing
from expression import Expression
from faculty import Faculty
from model import Kind
from providers import JSONModel, SuppliedResearch
from run_binding import ProviderJournal
from test_providers import completion
from test_run_binding import CONFIGURATION, fixture_binding
from test_voice_resolution import calibration_fixture
from voice_resolution import PROFILE


AUDIT_NOTE = ('One paragraph revised; Pangram 92% to 100%; author validated full '
              'revised passage. Not isolated from rhetorical changes.')
TRANSCRIPT = 'Synthetic spoken example: Pangram and 100% are words in this example.'
SUBJECT = 'A synthetic relation has a stated condition.'


class VoiceMetadataIsolationTests(unittest.TestCase):
    def setUp(self):
        self.graph, self.binding, _ = fixture_binding(self)
        self.journals = {role: ProviderJournal(self.graph, self.binding, role)
                         for role in ('construction', 'expression', 'checking')}
        self.models = {role: JSONModel(**CONFIGURATION, journal=self.journals[role],
                                      transport=partial(self.transport, role))
                       for role in self.journals}
        self.construction_reviews = 0
        self.checks = 0
        source = self.graph.add(Kind.EVIDENCE, {
            'Source ID': 'S-fixture', 'User transcript (segments joined)': TRANSCRIPT})
        exemplar = self.graph.add(Kind.EVIDENCE, {
            'Exemplar ID': 'E-fixture', 'Source ID': 'S-fixture',
            'Exemplar type': 'Original spoken', 'Exact excerpt': TRANSCRIPT,
            'Layer': 'Linguistic', 'Written validation': 'Not validated for writing'})
        rule = self.graph.add(Kind.RULE, {
            'Rule ID': 'R-fixture', 'Layer': 'Linguistic; rhetorical',
            'Candidate rule': 'State the synthetic relation directly.',
            'Review note': AUDIT_NOTE, 'Status': 'Provisionally supported',
            'Applicability': 'Written; generalization pending',
            'activation': 'candidate_only'})
        self.graph.link(exemplar, 'derived_from', source)
        self.graph.link(rule, 'grounded_in', exemplar)
        experiments = []
        for prototype, score, validation, limitation in (
            ('001', 0.92, 'Not separately validated', 'Baseline; three flagged sentences'),
            ('002', 1.0, 'Synthetic passage-only author approval.',
             'One paragraph changed; rhetorical and linguistic changes confounded'),
        ):
            record = self.graph.add(Kind.EVIDENCE, {
                'Prototype': prototype, 'Topic': 'Synthetic historical experiment',
                'Ledger': 'fixture-ledger', 'Pangram human classification': score,
                'Author validation': validation, 'Change / limitations': limitation,
                'Lineage': 'Synthetic parent record'})
            experiments.append(record)
            self.graph.link(rule, 'grounded_in', record)
        self.ids = {'source': source, 'exemplar': exemplar, 'rule': rule,
                    'experiments': experiments}
        self.authoritative = {ident: self.graph.get(ident)
                              for ident in (source, exemplar, rule, *experiments)}
        self.faculty = Faculty(self.graph, self.models['construction'],
                               SuppliedResearch([{'text': SUBJECT, 'source': 'fixture:subject'}]),
                               execution_profile=PROFILE,
                               written_calibration=calibration_fixture())
        self.expression = Expression(self.graph, self.models['expression'])
        self.checking = Checking(self.graph, self.models['checking'])

    @staticmethod
    def voice_binding():
        return {'rule_id': 'R-fixture', 'exemplar_ids': ['E-fixture'],
                'layer': 'linguistic', 'application': 'State the relation directly.',
                'criterion': 'The expression states the relation without announcing it.'}

    def transport(self, role, request):
        recorded = self.journals[role].inspect()[-1]
        self.assertEqual(recorded['state'], 'invoking')
        self.assertEqual(recorded['request'].encode('utf-8'), request.data)
        context = json.loads(json.loads(request.data)['messages'][1]['content'])
        operation = recorded['operation']
        if operation == 'construction':
            result = {'claims': [{'key': 'c1', 'text': SUBJECT, 'origin': 'external',
                                   'evidence': ['source0']}],
                      'acts': [{'purpose': 'State the synthetic relation.', 'claims': ['c1'],
                                'voice_bindings': [self.voice_binding()]}]}
        elif operation == 'construction_review':
            self.construction_reviews += 1
            result = {'findings': [
                {'layer': layer,
                 'status': 'fail' if layer == 'rhetorical_plan' and self.construction_reviews == 1 else 'pass',
                 'reason': 'Synthetic review of the voice criterion.'}
                for layer in ('conceptual', 'epistemic', 'rhetorical_plan')]}
        elif operation == 'voice_resolution':
            binding = self.voice_binding()
            binding['criterion'] = 'The synthetic relation is stated directly without a preview.'
            result = {'status': 'bindings', 'acts': [
                {'id': act['id'], 'voice_bindings': [copy.deepcopy(binding)]}
                for act in context['acts']]}
        elif operation == 'expression':
            result = {'status': 'draft', 'sentences': [{
                'text': SUBJECT if 'repair' in context else 'I will state the synthetic relation.',
                'acts': context['acts']}]}
        elif operation == 'checking':
            self.checks += 1
            sentence = context['draft']['sentences'][0]['id']
            findings = []
            for layer in sorted(LAYERS):
                checks = []
                for criterion in context['construction']['criteria']:
                    if criterion['layer'] != layer:
                        continue
                    fails = criterion['id'] == 'base:linguistic' and self.checks == 1
                    checks.append({'criterion_id': criterion['id'],
                                   'status': 'fail' if fails else 'pass',
                                   'observation': 'Synthetic directness finding.',
                                   'sentences': [sentence],
                                   'defect_type': 'expression' if fails else 'none',
                                   'repair': ('State the same relation without the announcement.'
                                              if fails else None)})
                findings.append({'layer': layer,
                                 'status': 'fail' if any(c['status'] == 'fail' for c in checks) else 'pass',
                                 'reason': 'Synthetic criterion assessment.',
                                 'sentences': [sentence], 'checks': checks})
            result = {'findings': findings}
        else:
            self.fail('Unexpected provider operation: ' + operation)
        return completion(json.dumps(result))

    def test_journaled_operations_exclude_audit_results_and_keep_exact_voice_provenance(self):
        with patch.dict('os.environ', {'TEST_KEY': 'fixture-secret-key'}):
            original_plan = self.faculty.build('Express the synthetic relation.')
            original_snapshot = self.faculty.c.snapshot(original_plan)
            failed_review = self.faculty.review(original_plan, self.models['construction'])
            plan = self.faculty.repair_voice(original_plan, failed_review, actor='author')
            passing_review = self.faculty.review(plan, self.models['construction'])
            self.faculty.close(plan, passing_review, 'author')
            snapshot = self.faculty.c.snapshot(plan)
            first = self.expression.run(plan)
            assessment = self.checking.assess(first)
            revised = Editing(self.graph, self.expression, self.checking).run(
                first, assessment, actor='author')
            final_assessment = self.checking.assess(revised)
        self.assertEqual(self.checking.inspect(final_assessment)['state'], 'checks_passed')
        self.assertEqual(self.faculty.c.snapshot(original_plan), original_snapshot)
        self.assertEqual(self.faculty.c.snapshot(plan), snapshot)
        self.assertEqual({ident: self.graph.get(ident) for ident in self.authoritative},
                         self.authoritative)
        self.assertIn(AUDIT_NOTE, json.dumps(snapshot))
        self.assertIn('Pangram human classification', json.dumps(snapshot))
        self.assertIn(AUDIT_NOTE, json.dumps(self.expression.inspect(first)['input']))
        self.assertEqual(self.graph.get(self.ids['rule'])['payload']['Review note'], AUDIT_NOTE)

        records = [record for journal in self.journals.values() for record in journal.inspect()]
        self.assertEqual(sorted(record['operation'] for record in records), sorted([
            'construction', 'construction_review', 'voice_resolution', 'construction_review',
            'expression', 'checking', 'expression', 'checking']))
        for record in records:
            with self.subTest(operation=record['operation'], invocation=record['id']):
                self.assertEqual(record['state'], 'succeeded')
                context = json.loads(json.loads(record['request'])['messages'][1]['content'])
                serialized = json.dumps(context)
                self.assertNotIn(AUDIT_NOTE, serialized)
                self.assertNotIn('Review note', serialized)
                self.assertNotIn('review_note', serialized)
                self.assertNotIn('Pangram human classification', serialized)
                self.assertNotIn('Change / limitations', serialized)
                self.assertIn(TRANSCRIPT, serialized)
                self.assertIn(self.ids['source'], serialized)
                self.assertIn(self.ids['exemplar'], serialized)
                self.assertIn(self.ids['rule'], serialized)
                packet = context.get('construction', context)
                self.assertEqual(packet['written_calibration'], calibration_fixture())
                if 'voice_catalog' in packet:
                    catalog = packet['voice_catalog']
                    projected_rule = catalog['rules'][0]
                    payload = projected_rule['payload']
                    grounding = {item['id']: item for item in catalog['grounding_records']}
                    self.assertEqual(set(grounding), set(self.ids['experiments']))
                    for ident, experiment in grounding.items():
                        original = self.authoritative[ident]
                        self.assertIn('historical passage', experiment['projection_use'])
                        self.assertIn('does not validate an isolated rule', experiment['projection_use'])
                        self.assertEqual({key: value for key, value in experiment.items()
                                          if key not in {'payload', 'projection_use'}},
                                         {key: value for key, value in original.items() if key != 'payload'})
                        self.assertEqual(experiment['payload']['Author validation'],
                                         original['payload']['Author validation'])
                        self.assertEqual(experiment['payload']['Lineage'], original['payload']['Lineage'])
                        self.assertIn(ident, projected_rule['grounding_ids'])
                else:
                    projected_rule = packet['voice_rules'][0]
                    payload = {'Status': projected_rule['status'],
                               'Applicability': projected_rule['applicability'],
                               'activation': projected_rule['activation']}
                    for act in packet['intellectual_plan']:
                        for example in act['worked_examples']:
                            self.assertEqual(example['rule'], projected_rule)
                self.assertEqual(projected_rule['authority'], 'advisory_only')
                self.assertEqual(payload['Status'], 'Provisionally supported')
                self.assertEqual(payload['Applicability'], 'Written; generalization pending')
                self.assertEqual(payload['activation'], 'candidate_only')

        writer_records = self.journals['expression'].inspect()
        repair_packet = json.loads(json.loads(writer_records[1]['request'])['messages'][1]['content'])
        repair = repair_packet['repair']
        self.assertEqual(repair['prior_draft']['text'], self.expression.inspect(first)['text'])
        self.assertEqual(repair['assessment'], assessment)
        attempt = Editing(self.graph, self.expression, self.checking).inspect(repair['editing_attempt'])
        self.assertIn(AUDIT_NOTE, json.dumps(attempt['input']))
        self.assertNotIn('input', repair['prior_draft'])


if __name__ == '__main__':
    unittest.main()
