"""One-paragraph expression and revision-bound continuity fixtures; no live calls."""
import copy
import hashlib
import unittest

from checking import Checking, LAYERS
from editing import Editing
from expression import Expression
from faculty import Faculty
from model import Graph
from providers import SuppliedResearch
from test_construction_closure import close_fixture_plan


class ParagraphReasoner:
    def propose(self, context):
        return {
            'claims': [{'key': 'c' + str(i), 'text': 'Fixture hypothesis ' + str(i),
                        'origin': 'agent_hypothesis', 'evidence': ['intent']} for i in range(3)],
            'acts': [{'purpose': 'Explain fixture ' + str(i), 'claims': ['c' + str(i)]}
                     for i in range(3)],
        }


class ParagraphWriter:
    def __init__(self):
        self.calls = []
        self.callback = None
        self.mode = 'good'

    def realize(self, context):
        self.calls.append(copy.deepcopy(context))
        if self.callback:
            self.callback()
        if self.mode == 'two_paragraphs':
            return {'status': 'draft', 'sentences': [
                {'text': 'First paragraph.\n\nSecond paragraph.', 'acts': context['acts']}]}
        if self.mode == 'later_act':
            return {'status': 'draft', 'sentences': [
                {'text': 'A later act.', 'acts': [context['plan_acts'][-1]]}]}
        return {'status': 'draft', 'sentences': [
            {'text': '  Fixture sentence %d.  ' % (i + len(self.calls)), 'acts': [act]}
            for i, act in enumerate(context['acts'])]}


class ParagraphReviewer:
    def __init__(self):
        self.calls = []
        self.fail = None

    def assess(self, context):
        self.calls.append(copy.deepcopy(context))
        return [{'layer': layer, 'status': 'fail' if layer == self.fail else 'pass',
                 'reason': 'Fixture review only',
                 'sentences': [context['draft']['sentences'][0]['id']]}
                for layer in sorted(LAYERS)]


class ParagraphExpressionTests(unittest.TestCase):
    def setUp(self):
        self.g = Graph()
        self.addCleanup(self.g.db.close)
        self.faculty = Faculty(self.g, ParagraphReasoner(), SuppliedResearch())
        self.plan = self.faculty.build('Explain three fixture hypotheses in order')
        close_fixture_plan(self.faculty, self.plan)
        self.acts = self.faculty.c.snapshot(self.plan)['acts']
        self.writer = ParagraphWriter()
        self.expression = Expression(self.g, self.writer)
        self.reviewer = ParagraphReviewer()
        self.checking = Checking(self.g, self.reviewer)

    def scope(self, index=0, previous=None, acts=None):
        return {'id': 'fixture-paragraph-' + str(index), 'index': index,
                'acts': acts or [self.acts[index]], 'prior_paragraphs': previous or []}

    def first(self):
        run = self.expression.run(self.plan, paragraph=self.scope())
        assessment = self.checking.assess(run)
        return {'run': run, 'assessment': assessment,
                'text_sha256': self.expression.inspect(run)['text_sha256']}

    def test_only_current_paragraph_acts_generated_with_full_closed_graph(self):
        run = self.expression.run(self.plan, paragraph=self.scope())
        context = self.writer.calls[-1]
        self.assertEqual(context['acts'], [self.acts[0]])
        self.assertEqual(context['plan_acts'], self.acts)
        self.assertTrue(set(self.acts) <= set(context['nodes']))
        self.assertEqual(context['prior_paragraphs'], [])
        draft = self.expression.inspect(run)
        self.assertEqual(len(draft['sentences']), 1)
        self.assertEqual(draft['text'], 'Fixture sentence 1.')
        self.assertEqual(draft['text_sha256'], hashlib.sha256(b'Fixture sentence 1.').hexdigest())
        self.assertEqual(draft['input']['paragraph'], self.scope())
        assessment = self.checking.assess(run)
        self.assertEqual(self.checking.inspect(assessment)['state'], 'checks_passed')
        self.assertEqual(self.reviewer.calls[-1]['construction']['acts'], [self.acts[0]])
        self.assertEqual({finding['layer'] for finding in self.checking.inspect(assessment)['findings']}, LAYERS)

    def test_next_paragraph_receives_exact_prior_text_and_references(self):
        prior = self.first()
        scope = self.scope(1, [prior])
        run = self.expression.run(self.plan, paragraph=scope)
        context = self.writer.calls[-1]
        self.assertEqual(context['acts'], [self.acts[1]])
        self.assertEqual(context['prior_paragraphs'][0], {
            'id': 'fixture-paragraph-0', 'index': 0, 'acts': [self.acts[0]],
            **prior, 'text': self.expression.inspect(prior['run'])['text']})
        self.checking.assess(run)
        self.assertEqual(self.reviewer.calls[-1]['construction']['paragraph'], scope)
        self.assertEqual(self.reviewer.calls[-1]['construction']['prior_paragraphs'], context['prior_paragraphs'])
        self.assertNotIn('pangram', context)

    def test_two_paragraph_output_and_later_acts_rejected_atomically(self):
        for mode in ('two_paragraphs', 'later_act'):
            self.writer.mode = mode
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.expression.run(self.plan, paragraph=self.scope())
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM expression_run').fetchone()[0], 0)
        self.assertEqual(self.g.db.execute("SELECT count(*) FROM node WHERE kind='sentence'").fetchone()[0], 0)

    def test_invalid_scope_and_unchecked_prior_never_invoke_writer(self):
        invalid = [self.scope(acts=[self.acts[0], self.acts[2]]),
                   self.scope(acts=[self.acts[1]]),
                   self.scope(1), dict(self.scope(), detector_feedback='Do not pass this')]
        for scope in invalid:
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                self.expression.run(self.plan, paragraph=scope)
        self.assertEqual(self.writer.calls, [])
        prior_run = self.expression.run(self.plan, paragraph=self.scope())
        reference = {'run': prior_run, 'assessment': 'missing',
                     'text_sha256': self.expression.inspect(prior_run)['text_sha256']}
        with self.assertRaises(ValueError):
            self.expression.run(self.plan, paragraph=self.scope(1, [reference]))
        self.assertEqual(len(self.writer.calls), 1)

    def test_stale_prior_invalidates_following_expression_and_assessment(self):
        prior = self.first()
        run = self.expression.run(self.plan, paragraph=self.scope(1, [prior]))
        assessment = self.checking.assess(run)
        sentence = self.expression.inspect(prior['run'])['sentences'][0]
        self.g.revise(sentence['id'], dict(sentence['payload'], text='Changed prior fixture.'))
        self.assertEqual(self.expression.inspect(run)['state'], 'stale')
        self.assertEqual(self.checking.inspect(assessment)['state'], 'stale')
        with self.assertRaises(ValueError):
            self.checking.assess(run)

    def test_prior_change_during_provider_call_rejects_output(self):
        prior = self.first()
        sentence = self.expression.inspect(prior['run'])['sentences'][0]
        self.writer.callback = lambda: self.g.revise(sentence['id'], dict(sentence['payload'], text='Concurrent prior change.'))
        with self.assertRaises(ValueError):
            self.expression.run(self.plan, paragraph=self.scope(1, [prior]))
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM expression_run').fetchone()[0], 1)

    def test_editing_reuses_current_paragraph_scope_and_prior_context(self):
        prior = self.first()
        scope = self.scope(1, [prior])
        original = self.expression.run(self.plan, paragraph=scope)
        self.reviewer.fail = 'linguistic'
        assessment = self.checking.assess(original)
        edited = Editing(self.g, self.expression, self.checking).run(original, assessment, actor='author')
        context = self.writer.calls[-1]
        self.assertEqual(context['paragraph'], scope)
        self.assertEqual(context['acts'], [self.acts[1]])
        self.assertEqual(context['repair']['previous_run'], original)
        self.assertEqual(context['prior_paragraphs'][0]['run'], prior['run'])
        self.assertEqual(self.expression.inspect(edited)['input']['paragraph'], scope)
        self.assertEqual(len(self.expression.inspect(edited)['sentences']), 1)
        self.assertEqual(self.checking.inspect(prior['assessment'])['state'], 'checks_passed')

    def test_full_plan_fixture_mode_still_covers_all_acts(self):
        run = self.expression.run(self.plan)
        self.assertEqual(self.writer.calls[-1]['acts'], self.acts)
        self.assertNotIn('paragraph', self.writer.calls[-1])
        self.assertEqual(len(self.expression.inspect(run)['sentences']), 3)
        self.assertEqual(self.checking.inspect(self.checking.assess(run))['state'], 'checks_passed')


if __name__ == '__main__':
    unittest.main()
