"""Coordinator gates and recovery behavior; all providers are test fixtures."""
import copy
import sqlite3
import unittest

from model import Graph
from faculty import Faculty
from expression import Expression
from checking import Checking
from execution import Execution
from test_faculty import Reasoner, Research
from test_expression import Writer
from test_checking import Reviewer
from test_helpers import FixtureConstructionReviewer
from providers import JSONModel
from run_binding import ProviderJournal
from test_run_binding import CONFIGURATION, fixture_binding


class CountedReasoner(Reasoner):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def propose(self, context):
        self.calls += 1
        return super().propose(context)


class CountedWriter(Writer):
    def __init__(self):
        super().__init__('good')
        self.calls = []

    def realize(self, context):
        self.calls.append(copy.deepcopy(context))
        return super().realize(context)


class PipelineReviewer(Reviewer, FixtureConstructionReviewer):
    pass


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.g = Graph()
        self.addCleanup(self.g.db.close)

    def engine(self, fail=None, reviewer=None):
        return Execution(
            self.g, Faculty(self.g, CountedReasoner(), Research()),
            Expression(self.g, CountedWriter()),
            Checking(self.g, reviewer or PipelineReviewer(fail)),
        )

    def ready(self, engine, max_attempts=3):
        started = engine.start('Memory', max_attempts, mode='fixture')
        self.assertEqual(started['state'], 'awaiting_construction_closure')
        return engine.close_construction(started['id'], actor='author')

    def test_unbound_live_run_stops_before_any_provider(self):
        engine = self.engine()
        with self.assertRaises(ValueError):
            engine.start('Memory')
        self.assertEqual(engine.f.reasoner.calls, 0)
        self.assertEqual(engine.e.writer.calls, [])
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM execution').fetchone()[0], 0)

    def bound_engine(self):
        _, binding, _ = fixture_binding(self, graph=self.g)
        providers = {
            role: JSONModel(**CONFIGURATION, transport=lambda request: None,
                            journal=ProviderJournal(self.g, binding, role))
            for role in ('construction', 'expression', 'checking')
        }
        engine = Execution(
            self.g, Faculty(self.g, providers['construction'], Research(),
                            baseline_digest=binding.inspect()['ledger']['sha256']),
            Expression(self.g, providers['expression']), Checking(self.g, providers['checking']),
            binding=binding,
        )
        return engine, providers

    def test_bound_workers_must_use_same_binding_and_role(self):
        engine, providers = self.bound_engine()
        current = {'binding_id': engine.binding.id, 'mode': 'fixture'}
        engine._binding_current(current)
        _, other, _ = fixture_binding(self, graph=self.g)
        original = providers['expression'].journal
        providers['expression'].journal = ProviderJournal(self.g, other, 'expression')
        with self.assertRaises(ValueError):
            engine.start('Memory', mode='fixture')
        providers['expression'].journal = ProviderJournal(self.g, engine.binding, 'construction')
        with self.assertRaises(ValueError):
            engine._binding_current(current)
        providers['expression'].journal = original
        providers['expression'].model = 'undeclared-model'
        with self.assertRaises(ValueError):
            engine._binding_current(current)
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM provider_invocation').fetchone()[0], 0)
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM execution').fetchone()[0], 0)

    def test_bound_run_rejects_unjournaled_worker_and_wrong_ledger(self):
        engine, providers = self.bound_engine()
        engine.f.reasoner = CountedReasoner()
        with self.assertRaises(ValueError):
            engine.start('Memory', mode='fixture')
        self.assertEqual(engine.f.reasoner.calls, 0)
        engine.f.reasoner = providers['construction']
        engine.f.baseline_digest = 'a-different-ledger'
        with self.assertRaises(ValueError):
            engine.start('Memory', mode='fixture')
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM provider_invocation').fetchone()[0], 0)
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM execution').fetchone()[0], 0)

    def test_bound_construction_review_cannot_override_declared_provider(self):
        engine, _ = self.bound_engine()
        class UndeclaredReviewer(FixtureConstructionReviewer):
            calls = 0
            def assess_construction(self, context):
                self.calls += 1
                return super().assess_construction(context)
        reviewer = UndeclaredReviewer()
        with self.assertRaisesRegex(ValueError, 'declared checking provider'):
            engine.review_construction('unused-execution-id', reviewer)
        self.assertEqual(reviewer.calls, 0)

    def test_construction_requires_review_and_explicit_closure(self):
        engine = self.engine()
        started = engine.start('Memory', mode='fixture')
        self.assertEqual(started['state'], 'awaiting_construction_closure')
        self.assertEqual(engine.e.writer.calls, [])
        self.assertEqual(started['mode'], 'fixture')
        self.assertEqual(started['active_loop'], 'construction')
        self.assertEqual(started['loop_owner'], 'src/faculty.py')
        with self.assertRaises(ValueError):
            engine.advance(started['id'])
        with self.assertRaises(PermissionError):
            engine.close_construction(started['id'])
        with self.assertRaises(PermissionError):
            engine.close_construction(started['id'], actor='agent')
        ready = engine.close_construction(started['id'], actor='author')
        self.assertEqual(ready['state'], 'ready')
        self.assertEqual(engine.e.writer.calls, [])

    def test_separate_reviewer_can_close_an_unreviewed_fixture(self):
        engine = self.engine(reviewer=Reviewer())
        started = engine.start('Memory', mode='fixture')
        self.assertEqual(started['state'], 'awaiting_construction_review')
        reviewed = engine.review_construction(started['id'], FixtureConstructionReviewer())
        self.assertEqual(reviewed['state'], 'awaiting_construction_closure')
        self.assertEqual(engine.e.writer.calls, [])

    def test_failed_construction_review_cannot_reach_expression(self):
        class Failed(PipelineReviewer):
            def assess_construction(self, context):
                findings = super().assess_construction(context)
                findings[1]['status'] = 'uncertain'
                return findings
        engine = self.engine(reviewer=Failed())
        started = engine.start('Memory', mode='fixture')
        self.assertEqual(started['state'], 'construction_review_required')
        with self.assertRaises(ValueError):
            engine.close_construction(started['id'], actor='author')
        with self.assertRaises(ValueError):
            engine.advance(started['id'])
        self.assertEqual(engine.e.writer.calls, [])

    def test_all_checks_pass_still_requires_author_validation(self):
        engine = self.engine()
        ready = self.ready(engine)
        result = engine.advance(ready['id'])
        self.assertEqual(result['state'], 'awaiting_approval')
        self.assertEqual(result['active_loop'], 'validation')
        self.assertNotIn('approved_by', result)
        with self.assertRaises(PermissionError):
            engine.approve(result['id'], 'agent')
        approved = engine.approve(result['id'], 'author')
        self.assertEqual(approved['state'], 'closed')
        self.assertEqual(approved['closure_authority'], 'author')
        self.assertEqual(approved['mode'], 'fixture')

    def test_targeted_retry_receives_findings_and_budget_never_closes(self):
        engine = self.engine('linguistic')
        ready = self.ready(engine, max_attempts=2)
        first = engine.advance(ready['id'])
        self.assertEqual(first['state'], 'suspended_reopen')
        original = engine.e.inspect(first['run'])
        findings = engine.c.inspect(first['assessment'])['findings']
        with self.assertRaises(PermissionError):
            engine.advance(first['id'])
        second = engine.advance(first['id'], actor='author')
        self.assertNotEqual(first['run'], second['run'])
        repair = engine.e.writer.calls[-1]['repair']
        self.assertEqual(repair['previous_run'], first['run'])
        self.assertEqual(repair['prior_draft'], original)
        self.assertEqual(repair['findings'], findings)
        self.assertEqual(engine.e.inspect(first['run']), original)
        exhausted = engine.advance(first['id'], actor='author')
        self.assertEqual(exhausted['state'], 'budget_exhausted')
        self.assertEqual(exhausted['attempts'], 2)
        self.assertEqual(len(engine.e.writer.calls), 2)
        self.assertNotIn('approved_by', exhausted)
        with self.assertRaises(ValueError):
            engine.approve(first['id'], 'author')

    def test_intellectual_failure_cannot_enter_expression_repair(self):
        engine = self.engine('epistemic')
        ready = self.ready(engine)
        result = engine.advance(ready['id'])
        self.assertEqual(result['route'], 'construction')
        with self.assertRaises(ValueError):
            engine.advance(result['id'], actor='author')
        self.assertEqual(len(engine.e.writer.calls), 1)

    def test_stale_expression_cannot_be_approved(self):
        engine = self.engine()
        ready = self.ready(engine)
        result = engine.advance(ready['id'])
        sentence = engine.e.inspect(result['run'])['sentences'][0]['id']
        self.g.revise(sentence, {'text': 'Changed fixture'})
        self.assertEqual(engine.inspect(result['id'])['state'], 'stale')
        with self.assertRaises(ValueError):
            engine.approve(result['id'], 'author')

    def test_changed_construction_blocks_first_expression(self):
        engine = self.engine()
        ready = self.ready(engine)
        intent = engine.f.inspect(ready['plan'])['intent']['id']
        self.g.revise(intent, {'text': 'Changed fixture intent'})
        self.assertEqual(engine.inspect(ready['id'])['state'], 'stale')
        with self.assertRaises(ValueError):
            engine.advance(ready['id'])
        self.assertEqual(engine.e.writer.calls, [])

    def test_checkpoint_history_is_preserved_and_append_only(self):
        engine = self.engine()
        started = engine.start('Memory', mode='fixture')
        earlier = engine.history(started['id'])
        engine.close_construction(started['id'], actor='author')
        result = engine.advance(started['id'])
        history = engine.history(started['id'])
        self.assertEqual(history[:len(earlier)], earlier)
        self.assertEqual([r['revision'] for r in history], list(range(1, len(history) + 1)))
        self.assertEqual(history[-1]['state'], result['state'])
        for sql in (
            'UPDATE execution_revision SET data=data WHERE execution_id=?',
            'DELETE FROM execution_revision WHERE execution_id=?',
        ):
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                with self.g.db:
                    self.g.db.execute(sql, (started['id'],))
        self.assertEqual(engine.history(started['id']), history)


if __name__ == '__main__':
    unittest.main()
