import unittest
from model import Graph,Kind
from construction import Construction
class ConstructionTests(unittest.TestCase):
    def setUp(self):
        self.g=Graph(); self.addCleanup(self.g.db.close); self.c=Construction(self.g); self.i=self.c.intent('Explain memory'); self.e=self.g.add(Kind.EVIDENCE,{'text':'Author hypothesis'}); self.cl=self.c.claim('Episodes provide context',[self.e],'author'); self.a=self.c.act(self.i,'Explain hypothesis',[self.cl])
    def test_gate(self):
        self.assertEqual(self.c.check(self.i,[self.a]),[]); s=self.c.sentence(self.i,[self.a],[self.a],'Episodes provide context.'); self.assertTrue(self.g.validate_sentence(s)); self.g.revise(self.e,{'text':'Revised'}); self.assertEqual(self.g.get(s)['status'],'stale'); self.assertRaises(ValueError,self.c.sentence,self.i,[self.a],[self.a],'Again')
    def test_missing(self):
        self.assertRaises(ValueError,self.c.claim,'Unsupported',[],'author'); a=self.g.add(Kind.ACT,{}); self.assertTrue(self.c.check(self.i,[a])); self.assertRaises(ValueError,self.c.sentence,self.i,[self.a],[],'Orphan')
    def test_cycle(self):
        self.g.link(self.cl,'depends',self.cl); self.assertTrue(self.c.check(self.i,[self.a]))
