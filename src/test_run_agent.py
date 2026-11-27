import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from model import Graph
from run_agent import execute, ResearchBridge, inspect_execution, main
from research_loop import BoundSources
from execution import Execution
from faculty import Faculty
from expression import Expression
from checking import Checking
from test_faculty import Reasoner, Research
from test_expression import Writer
from test_checking import Reviewer
from test_run_binding import fixture_binding


class ConstructionReviewer(Reviewer):
    def assess_construction(self, context):
        return [{'layer': layer, 'status': 'pass', 'reason': 'Deterministic fixture judgment only'}
                for layer in ('conceptual', 'epistemic', 'rhetorical_plan')]


class ObservedWriter(Writer):
    def __init__(self):
        super().__init__('good')
        self.calls = []
    def realize(self, context):
        self.calls.append(context)
        return super().realize(context)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.graph = Graph()
        self.addCleanup(self.graph.db.close)

    def test_stops_at_construction_closure_before_any_prose(self):
        writer = ObservedWriter()
        result = execute(self.graph, 'Memory', Reasoner(), writer, ConstructionReviewer(),
                         ResearchBridge(Research(), 'support', 'challenge'), mode='fixture')
        self.assertEqual(result['state'], 'awaiting_construction_closure')
        self.assertFalse(writer.calls)
        self.assertEqual(len(result['research_report']['attempts']), 2)
        self.assertNotIn('run', result)
        report = inspect_execution(self.graph, result['id'])
        self.assertEqual(len(report['construction_review']['findings']), 3)
        self.assertEqual(report['binding_verification']['state'], 'unbound_fixture')

    def test_resume_requires_explicit_closure_and_separate_author_validation(self):
        writer = ObservedWriter()
        reviewer = ConstructionReviewer()
        result = execute(self.graph, 'Memory', Reasoner(), writer, reviewer, Research(), mode='fixture')
        engine = Execution(self.graph, Faculty(self.graph, Reasoner(), Research()),
                           Expression(self.graph, writer), Checking(self.graph, reviewer))
        with self.assertRaises(ValueError): engine.advance(result['id'])
        with self.assertRaises(PermissionError): engine.close_construction(result['id'], actor='agent')
        closed_construction = engine.close_construction(result['id'], actor='author')
        self.assertEqual(closed_construction['state'], 'ready')
        self.assertFalse(writer.calls)
        expression = engine.advance(result['id'])
        self.assertEqual(expression['state'], 'awaiting_approval')
        self.assertEqual(len(writer.calls), 1)
        self.assertEqual(engine.approve(result['id'], 'author')['state'], 'closed')
        self.assertEqual(len(inspect_execution(self.graph, result['id'])['draft']['sentences']), 1)

    def test_failed_research_suspends(self):
        class Broken:
            def search(self, question): raise OSError('offline')
        result = execute(self.graph, 'Memory', Reasoner(), ObservedWriter(), ConstructionReviewer(),
                         ResearchBridge(Broken(), 'support', 'challenge'), mode='fixture')
        self.assertEqual(result['state'], 'suspended_error')
        self.assertNotIn('run', result)

    def test_unbound_live_api_cannot_run(self):
        class UntouchedReasoner:
            def propose(self, context): raise AssertionError('Provider should not be called')
        with self.assertRaises(ValueError):
            execute(self.graph, 'Memory', UntouchedReasoner(), ObservedWriter(), ConstructionReviewer(), Research())

    def test_inspection_reports_stale_construction_without_writing(self):
        writer, reviewer = ObservedWriter(), ConstructionReviewer()
        result = execute(self.graph, 'Memory', Reasoner(), writer, reviewer, Research(), mode='fixture')
        engine = Execution(self.graph, Faculty(self.graph, Reasoner(), Research()),
                           Expression(self.graph, writer), Checking(self.graph, reviewer))
        engine.close_construction(result['id'], actor='author')
        plan = engine.f.inspect(result['plan'])
        self.graph.revise(plan['intent']['id'], {'text': 'Changed author intent'})
        before = self.graph.db.total_changes
        report = inspect_execution(self.graph, result['id'])
        self.assertEqual(report['execution']['state'], 'ready')
        self.assertEqual(report['current_state'], 'stale')
        self.assertEqual(self.graph.db.total_changes, before)

    def test_bound_text_reaches_constructor_with_source_hash(self):
        _, binding, root = fixture_binding(self, self.graph)
        sources = BoundSources(binding)
        seen = []
        class Capture(Reasoner):
            def propose(self, context):
                seen.append(context)
                return super().propose(context)
        faculty = Faculty(self.graph, Capture(), sources)
        faculty.build('Memory')
        evidence = seen[0]['evidence']['source0']
        self.assertEqual(evidence['text'], (root / 'source.txt').read_text())
        self.assertEqual(evidence['metadata']['sha256'], binding.inspect()['sources'][0]['sha256'])
        self.assertEqual(evidence['source'], str(root / 'source.txt'))

    def test_binary_source_rejected_before_constructor(self):
        _, binding, root = fixture_binding(self, self.graph)
        (root / 'source.txt').write_bytes(b'\xff\x00')
        # An unchanged binding also refuses the changed file before decoding.
        with self.assertRaises(ValueError): BoundSources(binding)

    def test_cli_invalid_configuration_never_calls_model_or_creates_database(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            database = Path(directory) / 'run.sqlite'
            config.write_text(json.dumps({'mode': 'live'}))
            with patch('providers.JSONModel._http') as transport, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    main(['start', '--config', str(config), '--database', str(database), '--live'])
            transport.assert_not_called()
            self.assertFalse(database.exists())

    def test_cli_inspection_is_read_only_and_uses_no_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.sqlite'
            graph = Graph(str(path))
            result = execute(graph, 'Memory', Reasoner(), ObservedWriter(), ConstructionReviewer(), Research(), mode='fixture')
            graph.db.close()
            before = path.read_bytes()
            with patch('providers.JSONModel._http') as transport, contextlib.redirect_stdout(io.StringIO()):
                report = main(['inspect', '--database', str(path), '--execution', result['id']])
            transport.assert_not_called()
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(report['execution']['state'], 'awaiting_construction_closure')

    def test_evaluation_cannot_start_without_committed_case_configs(self):
        import evaluate
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'evaluation'
            with patch('evaluate.subprocess.run') as process, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit): evaluate.main([str(destination), '--live'])
            process.assert_not_called()
            self.assertFalse(destination.exists())


if __name__ == '__main__': unittest.main()
