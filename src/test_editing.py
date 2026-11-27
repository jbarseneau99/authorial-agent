"""Fixture checks for feedback-bound repair; no live model or author validation."""
import copy
import unittest

from checking import Checking, LAYERS
from editing import Editing
from expression import Expression
from faculty import Faculty
from model import Graph
from test_faculty import Reasoner, Research


class ConstructionReviewer:
    def assess_construction(self, context):
        return [
            {'layer': layer, 'status': 'pass', 'reason': 'Fixture structural review'}
            for layer in ('conceptual', 'epistemic', 'rhetorical_plan')
        ]


class RecordingWriter:
    def __init__(self):
        self.calls = []
        self.action = None

    def realize(self, context):
        self.calls.append(copy.deepcopy(context))
        if self.action:
            self.action()
        return {
            'status': 'draft',
            'sentences': [
                {'text': 'Fixture expression %d.' % len(self.calls), 'acts': [act]}
                for act in context['acts']
            ],
        }


class Reviewer:
    def __init__(self, layer='linguistic', status='fail'):
        self.layer, self.status = layer, status

    def assess(self, context):
        sentence = context['draft']['sentences'][0]['id']
        return [
            {'layer': layer,
             'status': self.status if layer == self.layer else 'pass',
             'reason': 'Exact fixture finding for ' + layer,
             'sentences': [sentence]}
            for layer in sorted(LAYERS)
        ]


class EditingTests(unittest.TestCase):
    def setUp(self):
        self.g = Graph()
        self.addCleanup(self.g.db.close)
        self.faculty = Faculty(self.g, Reasoner(), Research())
        self.plan = self.faculty.build('Memory')
        review = self.faculty.review(self.plan, ConstructionReviewer())
        self.faculty.close(self.plan, review, actor='author')
        self.writer = RecordingWriter()
        self.expression = Expression(self.g, self.writer)
        self.original = self.expression.run(self.plan)
        self.checking = Checking(self.g, Reviewer())
        self.assessment = self.checking.assess(self.original)
        self.editing = Editing(self.g, self.expression, self.checking)

    def test_repair_receives_exact_draft_and_findings_without_overwrite(self):
        original = self.expression.inspect(self.original)
        findings = self.checking.inspect(self.assessment)['findings']
        new = self.editing.run(self.original, self.assessment, actor='author')
        self.assertNotEqual(new, self.original)
        self.assertEqual(self.expression.inspect(self.original), original)
        self.assertEqual(self.checking.inspect(self.assessment)['findings'], findings)
        context = self.writer.calls[-1]['repair']
        self.assertEqual(context['prior_draft'], original)
        self.assertEqual(context['findings'], findings)
        self.assertEqual(context['previous_run'], self.original)
        self.assertEqual(context['assessment'], self.assessment)
        self.assertEqual(context['affected_sentences'], [original['sentences'][0]['id']])
        self.assertTrue(context['affected_acts'])
        receipt = self.editing.inspect(context['editing_attempt'])
        self.assertEqual(receipt['input'], context)
        self.assertEqual(receipt['run'], new)
        self.assertEqual(receipt['state'], 'expression_returned')
        self.assertEqual(
            self.checking.inspect(self.assessment)['tickets'][0]['state'], 'authorized'
        )

    def test_requires_explicit_authority_before_any_call(self):
        count = len(self.writer.calls)
        with self.assertRaises(PermissionError):
            self.editing.run(self.original, self.assessment)
        with self.assertRaises(PermissionError):
            self.editing.run(self.original, self.assessment, actor='agent')
        self.assertEqual(len(self.writer.calls), count)
        self.assertEqual(
            self.checking.inspect(self.assessment)['tickets'][0]['state'], 'proposed'
        )

    def test_wrong_or_stale_assessment_never_invokes_writer(self):
        other = self.expression.run(self.plan)
        count = len(self.writer.calls)
        with self.assertRaises(ValueError):
            self.editing.run(other, self.assessment, actor='author')
        sentence = self.expression.inspect(self.original)['sentences'][0]['id']
        self.g.revise(sentence, {'text': 'Changed fixture'})
        with self.assertRaises(ValueError):
            self.editing.run(self.original, self.assessment, actor='author')
        self.assertEqual(len(self.writer.calls), count)

    def test_construction_and_uncertain_findings_cannot_be_edited(self):
        count = len(self.writer.calls)
        for layer, status in (
            ('epistemic', 'fail'), ('rhetorical', 'fail'),
            ('conceptual', 'fail'), ('linguistic', 'uncertain'),
        ):
            self.checking.reviewer = Reviewer(layer, status)
            assessment = self.checking.assess(self.original)
            with self.subTest(layer=layer, status=status), self.assertRaises(ValueError):
                self.editing.run(self.original, assessment, actor='author')
        self.assertEqual(len(self.writer.calls), count)

    def test_request_saved_before_invocation_and_failure_preserved(self):
        def fail():
            context = self.writer.calls[-1]['repair']
            receipt = self.editing.inspect(context['editing_attempt'])
            self.assertEqual(receipt['input'], context)
            self.assertEqual(receipt['state'], 'invocation_pending')
            raise RuntimeError('Provider detail must not enter the error receipt')
        self.writer.action = fail
        with self.assertRaises(RuntimeError):
            self.editing.run(self.original, self.assessment, actor='author')
        attempt = self.writer.calls[-1]['repair']['editing_attempt']
        receipt = self.editing.inspect(attempt)
        self.assertEqual(receipt['state'], 'unresolved')
        self.assertEqual(receipt['error_type'], 'RuntimeError')
        self.assertIsNone(receipt['run'])

    def test_prior_revision_changed_during_call_is_unresolved(self):
        sentence = self.expression.inspect(self.original)['sentences'][0]['id']
        self.writer.action = lambda: self.g.revise(sentence, {'text': 'Concurrent fixture'})
        with self.assertRaises(ValueError):
            self.editing.run(self.original, self.assessment, actor='author')
        attempt = self.writer.calls[-1]['repair']['editing_attempt']
        receipt = self.editing.inspect(attempt)
        self.assertEqual(receipt['state'], 'unresolved')
        self.assertIsNotNone(receipt['run'])
        self.assertEqual(self.checking.inspect(self.assessment)['state'], 'stale')


if __name__ == '__main__':
    unittest.main()
