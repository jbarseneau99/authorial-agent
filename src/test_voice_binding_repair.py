"""Synthetic bounded voice repair: fixed argument, versioned bindings, no live calls."""
import copy
import json
import sqlite3
import unittest

from faculty import Faculty, VoiceRepairReopen
from model import Graph, Kind
from providers import SuppliedResearch
from test_construction_closure import ClosureReasoner, ClosureReviewer
from test_voice_resolution import (ResolvedReasoner, SUBJECT_SOURCE, TRANSCRIPT,
                                   add_voice_fixture, calibration_fixture)
from voice_resolution import PROFILE


class VoiceReview:
    def __init__(self, statuses=None):
        self.statuses = statuses or {'conceptual': 'pass', 'epistemic': 'pass', 'rhetorical_plan': 'fail'}

    def assess_construction(self, context):
        return [{'layer': layer, 'status': status,
                 'reason': 'The synthetic binding needs a distinct, grounded application.'}
                for layer, status in self.statuses.items()]


class RepairReasoner(ResolvedReasoner):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.change = None
        self.during = None

    def resolve_voice(self, context):
        self.calls.append(copy.deepcopy(context))
        acts = []
        for act in context['acts']:
            bindings = [{'rule_id': binding['rule_key'], 'exemplar_ids': binding['exemplar_keys'],
                         'layer': binding['layer'], 'application': binding['application'],
                         'criterion': binding['criterion']} for binding in act['voice_bindings']]
            acts.append({'id': act['id'], 'voice_bindings': bindings})
        acts[0]['voice_bindings'][0].update(
            rule_id='R002', layer='rhetorical',
            application='Use the direct fixture relation to enact this act without announcing it.',
            criterion='The stated relation carries the act while its purpose is not announced.')
        result = {'status': 'bindings', 'acts': acts}
        if self.change:
            result = self.change(result) or result
        if self.during:
            self.during(context)
        return result


class VoiceBindingRepairTests(unittest.TestCase):
    def setUp(self):
        self.graph = Graph()
        self.addCleanup(self.graph.db.close)
        self.ids = add_voice_fixture(self.graph)
        self.other_rule = self.graph.add(Kind.RULE, {
            'Rule ID': 'R002', 'Layer': 'Rhetorical',
            'Candidate rule': 'Enact the synthetic relation without announcing the act.',
            'Status': 'Unconfirmed', 'activation': 'candidate_only'})
        self.graph.link(self.other_rule, 'grounded_in', self.ids['exemplar'])
        other_exemplar = self.graph.add(Kind.EVIDENCE, {
            'Exemplar ID': 'E002', 'Source ID': 'S001', 'Exemplar type': 'Original spoken',
            'Exact excerpt': 'Synthetic fixture transcript', 'Layer': 'Linguistic',
            'Written validation': 'Not validated for writing'})
        other_rule = self.graph.add(Kind.RULE, {
            'Rule ID': 'R003', 'Layer': 'Linguistic', 'Candidate rule': 'A separate synthetic rule',
            'Status': 'Unconfirmed', 'activation': 'candidate_only'})
        self.graph.link(other_exemplar, 'derived_from', self.ids['source'])
        self.graph.link(other_rule, 'grounded_in', other_exemplar)
        self.reasoner = RepairReasoner()
        self.faculty = Faculty(self.graph, self.reasoner,
            SuppliedResearch([{'text': SUBJECT_SOURCE, 'source': 'fixture:subject'}]),
            execution_profile=PROFILE, written_calibration=calibration_fixture())
        self.plan = self.faculty.build('Preserve this synthetic argument.')
        self.review = self.faculty.review(self.plan, VoiceReview())

    def rows(self, table):
        return self.graph.db.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()

    def last_attempt(self):
        ident = self.graph.db.execute('SELECT id FROM voice_repair_attempt ORDER BY rowid DESC LIMIT 1').fetchone()[0]
        return self.faculty.inspect_voice_repair(ident)

    def test_changed_binding_creates_only_new_act_version_and_requires_fresh_closure(self):
        before = self.faculty.c.snapshot(self.plan)
        old_nodes, old_history, old_edges = self.rows('node'), self.rows('history'), self.rows('edge')
        old_plan, old_review = self.rows('construction_plan'), self.rows('construction_review')
        def pending(context):
            record = self.faculty.inspect_voice_repair(context['repair']['attempt'])
            self.assertEqual(record['state'], 'invocation_pending')
            self.assertEqual(record['input'], context)
        self.reasoner.during = pending
        updated = self.faculty.repair_voice(self.plan, self.review, actor='author')
        after = self.faculty.c.snapshot(updated)
        self.assertEqual(before, self.faculty.c.snapshot(self.plan))
        self.assertEqual(before['intent'], after['intent'])
        self.assertNotEqual(before['acts'][0], after['acts'][0])
        self.assertEqual(before['acts'][1], after['acts'][1])
        for original, current in zip(before['acts'], after['acts']):
            previous_record, current_record = before['nodes'][original], after['nodes'][current]
            self.assertEqual(previous_record['node']['payload']['purpose'], current_record['node']['payload']['purpose'])
            self.assertEqual([edge for edge in previous_record['edges'] if edge[0] != 'applies'],
                             [edge for edge in current_record['edges'] if edge[0] != 'applies'])
        self.assertEqual(after['nodes'][after['acts'][0]]['node']['payload']['voice_bindings'][0]['rule_id'],
                         self.other_rule)
        self.assertEqual(self.rows('node')[:len(old_nodes)], old_nodes)
        self.assertEqual(self.rows('history')[:len(old_history)], old_history)
        self.assertEqual(self.rows('edge')[:len(old_edges)], old_edges)
        self.assertEqual(len(self.rows('node')), len(old_nodes) + 1)
        self.assertEqual(self.rows('construction_plan')[:1], old_plan)
        self.assertEqual(self.rows('construction_review'), old_review)
        self.assertEqual(self.graph.get(self.other_rule)['payload']['activation'], 'candidate_only')
        self.assertEqual(self.faculty.inspect(updated)['state'], 'proposed_unvalidated')
        self.assertEqual(self.rows('construction_closure'), [])
        with self.assertRaises(ValueError):
            self.faculty.c.require_closed(updated)
        record = self.last_attempt()
        self.assertEqual(record['state'], 'plan_proposed')
        self.assertEqual(record['new_plan'], updated)
        self.assertEqual(record['input'], self.reasoner.calls[0])
        self.assertEqual(record['snapshot'], json.loads(json.dumps(before)))
        self.assertEqual(record['input']['repair']['review']['snapshot_sha256'], record['snapshot_sha256'])
        self.assertEqual(record['input']['repair']['review']['findings'], self.faculty.inspect_review(self.review)['findings'])
        self.assertEqual([item['changed'] for item in record['lineage']['act_versions']], [True, False])
        self.assertEqual(json.dumps(record['input']).count(TRANSCRIPT), 1)
        self.assertEqual(json.dumps(record['input']).count(SUBJECT_SOURCE), 1)
        passing = self.faculty.review(updated, ClosureReviewer())
        self.faculty.close(updated, passing, 'author')
        self.assertEqual(self.faculty.c.require_closed(updated)['review'], passing)

    def test_author_operational_identity_is_required_before_recording_or_calling(self):
        for actor in (None, 'model', 'agent'):
            with self.subTest(actor=actor), self.assertRaises(PermissionError):
                self.faculty.repair_voice(self.plan, self.review, actor=actor)
        self.assertEqual(self.reasoner.calls, [])
        self.assertEqual(self.rows('voice_repair_attempt'), [])

    def test_uncertainty_or_substantive_failure_cannot_enter_voice_repair(self):
        for layer, status in [('conceptual', 'fail'), ('conceptual', 'uncertain'),
                              ('epistemic', 'fail'), ('epistemic', 'uncertain'),
                              ('rhetorical_plan', 'uncertain'), ('rhetorical_plan', 'pass')]:
            with self.subTest(layer=layer, status=status):
                statuses = {'conceptual': 'pass', 'epistemic': 'pass', 'rhetorical_plan': 'fail'}
                statuses[layer] = status
                review = self.faculty.review(self.plan, VoiceReview(statuses))
                with self.assertRaises(ValueError):
                    self.faculty.repair_voice(self.plan, review, actor='author')
        self.assertEqual(self.reasoner.calls, [])
        self.assertEqual(self.rows('voice_repair_attempt'), [])

    def test_stale_or_misbound_review_is_rejected_before_call(self):
        other_plan = self.faculty.build('Another synthetic argument.')
        other_review = self.faculty.review(other_plan, VoiceReview())
        with self.assertRaises(ValueError):
            self.faculty.repair_voice(self.plan, other_review, actor='author')
        source = self.graph.get(self.ids['source'])['payload']
        self.graph.revise(self.ids['source'], dict(source, extra='Changed fixture evidence'))
        with self.assertRaises(ValueError):
            self.faculty.repair_voice(self.plan, self.review, actor='author')
        self.assertEqual(self.reasoner.calls, [])

    def test_closed_or_legacy_plan_is_ineligible(self):
        passing = self.faculty.review(self.plan, ClosureReviewer())
        self.faculty.close(self.plan, passing, 'author')
        with self.assertRaisesRegex(ValueError, 'unclosed'):
            self.faculty.repair_voice(self.plan, self.review, actor='author')
        legacy = Faculty(self.graph, ClosureReasoner(), SuppliedResearch())
        legacy_plan = legacy.build('A legacy synthetic argument.')
        review = legacy.review(legacy_plan, VoiceReview())
        with self.assertRaisesRegex(ValueError, 'resolved voice profile'):
            legacy.repair_voice(legacy_plan, review, actor='author')
        self.assertEqual(self.reasoner.calls, [])

    def test_meaning_purpose_order_or_identity_edits_are_rejected_and_recorded(self):
        changes = [lambda result: result.update(claims=[{'text': 'A changed meaning'}]),
                   lambda result: result.update(intent='A different intent'),
                   lambda result: result['acts'][0].update(purpose='A different purpose'),
                   lambda result: result['acts'][0].update(claim_ids=['different-claim']),
                   lambda result: result['acts'].reverse(),
                   lambda result: result['acts'].pop(),
                   lambda result: result['acts'][0].pop('id'),
                   lambda result: result['acts'][0].update(id='unknown-act'),
                   lambda result: result['acts'][0].update(id=result['acts'][1]['id'])]
        before = self.rows('node'), self.rows('history'), self.rows('edge'), self.rows('construction_plan')
        for change in changes:
            with self.subTest(change=change):
                self.reasoner.change = change
                with self.assertRaises(ValueError):
                    self.faculty.repair_voice(self.plan, self.review, actor='author')
                self.assertEqual(self.last_attempt()['state'], 'unresolved')
                self.assertIsNotNone(self.last_attempt()['response'])
                self.assertEqual((self.rows('node'), self.rows('history'), self.rows('edge'),
                                  self.rows('construction_plan')), before)

    def test_invalid_or_ungrounded_bindings_never_create_a_plan(self):
        for field, value in [('rule_id', 'R999'), ('exemplar_ids', ['E999']),
                             ('exemplar_ids', ['E002']), ('layer', 'conceptual'),
                             ('application', ''), ('criterion', '')]:
            with self.subTest(field=field, value=value):
                self.reasoner.change = lambda result, field=field, value=value: result['acts'][0]['voice_bindings'][0].update({field: value})
                with self.assertRaises(ValueError):
                    self.faculty.repair_voice(self.plan, self.review, actor='author')
                self.assertEqual(self.last_attempt()['state'], 'unresolved')
                self.assertEqual(len(self.rows('construction_plan')), 1)

    def test_changed_evidence_during_call_retains_response_but_cannot_create_plan(self):
        def changed(context):
            source = self.graph.get(self.ids['source'])['payload']
            self.graph.revise(self.ids['source'], dict(source, extra='Changed during fixture call'))
        self.reasoner.during = changed
        before = len(self.rows('node'))
        with self.assertRaises(ValueError):
            self.faculty.repair_voice(self.plan, self.review, actor='author')
        record = self.last_attempt()
        self.assertEqual(record['state'], 'unresolved')
        self.assertEqual(record['response']['status'], 'bindings')
        self.assertEqual(len(self.rows('node')), before)
        self.assertEqual(len(self.rows('construction_plan')), 1)

    def test_changed_exact_review_during_call_is_rejected(self):
        def changed(context):
            findings = self.faculty.inspect_review(self.review)['findings']
            findings[0]['reason'] = 'A changed synthetic observation.'
            with self.graph.db:
                self.graph.db.execute('UPDATE construction_review SET findings=? WHERE id=?',
                                      (json.dumps(findings), self.review))
        self.reasoner.during = changed
        with self.assertRaisesRegex(ValueError, 'review changed'):
            self.faculty.repair_voice(self.plan, self.review, actor='author')
        self.assertEqual(self.last_attempt()['state'], 'unresolved')
        self.assertEqual(len(self.rows('construction_plan')), 1)

    def test_explicit_reopen_retains_reason_and_exact_request_without_graph_changes(self):
        response = {'status': 'reopen', 'layer': 'epistemic',
                    'reason': 'The synthetic diagnosis needs evidence outside binding repair.'}
        self.reasoner.change = lambda result: response
        before = self.rows('node'), self.rows('history'), self.rows('edge'), self.rows('construction_plan')
        with self.assertRaises(VoiceRepairReopen) as raised:
            self.faculty.repair_voice(self.plan, self.review, actor='author')
        record = self.faculty.inspect_voice_repair(raised.exception.attempt)
        self.assertEqual(record['state'], 'reopen_requested')
        self.assertEqual(record['response'], response)
        self.assertEqual(raised.exception.layer, 'epistemic')
        self.assertEqual(raised.exception.reason, response['reason'])
        self.assertEqual(record['input'], self.reasoner.calls[0])
        self.assertEqual((self.rows('node'), self.rows('history'), self.rows('edge'),
                          self.rows('construction_plan')), before)

    def test_provider_error_keeps_preexisting_request_record(self):
        def failed(context):
            raise RuntimeError('Synthetic provider interruption')
        self.reasoner.during = failed
        with self.assertRaises(RuntimeError):
            self.faculty.repair_voice(self.plan, self.review, actor='author')
        record = self.last_attempt()
        self.assertEqual(record['state'], 'unresolved')
        self.assertEqual(record['error_type'], 'RuntimeError')
        self.assertEqual(record['input'], self.reasoner.calls[0])
        self.assertIsNone(record['response'])

    def test_graph_and_plan_commit_is_atomic_when_plan_insert_fails(self):
        before = self.rows('node'), self.rows('history'), self.rows('edge'), self.rows('construction_plan')
        self.graph.db.execute("CREATE TRIGGER reject_fixture_plan BEFORE INSERT ON construction_plan BEGIN SELECT RAISE(ABORT, 'Synthetic plan insertion failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.faculty.repair_voice(self.plan, self.review, actor='author')
        self.assertEqual(self.last_attempt()['state'], 'unresolved')
        self.assertEqual((self.rows('node'), self.rows('history'), self.rows('edge'),
                          self.rows('construction_plan')), before)


if __name__ == '__main__':
    unittest.main()
