"""Synthetic criterion coverage and local repair boundary tests; no live calls."""
import copy
import json
import unittest

from checking import Checking, LAYERS
from editing import Editing, LocalRepairScopeError
from expression import Expression
from faculty import Faculty
from model import Graph
from providers import SuppliedResearch
from test_construction_closure import close_fixture_plan
from test_voice_resolution import (ResolvedReasoner, SUBJECT_SOURCE, TRANSCRIPT,
                                   add_voice_fixture, calibration_fixture)


def criterion_findings(context, *, failure=None, status='fail', defect_type='expression'):
    findings=[]
    sentences=context['draft']['sentences']
    for layer in sorted(LAYERS):
        checks=[]
        for criterion in context['construction']['criteria']:
            if criterion['layer']!=layer:
                continue
            refs=[sentence['id'] for sentence in sentences
                  if set(sentence['acts']) & set(criterion['act_ids'])]
            failed=criterion['id']==failure
            checks.append({'criterion_id':criterion['id'],
                           'status':status if failed else 'pass',
                           'observation':'Synthetic observation of the stated fixture criterion.',
                           'sentences':refs,'defect_type':defect_type if failed else 'none',
                           'repair':'State the fixture relation directly in the targeted sentence.' if failed else None})
        states={item['status'] for item in checks}
        aggregate='uncertain' if 'uncertain' in states else 'fail' if 'fail' in states else 'pass'
        targets=[item for item in checks if item['status']!='pass'] or checks
        findings.append({'layer':layer,'status':aggregate,'reason':'Synthetic layer summary.',
                         'sentences':sorted({ref for item in targets for ref in item['sentences']}),
                         'checks':checks})
    return findings


class CriteriaReviewer:
    def __init__(self, *, fail=False, status='fail', defect_type='expression', mutation=None):
        self.fail,self.status,self.defect_type,self.mutation=fail,status,defect_type,mutation
        self.context=None

    def assess(self, context):
        self.context=copy.deepcopy(context)
        failure=next(item['id'] for item in context['construction']['criteria']
                     if item['id'].startswith('binding:')) if self.fail else None
        result=criterion_findings(context,failure=failure,status=self.status,defect_type=self.defect_type)
        if self.mutation:
            self.mutation(result,context)
        return result


class LocalWriter:
    def __init__(self):
        self.contexts=[]
        self.mode='initial'

    def realize(self, context):
        self.contexts.append(copy.deepcopy(context))
        if self.mode=='initial':
            return {'status':'draft','sentences':[
                {'text':'The first synthetic relation is stated.','acts':[context['acts'][0]]},
                {'text':'The second synthetic relation stays unchanged.','acts':[context['acts'][1]]}]}
        prior=context['repair']['prior_draft']['sentences']
        if self.mode=='reopen':
            return {'status':'reopen','layer':'rhetorical','acts':[context['acts'][0]],
                    'reason':'The fixture repair requires a different intellectual-act arrangement.'}
        sentences=[{'text':item['text'],'acts':list(item['acts'])} for item in prior]
        sentences[0]['text']='The repaired synthetic relation is stated directly.'
        if self.mode=='wide':
            sentences[1]['text']='The writer also changed an unaffected sentence.'
        elif self.mode=='split':
            sentences.insert(1,{'text':'An additional sentence was introduced.','acts':list(sentences[0]['acts'])})
        return {'status':'draft','sentences':sentences}


class ResolvedFixture(unittest.TestCase):
    def setUp(self):
        self.g=Graph()
        self.addCleanup(self.g.db.close)
        add_voice_fixture(self.g)
        self.faculty=Faculty(self.g,ResolvedReasoner(),
                             SuppliedResearch([{'text':SUBJECT_SOURCE,'source':'fixture:subject'}]),
                             execution_profile='resolved-voice-v1',written_calibration=calibration_fixture())
        self.plan=self.faculty.build('Construct the synthetic fixture')
        close_fixture_plan(self.faculty,self.plan)
        self.writer=LocalWriter()
        self.expression=Expression(self.g,self.writer)
        acts=self.expression.context(self.plan)['acts']
        self.run=self.expression.run(self.plan,paragraph={'id':'fixture-paragraph','index':0,
                                                        'acts':acts,'prior_paragraphs':[]})


class ResolvedCheckingTests(ResolvedFixture):
    def test_compact_request_keeps_source_once_and_full_snapshot_for_freshness(self):
        reviewer=CriteriaReviewer()
        checking=Checking(self.g,reviewer)
        assessment=checking.assess(self.run)
        packet=reviewer.context
        self.assertEqual(packet['execution_profile'],'resolved-voice-v1')
        self.assertEqual(json.dumps(packet).count(SUBJECT_SOURCE),1)
        self.assertEqual(json.dumps(packet).count(TRANSCRIPT),1)
        self.assertNotIn('nodes',packet['construction'])
        self.assertNotIn('input',packet['draft'])
        self.assertEqual(len(packet['construction']['criteria']),6)
        self.assertEqual(packet['construction']['written_calibration'],calibration_fixture())
        self.assertEqual(checking.inspect(assessment)['state'],'checks_passed')
        saved=json.loads(self.g.db.execute('SELECT snapshot FROM assessment WHERE id=?',(assessment,)).fetchone()[0])
        self.assertIn('nodes',saved['construction'])
        self.assertIn('input',saved['draft'])
        self.assertEqual(saved,json.loads(json.dumps(checking.snapshot(self.run))))

    def test_missing_duplicate_wrong_layer_or_out_of_scope_check_never_passes(self):
        def linguistic(findings):
            return next(item for item in findings if item['layer']=='linguistic')
        def missing(findings,context):
            linguistic(findings)['checks'].pop()
        def duplicate(findings,context):
            linguistic(findings)['checks'].append(copy.deepcopy(linguistic(findings)['checks'][-1]))
        def wrong_layer(findings,context):
            moved=linguistic(findings)['checks'].pop()
            next(item for item in findings if item['layer']=='conceptual')['checks'].append(moved)
        def wrong_scope(findings,context):
            target=next(item for item in linguistic(findings)['checks'] if item['criterion_id'].startswith('binding:'))
            target['sentences']=[context['draft']['sentences'][1]['id']]
        def unknown(findings,context):
            linguistic(findings)['checks'][-1]['criterion_id']='unbound-criterion'
        for mutation in (missing,duplicate,wrong_layer,wrong_scope,unknown):
            with self.subTest(mutation=mutation):
                checking=Checking(self.g,CriteriaReviewer(mutation=mutation))
                with self.assertRaises(ValueError):
                    checking.assess(self.run)
                self.assertEqual(self.g.db.execute('SELECT count(*) FROM assessment').fetchone()[0],0)

    def test_aggregate_pass_cannot_hide_failure_and_target_refs_must_match(self):
        def change(field,value):
            def mutate(findings,context):
                next(item for item in findings if item['layer']=='linguistic')[field]=value(context) if callable(value) else value
            return mutate
        def remove_repair(findings,context):
            for finding in findings:
                for check in finding['checks']:
                    if check['status']=='fail':
                        check['repair']=''
        mutations=[change('status','pass'),
                   change('sentences',lambda context:[item['id'] for item in context['draft']['sentences']]),
                   remove_repair]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                checking=Checking(self.g,CriteriaReviewer(fail=True,mutation=mutation))
                with self.assertRaises(ValueError):
                    checking.assess(self.run)

    def test_genuine_uncertainty_remains_author_review(self):
        reviewer=CriteriaReviewer(fail=True,status='uncertain',defect_type='evidence_limit')
        checking=Checking(self.g,reviewer)
        assessment=checking.inspect(checking.assess(self.run))
        self.assertEqual(assessment['state'],'review_required')
        self.assertEqual(assessment['tickets'][0]['route'],'author_review')
        self.assertIn('separate and pending',reviewer.context['evaluation_scope']['author_validation'])
        self.assertIn('Provisional status alone',reviewer.context['evaluation_scope']['voice_evidence'])

    def test_changed_sentence_act_edge_invalidates_assessment(self):
        checking=Checking(self.g,CriteriaReviewer())
        assessment=checking.assess(self.run)
        sentence=self.expression.inspect(self.run)['sentences'][0]['id']
        with self.g.db:
            self.g.db.execute("DELETE FROM edge WHERE src=? AND rel='realizes'",(sentence,))
        self.assertEqual(checking.inspect(assessment)['state'],'stale')


class ResolvedEditingTests(ResolvedFixture):
    def prepare_edit(self,defect_type='expression'):
        checking=Checking(self.g,CriteriaReviewer(fail=True,defect_type=defect_type))
        assessment=checking.assess(self.run)
        return checking,assessment,Editing(self.g,self.expression,checking)

    def test_targeted_repair_preserves_unaffected_sentence_and_mapping(self):
        checking,assessment,editing=self.prepare_edit()
        before=self.expression.inspect(self.run)
        self.writer.mode='local'
        updated=editing.run(self.run,assessment,actor='author')
        after=self.expression.inspect(updated)
        self.assertNotEqual(before['sentences'][0]['payload']['text'],after['sentences'][0]['payload']['text'])
        self.assertEqual(before['sentences'][1]['payload']['text'],after['sentences'][1]['payload']['text'])
        self.assertEqual(self.expression.inspect(self.run),before)
        request=self.writer.contexts[-1]['repair']
        self.assertEqual(request['affected_sentences'],[before['sentences'][0]['id']])
        policy=request['local_repair_policy']
        self.assertEqual(policy['affected_positions'],[0])
        self.assertEqual(policy['preserved_sentences'][0]['id'],before['sentences'][1]['id'])
        self.assertEqual(editing.inspect(request['editing_attempt'])['state'],'expression_returned')

    def test_wider_rewrite_and_changed_sentence_boundaries_are_preserved_but_unresolved(self):
        for mode in ('wide','split'):
            with self.subTest(mode=mode):
                checking,assessment,editing=self.prepare_edit()
                self.writer.mode=mode
                with self.assertRaises(LocalRepairScopeError):
                    editing.run(self.run,assessment,actor='author')
                receipt=editing.inspect(self.writer.contexts[-1]['repair']['editing_attempt'])
                self.assertEqual(receipt['state'],'unresolved')
                self.assertEqual(receipt['error_type'],'LocalRepairScopeError')
                self.assertIsNotNone(receipt['run'])
                self.assertEqual(self.expression.inspect(self.run)['sentences'][1]['payload']['text'],
                                 'The second synthetic relation stays unchanged.')

    def test_linguistic_layer_cannot_send_construction_or_evidence_defect_to_editing(self):
        calls=len(self.writer.contexts)
        for defect_type in ('construction','evidence_limit'):
            with self.subTest(defect_type=defect_type):
                checking,assessment,editing=self.prepare_edit(defect_type)
                with self.assertRaisesRegex(ValueError,'diagnosed expression defects'):
                    editing.run(self.run,assessment,actor='author')
        self.assertEqual(len(self.writer.contexts),calls)

    def test_repair_can_request_reopening_without_changing_prose(self):
        checking,assessment,editing=self.prepare_edit()
        self.writer.mode='reopen'
        updated=editing.run(self.run,assessment,actor='author')
        self.assertEqual(self.expression.inspect(updated)['state'],'reopen_requested')
        self.assertEqual(self.expression.inspect(self.run)['state'],'draft_unvalidated')


if __name__=='__main__':
    unittest.main()
