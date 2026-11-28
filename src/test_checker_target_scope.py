"""Synthetic comparative checking retains context without widening repair scope."""
import copy
import json
import unittest

from checking import Checking
from editing import Editing
from test_resolved_checking_editing import ResolvedFixture, criterion_findings


class ComparisonReviewer:
    def __init__(self, *, fail=False, add_context_target=False):
        self.fail = fail
        self.add_context_target = add_context_target
        self.context = None

    def assess(self, context):
        self.context = copy.deepcopy(context)
        criteria = {item['id']: item for item in context['construction']['criteria']}
        findings = criterion_findings(context)
        first, peer = context['draft']['sentences']
        target = next(item for item in criteria.values() if item['id'].startswith('binding:'))
        for finding in findings:
            for check in finding['checks']:
                check['sentences'] = list(criteria[check['criterion_id']]['target_sentence_ids'])
                if check['criterion_id'] != target['id']:
                    continue
                check['observation'] = (
                    f'The target sentence "{first["text"]}" is compared with contextual '
                    f'peer {peer["id"]}: "{peer["text"]}". The peer is comparison context.')
                if self.fail:
                    check.update(status='fail', defect_type='expression',
                                 repair='Clarify the first relation while preserving the contextual peer.')
                if self.add_context_target:
                    check['sentences'].append(peer['id'])
            finding['status'] = 'fail' if any(check['status'] == 'fail' for check in finding['checks']) else 'pass'
            targeted = [check for check in finding['checks'] if check['status'] != 'pass'] or finding['checks']
            finding['sentences'] = sorted({ident for check in targeted for ident in check['sentences']})
        return findings


class CheckerTargetScopeTests(ResolvedFixture):
    def test_projection_adds_explicit_targets_without_changing_canonical_criteria_or_snapshot(self):
        checking = Checking(self.g, None)
        snapshot = checking.snapshot(self.run)
        original = copy.deepcopy(snapshot)
        canonical = self.expression.writer_context(snapshot['construction'])['criteria']
        packet = checking.reviewer_context(self.run, snapshot)
        first, second = packet['draft']['sentences']
        self.assertEqual(packet['draft']['text'], self.expression.inspect(self.run)['text'])
        self.assertEqual(packet['draft']['sentences'], [first, second])
        self.assertEqual(first['text'], 'The first synthetic relation is stated.')
        self.assertEqual(second['text'], 'The second synthetic relation stays unchanged.')
        projected = packet['construction']['criteria']
        for criterion in projected[:4]:
            self.assertEqual(criterion['target_sentence_ids'], [first['id'], second['id']])
        self.assertEqual(projected[4]['target_sentence_ids'], [first['id']])
        self.assertEqual(projected[5]['target_sentence_ids'], [second['id']])
        self.assertEqual([{key: value for key, value in criterion.items() if key != 'target_sentence_ids'}
                          for criterion in projected], canonical)
        self.assertTrue(all('target_sentence_ids' not in criterion for criterion in canonical))
        self.assertEqual(snapshot, original)
        self.assertEqual(checking.snapshot(self.run), original)

    def test_passing_comparison_can_describe_peer_but_target_only_its_own_sentence(self):
        reviewer = ComparisonReviewer()
        checking = Checking(self.g, reviewer)
        assessment = checking.inspect(checking.assess(self.run))
        self.assertEqual(assessment['state'], 'checks_passed')
        self.assertEqual(assessment['tickets'], [])
        first, peer = reviewer.context['draft']['sentences']
        check = next(check for finding in assessment['findings'] for check in finding['checks']
                     if check['criterion_id'].startswith('binding:'))
        self.assertEqual(check['sentences'], [first['id']])
        self.assertIn(peer['id'], check['observation'])
        self.assertIn(peer['text'], check['observation'])
        stored = json.loads(self.g.db.execute('SELECT snapshot FROM assessment WHERE id=?',
                                              (assessment['id'],)).fetchone()[0])
        self.assertEqual(stored, json.loads(json.dumps(checking.snapshot(self.run))))
        self.assertNotIn('target_sentence_ids', json.dumps(stored))

    def test_contextual_peer_in_target_references_still_rejected_for_pass_and_fail(self):
        for fail in (False, True):
            with self.subTest(fail=fail):
                checking = Checking(self.g, ComparisonReviewer(fail=fail, add_context_target=True))
                with self.assertRaisesRegex(ValueError, 'scope'):
                    checking.assess(self.run)
                self.assertEqual(self.g.db.execute('SELECT count(*) FROM assessment').fetchone()[0], 0)
                self.assertEqual(self.g.db.execute('SELECT count(*) FROM reopen_ticket').fetchone()[0], 0)

    def test_comparison_failure_repairs_target_without_changing_contextual_peer(self):
        reviewer = ComparisonReviewer(fail=True)
        checking = Checking(self.g, reviewer)
        assessment = checking.assess(self.run)
        before = self.expression.inspect(self.run)
        self.writer.mode = 'local'
        editing = Editing(self.g, self.expression, checking)
        revised = editing.run(self.run, assessment, actor='author')
        after = self.expression.inspect(revised)
        repair = self.writer.contexts[-1]['repair']
        self.assertEqual(repair['affected_sentences'], [before['sentences'][0]['id']])
        self.assertEqual(repair['local_repair_policy']['affected_positions'], [0])
        self.assertIn(before['sentences'][1]['id'], json.dumps(repair['findings']))
        self.assertNotEqual(after['sentences'][0]['payload']['text'], before['sentences'][0]['payload']['text'])
        self.assertEqual(after['sentences'][1]['payload']['text'], before['sentences'][1]['payload']['text'])
        self.assertEqual(self.expression.inspect(self.run), before)


if __name__ == '__main__':
    unittest.main()
