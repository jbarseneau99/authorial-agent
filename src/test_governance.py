import unittest
from governance import BilateralResearch, assess
class GovernanceTests(unittest.TestCase):
    def test_dedup_and_direction(self):
        class P:
            def search(self,q): return [{'source':'s','text':'t','metadata':{'doi':'D'}}]
        r=BilateralResearch(P()).investigate('claim','support query','challenge query')
        self.assertEqual(len(r['records']),1); self.assertEqual(r['records'][0]['directions'],['support','challenge']); self.assertEqual(r['records'][0]['polarity'],'unassessed')
        self.assertIsNone(assess(r,[])['sufficient'])
    def test_dependency(self):
        r={'records':[{'id':'a'},{'id':'b'},{'id':'c'}],'attempts':[{'status':'retrieved'}]}
        j=[{'id':i,'polarity':'supports','rationale':'reviewed','origin_group':'same','dependency_basis':'shared dataset'} for i in ['a','b']]+[{'id':'c','polarity':'challenges','rationale':'reviewed'}]
        a=assess(r,j); self.assertEqual(a['mass'],3); self.assertEqual(len(a['declared_origin_groups']),1); self.assertEqual(a['unknown_independence'],['c']); self.assertIsNone(a['sufficient'])
    def test_failed_search(self):
        class P:
            def search(self,q): raise RuntimeError()
        r=BilateralResearch(P()).investigate('claim','a','b'); self.assertEqual(assess(r,[])['status'],'research_incomplete')
    def test_invalid_judgment(self):
        with self.assertRaises(ValueError): assess({'records':[],'attempts':[]},[{'id':'invented','polarity':'supports'}])
