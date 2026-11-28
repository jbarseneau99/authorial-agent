"""Synthetic construction voice-resolution fixtures; no live prose or calls."""
import copy
import hashlib
import json
import unittest

from faculty import Faculty
from expression import Expression
from model import Graph, Kind
from providers import SuppliedResearch
from test_construction_closure import ClosureReviewer, close_fixture_plan
from voice_resolution import PROFILE, validate_written_calibration


TRANSCRIPT = 'Synthetic fixture transcript: a claim needs its stated reason.'
SUBJECT_SOURCE = 'Synthetic subject evidence, distinct from the voice transcript.'


def add_voice_fixture(graph):
    source = graph.add(Kind.EVIDENCE, {'Source ID': 'S001',
                                      'User transcript (segments joined)': TRANSCRIPT})
    exemplar = graph.add(Kind.EVIDENCE, {'Exemplar ID': 'E001', 'Source ID': 'S001',
                                        'Exemplar type': 'Original spoken',
                                        'Exact excerpt': 'a claim needs its stated reason',
                                        'Layer': 'Linguistic',
                                        'Written validation': 'Not validated for writing'})
    rule = graph.add(Kind.RULE, {'Rule ID': 'R001', 'Layer': 'Linguistic; rhetorical',
                                 'Candidate rule': 'State the fixture relation directly',
                                 'Status': 'Unconfirmed', 'activation': 'candidate_only'})
    graph.link(exemplar, 'derived_from', source)
    graph.link(rule, 'grounded_in', exemplar)
    return {'source': source, 'exemplar': exemplar, 'rule': rule}


def calibration_fixture():
    text = 'Generated calibration fixture approved for this passage only.'
    return [{'id': 'calibration-fixture', 'source_path': 'fixture:approved-passage',
             'sha256': hashlib.sha256(text.encode()).hexdigest(), 'text': text,
             'authority': 'generated_author_approved_passage', 'scope': 'passage_only',
             'author_judgment': 'Synthetic fixture approval, not an actual author judgment.'}]


class ResolvedReasoner:
    def __init__(self, mutation=None):
        self.context = None
        self.mutation = mutation

    def propose(self, context):
        self.context = copy.deepcopy(context)
        binding = {'rule_id': 'R001', 'exemplar_ids': ['E001'], 'layer': 'linguistic',
                   'application': 'Realize the fixture claim through a direct relation.',
                   'criterion': 'The expression states the fixture relation without announcing the act.'}
        result = {'claims': [{'key': 'c1', 'text': 'A synthetic source claim',
                              'origin': 'external', 'evidence': ['source0']}],
                  'acts': [{'purpose': 'Introduce the synthetic claim', 'claims': ['c1'],
                            'voice_bindings': [copy.deepcopy(binding)]},
                           {'purpose': 'Distinguish the synthetic claim', 'claims': ['c1'],
                            'voice_bindings': [copy.deepcopy(binding)]}]}
        if self.mutation:
            self.mutation(result)
        return result


class CapturingReviewer(ClosureReviewer):
    def assess_construction(self, context):
        self.context = copy.deepcopy(context)
        return super().assess_construction(context)


class VoiceResolutionTests(unittest.TestCase):
    def setUp(self):
        self.graph = Graph()
        self.addCleanup(self.graph.db.close)
        self.ids = add_voice_fixture(self.graph)

    def faculty(self, reasoner=None, calibration=None):
        return Faculty(self.graph, reasoner or ResolvedReasoner(),
                       SuppliedResearch([{'text': SUBJECT_SOURCE, 'source': 'fixture:subject'}]),
                       execution_profile=PROFILE, written_calibration=calibration)

    def test_each_act_resolves_human_keys_to_grounded_graph_ids(self):
        faculty = self.faculty()
        plan = faculty.build('Construct the synthetic fixture')
        snapshot = faculty.c.snapshot(plan)
        self.assertEqual(len(snapshot['acts']), 2)
        for ident in snapshot['acts']:
            binding = snapshot['nodes'][ident]['node']['payload']['voice_bindings'][0]
            self.assertEqual(binding['rule_id'], self.ids['rule'])
            self.assertEqual(binding['rule_key'], 'R001')
            self.assertEqual(binding['exemplar_ids'], [self.ids['exemplar']])
            self.assertEqual(binding['exemplar_keys'], ['E001'])
            self.assertIn(( 'applies', self.ids['rule']), self.graph.prerequisites(ident))
        self.assertEqual(self.graph.get(self.ids['rule'])['payload']['activation'], 'candidate_only')
        self.assertEqual(snapshot['execution_profile'], PROFILE)

    def test_bad_selection_is_rejected_before_graph_mutation(self):
        def edit(field, value):
            return lambda result: result['acts'][0]['voice_bindings'][0].update({field: value})
        mutations = [edit('rule_id', 'R999'), edit('exemplar_ids', ['E999']),
                     edit('layer', 'conceptual'), edit('application', ''), edit('criterion', ''),
                     edit('exemplar_ids', []), edit('exemplar_ids', ['E001', 'E001']),
                     lambda result: result['acts'][1].pop('voice_bindings')]
        before = self.graph.db.execute('SELECT count(*) FROM node').fetchone()[0]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    self.faculty(ResolvedReasoner(mutation)).build('Construct the fixture')
                self.assertEqual(self.graph.db.execute('SELECT count(*) FROM node').fetchone()[0], before)
                self.assertEqual(self.graph.db.execute('SELECT count(*) FROM construction_plan').fetchone()[0], 0)

    def test_exemplar_from_another_rule_cannot_be_borrowed_as_grounding(self):
        exemplar = self.graph.add(Kind.EVIDENCE, {'Exemplar ID': 'E002', 'Source ID': 'S001',
            'Exemplar type': 'Original spoken', 'Exact excerpt': 'Synthetic fixture transcript',
            'Layer': 'Linguistic', 'Written validation': 'Not validated for writing'})
        rule = self.graph.add(Kind.RULE, {'Rule ID': 'R002', 'Layer': 'Linguistic',
            'Candidate rule': 'Another synthetic rule', 'activation': 'candidate_only'})
        self.graph.link(exemplar, 'derived_from', self.ids['source'])
        self.graph.link(rule, 'grounded_in', exemplar)
        reasoner = ResolvedReasoner(lambda result: result['acts'][0]['voice_bindings'][0].update(exemplar_ids=['E002']))
        with self.assertRaisesRegex(ValueError, 'ground the selected rule'):
            self.faculty(reasoner).build('Construct the fixture')

    def test_compact_requests_contain_each_source_once_and_preserve_full_snapshot(self):
        reasoner = ResolvedReasoner()
        faculty = self.faculty(reasoner, calibration_fixture())
        plan = faculty.build('Construct the synthetic fixture')
        reviewer = CapturingReviewer()
        review = faculty.review(plan, reviewer)
        for packet in (reasoner.context, reviewer.context):
            serialized = json.dumps(packet)
            self.assertEqual(serialized.count(TRANSCRIPT), 1)
            self.assertEqual(serialized.count(SUBJECT_SOURCE), 1)
            self.assertNotIn('voice_evidence', packet)
            self.assertEqual(len(packet['voice_catalog']['rules']), 1)
            self.assertEqual(len(packet['voice_catalog']['exemplars']), 1)
            self.assertEqual(len(packet['voice_catalog']['sources']), 1)
            self.assertEqual(packet['written_calibration'], calibration_fixture())
        snapshot = faculty.c.snapshot(plan)
        self.assertIn('voice_evidence', snapshot)
        self.assertEqual(snapshot['written_calibration'], calibration_fixture())
        self.assertEqual(len(snapshot['authentic_exemplars']), 1)
        faculty.close(plan, review, 'author')
        self.assertEqual(faculty.c.require_closed(plan)['plan'], plan)

    def test_changed_binding_or_applies_edge_invalidates_closed_plan(self):
        faculty = self.faculty()
        plan = faculty.build('Construct the synthetic fixture')
        close_fixture_plan(faculty, plan)
        act = faculty.c.snapshot(plan)['acts'][0]
        with self.graph.db:
            self.graph.db.execute("DELETE FROM edge WHERE src=? AND rel='applies'", (act,))
        with self.assertRaisesRegex(ValueError, 'edges differ'):
            faculty.c.require_closed(plan)

    def test_review_can_detect_omitted_rule_without_expanding_writer_evidence(self):
        other = self.graph.add(Kind.RULE, {'Rule ID': 'R002', 'Layer': 'Rhetorical',
            'Candidate rule': 'A second available synthetic application',
            'Status': 'Unconfirmed', 'activation': 'candidate_only'})
        self.graph.link(other, 'grounded_in', self.ids['exemplar'])
        faculty = self.faculty()
        plan = faculty.build('Construct the synthetic fixture')
        reviewer = CapturingReviewer()
        review = faculty.review(plan, reviewer)
        self.assertEqual({rule['rule_id'] for rule in reviewer.context['voice_catalog']['rules']},
                         {'R001', 'R002'})
        self.assertEqual(json.dumps(reviewer.context).count(TRANSCRIPT), 1)
        faculty.close(plan, review, 'author')
        expression = Expression(self.graph, None)
        packet = expression.writer_context(expression.context(plan))
        self.assertEqual({rule['key'] for rule in packet['voice_rules']}, {'R001'})
        self.assertEqual({item['key'] for item in packet['voice_exemplars']}, {'E001'})

    def test_calibration_requires_exact_generated_passage_approval(self):
        self.assertEqual(validate_written_calibration(None), [])
        original = calibration_fixture()
        validated = validate_written_calibration(original)
        original[0]['text'] = 'Caller changed the record'
        self.assertEqual(validated, calibration_fixture())
        for field, value in [('authority', 'authentic_author_writing'), ('scope', 'whole_corpus'),
                             ('author_judgment', ''), ('sha256', '0' * 64)]:
            with self.subTest(field=field):
                bad = calibration_fixture()
                bad[0][field] = value
                with self.assertRaises(ValueError):
                    validate_written_calibration(bad)


if __name__ == '__main__':
    unittest.main()
