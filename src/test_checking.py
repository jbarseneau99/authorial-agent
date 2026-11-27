import unittest
from model import Graph
from faculty import Faculty
from test_faculty import Reasoner,Research
from test_expression import Writer
from expression import Expression
from checking import Checking,LAYERS
from test_helpers import close_fixture_plan
class Reviewer:
    def __init__(self,fail=None): self.fail=fail
    def assess(self,c):
        return [{'layer':l,'status':'fail' if l==self.fail else 'pass','reason':'Fixture judgment','sentences':[c['draft']['sentences'][0]['id']]} for l in sorted(LAYERS)]
class CheckingTests(unittest.TestCase):
    def setUp(self):
        self.g=Graph(); self.addCleanup(self.g.db.close); f=Faculty(self.g,Reasoner(),Research()); self.p=f.build('Memory'); close_fixture_plan(f,self.p); self.e=Expression(self.g,Writer('good')); self.r=self.e.run(self.p)
    def test_pass_not_approval(self):
        c=Checking(self.g,Reviewer()); a=c.assess(self.r); self.assertEqual(c.inspect(a)['state'],'checks_passed'); self.assertEqual(c.inspect(a)['tickets'],[])
    def test_route_and_authority(self):
        c=Checking(self.g,Reviewer('epistemic')); a=c.assess(self.r); t=c.inspect(a)['tickets'][0]; self.assertEqual(t['route'],'construction'); self.assertRaises(PermissionError,c.authorize,t['id'],'agent'); c.authorize(t['id'],'author'); self.assertEqual(c.inspect(a)['tickets'][0]['state'],'authorized')
    def test_stale(self):
        c=Checking(self.g,Reviewer('linguistic')); a=c.assess(self.r); t=c.inspect(a)['tickets'][0]; self.assertEqual(t['route'],'expression'); s=self.e.inspect(self.r)['sentences'][0]['id']; self.g.revise(s,{'text':'Changed'}); self.assertEqual(c.inspect(a)['state'],'stale'); self.assertRaises(ValueError,c.authorize,t['id'],'author')
