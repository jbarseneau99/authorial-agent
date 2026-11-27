"""Fixture tests for closure enforcement; no live or voice-quality claims."""
import copy
import json
import unittest
from construction import CONSTRUCTION_LAYERS
from expression import Expression
from faculty import Faculty
from model import Graph, Kind
from providers import SuppliedResearch


class ClosureReasoner:
    def __init__(self):
        self.context = None

    def propose(self, context):
        self.context = copy.deepcopy(context)
        return {'claims': [{'key': 'c1', 'text': 'A clearly marked fixture hypothesis',
                            'origin': 'agent_hypothesis', 'evidence': ['intent']}],
                'acts': [{'purpose': 'Qualify the fixture hypothesis', 'claims': ['c1']}]}


class ClosureReviewer:
    def __init__(self, status='pass'):
        self.status = status

    def assess_construction(self, context):
        return [{'layer': layer, 'status': self.status,
                 'reason': 'Fixture judgment only; no truth certification.'}
                for layer in sorted(CONSTRUCTION_LAYERS)]


class ClosureWriter:
    def __init__(self):
        self.calls = []

    def realize(self, context):
        self.calls.append(copy.deepcopy(context))
        return {'status': 'draft', 'sentences': [{'text': 'A fixture hypothesis remains uncertain.',
                                                 'acts': context['acts']}]}


def close_fixture_plan(faculty, plan):
    """Explicit trusted-host author authorization, limited to synthetic fixtures."""
    review = faculty.review(plan, ClosureReviewer())
    return faculty.close(plan, review, 'author')


class ConstructionClosureTests(unittest.TestCase):
    def setUp(self):
        self.g = Graph()
        self.addCleanup(self.g.db.close)
        self.reasoner = ClosureReasoner()
        self.f = Faculty(self.g, self.reasoner, SuppliedResearch())
        self.writer = ClosureWriter()
        self.e = Expression(self.g, self.writer)

    def add_voice_fixture(self):
        source = self.g.add(Kind.EVIDENCE, {'Source ID': 'fixture-source',
                                          'User transcript (segments joined)': 'I would examine the evidence before making that claim.'})
        exemplar = self.g.add(Kind.EVIDENCE, {'Exemplar ID': 'fixture-exemplar',
                                             'Source ID': 'fixture-source',
                                             'Exemplar type': 'Original spoken',
                                             'Exact excerpt': 'I would examine the evidence',
                                             'Written validation': 'Not validated for writing'})
        rule = self.g.add(Kind.RULE, {'Rule ID': 'fixture-rule',
                                     'Candidate rule': 'Consider evidence before assertion',
                                     'activation': 'candidate_only'})
        self.g.link(exemplar, 'derived_from', source)
        self.g.link(rule, 'grounded_in', exemplar)
        return source, exemplar, rule

    def test_unclosed_and_provider_pass_cannot_reach_writer(self):
        plan = self.f.build('Consider the fixture hypothesis')
        with self.assertRaisesRegex(ValueError, 'not closed'):
            self.e.run(plan)
        review = self.f.review(plan, ClosureReviewer())
        self.assertEqual(self.f.inspect_review(review)['state'], 'checks_passed')
        with self.assertRaisesRegex(ValueError, 'not closed'):
            self.e.run(plan)
        with self.assertRaises(PermissionError):
            self.f.close(plan, review, 'model')
        self.assertEqual(self.writer.calls, [])
        closure = self.f.close(plan, review, 'author')
        result = self.e.inspect(self.e.run(plan))
        self.assertEqual(result['state'], 'draft_unvalidated')
        self.assertEqual(result['input']['construction_closure']['id'], closure)
        self.assertFalse(self.f.inspect(plan)['acts'][0]['claims'][0]['payload']['verified'])

    def test_failed_or_uncertain_review_prevents_closure(self):
        for status in ('fail', 'uncertain'):
            with self.subTest(status=status):
                plan = self.f.build('Consider the fixture hypothesis')
                review = self.f.review(plan, ClosureReviewer(status))
                with self.assertRaisesRegex(ValueError, 'passing construction review'):
                    self.f.close(plan, review, 'author')
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM construction_closure').fetchone()[0], 0)

    def test_review_shape_and_changed_input_are_rejected_atomically(self):
        plan = self.f.build('Consider the fixture hypothesis')
        class MissingLayer:
            def assess_construction(self, context):
                return ClosureReviewer().assess_construction(context)[:2]
        with self.assertRaises(ValueError):
            self.f.review(plan, MissingLayer())
        outer = self
        class ChangesIntent:
            def assess_construction(self, context):
                outer.g.revise(context['intent'], {'text': 'Changed during review'})
                return ClosureReviewer().assess_construction(context)
        with self.assertRaises(ValueError):
            self.f.review(plan, ChangesIntent())
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM construction_review').fetchone()[0], 0)

    def test_intent_evidence_and_plan_order_changes_invalidate_closure(self):
        for change in ('intent', 'evidence', 'plan'):
            with self.subTest(change=change):
                plan = self.f.build('Consider the fixture hypothesis')
                close_fixture_plan(self.f, plan)
                draft = self.e.run(plan)
                snapshot = self.f.c.snapshot(plan)
                if change == 'plan':
                    with self.g.db:
                        self.g.db.execute('UPDATE construction_plan SET acts=? WHERE id=?', ('[]', plan))
                else:
                    ident = snapshot['intent'] if change == 'intent' else next(
                        key for key, value in snapshot['nodes'].items() if value['node']['kind'] == 'evidence')
                    self.g.revise(ident, {'text': 'Revised fixture input'})
                with self.assertRaises(ValueError):
                    self.e.run(plan)
                self.assertEqual(self.e.inspect(draft)['state'], 'stale')

    def test_rule_source_and_exemplar_changes_invalidate_closure(self):
        for change in (0, 1, 2):
            with self.subTest(change=change):
                graph = Graph()
                self.addCleanup(graph.db.close)
                previous = self.g
                self.g = graph
                source, exemplar, rule = self.add_voice_fixture()
                self.g = previous
                faculty = Faculty(graph, ClosureReasoner(), SuppliedResearch())
                plan = faculty.build('Consider the fixture hypothesis')
                close_fixture_plan(faculty, plan)
                expression = Expression(graph, ClosureWriter())
                draft = expression.run(plan)
                ident = (source, exemplar, rule)[change]
                graph.revise(ident, dict(graph.get(ident)['payload'], revision_note='Changed fixture'))
                with self.assertRaises(ValueError):
                    expression.run(plan)
                self.assertEqual(expression.inspect(draft)['state'], 'stale')

    def test_source_grounding_reaches_every_provider_without_activation(self):
        source, exemplar, rule = self.add_voice_fixture()
        plan = self.f.build('Consider the fixture hypothesis')
        close_fixture_plan(self.f, plan)
        expression = self.e.context(plan)
        review = self.f.c.snapshot(plan)
        for context in (self.reasoner.context, expression, review):
            self.assertEqual(context['authentic_exemplars'][0]['id'], exemplar)
            self.assertEqual(context['authentic_exemplars'][0]['sources'][0]['id'], source)
            self.assertEqual(context['voice_candidates'][0]['authority'], 'advisory_only')
            self.assertEqual(context['voice_candidates'][0]['payload']['activation'], 'candidate_only')
            self.assertIn(rule, context['voice_evidence'])
            self.assertIn('per_act_relevance_not_assessed', context['selection_status'])
        self.assertEqual(self.reasoner.context['authentic_exemplars'], expression['authentic_exemplars'])

    def test_unmatched_spoken_excerpt_rejected(self):
        source, exemplar, rule = self.add_voice_fixture()
        payload = self.g.get(exemplar)['payload']
        self.g.revise(exemplar, dict(payload, **{'Exact excerpt': 'This was not in the source'}))
        # Build a fresh candidate rule because revising evidence stales dependents.
        new_rule = self.g.add(Kind.RULE, {'activation': 'candidate_only'})
        self.g.link(new_rule, 'grounded_in', exemplar)
        faculty = Faculty(self.g, ClosureReasoner(), SuppliedResearch(), rule_ids=[new_rule])
        with self.assertRaisesRegex(ValueError, 'does not match'):
            faculty.build('Consider the fixture hypothesis')
        self.assertIsNone(faculty.reasoner.context)

    def test_experiment_not_promoted_to_authentic_exemplar(self):
        rule = self.g.add(Kind.RULE, {'activation': 'candidate_only'})
        experiment = self.g.add(Kind.EVIDENCE, {'Prototype': 'fixture', 'Author validation': 'Unknown'})
        self.g.link(rule, 'grounded_in', experiment)
        faculty = Faculty(self.g, ClosureReasoner(), SuppliedResearch(), rule_ids=[rule])
        faculty.build('Consider the fixture hypothesis')
        self.assertEqual(faculty.reasoner.context['authentic_exemplars'], [])
        self.assertIn(experiment, faculty.reasoner.context['voice_evidence'])

    def test_explicit_rule_selection_excludes_unselected_rule(self):
        _, exemplar, rule = self.add_voice_fixture()
        extra = self.g.add(Kind.RULE, {'activation': 'candidate_only', 'text': 'Unselected'})
        faculty = Faculty(self.g, ClosureReasoner(), SuppliedResearch(), rule_ids=[rule])
        plan = faculty.build('Consider the fixture hypothesis')
        context = faculty.c.snapshot(plan)
        self.assertEqual([r['id'] for r in context['voice_candidates']], [rule])
        self.assertNotIn(extra, context['voice_evidence'])
        self.assertIn(exemplar, context['voice_evidence'])

    def test_repair_context_preserved_and_original_not_overwritten(self):
        plan = self.f.build('Consider the fixture hypothesis')
        close_fixture_plan(self.f, plan)
        original = self.e.run(plan)
        repair = {'prior_run': original, 'findings': [{'reason': 'Fixture wording repair'}]}
        revised = self.e.run(plan, repair=repair)
        repair['findings'][0]['reason'] = 'Caller mutation'
        self.assertNotIn('repair', self.e.inspect(original)['input'])
        self.assertEqual(self.e.inspect(revised)['input']['repair']['findings'][0]['reason'], 'Fixture wording repair')
        self.assertNotEqual(original, revised)
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM expression_input').fetchone()[0], 2)

    def test_forged_state_without_witness_and_later_failure_block_expression(self):
        plan = self.f.build('Consider the fixture hypothesis')
        with self.g.db:
            self.g.db.execute("UPDATE construction_plan SET state='closed' WHERE id=?", (plan,))
        with self.assertRaisesRegex(ValueError, 'missing or stale'):
            self.e.run(plan)
        valid = self.f.build('Consider another fixture hypothesis')
        close_fixture_plan(self.f, valid)
        self.f.review(valid, ClosureReviewer('fail'))
        with self.assertRaisesRegex(ValueError, 'not closed'):
            self.e.run(valid)


if __name__ == '__main__':
    unittest.main()
