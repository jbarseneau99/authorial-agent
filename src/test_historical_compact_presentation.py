"""Historical input presentation with real ledger data and fixture transports."""
import copy
import json
import unittest
from unittest.mock import patch

from checking import Checking
from editing import Editing
from expression import Expression
from faculty import Faculty
from providers import SuppliedResearch
from run_agent import validate_configuration
import test_full_voice_corpus
import test_paragraph_cli
from test_construction_closure import close_fixture_plan
from test_providers import completion
from test_voice_resolution import calibration_fixture
from voice_resolution import FULL_CORPUS_SCOPE, HISTORICAL_COMPACT_PRESENTATION, PROFILE


class HistoricalCompactPresentationTests(unittest.TestCase):
    records = test_full_voice_corpus.FullVoiceCorpusTests.records

    def setUp(self):
        self.construction_review_count = 0
        test_full_voice_corpus.FullVoiceCorpusTests.setUp(self)

    def faculty(self, reasoner=None):
        return Faculty(self.graph, reasoner or self.models['construction'],
                       SuppliedResearch([{'text': test_full_voice_corpus.SUBJECT, 'source': 'fixture:subject'}]),
                       baseline_digest=self.baseline, execution_profile=PROFILE,
                       voice_context_scope=FULL_CORPUS_SCOPE,
                       voice_context_presentation=HISTORICAL_COMPACT_PRESENTATION,
                       written_calibration=calibration_fixture())

    def transport(self, role, request):
        record = self.journals[role].inspect()[-1]
        context = json.loads(json.loads(request.data)['messages'][1]['content'])
        if record['operation'] == 'construction_review':
            self.construction_review_count += 1
            if self.construction_review_count == 1:
                return completion(json.dumps({'findings': [
                    {'layer': layer, 'status': 'fail' if layer == 'rhetorical_plan' else 'pass',
                     'reason': 'A synthetic binding criterion needs clarification.'}
                    for layer in ('conceptual', 'epistemic', 'rhetorical_plan')]}))
        if record['operation'] == 'voice_resolution':
            acts = []
            for act in context['acts']:
                bindings = [{'rule_id': binding['rule_key'], 'exemplar_ids': binding['exemplar_keys'],
                             'layer': binding['layer'], 'application': binding['application'],
                             'criterion': binding['criterion'] + ' Preserve the synthetic relation.'}
                            for binding in act['voice_bindings']]
                acts.append({'id': act['id'], 'voice_bindings': bindings})
            return completion(json.dumps({'status': 'bindings', 'acts': acts}))
        return test_full_voice_corpus.FullVoiceCorpusTests.transport(self, role, request)

    def test_journaled_generation_has_all_rules_and_exact_excerpts_while_reviewers_keep_full_sources(self):
        faculty = self.faculty()
        with patch.dict('os.environ', {'TEST_KEY': 'fixture-secret-key'}):
            original = faculty.build('Synthetic compact-presentation fixture.')
            original_snapshot = faculty.c.snapshot(original)
            review = faculty.review(original, self.models['construction'])
            plan = faculty.repair_voice(original, review, actor='author')
            passing = faculty.review(plan, self.models['construction'])
            faculty.close(plan, passing, 'author')
            frozen = faculty.c.snapshot(plan)
            expression = Expression(self.graph, self.models['expression'])
            checking = Checking(self.graph, self.models['checking'])
            first = expression.run(plan)
            assessment = checking.assess(first)
            revised = Editing(self.graph, expression, checking).run(first, assessment, actor='author')
            self.assertEqual(checking.inspect(checking.assess(revised))['state'], 'checks_passed')
        self.assertEqual(faculty.c.snapshot(original), original_snapshot)
        self.assertEqual(faculty.c.snapshot(plan), frozen)
        self.assertEqual(self.records('Source evidence'), self.sources)
        self.assertEqual(self.records('Exemplars'), self.exemplars)
        expected_rules = self.records('Candidate rules')
        records = [record for journal in self.journals.values() for record in journal.inspect()]
        self.assertEqual(len(records), 8)
        for record in records:
            with self.subTest(operation=record['operation']):
                self.assertEqual(record['state'], 'succeeded')
                context = json.loads(json.loads(record['request'])['messages'][1]['content'])
                packet = context.get('construction', context)
                self.assertEqual(packet['voice_context_presentation'], HISTORICAL_COMPACT_PRESENTATION)
                self.assertEqual(packet['written_calibration'], calibration_fixture())
                if 'voice_catalog' in packet:
                    catalog = packet['voice_catalog']
                    rules = {item['rule_id']: item for item in catalog['rules']}
                    examples = {item['exemplar_id']: item for item in catalog['exemplars']}
                    if record['operation'] == 'construction_review':
                        self.assertEqual(len(catalog['sources']), 35)
                        self.assertEqual({item['payload']['Source ID']: item for item in catalog['sources']}, self.sources)
                    else:
                        self.assertEqual(catalog['sources'], [])
                        self.assertNotIn('User transcript (segments joined)', json.dumps(packet))
                        for key, original_rule in expected_rules.items():
                            self.assertEqual(rules[key]['text'], original_rule['payload']['Candidate rule'])
                            self.assertEqual(rules[key]['status'], original_rule['payload']['Status'])
                            self.assertEqual(rules[key]['activation'], 'candidate_only')
                            self.assertNotIn('payload', rules[key])
                        for key, original_example in self.exemplars.items():
                            self.assertEqual(examples[key]['text'], original_example['payload']['Exact excerpt'])
                            self.assertEqual(examples[key]['id'], original_example['id'])
                        self.assertEqual(rules['R016']['allowed_layers'], ['epistemic'])
                else:
                    rules = {item['key']: item for item in packet['voice_rules']}
                    examples = {item['key']: item for item in packet['voice_exemplars']}
                    for key, original_example in self.exemplars.items():
                        self.assertEqual(examples[key]['excerpt'], original_example['payload']['Exact excerpt'])
                    self.assertEqual(sum(bool(item['selected_for_acts']) for item in rules.values()), 4)
                    self.assertEqual(sum(len(act['worked_examples']) for act in packet['intellectual_plan']), 4)
                    if record['operation'] == 'checking':
                        transcripts = {item['source_key']: item['transcript'] for item in packet['source_contexts']}
                        self.assertEqual(transcripts, {key: value['payload']['User transcript (segments joined)']
                                                      for key, value in self.sources.items()})
                    else:
                        self.assertEqual(packet['source_contexts'], [])
                        self.assertNotIn('User transcript (segments joined)', json.dumps(packet))
                        self.assertTrue(all(item['text_visibility'] == 'withheld_from_expression'
                                            for item in packet['source_references']))
                        if 'repair' in packet:
                            self.assertNotIn('input', packet['repair']['prior_draft'])
                self.assertEqual(len(rules), 18)
                self.assertEqual(len(examples), 84)
                self.assertTrue(all(rule['authority'] == 'advisory_only' for rule in rules.values()))
        self.assertIn(self.sources['S007']['payload']['User transcript (segments joined)'],
                      json.dumps(frozen, ensure_ascii=False))

    def test_omitted_source_context_still_invalidates_frozen_construction(self):
        faculty = self.faculty(test_full_voice_corpus.CorpusReasoner())
        plan = faculty.build('Synthetic source-omission freshness fixture.')
        close_fixture_plan(faculty, plan)
        source = self.sources['S007']
        self.graph.revise(source['id'], dict(source['payload'], fixture_revision='changed'))
        with self.assertRaisesRegex(ValueError, 'Voice inputs changed'):
            faculty.c.require_closed(plan)
        self.assertEqual(self.journals['expression'].inspect(), [])

    def test_presentation_requires_full_scope_complete_rules_and_matching_configuration(self):
        config = test_paragraph_cli.live_configuration()
        config.update(execution_profile=PROFILE, voice_context_scope=FULL_CORPUS_SCOPE,
                      voice_context_presentation=HISTORICAL_COMPACT_PRESENTATION)
        self.assertEqual(validate_configuration(copy.deepcopy(config)), config)
        for changes in ({'voice_context_scope': None}, {'voice_context_presentation': 'unknown'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_configuration(dict(config, **changes))
        faculty = self.faculty(test_full_voice_corpus.CorpusReasoner())
        faculty.rule_ids = [self.records('Candidate rules')['R001']['id']]
        with self.assertRaisesRegex(ValueError, 'complete bound rule catalog'):
            faculty.build('Cannot silently narrow the historical catalog.')
        engine, manifest = test_paragraph_cli.ParagraphCLITests.live_components_fixture(self)
        engine.f.voice_context_presentation = HISTORICAL_COMPACT_PRESENTATION
        with self.assertRaisesRegex(ValueError, 'Voice context presentation'):
            engine._bound_components(manifest)


if __name__ == '__main__':
    unittest.main()
