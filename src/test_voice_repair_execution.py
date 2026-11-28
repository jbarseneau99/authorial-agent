"""Construction-owner repair progression with synthetic providers only."""
import copy
import unittest

from checking import Checking
from execution import Execution
from expression import Expression
from faculty import Faculty
from model import Graph
from providers import SuppliedResearch
from run_agent import validate_configuration
from test_paragraph_cli import live_configuration
from test_voice_resolution import ResolvedReasoner, SUBJECT_SOURCE, add_voice_fixture


class RepairReasoner(ResolvedReasoner):
    def __init__(self):
        super().__init__()
        self.repairs = []
        self.reopen = False

    def resolve_voice(self, context):
        self.repairs.append(copy.deepcopy(context))
        if self.reopen:
            return {'status': 'reopen', 'layer': 'rhetorical_plan',
                    'reason': 'This synthetic repair requires changing the act arrangement.'}
        acts = []
        for act in context['acts']:
            bindings = [{'rule_id': binding['rule_key'],
                         'exemplar_ids': list(binding['exemplar_keys']),
                         'layer': binding['layer'], 'application': binding['application'],
                         'criterion': binding['criterion']} for binding in act['voice_bindings']]
            acts.append({'id': act['id'], 'voice_bindings': bindings})
        acts[0]['voice_bindings'][0]['criterion'] = 'The first fixture relation appears directly without a preview.'
        return {'status': 'bindings', 'acts': acts}


class Reviewer:
    def __init__(self):
        self.calls = 0
        self.always_fail = False
        self.block = None

    def assess_construction(self, context):
        self.calls += 1
        result = [{'layer': layer, 'status': 'pass', 'reason': 'Synthetic passing construction criterion.'}
                  for layer in ['conceptual', 'epistemic', 'rhetorical_plan']]
        if self.calls == 1 or self.always_fail:
            result[-1].update(status='fail', reason='The first voice criterion does not test its stated application.')
        if self.block:
            result[0].update(status=self.block, reason='A substantive fixture issue requires separate review.')
        return result


class Writer:
    def __init__(self):
        self.calls = 0

    def realize(self, context):
        self.calls += 1
        raise AssertionError('Binding repair and construction review cannot generate prose')


class VoiceRepairExecutionTests(unittest.TestCase):
    def setUp(self):
        self.graph = Graph()
        self.addCleanup(self.graph.db.close)
        add_voice_fixture(self.graph)
        self.reasoner, self.reviewer, self.writer = RepairReasoner(), Reviewer(), Writer()
        self.faculty = Faculty(self.graph, self.reasoner,
                               SuppliedResearch([{'text': SUBJECT_SOURCE, 'source': 'fixture:subject'}]),
                               execution_profile='resolved-voice-v1')

    def engine(self, budget=2):
        return Execution(self.graph, self.faculty, Expression(self.graph, self.writer),
                         Checking(self.graph, self.reviewer), max_voice_repairs=budget)

    def test_repair_keeps_prior_plan_and_requires_fresh_review_then_explicit_closure(self):
        engine = self.engine()
        first = engine.start('Synthetic repair fixture', mode='fixture')
        self.assertEqual(first['state'], 'construction_review_required')
        original_plan = first['plan']
        original = self.faculty.c.snapshot(original_plan)
        with self.assertRaises(PermissionError):
            engine.repair_voice(first['id'])
        self.assertEqual(self.reasoner.repairs, [])
        result = engine.repair_voice(first['id'], actor='author')
        self.assertEqual(result['state'], 'awaiting_construction_closure')
        self.assertNotEqual(result['plan'], original_plan)
        self.assertEqual(result['voice_repair_attempts'], 1)
        self.assertEqual(self.faculty.c.snapshot(original_plan), original)
        self.assertIsNone(result['closure'])
        self.assertEqual(self.writer.calls, 0)
        with self.assertRaises(ValueError):
            engine.advance(first['id'])
        self.assertEqual(engine.close_construction(first['id'], actor='author')['state'], 'ready')

    def test_uncertainty_or_meaning_failure_cannot_enter_binding_only_repair(self):
        for status in ['fail', 'uncertain']:
            with self.subTest(status=status):
                self.reviewer.block = status
                engine = self.engine()
                first = engine.start('Blocked synthetic fixture', mode='fixture')
                with self.assertRaisesRegex(ValueError, 'meaning checks passed'):
                    engine.repair_voice(first['id'], actor='author')
        self.assertEqual(self.reasoner.repairs, [])
        self.assertEqual(self.writer.calls, 0)

    def test_budget_is_explicit_and_exhaustion_does_not_grant_closure(self):
        engine = self.engine(budget=0)
        first = engine.start('Disabled repair fixture', mode='fixture')
        with self.assertRaisesRegex(ValueError, 'budget'):
            engine.repair_voice(first['id'], actor='author')
        self.reviewer.calls = 0
        self.reviewer.always_fail = True
        engine = self.engine(budget=1)
        first = engine.start('Budgeted repair fixture', mode='fixture')
        result = engine.repair_voice(first['id'], actor='author')
        self.assertEqual(result['state'], 'construction_review_required')
        self.assertEqual(len(self.reasoner.repairs), 1)
        exhausted = engine.repair_voice(first['id'], actor='author')
        self.assertEqual(exhausted['state'], 'construction_review_required')
        self.assertIn('budget exhausted', exhausted['unresolved'])
        self.assertEqual(len(self.reasoner.repairs), 1)
        self.assertIsNone(exhausted['closure'])

    def test_wider_reopening_keeps_original_plan_unclosed(self):
        engine = self.engine()
        first = engine.start('Reopen fixture', mode='fixture')
        self.reasoner.reopen = True
        result = engine.repair_voice(first['id'], actor='author')
        self.assertEqual(result['state'], 'construction_review_required')
        self.assertEqual(result['route'], 'construction')
        self.assertEqual(result['plan'], first['plan'])
        self.assertEqual(result['unresolved']['layer'], 'rhetorical_plan')
        self.assertEqual(self.writer.calls, 0)

    def test_configuration_requires_resolved_profile_and_nonnegative_integer_budget(self):
        config = live_configuration()
        config.update(execution_profile='resolved-voice-v1', max_voice_repairs=2)
        self.assertEqual(validate_configuration(copy.deepcopy(config)), config)
        for value in [-1, True, 1.5, '2']:
            invalid = copy.deepcopy(config)
            invalid['max_voice_repairs'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_configuration(invalid)
        config.pop('execution_profile')
        with self.assertRaises(ValueError):
            validate_configuration(config)


if __name__ == '__main__':
    unittest.main()
