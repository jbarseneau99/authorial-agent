import unittest
from pathlib import Path
from model import Graph
from ingest import ingest
from learning import Learning
from coverage import assess,objectives,propose_teaching
class CoverageTests(unittest.TestCase):
    def test_inventory(self):
        g=Graph(); m=ingest(g,Path(__file__).with_name('Authorial_Voice_Ledger_v0.4.xlsx')); r=assess(g,m['sha256'])
        self.assertEqual(sum(x['exemplars'] for x in r.values()),84)
        self.assertEqual(sum(x['candidate_rules'] for x in r.values()),19)
        self.assertEqual(sum(x['active_rules'] for x in r.values()),0)
        l=Learning(g,'author'); s=propose_teaching(l,objectives(r)[0]); self.assertRaises(ValueError,l.acquire,'example','test',s); l.elect(s,'author'); l.acquire('example','test',s)
    def test_unknown(self):
        g=Graph(); ingest(g,Path(__file__).with_name('Authorial_Voice_Ledger_v0.4.xlsx')); self.assertRaises(ValueError,assess,g,'unknown')
    def test_multilayer_and_live_evidence(self):
        g=Graph(); m=ingest(g,Path(__file__).with_name('Authorial_Voice_Ledger_v0.4.xlsx')); l=Learning(g,'author'); before=assess(g,m['sha256']); e=l.acquire('example','author feedback'); p=g.get(e)['payload']; p.update({'Layer':'Linguistic; rhetorical','Exemplar type':'Author-validated written'}); g.revise(e,p); after=assess(g,m['sha256'])
        for layer in ('Linguistic','Rhetorical'):
            self.assertEqual(after[layer]['written_validated'],before[layer]['written_validated']+1)
