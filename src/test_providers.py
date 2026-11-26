import json, unittest
from unittest.mock import patch
from providers import JSONModel
class ProviderTests(unittest.TestCase):
    def test_contract(self):
        def transport(req):
            body=json.loads(req.data); self.assertEqual(body['model'],'test'); self.assertEqual(body['response_format']['type'],'json_object')
            return {'choices':[{'finish_reason':'stop','message':{'content':'{"claims":[],"acts":[]}'}}]}
        with patch.dict('os.environ',{'TEST_KEY':'dummy'}):
            self.assertEqual(JSONModel('test','https://example.invalid/chat','TEST_KEY',transport).propose({}),{'claims':[],'acts':[]})
    def test_missing_key(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(RuntimeError): JSONModel('test','https://example.invalid/chat','TEST_KEY').propose({})
    def test_truncation(self):
        with patch.dict('os.environ',{'TEST_KEY':'dummy'}):
            with self.assertRaises(ValueError): JSONModel('test','https://example.invalid/chat','TEST_KEY',lambda r:{'choices':[{'finish_reason':'length'}]}).propose({})
