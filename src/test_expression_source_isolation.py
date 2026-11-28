"""Subject-source isolation at the writer boundary; synthetic fixtures only."""
import copy
import hashlib
import json
import unittest

from checking import Checking, LAYERS
from editing import Editing
from expression import Expression
from faculty import Faculty
from model import Graph, Kind
from providers import SuppliedResearch
from test_helpers import close_fixture_plan


SUBJECT = 'SUBJECT-SOURCE-ONLY: The original manuscript wording must not be a rewrite prompt.'
EXEMPLAR = 'VOICE-EXACT: I would examine the evidence before making that claim.'
CLAIM = 'The fixture claim preserves the source proposition in constructed form.'


class Reasoner:
    def propose(self, context):
        self.context = copy.deepcopy(context)
        return {'claims': [{'key': 'c1', 'text': CLAIM, 'origin': 'external',
                            'evidence': ['source0']}],
                'acts': [{'purpose': 'Explain the bounded fixture claim', 'claims': ['c1']}]}


class Writer:
    def __init__(self):
        self.calls = []
        self.serialized_requests = []

    def realize(self, context):
        self.calls.append(copy.deepcopy(context))
        self.serialized_requests.append(json.dumps(context, sort_keys=True))
        return {'status': 'draft', 'sentences': [
            {'text': 'Fixture expression attempt %d.' % len(self.calls), 'acts': context['acts']}]}


class Reviewer:
    def __init__(self):
        self.calls = []
        self.linguistic_failure = False

    def assess(self, context):
        self.calls.append(copy.deepcopy(context))
        return [{'layer': layer,
                 'status': 'fail' if layer == 'linguistic' and self.linguistic_failure else 'pass',
                 'reason': 'Fixture finding on this exact expression',
                 'sentences': [context['draft']['sentences'][0]['id']]}
                for layer in sorted(LAYERS)]


class ExpressionSourceIsolationTests(unittest.TestCase):
    def setUp(self):
        self.graph = Graph()
        self.addCleanup(self.graph.db.close)
        transcript = self.graph.add(Kind.EVIDENCE, {
            'Source ID': 'voice-fixture', 'User transcript (segments joined)': EXEMPLAR})
        exemplar = self.graph.add(Kind.EVIDENCE, {
            'Source ID': 'voice-fixture', 'Exemplar type': 'Original spoken',
            'Exact excerpt': EXEMPLAR, 'Written validation': 'Not validated for writing'})
        rule = self.graph.add(Kind.RULE, {
            'Candidate rule': 'Preserve evidence qualifications', 'activation': 'candidate_only'})
        self.graph.link(exemplar, 'derived_from', transcript)
        self.graph.link(rule, 'grounded_in', exemplar)
        self.reasoner = Reasoner()
        research = SuppliedResearch([{'text': SUBJECT, 'source': 'fixture-subject.md',
                                     'metadata': {'fixture': True}}])
        self.faculty = Faculty(self.graph, self.reasoner, research)
        self.plan = self.faculty.build('Express one fixture claim using its source for content only')
        close_fixture_plan(self.faculty, self.plan)
        self.before = self.faculty.c.snapshot(self.plan)
        self.serialized_before = json.loads(json.dumps(self.before))
        self.source_id = next(ident for ident, record in self.before['nodes'].items()
                              if record['node']['payload'].get('origin') == 'retrieved_unverified')
        self.writer = Writer()
        self.expression = Expression(self.graph, self.writer)
        self.reviewer = Reviewer()
        self.checking = Checking(self.graph, self.reviewer)
        self.scope = {'id': 'fixture-paragraph', 'index': 0,
                      'acts': self.before['acts'], 'prior_paragraphs': []}

    def assert_writer_isolation(self, context):
        serialized = json.dumps(context, sort_keys=True)
        self.assertNotIn(SUBJECT, serialized)
        self.assertIn(CLAIM, serialized)
        self.assertIn(EXEMPLAR, serialized)
        self.assertEqual(context['voice_evidence'], self.serialized_before['voice_evidence'])
        self.assertEqual(context['authentic_exemplars'], self.serialized_before['authentic_exemplars'])
        self.assertEqual(context['voice_candidates'], self.serialized_before['voice_candidates'])
        self.assertEqual(context['acts'], self.before['acts'])
        source = context['nodes'][self.source_id]
        self.assertEqual(source['edges'], self.before['nodes'][self.source_id]['edges'])
        self.assertEqual(source['node']['id'], self.source_id)
        self.assertEqual(source['node']['payload']['source'], 'fixture-subject.md')
        self.assertEqual(source['node']['payload']['metadata'], {'fixture': True})
        self.assertEqual(source['node']['payload']['text_sha256'],
                         hashlib.sha256(SUBJECT.encode('utf-8')).hexdigest())
        self.assertNotIn('text', source['node']['payload'])

    def test_initial_writer_omits_subject_body_but_checker_and_graph_keep_it(self):
        run = self.expression.run(self.plan, paragraph=self.scope)
        self.assert_writer_isolation(self.writer.calls[-1])
        self.assertNotIn(SUBJECT, self.writer.serialized_requests[-1])
        self.assertIn(SUBJECT, json.dumps(self.reasoner.context))
        self.assertEqual(self.faculty.c.snapshot(self.plan), self.before)
        self.checking.assess(run)
        self.assertIn(SUBJECT, json.dumps(self.reviewer.calls[-1]))
        self.assertEqual(self.reviewer.calls[-1]['construction']['nodes'][self.source_id],
                         self.before['nodes'][self.source_id])
        self.assertIn(SUBJECT, json.dumps(self.expression.inspect(run)['input']))

    def test_linguistic_repair_projects_nested_source_without_altering_evidence(self):
        original = self.expression.run(self.plan, paragraph=self.scope)
        original_record = self.expression.inspect(original)
        self.reviewer.linguistic_failure = True
        assessment = self.checking.assess(original)
        findings = copy.deepcopy(self.checking.inspect(assessment)['findings'])
        editing = Editing(self.graph, self.expression, self.checking)
        revised = editing.run(original, assessment, actor='author')
        context = self.writer.calls[-1]
        self.assert_writer_isolation(context)
        self.assertTrue(all(SUBJECT not in request for request in self.writer.serialized_requests))
        repair = context['repair']
        self.assertNotIn('text', repair['prior_draft']['input']['nodes'][self.source_id]['node']['payload'])
        self.assertEqual(repair['prior_draft']['text'], original_record['text'])
        self.assertEqual(repair['findings'], findings)
        self.assertEqual(repair['affected_sentences'], [original_record['sentences'][0]['id']])
        self.assertTrue(repair['affected_acts'])
        self.assertEqual(self.expression.inspect(original), original_record)
        self.assertEqual(self.faculty.c.snapshot(self.plan), self.before)
        self.assertIn(SUBJECT, json.dumps(editing.inspect(repair['editing_attempt'])['input']))
        self.reviewer.linguistic_failure = False
        self.checking.assess(revised)
        self.assertIn(SUBJECT, json.dumps(self.reviewer.calls[-1]))

    def test_omitted_source_revision_still_invalidates_closure_and_blocks_writer(self):
        run = self.expression.run(self.plan, paragraph=self.scope)
        calls = len(self.writer.calls)
        source = self.graph.get(self.source_id)
        self.graph.revise(self.source_id, dict(source['payload'], text=SUBJECT + ' Changed.'))
        self.assertEqual(self.expression.inspect(run)['state'], 'stale')
        with self.assertRaises(ValueError):
            self.expression.run(self.plan, paragraph=self.scope)
        self.assertEqual(len(self.writer.calls), calls)


if __name__ == '__main__':
    unittest.main()
