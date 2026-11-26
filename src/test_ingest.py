import unittest
from pathlib import Path
from model import Graph
from ingest import ingest
from learning import Learning
class ImportTests(unittest.TestCase):
    def test_baseline(self):
        g=Graph(); p=Path(__file__).parent/'Authorial_Voice_Ledger_v0.4.xlsx'
        if not p.exists(): p=p.parent.parent/p.name
        m=ingest(g,p); self.assertEqual(m['counts']['Exemplars'],84); self.assertEqual(m['unresolved'],[])
        n=g.db.execute('SELECT count(*) FROM node').fetchone()[0]
        self.assertEqual(ingest(g,p),m); self.assertEqual(g.db.execute('SELECT count(*) FROM node').fetchone()[0],n)
        self.assertEqual(Learning(g,'author').snapshot(),(0,{}))
        self.assertEqual(g.db.execute('PRAGMA foreign_key_check').fetchall(),[])
