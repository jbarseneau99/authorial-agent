"""Paragraph CLI read-only inspection and committed-addendum regression tests."""
import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from checking import Checking
from execution import Execution
from expression import Expression
from faculty import Faculty
from model import Graph
from pangram_check import PangramCheck
from paragraph_loop import ParagraphLoop
from providers import JSONModel
from run_agent import PARAGRAPH_ADDENDUM, ROOT, main, validate_configuration
from run_binding import ProviderJournal, RunBinding
from test_faculty import Research
from test_pangram_check import CONFIG, TEXT, result_for
from test_paragraph_loop import PipelineReviewer, TwoActReasoner
from test_run_binding import CONFIGURATION, fixture_binding


def live_configuration():
    return {
        'mode': 'live', 'intent': 'Synthetic configuration validation only',
        'procedure': 'procedure.json', 'ledger': 'ledger.bin', 'sources': ['source.txt'],
        'providers': {role: dict(CONFIGURATION) for role in ('construction', 'expression', 'checking')},
        'prompt_templates_sha256': JSONModel.templates_digest(),
        'paragraph_mode': 'pangram-gated-v1', 'pangram': dict(CONFIG),
        'procedure_addenda': [PARAGRAPH_ADDENDUM], 'paragraph_groups': None,
        'max_attempts': 3,
    }


class ParagraphCLITests(unittest.TestCase):
    def live_components_fixture(self):
        """Isolate pre-provider validation from Git, credentials and HTTP.

        The fixture binding is explicitly promoted only in mocked inspection;
        this test is not evidence of live execution or a real commit binding.
        """
        graph, _, root = fixture_binding(self)
        config = live_configuration()
        (root / 'configuration.json').write_text(json.dumps(config))
        addendum = root / PARAGRAPH_ADDENDUM
        addendum.parent.mkdir(parents=True)
        addendum.write_bytes((ROOT / PARAGRAPH_ADDENDUM).read_bytes())
        binding = RunBinding.create(
            graph, repository_root=root, procedure_path='procedure.json', ledger_path='ledger.bin',
            source_paths=['source.txt'], providers=config['providers'],
            prompt_templates=JSONModel.prompt_templates(), mode='fixture',
            configuration_path='configuration.json', addenda_paths=[PARAGRAPH_ADDENDUM])
        manifest = binding.inspect()
        manifest['mode'] = 'live'
        self.enterContext(patch.object(binding, 'verify', return_value=manifest))
        self.enterContext(patch.object(binding, 'inspect', return_value=manifest))
        providers = {role: JSONModel(**settings, transport=lambda request: None,
                                    journal=ProviderJournal(graph, binding, role))
                     for role, settings in config['providers'].items()}
        faculty = Faculty(graph, providers['construction'], Research(),
                          baseline_digest=manifest['ledger']['sha256'])
        expression = Expression(graph, providers['expression'])
        checking = Checking(graph, providers['checking'])
        scanner = PangramCheck(graph, expression, checking, binding=binding,
                               configuration=config['pangram'], transport=lambda request: None)
        self.enterContext(patch.object(scanner, 'preflight', return_value={'state': 'ready'}))
        paragraphs = ParagraphLoop(graph, expression, checking, scanner,
                                   paragraph_groups=None, max_attempts=3)
        engine = Execution(graph, faculty, expression, checking, binding=binding,
                           paragraph_loop=paragraphs)
        # Establish that later rejections cannot be explained by an unrelated
        # missing journal, role, ledger, credential or detector component.
        engine._bound_components(manifest)
        return engine, manifest

    def test_live_api_rejects_changed_intent_before_construction(self):
        engine, manifest = self.live_components_fixture()
        with patch.object(engine.f, 'build', side_effect=AssertionError('Construction must not run')) as build:
            with self.assertRaises(ValueError):
                engine.start('An intent absent from the bound configuration', mode='live')
        build.assert_not_called()
        self.assertEqual(engine.g.db.execute('SELECT count(*) FROM execution').fetchone()[0], 0)

    def test_live_api_rejects_changed_rules_or_paragraph_contract_before_construction(self):
        changes = ('rules', 'mode', 'policy', 'declared_addendum', 'bound_addendum', 'groups', 'budget')
        for change in changes:
            with self.subTest(change=change):
                engine, manifest = self.live_components_fixture()
                config = manifest['configuration']['contents']
                if change == 'rules':
                    engine.f.rule_ids = ['unbound-rule-selection']
                elif change == 'mode':
                    config.pop('paragraph_mode')
                elif change == 'policy':
                    config['pangram']['policy'] = 'accept-anything'
                elif change == 'declared_addendum':
                    config['procedure_addenda'] = []
                elif change == 'bound_addendum':
                    manifest['procedure_addenda'] = []
                elif change == 'groups':
                    config['paragraph_groups'] = [[0, 1]]
                else:
                    config['max_attempts'] = 7
                with patch.object(engine.f, 'build', side_effect=AssertionError('Construction must not run')) as build:
                    with self.assertRaises(ValueError):
                        engine.start(config['intent'], mode='live')
                build.assert_not_called()
                self.assertEqual(engine.g.db.execute('SELECT count(*) FROM execution').fetchone()[0], 0)

    def make_pending_paragraph_run(self, path):
        graph = Graph(str(path))
        faculty = Faculty(graph, TwoActReasoner(), Research())
        calls, submitted = [], {}

        class Writer:
            def realize(self, context):
                return {'status': 'draft', 'sentences': [
                    {'text': TEXT + ' Paragraph ' + str(context['paragraph']['index']) + '.',
                     'acts': context['acts']}]}

        def transport(request):
            calls.append(request.get_method())
            if request.get_method() == 'POST':
                task = 'fixture-task-' + str(len(submitted))
                submitted[task] = json.loads(request.data)['text']
                return {'task_id': task}
            return result_for(submitted[request.full_url.rsplit('/', 1)[1]])

        expression = Expression(graph, Writer())
        checking = Checking(graph, PipelineReviewer())
        scanner = PangramCheck(graph, expression, checking, configuration=CONFIG, transport=transport)
        paragraphs = ParagraphLoop(graph, expression, checking, scanner)
        engine = Execution(graph, faculty, expression, checking, paragraph_loop=paragraphs)
        initial = engine.start('Synthetic two-paragraph CLI fixture', mode='fixture')
        engine.close_construction(initial['id'], actor='author')
        self.assertEqual(engine.advance(initial['id'])['state'], 'suspended_detector_pending')
        self.assertEqual(engine.advance(initial['id'])['state'], 'ready_for_next_paragraph')
        latest = engine.advance(initial['id'])
        self.assertEqual(latest['state'], 'suspended_detector_pending')
        self.assertEqual(calls, ['POST', 'GET', 'POST'])
        graph.db.close()
        return initial['id'], latest

    def test_inspect_shows_current_scans_without_writes_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'paragraphs.sqlite'
            execution, latest = self.make_pending_paragraph_run(database)
            before = database.read_bytes()
            with (patch('providers.JSONModel._http') as model,
                  patch('pangram_check.PangramCheck._http') as detector,
                  contextlib.redirect_stdout(io.StringIO())):
                report = main(['inspect', '--database', str(database), '--execution', execution])
            model.assert_not_called()
            detector.assert_not_called()
            self.assertEqual(database.read_bytes(), before)
            self.assertEqual(report['execution']['execution_scope'], 'paragraphs')
            self.assertEqual(report['current_state'], 'suspended_detector_pending')
            self.assertEqual(report['paragraph_progress']['active_index'], 1)
            self.assertEqual([scan['state'] for scan in report['pangram_scans']], ['passed', 'pending'])
            self.assertEqual(report['pangram_scans'][-1]['id'], latest['scan'])
            self.assertEqual(report['pangram_scans'][0]['version'], '4.1')
            self.assertTrue(report['paragraph_history'])

    def test_inspect_exposes_stale_prior_scan_without_mutating_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'paragraphs.sqlite'
            execution, latest = self.make_pending_paragraph_run(database)
            graph = Graph(str(database))
            expression = Expression(graph, None)
            prior = latest['paragraph_progress']['paragraphs'][0]
            sentence = expression.inspect(prior['run'])['sentences'][0]
            graph.revise(sentence['id'], dict(sentence['payload'], text='Changed prior fixture.'))
            graph.db.close()
            before = database.read_bytes()
            with (patch('providers.JSONModel._http') as model,
                  patch('pangram_check.PangramCheck._http') as detector,
                  contextlib.redirect_stdout(io.StringIO())):
                report = main(['inspect', '--database', str(database), '--execution', execution])
            model.assert_not_called()
            detector.assert_not_called()
            self.assertEqual(database.read_bytes(), before)
            self.assertEqual(report['current_state'], 'stale')
            self.assertEqual(report['paragraph_progress']['state'], 'stale')
            self.assertTrue(all(scan['state'] == 'stale' for scan in report['pangram_scans']))

    def test_new_live_configuration_rejects_legacy_or_unbound_policy_before_io(self):
        valid = live_configuration()
        self.assertEqual(validate_configuration(copy.deepcopy(valid)), valid)
        changes = [lambda config: config.pop('paragraph_mode'),
                   lambda config: config.update(paragraph_mode='whole_plan_legacy'),
                   lambda config: config.update(procedure_addenda=[]),
                   lambda config: config['pangram'].update(policy='accept-anything')]
        for mutate in changes:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as directory:
                config = copy.deepcopy(valid)
                mutate(config)
                configuration = Path(directory) / 'configuration.json'
                configuration.write_text(json.dumps(config), encoding='utf-8')
                database = Path(directory) / 'run.sqlite'
                with (patch('providers.JSONModel._http') as model,
                      patch('pangram_check.PangramCheck._http') as detector,
                      contextlib.redirect_stderr(io.StringIO())):
                    with self.assertRaises(SystemExit):
                        main(['start', '--config', str(configuration), '--database', str(database), '--live'])
                model.assert_not_called()
                detector.assert_not_called()
                self.assertFalse(database.exists())

    def test_declared_addendum_must_be_bound_and_its_exact_file_remain_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/runtime.py').write_text('# Synthetic runtime fixture only.\n')
            (root / 'procedure.json').write_text(json.dumps({'version': '0.2', 'status': 'unvalidated reconstruction'}))
            (root / 'ledger.bin').write_bytes(b'synthetic ledger fixture')
            (root / 'source.txt').write_text('Synthetic source fixture.')
            addendum = root / PARAGRAPH_ADDENDUM
            addendum.parent.mkdir(parents=True)
            addendum.write_text(json.dumps({'version': '0.1', 'status': 'author-directed'}))
            config = live_configuration()
            (root / 'configuration.json').write_text(json.dumps(config))
            def git(*args):
                subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
            git('init', '-q')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '-qm', 'Synthetic committed configuration fixture')
            graph = Graph()
            self.addCleanup(graph.db.close)
            parameters = dict(repository_root=root, procedure_path='procedure.json', ledger_path='ledger.bin',
                              source_paths=['source.txt'], providers=config['providers'],
                              prompt_templates=JSONModel.prompt_templates(), mode='live',
                              configuration_path='configuration.json')
            with patch('run_binding.__file__', str(root / 'src/run_binding.py')):
                # A declared path alone is not a bound, hashed procedure artifact.
                with self.assertRaises(ValueError):
                    RunBinding.create(graph, **parameters, addenda_paths=[])
                binding = RunBinding.create(graph, **parameters, addenda_paths=[PARAGRAPH_ADDENDUM])
                manifest = binding.verify()
                self.assertEqual(manifest['procedure_addenda'][0]['path'], str(addendum))
                self.assertEqual(manifest['configuration']['contents']['procedure_addenda'], [PARAGRAPH_ADDENDUM])
                addendum.write_text(json.dumps({'version': '0.1', 'status': 'changed fixture'}))
                with self.assertRaises(ValueError):
                    binding.verify()


if __name__ == '__main__':
    unittest.main()
