import unittest
from model import Graph
from learning import Learning
class TestLearning(unittest.TestCase):
    def setUp(self): self.g=Graph(); self.l=Learning(self.g,'author')
    def test_teaching(self):
        s=self.l.propose_session('Challenge arguments')
        with self.assertRaises(ValueError): self.l.acquire('example','interview',s)
        with self.assertRaises(PermissionError): self.l.elect(s,'agent')
        ep=self.l.elect(s,'author'); e=self.l.acquire('example','interview',s)
        self.assertIn(('context',ep),self.g.prerequisites(e))
        self.l.close(s,'author')
        with self.assertRaises(ValueError): self.l.acquire('late','interview',s)
    def test_rule_governance(self):
        e=self.l.acquire('Direct expression','author correction'); p=self.l.propose_rule('VR-test','Perform the act',[e])
        self.assertEqual(self.l.snapshot(),(0,{}))
        with self.assertRaises(PermissionError): self.l.decide(p,'agent',True)
        self.assertEqual(self.l.decide(p,'author',True),1)
        p2=self.l.propose_rule('VR-test','Revision',[e]); self.l.decide(p2,'author',False)
        self.assertEqual(self.l.snapshot()[1]['VR-test']['body'],'Perform the act')
        p3=self.l.propose_rule('VR-test','New revision',[e]); self.l.decide(p3,'author',True)
        self.assertEqual(self.g.db.execute('SELECT count(*) FROM ledger_version').fetchone()[0],2)
    def test_no_rule_required(self):
        s=self.l.propose_session('Explore'); self.l.elect(s,'author'); self.l.close(s,'author'); self.assertEqual(self.l.snapshot(),(0,{}))
if __name__=='__main__': unittest.main()
