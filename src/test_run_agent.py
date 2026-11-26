import unittest
from model import Graph
from run_agent import execute, ResearchBridge
from test_faculty import Reasoner, Research
from test_expression import Writer
from test_checking import Reviewer
class IntegrationTests(unittest.TestCase):
    def test_end_to_end(self):
        g=Graph(); self.addCleanup(g.db.close)
        result=execute(g,'Memory',Reasoner(),Writer('good'),Reviewer(),ResearchBridge(Research(),'support','challenge'))
        self.assertEqual(result['state'],'awaiting_approval'); self.assertEqual(len(result['research_report']['attempts']),2); self.assertTrue(result['draft']['sentences'])
    def test_failed_research_suspends(self):
        class Broken:
            def search(self,q): raise OSError('offline')
        g=Graph(); self.addCleanup(g.db.close)
        result=execute(g,'Memory',Reasoner(),Writer('good'),Reviewer(),ResearchBridge(Broken(),'support','challenge'))
        self.assertEqual(result['state'],'suspended_error'); self.assertNotIn('draft',result)
