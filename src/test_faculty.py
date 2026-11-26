import unittest
from model import Graph
from faculty import Faculty
class Research:
    def search(self,q): return [{'text':'Example research passage','source':'fixture:1'}]
class Reasoner:
    def __init__(self, bad=False): self.bad=bad
    def propose(self,c):
        return {'claims':[{'key':'c','text':'Proposed memory hypothesis','origin':'agent_hypothesis','evidence':['missing' if self.bad else 'intent']}], 'acts':[{'purpose':'State hypothesis','claims':['c']}]}
class FacultyTests(unittest.TestCase):
    def setUp(self): self.g=Graph(); self.addCleanup(self.g.db.close)
    def test_build(self):
        f=Faculty(self.g,Reasoner(),Research()); p=f.inspect(f.build('Explore memory')); self.assertEqual(p['structural_errors'],[]); self.assertEqual(p['state'],'proposed_unvalidated'); self.assertFalse(p['acts'][0]['claims'][0]['payload']['verified'])
    def test_reject_unknown_reference(self):
        f=Faculty(self.g,Reasoner(True),Research()); self.assertRaises(ValueError,f.build,'Explore memory'); self.assertEqual(self.g.db.execute('SELECT count(*) FROM node').fetchone()[0],0)
