import unittest
from research import EuropePMC
from faculty import Faculty
from model import Graph
from test_faculty import Reasoner
class ResearchTests(unittest.TestCase):
    def test_retrieval(self):
        row={'id':'123','source':'MED','doi':'10.1/example','abstractText':'Retrieved abstract'}
        r=EuropePMC(transport=lambda url:{'resultList':{'result':[row,row,{'id':'456'}]}}).search('memory')
        self.assertEqual(len(r),1); self.assertEqual(r[0]['metadata']['independence'],'unknown'); self.assertEqual(r[0]['text'],'Retrieved abstract')
    def test_provenance_persisted(self):
        g=Graph(); self.addCleanup(g.db.close)
        r=EuropePMC(transport=lambda url:{'resultList':{'result':[{'id':'123','source':'MED','abstractText':'Evidence'}]}})
        Faculty(g,Reasoner(),r).build('memory')
        import json
        records=[json.loads(x[0]) for x in g.db.execute("SELECT payload FROM node WHERE kind='evidence'")]
        self.assertTrue(any(x.get('metadata',{}).get('verification')=='unverified' for x in records))
    def test_failure_propagates(self):
        r=EuropePMC(transport=lambda url: {})
        with self.assertRaises(KeyError): r.search('memory')
