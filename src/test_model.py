import unittest, tempfile, os
from model import Graph,Kind
class Tests(unittest.TestCase):
    def test_graph(self):
        g=Graph(); c=g.add(Kind.CLAIM,{'text':'claim'}); a=g.add(Kind.ACT,{'type':'assertion'}); b=g.add(Kind.ACT,{'type':'qualification'}); s=g.add(Kind.SENTENCE,{'text':'sentence'}); p=g.add(Kind.APPROVAL,{'actor':'author'})
        self.assertFalse(g.validate_sentence(s)); g.link(a,'asserts',c); g.link(s,'realizes',a); g.link(s,'realizes',b); g.link(p,'approves',s); self.assertTrue(g.validate_sentence(s)); g.revise(c,{'text':'revised'}); self.assertEqual(g.get(s)['status'],'stale'); self.assertEqual(g.get(p)['status'],'stale'); self.assertEqual(g.get(b)['status'],'draft'); self.assertEqual(g.get(c)['revision'],2)
        with self.assertRaises(ValueError): g.link(c,'realizes',s)
    def test_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'graph.db'); g=Graph(path); i=g.add(Kind.INTENT,{'text':'intent'}); g.db.close(); g=Graph(path); self.assertEqual(g.get(i)['payload']['text'],'intent'); g.db.close()
if __name__=='__main__': unittest.main()
