import unittest
from model import Graph
from faculty import Faculty
from expression import Expression
from checking import Checking
from execution import Execution
from test_faculty import Reasoner,Research
from test_expression import Writer
from test_checking import Reviewer
class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.g=Graph(); self.addCleanup(self.g.db.close)
    def engine(self,fail=None):
        return Execution(self.g,Faculty(self.g,Reasoner(),Research()),Expression(self.g,Writer('good')),Checking(self.g,Reviewer(fail)))
    def test_closure(self):
        e=self.engine(); x=e.start('Memory'); self.assertEqual(x['state'],'awaiting_approval'); self.assertRaises(PermissionError,e.approve,x['id'],'agent'); self.assertEqual(e.approve(x['id'],'author')['state'],'closed')
    def test_retry_budget(self):
        e=self.engine('linguistic'); x=e.start('Memory',2); self.assertEqual(x['state'],'suspended_reopen'); self.assertRaises(PermissionError,e.advance,x['id']); y=e.advance(x['id'],'author'); self.assertNotEqual(x['run'],y['run']); self.assertEqual(e.advance(x['id'],'author')['state'],'budget_exhausted')
    def test_intellectual_suspend(self):
        e=self.engine('epistemic'); x=e.start('Memory'); self.assertRaises(ValueError,e.advance,x['id'],'author')
    def test_stale(self):
        e=self.engine(); x=e.start('Memory'); s=e.e.inspect(x['run'])['sentences'][0]['id']; self.g.revise(s,{'text':'Changed'}); self.assertRaises(ValueError,e.approve,x['id'],'author')
