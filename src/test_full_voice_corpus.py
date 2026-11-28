"""Bound ledger projection with synthetic provider transports; no live calls."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from functools import partial
from unittest.mock import patch

from checking import Checking
from editing import Editing
from expression import Expression
from faculty import Faculty
from ingest import ingest
from model import Graph
from providers import JSONModel, SuppliedResearch
from run_agent import validate_configuration
from run_binding import ProviderJournal, RunBinding
from test_construction_closure import close_fixture_plan
import test_paragraph_cli
from test_paragraph_cli import live_configuration
from test_providers import completion
from test_resolved_checking_editing import criterion_findings
from test_run_binding import CONFIGURATION
from voice_resolution import FULL_CORPUS_SCOPE, PROFILE, compact_voice_catalog, resolve_voice_bindings


SUBJECT = 'A synthetic claim retains its qualification.'


class CorpusReasoner:
    def propose(self, context):
        return {'claims': [{'key': 'c1', 'text': SUBJECT, 'origin': 'external', 'evidence': ['source0']}],
                'acts': [{'purpose': 'Explain a qualified synthetic claim.', 'claims': ['c1'],
                          'voice_bindings': [
                              {'rule_id': rule, 'exemplar_ids': [example], 'layer': layer,
                               'application': 'Use this recorded operation for the synthetic act.',
                               'criterion': 'The synthetic act preserves the stated operation.'}
                              for rule, example, layer in [('R001', 'E001', 'conceptual'),
                                                           ('R016', 'E074', 'epistemic'),
                                                           ('R008', 'E021', 'rhetorical'),
                                                           ('R018', 'E054', 'linguistic')]]}]}


class FullVoiceCorpusTests(unittest.TestCase):
    def setUp(self):
        self.graph = Graph()
        self.addCleanup(self.graph.db.close)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'src').mkdir()
        (root / 'src/runtime.py').write_text('# Synthetic test runtime.\n')
        (root / 'procedure.json').write_text('{"version":"fixture","status":"synthetic test only"}')
        (root / 'subject.txt').write_text(SUBJECT)
        workbook = Path(__file__).parent / 'Authorial_Voice_Ledger_v0.4.xlsx'
        if not workbook.exists():
            workbook = workbook.parent.parent / workbook.name
        shutil.copyfile(workbook, root / 'ledger.xlsx')
        self.baseline = ingest(self.graph, root / 'ledger.xlsx')['sha256']
        self.binding = RunBinding.create(
            self.graph, repository_root=root, procedure_path='procedure.json', ledger_path='ledger.xlsx',
            source_paths=['subject.txt'], providers={role: dict(CONFIGURATION)
                for role in ('construction', 'expression', 'checking')},
            prompt_templates=JSONModel.prompt_templates(), mode='fixture')
        self.journals = {role: ProviderJournal(self.graph, self.binding, role)
                         for role in ('construction', 'expression', 'checking')}
        self.models = {role: JSONModel(**CONFIGURATION, journal=self.journals[role],
                                      transport=partial(self.transport, role)) for role in self.journals}
        self.check_count = 0
        self.exemplars = self.records('Exemplars')
        self.sources = self.records('Source evidence')

    def records(self, sheet):
        return {key: self.graph.get(ident) for key, ident in self.graph.db.execute(
            'SELECT record_key,node_id FROM imported_record WHERE digest=? AND sheet=?',
            (self.baseline, sheet))}

    def faculty(self, scope=FULL_CORPUS_SCOPE, reasoner=None):
        return Faculty(self.graph, reasoner or self.models['construction'],
                       SuppliedResearch([{'text': SUBJECT, 'source': 'fixture:subject'}]),
                       baseline_digest=self.baseline, execution_profile=PROFILE,
                       voice_context_scope=scope)

    def transport(self, role, request):
        record = self.journals[role].inspect()[-1]
        self.assertEqual(record['state'], 'invoking')
        self.assertEqual(record['request'].encode(), request.data)
        context = json.loads(json.loads(request.data)['messages'][1]['content'])
        if record['operation'] == 'construction':
            result = CorpusReasoner().propose(context)
        elif record['operation'] == 'construction_review':
            result = {'findings': [{'layer': layer, 'status': 'pass', 'reason': 'Synthetic construction review.'}
                                  for layer in ('conceptual', 'epistemic', 'rhetorical_plan')]}
        elif record['operation'] == 'expression':
            result = {'status': 'draft', 'sentences': [{
                'text': SUBJECT if 'repair' in context else 'The synthetic relation needs a local correction.',
                'acts': context['acts']}]}
        elif record['operation'] == 'checking':
            self.check_count += 1
            result = {'findings': criterion_findings(context,
                failure='base:linguistic' if self.check_count == 1 else None)}
        else:
            self.fail('Unexpected operation: ' + record['operation'])
        return completion(json.dumps(result))

    def test_all_84_excerpts_and_recorded_sources_reach_journaled_construction_expression_check_and_repair(self):
        faculty = self.faculty()
        before = self.graph.db.execute('SELECT * FROM edge ORDER BY src,rel,dst').fetchall()
        with patch.dict('os.environ', {'TEST_KEY': 'fixture-secret-key'}):
            plan = faculty.build('Express a synthetic fixture using the complete bound corpus.')
            review = faculty.review(plan, self.models['construction'])
            faculty.close(plan, review, 'author')
            frozen = faculty.c.snapshot(plan)
            expression = Expression(self.graph, self.models['expression'])
            checking = Checking(self.graph, self.models['checking'])
            first = expression.run(plan)
            assessment = checking.assess(first)
            revised = Editing(self.graph, expression, checking).run(first, assessment, actor='author')
            self.assertEqual(checking.inspect(checking.assess(revised))['state'], 'checks_passed')
        self.assertEqual(self.baseline, self.binding.inspect()['ledger']['sha256'])
        self.assertEqual(len(frozen['authentic_exemplars']), 84)
        self.assertEqual(faculty.c.snapshot(plan), frozen)
        self.assertEqual(self.records('Exemplars'), self.exemplars)
        self.assertEqual(self.records('Source evidence'), self.sources)
        self.assertEqual(self.graph.db.execute(
            "SELECT * FROM edge WHERE rel IN ('grounded_in','derived_from','context') ORDER BY src,rel,dst").fetchall(), before)
        requests = [record for journal in self.journals.values() for record in journal.inspect()]
        self.assertEqual(len(requests), 6)
        for record in requests:
            with self.subTest(operation=record['operation']):
                context = json.loads(json.loads(record['request'])['messages'][1]['content'])
                packet = context.get('construction', context)
                self.assertEqual(packet['voice_context_scope'], FULL_CORPUS_SCOPE)
                if 'voice_catalog' in packet:
                    catalog = packet['voice_catalog']
                    examples = {item['exemplar_id']: item for item in catalog['exemplars']}
                    transcripts = {item['payload']['Source ID']: item for item in catalog['sources']}
                    for key, original in self.exemplars.items():
                        self.assertEqual(examples[key]['payload'], original['payload'])
                        self.assertEqual(examples[key]['id'], original['id'])
                    self.assertEqual(transcripts, self.sources)
                    r016 = next(rule for rule in catalog['rules'] if rule['rule_id'] == 'R016')
                    self.assertEqual(r016['allowed_layers'], ['epistemic'])
                    self.assertEqual(r016['payload']['Layer'], 'Epistemic')
                    self.assertNotIn('Pangram human classification', json.dumps(packet))
                else:
                    examples = {item['key']: item for item in packet['voice_exemplars']}
                    transcripts = {item['source_key']: item for item in packet['source_contexts']}
                    for key, original in self.exemplars.items():
                        projected = examples[key]
                        self.assertEqual(projected['excerpt'], original['payload']['Exact excerpt'])
                        self.assertEqual(projected['id'], original['id'])
                        self.assertEqual(projected['source_ids'], [self.sources[original['payload']['Source ID']]['id']])
                        self.assertEqual(projected['written_validation'], original['payload']['Written validation'])
                    for key, original in self.sources.items():
                        self.assertEqual(transcripts[key]['transcript'], original['payload']['User transcript (segments joined)'])
                        self.assertEqual(transcripts[key]['provenance'], {key: value for key, value in original['payload'].items()
                                                                        if key != 'User transcript (segments joined)'})
                    self.assertEqual(sum(bool(item['selected_for_acts']) for item in examples.values()), 4)
                self.assertEqual(len(examples), 84)
                self.assertEqual(len(transcripts), 35)
                self.assertEqual(sum(bool(item['grounded_rule_ids']) for item in examples.values()), 47)
                self.assertTrue(all(item['authority'].startswith('original_spoken') for item in examples.values()))

    def test_unlinked_exemplar_is_available_but_cannot_be_falsely_bound_to_a_rule(self):
        faculty = self.faculty(reasoner=CorpusReasoner())
        voice = faculty.c.voice_context(faculty._rules(), self.baseline, FULL_CORPUS_SCOPE)
        catalog = compact_voice_catalog(voice)
        unlinked = next(item for item in catalog['exemplars'] if not item['grounded_rule_ids'])
        proposal = CorpusReasoner().propose({})['acts']
        proposal[0]['voice_bindings'][0]['exemplar_ids'] = [unlinked['exemplar_id']]
        before = self.graph.db.total_changes
        with self.assertRaisesRegex(ValueError, 'ground the selected rule'):
            resolve_voice_bindings(proposal, voice)
        self.assertEqual(self.graph.db.total_changes, before)
        proposal = CorpusReasoner().propose({})['acts']
        proposal[0]['voice_bindings'][1]['layer'] = 'linguistic'
        with self.assertRaisesRegex(ValueError, 'declared layer'):
            resolve_voice_bindings(proposal, voice)

    def test_changed_unlinked_exemplar_invalidates_full_corpus_closure(self):
        faculty = self.faculty(reasoner=CorpusReasoner())
        plan = faculty.build('Synthetic full-corpus freshness fixture.')
        close_fixture_plan(faculty, plan)
        catalog = compact_voice_catalog(faculty.c.snapshot(plan))
        unlinked = next(item for item in catalog['exemplars'] if not item['grounded_rule_ids'])
        node = self.graph.get(unlinked['id'])
        self.graph.revise(node['id'], dict(node['payload'], fixture_revision='Changed after closure'))
        with self.assertRaisesRegex(ValueError, 'Voice inputs changed'):
            faculty.c.require_closed(plan)
        self.assertEqual(self.journals['expression'].inspect(), [])

    def test_legacy_default_still_limits_catalog_to_grounding_and_writer_to_selected_examples(self):
        faculty = self.faculty(scope=None, reasoner=CorpusReasoner())
        plan = faculty.build('Synthetic legacy projection fixture.')
        close_fixture_plan(faculty, plan)
        snapshot = faculty.c.snapshot(plan)
        self.assertNotIn('voice_context_scope', snapshot)
        self.assertEqual(len(compact_voice_catalog(snapshot)['exemplars']), 47)
        expression = Expression(self.graph, None)
        packet = expression.writer_context(expression.context(plan))
        self.assertNotIn('voice_context_scope', packet)
        self.assertEqual(len(packet['voice_exemplars']), 4)

    def test_scope_is_explicit_profile_validated_and_checked_against_bound_configuration(self):
        config = live_configuration()
        config.update(execution_profile=PROFILE, voice_context_scope=FULL_CORPUS_SCOPE)
        self.assertEqual(validate_configuration(copy.deepcopy(config)), config)
        for changes in ({'voice_context_scope': 'all'}, {'execution_profile': None}):
            invalid = dict(config, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_configuration(invalid)
        engine, manifest = test_paragraph_cli.ParagraphCLITests.live_components_fixture(self)
        engine.f.voice_context_scope = FULL_CORPUS_SCOPE
        with self.assertRaisesRegex(ValueError, 'Voice context scope'):
            engine._bound_components(manifest)


if __name__ == '__main__':
    unittest.main()
