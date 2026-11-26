import json,tempfile,unittest
from pathlib import Path
from evaluate import prepare
class EvaluationTests(unittest.TestCase):
    def test_preparation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'run'; cases=prepare(root)
            self.assertEqual(len(cases),4)
            for c in cases:
                review=json.loads((root/c['id']/'review.json').read_text())
                self.assertIsNone(review['author_approval'])
                self.assertTrue(all(x['judgment'] is None for x in review['criteria']))
    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileExistsError): prepare(Path(d))
