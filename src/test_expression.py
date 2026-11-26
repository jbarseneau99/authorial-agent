import unittest
from model import Graph
from faculty import Faculty
from test_faculty import Reasoner, Research
from expression import Expression
class Writer:
    def __init__(self,mode): self.mode=mode
    def realize(self,c):
        if self.mode=='reopen': return {'status':'reopen','layer':'epistemic','acts':c['acts'],'reason':'Need evidence'}
        return {'status':'draft','sentences':[{'text':'A proposed hypothesis.','acts':c['acts'] if self.mode=='good' else ['unknown']}]}
class ExpressionTests(unittest.TestCase):
    def setUp(self):
        self.g=Graph(); self.addCleanup(self.g.db.close); self.p=Faculty(self.g,Reasoner(),Research()).build('Explore memory')
    def test_draft_and_invalidation(self):
        e=Expression(self.g,Writer('good')); r=e.run(self.p); s=e.inspect(r); self.assertEqual(s['state'],'draft_unvalidated'); a=self.g.prerequisites(s['sentences'][0]['id'])[0][1]; self.g.revise(a,{'purpose':'Changed'}); self.assertEqual(e.inspect(r)['state'],'stale')
    def test_reject(self):
        e=Expression(self.g,Writer('bad')); self.assertRaises(ValueError,e.run,self.p); self.assertEqual(self.g.db.execute('SELECT count(*) FROM expression_run').fetchone()[0],0); self.assertEqual(self.g.db.execute("SELECT count(*) FROM node WHERE kind='sentence'").fetchone()[0],0)
    def test_reopen(self):
        e=Expression(self.g,Writer('reopen')); s=e.inspect(e.run(self.p)); self.assertEqual(s['state'],'reopen_requested'); self.assertEqual(s['sentences'],[])
