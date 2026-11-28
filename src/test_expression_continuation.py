"""Bound continuation uses fixture transports only; no model or detector calls."""
import copy
from functools import partial
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from checking import Checking
from continuation import (continuation_reference, copy_source_database,
                          validate_binding, validate_reference)
from execution import Execution
from expression import Expression
from faculty import Faculty
from ingest import ingest
from model import Graph
from paragraph_loop import ParagraphLoop
from providers import JSONModel, SuppliedResearch
from run_agent import main
from run_binding import ProviderJournal, RunBinding
from test_full_voice_corpus import CorpusReasoner, SUBJECT
from test_paragraph_loop import FixtureDetector
from test_providers import completion
from test_resolved_checking_editing import criterion_findings
from test_run_binding import CONFIGURATION


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / 'src').mkdir()
        (self.root / 'src/runtime.py').write_text('# Synthetic continuation test runtime.\n')
        (self.root / 'procedure.json').write_text('{"version":"fixture","status":"synthetic test only"}')
        (self.root / 'subject.txt').write_text(SUBJECT)
        workbook = Path(__file__).parent / 'Authorial_Voice_Ledger_v0.4.xlsx'
        if not workbook.exists():
            workbook = workbook.parent.parent / workbook.name
        shutil.copyfile(workbook, self.root / 'ledger.xlsx')
        self.parent_path = self.root / 'parent.sqlite'
        self.parent_graph = Graph(str(self.parent_path))
        self.addCleanup(self.parent_graph.db.close)
        ingest(self.parent_graph, self.root / 'ledger.xlsx')
        self.config = {'id': 'fixture-parent', 'version': '0.1', 'mode': 'fixture',
                       'intent': 'Express a synthetic fixture using the complete bound corpus.',
                       'procedure': 'procedure.json', 'ledger': 'ledger.xlsx', 'sources': ['subject.txt'],
                       'providers': {role: dict(CONFIGURATION) for role in ('construction', 'expression', 'checking')},
                       'prompt_templates_sha256': JSONModel.templates_digest(),
                       'execution_profile': 'resolved-voice-v1', 'voice_context_scope': 'full_corpus_v1',
                       'paragraph_groups': 'all_acts_one_paragraph', 'max_attempts': 3,
                       'max_voice_repairs': 0, 'written_calibration': [],
                       'recovery_authorization': {'construction_closure_and_local_repairs': True}}
        self.requests = []
        self.fail_child = False
        self.fail_parent = True
        self.enterContext(patch.dict('os.environ', {'TEST_KEY': 'fixture-secret-key'}))
        self.parent_binding = self.binding(self.parent_graph, self.config, 'parent-config.json')
        self.parent_engine, self.parent_detector = self.engine(self.parent_graph, self.parent_binding, 'parent')
        current = self.parent_engine.start(self.config['intent'], max_attempts=3, mode='fixture')
        self.assertEqual(current['state'], 'awaiting_construction_closure')
        self.parent_engine.close_construction(current['id'], actor='author')
        for _ in range(3):
            current = self.parent_engine.advance(current['id'], actor='author')
            self.assertEqual(current['state'], 'suspended_reopen')
        self.parent = self.parent_engine.advance(current['id'], actor='author')
        self.assertEqual(self.parent['state'], 'budget_exhausted')
        self.parent_bytes = self.parent_path.read_bytes()
        self.reference = continuation_reference(self.parent_path, self.parent['id'])

    def binding(self, graph, config, filename):
        (self.root / filename).write_text(json.dumps(config))
        return RunBinding.create(graph, repository_root=self.root, procedure_path='procedure.json',
                                 ledger_path='ledger.xlsx', source_paths=['subject.txt'],
                                 providers=config['providers'], prompt_templates=JSONModel.prompt_templates(),
                                 mode='fixture', configuration_path=filename)

    def engine(self, graph, binding, phase):
        config = binding.inspect()['configuration']['contents']
        models = {role: JSONModel(**CONFIGURATION, journal=ProviderJournal(graph, binding, role),
                                  transport=partial(self.transport, phase, graph, binding, role))
                  for role in config['providers']}
        faculty = Faculty(graph, models['construction'],
                          SuppliedResearch([{'text': SUBJECT, 'source': 'fixture:subject'}]),
                          baseline_digest=binding.inspect()['ledger']['sha256'],
                          execution_profile='resolved-voice-v1', voice_context_scope='full_corpus_v1')
        expression = Expression(graph, models['expression'])
        checking = Checking(graph, models['checking'])
        detector = FixtureDetector(expression, checking, ['passed'])
        detector.binding = binding
        loop = ParagraphLoop(graph, expression, checking, detector,
                             paragraph_groups='all_acts_one_paragraph', max_attempts=config['max_attempts'])
        return Execution(graph, faculty, expression, checking, binding=binding, paragraph_loop=loop), detector

    def transport(self, phase, graph, binding, role, request):
        record = ProviderJournal(graph, binding, role).inspect()[-1]
        self.assertEqual(record['state'], 'invoking')
        self.assertEqual(record['request'].encode(), request.data)
        context = json.loads(json.loads(request.data)['messages'][1]['content'])
        self.requests.append((phase, record['operation'], copy.deepcopy(context)))
        if record['operation'] == 'construction':
            result = CorpusReasoner().propose(context)
        elif record['operation'] == 'construction_review':
            result = {'findings': [{'layer': layer, 'status': 'pass', 'reason': 'Synthetic construction review.'}
                                  for layer in ('conceptual', 'epistemic', 'rhetorical_plan')]}
        elif record['operation'] == 'expression':
            result = {'status': 'draft', 'sentences': [
                {'text': ('The repaired synthetic relation is direct.' if phase == 'child'
                          else 'The synthetic relation still needs a local correction.'), 'acts': context['acts']},
                {'text': 'This unaffected synthetic sentence stays exactly as recorded.', 'acts': context['acts']}]}
        elif record['operation'] == 'checking':
            failed = self.fail_parent if phase == 'parent' else self.fail_child
            findings = criterion_findings(context, failure='base:linguistic' if failed else None)
            if failed:
                finding = next(item for item in findings if item['layer'] == 'linguistic')
                finding['sentences'] = [context['draft']['sentences'][0]['id']]
                next(item for item in finding['checks'] if item['criterion_id'] == 'base:linguistic')['sentences'] = finding['sentences']
            result = {'findings': findings}
        else:
            self.fail('Unexpected fixture operation: ' + record['operation'])
        return completion(json.dumps(result))

    def child(self, *, budget=6, config_change=None, name='child'):
        path = self.root / (name + '.sqlite')
        copy_source_database(self.parent_path, path, self.reference)
        graph = Graph(str(path))
        self.addCleanup(graph.db.close)
        config = dict(copy.deepcopy(self.config), id='fixture-' + name, max_attempts=budget,
                      continuation=copy.deepcopy(self.reference))
        if config_change:
            config_change(config)
        binding = self.binding(graph, config, name + '-config.json')
        engine, detector = self.engine(graph, binding, 'child')
        return graph, engine, detector

    def test_journaled_repair_uses_new_binding_and_preserves_exact_parent(self):
        parent_history = self.parent_engine.history(self.parent['id'])
        parent_progress = self.parent_engine.paragraph_loop.history(self.parent['id'])
        parent_draft = self.parent_engine.e.inspect(self.parent['run'])
        parent_construction = self.parent_engine.e.c.snapshot(self.parent['plan'])
        before = len(self.requests)
        graph, engine, detector = self.child()
        new = engine.continue_expression(actor='author')
        self.assertEqual(new['state'], 'suspended_reopen')
        self.assertEqual(new['route'], 'expression')
        self.assertEqual(new['attempts'], 3)
        self.assertEqual(new['max_attempts'], 6)
        self.assertNotEqual(new['id'], self.parent['id'])
        self.assertNotEqual(new['binding_id'], self.parent['binding_id'])
        for key in ('plan', 'closure', 'construction_review', 'run', 'assessment'):
            self.assertEqual(new[key], self.parent[key])
        self.assertEqual(len(self.requests), before)
        self.assertEqual(detector.calls, [])
        inherited = engine.paragraph_loop.inspect(new['id'])['paragraphs'][0]
        self.assertEqual(inherited, parent_progress[-1]['paragraphs'][0])
        with self.assertRaisesRegex(ValueError, 'already has an execution'):
            engine.continue_expression(actor='author')
        complete = engine.advance(new['id'], actor='author')
        self.assertEqual(complete['state'], 'awaiting_approval')
        self.assertEqual(complete['attempts'], 4)
        self.assertNotEqual(complete['run'], self.parent['run'])
        self.assertEqual(complete['paragraph_progress']['authorial_validation'], 'pending')
        calls = self.requests[before:]
        self.assertEqual([operation for _, operation, _ in calls], ['expression', 'checking'])
        writer = calls[0][2]
        self.assertEqual(writer['repair']['previous_run'], self.parent['run'])
        self.assertEqual(writer['repair']['assessment'], self.parent['assessment'])
        self.assertEqual(writer['repair']['prior_draft']['text_sha256'], parent_draft['text_sha256'])
        self.assertEqual(writer['repair']['local_repair_policy']['affected_positions'], [0])
        self.assertEqual(writer['paragraph'], parent_draft['input']['paragraph'])
        self.assertNotIn('continuation', writer)
        self.assertNotIn('fraction_human', json.dumps(writer))
        draft = engine.e.inspect(complete['run'])
        self.assertEqual(draft['sentences'][1]['payload']['text'], parent_draft['sentences'][1]['payload']['text'])
        self.assertEqual({item['layer'] for item in engine.c.inspect(complete['assessment'])['findings']},
                         {'conceptual', 'epistemic', 'rhetorical', 'linguistic'})
        self.assertEqual([call[0] for call in detector.calls], ['start', 'advance'])
        records = [record for role in ('construction', 'expression', 'checking')
                   for record in ProviderJournal(graph, engine.binding, role).inspect()]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record['state'] == 'succeeded' for record in records))
        self.assertEqual(engine.history(self.parent['id']), parent_history)
        self.assertEqual(engine.paragraph_loop.history(self.parent['id']), parent_progress)
        self.assertEqual(engine.e.inspect(self.parent['run']), parent_draft)
        self.assertEqual(engine.e.c.snapshot(self.parent['plan']), parent_construction)
        self.assertEqual(self.parent_path.read_bytes(), self.parent_bytes)
        self.assertEqual(self.parent_engine.inspect(self.parent['id'])['state'], 'budget_exhausted')
        self.assertEqual(continuation_reference(self.parent_path, self.parent['id']), self.reference)
        for operation in ('UPDATE continuation_snapshot SET source_path=source_path', 'DELETE FROM continuation_snapshot'):
            with self.assertRaises(sqlite3.IntegrityError):
                with graph.db:
                    graph.db.execute(operation)

    def test_extended_budget_counts_inherited_attempts_and_still_stops(self):
        self.fail_child = True
        _, engine, detector = self.child(budget=5)
        child = engine.continue_expression(actor='author')
        before = len(self.requests)
        for number in (4, 5):
            child = engine.advance(child['id'], actor='author')
            self.assertEqual(child['state'], 'suspended_reopen')
            self.assertEqual(child['attempts'], number)
        exhausted = engine.advance(child['id'], actor='author')
        self.assertEqual(exhausted['state'], 'budget_exhausted')
        self.assertEqual(exhausted['attempts'], 5)
        self.assertEqual([item['number'] for item in exhausted['paragraph_progress']['paragraphs'][0]['attempts']],
                         [1, 2, 3, 4, 5])
        self.assertEqual(len(self.requests) - before, 4)
        self.assertEqual(detector.calls, [])
        self.assertEqual(self.parent_path.read_bytes(), self.parent_bytes)

    def test_reference_and_copy_are_read_only_and_reject_wrong_or_existing_targets(self):
        changes = self.parent_graph.db.total_changes
        output = io.StringIO()
        with patch('sys.stdout', output):
            result = main(['continuation-reference', '--database', str(self.parent_path),
                           '--execution', self.parent['id']])
        self.assertEqual(result, self.reference)
        self.assertEqual(json.loads(output.getvalue()), self.reference)
        self.assertEqual(self.parent_graph.db.total_changes, changes)
        self.assertEqual(self.parent_path.read_bytes(), self.parent_bytes)
        with self.assertRaises(ValueError):
            copy_source_database(self.parent_path, self.parent_path, self.reference)
        destination = self.root / 'not-created.sqlite'
        wrong = dict(self.reference, source_text_sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'differs'):
            copy_source_database(self.parent_path, destination, wrong)
        self.assertFalse(destination.exists())
        destination.write_bytes(b'existing evidence')
        with self.assertRaises(ValueError):
            copy_source_database(self.parent_path, destination, self.reference)
        self.assertEqual(destination.read_bytes(), b'existing evidence')

    def test_changed_import_is_rejected_before_a_provider_or_execution(self):
        graph, engine, _ = self.child()
        sentence = engine.e.inspect(self.parent['run'])['sentences'][0]
        graph.revise(sentence['id'], dict(sentence['payload'], text='Changed after import.'))
        before = len(self.requests)
        with self.assertRaises(ValueError):
            engine.continue_expression(actor='author')
        self.assertEqual(len(self.requests), before)
        self.assertEqual(graph.db.execute('SELECT count(*) FROM execution').fetchone()[0], 1)
        self.assertEqual(self.parent_path.read_bytes(), self.parent_bytes)

    def test_continuation_requires_author_new_snapshot_and_new_binding(self):
        graph, engine, _ = self.child()
        for actor in (None, 'agent'):
            with self.assertRaises(PermissionError):
                engine.continue_expression(actor=actor)
        with self.assertRaisesRegex(ValueError, 'explicit expression-continuation'):
            engine.start(self.config['intent'], max_attempts=6, mode='fixture')
        self.assertEqual(graph.db.execute('SELECT count(*) FROM execution').fetchone()[0], 1)
        with self.assertRaises(ValueError):
            self.parent_engine.continue_expression(actor='author')
        self.assertEqual(self.parent_path.read_bytes(), self.parent_bytes)

    def test_configuration_drift_and_unextended_budget_are_rejected(self):
        graph, engine, _ = self.child(config_change=lambda config: config.update(intent='Different intent'))
        before = len(self.requests)
        with self.assertRaisesRegex(ValueError, 'may change only'):
            engine.continue_expression(actor='author')
        self.assertEqual(len(self.requests), before)
        self.assertEqual(graph.db.execute('SELECT count(*) FROM execution').fetchone()[0], 1)
        old = self.parent_binding.inspect()
        current = engine.binding.inspect()
        current['configuration']['contents']['intent'] = old['configuration']['contents']['intent']
        for field, value in (('voice_context_scope', None), ('max_voice_repairs', 1),
                             ('sources', ['different.txt']), ('providers', {}),
                             ('prompt_templates_sha256', '0' * 64)):
            changed = copy.deepcopy(current)
            changed['configuration']['contents'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_binding(old, changed, self.reference)
        for field in ('ledger', 'procedure'):
            changed = copy.deepcopy(current)
            changed[field]['sha256'] = '0' * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_binding(old, changed, self.reference)
        for budget in (2, 3):
            changed = copy.deepcopy(current)
            changed['configuration']['contents']['max_attempts'] = budget
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                validate_binding(old, changed, self.reference)

    def test_detector_only_failure_cannot_be_registered_as_a_writing_repair(self):
        self.fail_parent = False
        self.parent_detector.outcomes = ['flagged']
        current = self.parent_engine.start(self.config['intent'], max_attempts=3, mode='fixture')
        self.parent_engine.close_construction(current['id'], actor='author')
        flagged = self.parent_engine.advance(current['id'])
        self.assertEqual(flagged['state'], 'suspended_detector_flagged')
        before = len(self.requests)
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            continuation_reference(self.parent_path, flagged['id'])
        self.assertEqual(len(self.requests), before)

    def test_driver_requires_exact_execution_when_parent_is_retained(self):
        path = Path(__file__).resolve().parents[1] / 'verification' / 'run_recovery_trial.py'
        spec = importlib.util.spec_from_file_location('continuation_test_driver', path)
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        rows = [(json.dumps({'id': 'parent'}),), (json.dumps({'id': 'child'}),)]
        with self.assertRaisesRegex(ValueError, '--execution'):
            driver.select_execution(rows)
        self.assertEqual(driver.select_execution(rows, 'child'), {'id': 'child'})
        with self.assertRaises(ValueError):
            driver.select_execution(rows, 'missing')

    def test_reference_schema_does_not_accept_detector_metadata(self):
        with self.assertRaises(ValueError):
            validate_reference(dict(self.reference, fraction_human=1.0))


if __name__ == '__main__':
    unittest.main()
