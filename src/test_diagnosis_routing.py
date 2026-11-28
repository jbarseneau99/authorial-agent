"""Synthetic diagnosis routing and local scope regression; no live requests."""
import copy
import json
import unittest

from checking import Checking, LAYERS
from editing import Editing, LocalRepairScopeError
from expression import Expression
from faculty import Faculty
from pangram_check import DEFAULT_CONFIGURATION, PangramCheck
from paragraph_loop import ParagraphLoop
from providers import SuppliedResearch
from test_checking import Reviewer as LegacyReviewer
from test_construction_closure import ClosureReasoner, close_fixture_plan
from test_resolved_checking_editing import ResolvedFixture, criterion_findings


class DiagnosticReviewer:
    def __init__(self, failures):
        self.failures = failures

    def assess(self, context):
        findings = criterion_findings(context)
        for finding in findings:
            for check in finding['checks']:
                failure = self.failures.get(check['criterion_id'])
                if failure is None:
                    continue
                status, defect_type, positions = failure
                check.update(status=status, defect_type=defect_type,
                             observation='The fixture expression differs from its closed requirement.',
                             repair='Restore the stated fixture requirement only in the diagnosed target.',
                             sentences=[context['draft']['sentences'][index]['id'] for index in positions])
            statuses = {check['status'] for check in finding['checks']}
            finding['status'] = 'uncertain' if 'uncertain' in statuses else 'fail' if 'fail' in statuses else 'pass'
            targets = [check for check in finding['checks'] if check['status'] != 'pass'] or finding['checks']
            finding['sentences'] = sorted({ref for check in targets for ref in check['sentences']})
        return findings


class ScopedWriter:
    def __init__(self):
        self.calls = []
        self.mode = 'initial'

    def realize(self, context):
        self.calls.append(copy.deepcopy(context))
        if self.mode == 'initial':
            return {'status': 'draft', 'sentences': [
                {'text': 'A first fixture expression needs repair.', 'acts': [context['acts'][0]]},
                {'text': 'This accepted fixture sentence must stay exact.', 'acts': [context['acts'][0]]},
                {'text': 'A final fixture expression needs repair.', 'acts': [context['acts'][1]]},
            ]}
        repair = context['repair']
        sentences = [{'text': sentence['text'], 'acts': list(sentence['acts'])}
                     for sentence in repair['prior_draft']['sentences']]
        affected = set(repair['affected_sentences'])
        for index, sentence in enumerate(repair['prior_draft']['sentences']):
            if sentence['id'] in affected:
                sentences[index]['text'] = f'The repaired fixture expression at position {index}.'
        if self.mode == 'wide':
            sentences[1]['text'] = 'The writer also changed an unaffected fixture sentence.'
        return {'status': 'draft', 'sentences': sentences}


class DiagnosisRoutingTests(ResolvedFixture):
    def setUp(self):
        super().setUp()
        self.writer = ScopedWriter()
        self.expression = Expression(self.g, self.writer)
        acts = self.expression.context(self.plan)['acts']
        self.run = self.expression.run(self.plan, paragraph={
            'id': 'diagnosis-fixture', 'index': 0, 'acts': acts, 'prior_paragraphs': []})

    def review(self, failures):
        reviewer = DiagnosticReviewer(failures)
        checking = Checking(self.g, reviewer)
        assessment = checking.assess(self.run)
        return checking, assessment, reviewer

    @staticmethod
    def expression_failures():
        return {'base:conceptual': ('fail', 'expression', [2]),
                'base:linguistic': ('fail', 'expression', [0])}

    def test_conceptual_and_linguistic_expression_faults_repair_locally_then_recheck(self):
        checking, assessment, reviewer = self.review(self.expression_failures())
        observed = checking.inspect(assessment)
        self.assertEqual({ticket['layer']: ticket['route'] for ticket in observed['tickets']},
                         {'conceptual': 'expression', 'linguistic': 'expression'})
        editing = Editing(self.g, self.expression, checking)
        before = self.expression.inspect(self.run)
        with self.assertRaises(PermissionError):
            editing.run(self.run, assessment, actor='model')
        self.assertEqual(len(self.writer.calls), 1)
        self.writer.mode = 'repair'
        updated = editing.run(self.run, assessment, actor='author')
        after = self.expression.inspect(updated)
        self.assertEqual(len(before['sentences']), len(after['sentences']))
        self.assertEqual(before['sentences'][1]['payload']['text'], after['sentences'][1]['payload']['text'])
        self.assertNotEqual(before['sentences'][0]['payload']['text'], after['sentences'][0]['payload']['text'])
        self.assertNotEqual(before['sentences'][2]['payload']['text'], after['sentences'][2]['payload']['text'])
        self.assertEqual([s['acts'] for s in before['detail']['sentences']],
                         [s['acts'] for s in after['detail']['sentences']])
        self.assertEqual(self.expression.inspect(self.run), before)
        self.assertEqual(checking.inspect(assessment)['state'], 'review_required')
        policy = self.writer.calls[-1]['repair']['local_repair_policy']
        self.assertEqual(policy['affected_positions'], [0, 2])
        self.assertEqual(policy['preserved_sentences'][0]['id'], before['sentences'][1]['id'])
        reviewer.failures = {}
        self.assertEqual(checking.inspect(checking.assess(updated))['state'], 'checks_passed')

    def test_each_layer_routes_a_definite_expression_diagnosis_to_expression(self):
        for layer in sorted(LAYERS):
            with self.subTest(layer=layer):
                checking, ident, _ = self.review({f'base:{layer}': ('fail', 'expression', [0])})
                assessment = checking.inspect(ident)
                self.assertEqual(assessment['tickets'][0]['route'], 'expression')
                Editing(self.g, self.expression, checking)._current(self.run, ident)

    def test_paragraph_loop_uses_diagnosed_expression_routes_without_calling_detector(self):
        reviewer = DiagnosticReviewer(self.expression_failures())
        checking = Checking(self.g, reviewer)
        calls = []
        def detector(request):
            calls.append(request)
            raise AssertionError('A failed four-layer check cannot invoke the detector')
        pangram = PangramCheck(self.g, self.expression, checking,
                              configuration=dict(DEFAULT_CONFIGURATION, expected_version='4.1'), transport=detector)
        loop = ParagraphLoop(self.g, self.expression, checking, pangram, paragraph_groups=[[0, 1]])
        loop.prepare('fixture-execution', self.plan, mode='fixture')
        state = loop.advance('fixture-execution')
        self.assertEqual(state['state'], 'expression_repair_required')
        self.assertEqual(calls, [])

    def test_construction_evidence_or_uncertainty_blocks_mixed_expression_repair(self):
        cases = [('fail', 'construction', 'construction'),
                 ('fail', 'evidence_limit', 'author_review'),
                 ('uncertain', 'expression', 'author_review'),
                 ('uncertain', 'construction', 'author_review')]
        calls = len(self.writer.calls)
        for status, defect, route in cases:
            with self.subTest(status=status, defect=defect):
                failures = self.expression_failures()
                failures['base:linguistic'] = (status, defect, [0])
                checking, ident, _ = self.review(failures)
                tickets = checking.inspect(ident)['tickets']
                self.assertEqual(next(t['route'] for t in tickets if t['layer'] == 'linguistic'), route)
                with self.assertRaisesRegex(ValueError, 'diagnosed expression defects'):
                    Editing(self.g, self.expression, checking).run(self.run, ident, actor='author')
        self.assertEqual(len(self.writer.calls), calls)

    def test_stronger_diagnosis_wins_within_the_same_layer(self):
        baseline = Checking(self.g, DiagnosticReviewer({}))
        packet = baseline.reviewer_context(self.run, baseline.snapshot(self.run))
        binding = next(c['id'] for c in packet['construction']['criteria']
                       if c['id'].startswith('binding:') and c['layer'] == 'linguistic')
        for defect, status, expected in [('construction', 'fail', 'construction'),
                                         ('evidence_limit', 'fail', 'author_review'),
                                         ('expression', 'uncertain', 'author_review')]:
            with self.subTest(defect=defect, status=status):
                failures = {'base:linguistic': ('fail', 'expression', [0]), binding: (status, defect, [0])}
                checking, ident, _ = self.review(failures)
                self.assertEqual(checking.inspect(ident)['tickets'][0]['route'], expected)
                with self.assertRaises(ValueError):
                    Editing(self.g, self.expression, checking).run(self.run, ident, actor='author')

    def test_misbound_duplicate_wrong_route_or_missing_ticket_never_reaches_writer(self):
        calls = len(self.writer.calls)
        for change in ('layer', 'route', 'assessment', 'missing'):
            with self.subTest(change=change):
                checking, ident, _ = self.review(self.expression_failures())
                tickets = checking.inspect(ident)['tickets']
                conceptual = next(t for t in tickets if t['layer'] == 'conceptual')
                other = checking.assess(self.run) if change == 'assessment' else None
                with self.g.db:
                    if change == 'layer':
                        self.g.db.execute("UPDATE reopen_ticket SET layer='linguistic' WHERE id=?", (conceptual['id'],))
                    elif change == 'route':
                        self.g.db.execute("UPDATE reopen_ticket SET route='author_review' WHERE id=?", (conceptual['id'],))
                    elif change == 'assessment':
                        self.g.db.execute('UPDATE reopen_ticket SET assessment=? WHERE id=?', (other, conceptual['id']))
                    else:
                        self.g.db.execute('DELETE FROM reopen_ticket WHERE id=?', (conceptual['id'],))
                with self.assertRaisesRegex(ValueError, 'tickets must match'):
                    Editing(self.g, self.expression, checking).run(self.run, ident, actor='author')
        self.assertEqual(len(self.writer.calls), calls)

    def test_current_criterion_scope_is_revalidated_before_using_stored_findings(self):
        checking, ident, _ = self.review(self.expression_failures())
        findings = checking.inspect(ident)['findings']
        next(f for f in findings if f['layer'] == 'conceptual')['checks'][0]['sentences'] = ['unknown-sentence']
        with self.g.db:
            self.g.db.execute('UPDATE assessment SET findings=? WHERE id=?', (json.dumps(findings), ident))
        with self.assertRaises(ValueError):
            Editing(self.g, self.expression, checking).run(self.run, ident, actor='author')
        self.assertEqual(len(self.writer.calls), 1)

    def move_conceptual_target(self, checking, ident):
        findings = checking.inspect(ident)['findings']
        finding = next(f for f in findings if f['layer'] == 'conceptual')
        target = self.expression.inspect(self.run)['sentences'][1]['id']
        next(check for check in finding['checks']
             if check['criterion_id'] == 'base:conceptual')['sentences'] = [target]
        finding['sentences'] = [target]
        with self.g.db:
            self.g.db.execute('UPDATE assessment SET findings=? WHERE id=?', (json.dumps(findings), ident))
        self.assertEqual(set(checking.current_repair_routes(checking.inspect(ident)).values()),
                         {'expression'})

    def test_valid_target_change_during_authorization_never_reaches_writer(self):
        checking, ident, _ = self.review(self.expression_failures())
        authorize = checking.authorize
        def changed_authorization(ticket, actor):
            authorize(ticket, actor)
            self.move_conceptual_target(checking, ident)
        checking.authorize = changed_authorization
        with self.assertRaisesRegex(ValueError, 'Assessment changed before editing'):
            Editing(self.g, self.expression, checking).run(self.run, ident, actor='author')
        self.assertEqual(len(self.writer.calls), 1)
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM editing_attempt').fetchone()[0], 0)

    def test_valid_target_change_during_provider_call_leaves_repair_unresolved(self):
        checking, ident, _ = self.review(self.expression_failures())
        realize = self.writer.realize
        self.writer.mode = 'repair'
        def changed_writer(context):
            result = realize(context)
            self.move_conceptual_target(checking, ident)
            return result
        self.writer.realize = changed_writer
        editing = Editing(self.g, self.expression, checking)
        with self.assertRaisesRegex(ValueError, 'Assessment changed during editing'):
            editing.run(self.run, ident, actor='author')
        record = editing.inspect(self.writer.calls[-1]['repair']['editing_attempt'])
        self.assertEqual(record['state'], 'unresolved')
        self.assertIsNotNone(record['run'])

    def test_multilayer_permission_does_not_allow_changes_to_clean_text(self):
        checking, ident, _ = self.review(self.expression_failures())
        before = self.expression.inspect(self.run)
        self.writer.mode = 'wide'
        editing = Editing(self.g, self.expression, checking)
        with self.assertRaises(LocalRepairScopeError):
            editing.run(self.run, ident, actor='author')
        record = editing.inspect(self.writer.calls[-1]['repair']['editing_attempt'])
        self.assertEqual(record['state'], 'unresolved')
        self.assertIsNotNone(record['run'])
        self.assertEqual(self.expression.inspect(self.run), before)

    def test_legacy_conceptual_failure_still_requires_author_review(self):
        faculty = Faculty(self.g, ClosureReasoner(), SuppliedResearch())
        plan = faculty.build('A separate legacy synthetic fixture')
        close_fixture_plan(faculty, plan)
        class Writer:
            def realize(self, context):
                return {'status': 'draft', 'sentences': [{'text': 'A legacy fixture.', 'acts': context['acts']}]}
        expression = Expression(self.g, Writer())
        run = expression.run(plan)
        checking = Checking(self.g, LegacyReviewer('conceptual'))
        ident = checking.assess(run)
        self.assertEqual(checking.inspect(ident)['tickets'][0]['route'], 'author_review')
        with self.assertRaisesRegex(ValueError, 'Only linguistic failures'):
            Editing(self.g, expression, checking).run(run, ident, actor='author')


if __name__ == '__main__':
    unittest.main()
