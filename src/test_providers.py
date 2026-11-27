import base64
import json
import sqlite3
import unittest
from unittest.mock import patch
from providers import JSONModel, PROMPT_TEMPLATES
from run_binding import ProviderJournal
from test_run_binding import CONFIGURATION, fixture_binding

def completion(content='{"claims":[],"acts":[]}', finish="stop"):
    return {"id": "fixture-response", "choices": [{"finish_reason": finish, "message": {"content": content}}]}

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.graph, self.binding, self.root = fixture_binding(self)
        self.journal = ProviderJournal(self.graph, self.binding, "construction")
    def model(self, transport):
        return JSONModel(**CONFIGURATION, transport=transport, journal=self.journal)
    def test_contract_and_exact_request_precedes_transport(self):
        context = {"evidence": {"source1": {"text": "fixture text"}}, "intent": "test"}
        response = completion()
        def transport(request):
            record = self.journal.inspect()[0]
            self.assertEqual(record["state"], "invoking")
            self.assertEqual(record["request"].encode("utf-8"), request.data)
            body = json.loads(request.data)
            self.assertEqual(body["model"], CONFIGURATION["model"])
            self.assertEqual(json.loads(body["messages"][1]["content"]), context)
            self.assertEqual(request.get_header("Authorization"), "Bearer fixture-secret-key")
            self.assertNotIn("fixture-secret-key", record["request"])
            return response
        with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
            self.assertEqual(self.model(transport).propose(context), {"claims": [], "acts": []})
        record = self.journal.inspect()[0]
        self.assertEqual(record["state"], "succeeded")
        self.assertEqual(record["events"][-2]["detail"]["body"], response)
        self.assertNotIn("fixture-secret-key", json.dumps(record))
    def test_missing_key_is_audited_without_transport(self):
        called = []
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError): self.model(lambda request: called.append(request)).propose({})
        self.assertFalse(called)
        self.assertEqual(self.journal.inspect()[0]["state"], "failed")
    def test_missing_journal_and_fixture_live_transport_rejected(self):
        with self.assertRaises(RuntimeError): JSONModel(**CONFIGURATION, transport=lambda request: completion()).propose({})
        with self.assertRaises(RuntimeError): JSONModel(**CONFIGURATION, journal=self.journal).propose({})
        self.assertEqual(self.journal.inspect()[0]["state"], "failed")
    def test_truncated_and_invalid_json_responses_are_retained(self):
        responses = [completion(finish="length"), completion(content="{invalid"), b"not json at all"]
        with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
            for response in responses:
                with self.subTest(response=response):
                    with self.assertRaises(ValueError): self.model(lambda request: response).propose({})
                    record = self.journal.inspect()[-1]
                    self.assertEqual(record["state"], "failed")
                    retained = next(event["detail"] for event in record["events"] if event["state"] == "response_received")
                    if isinstance(response, bytes): self.assertEqual(base64.b64decode(retained["body"]), response)
                    else: self.assertEqual(retained["body"], response)
    def test_configuration_or_prompt_change_prevents_transport(self):
        called = []
        model = self.model(lambda request: called.append(request))
        model.model = "different"
        with self.assertRaises(ValueError): model.propose({})
        self.assertEqual(self.journal.inspect()[-1]["state"], "rejected")
        model.model = CONFIGURATION["model"]
        with patch.dict(PROMPT_TEMPLATES["construction"], {"role": "Different instruction"}):
            with self.assertRaises(ValueError): model.propose({})
        self.assertFalse(called)
    def test_input_change_prevents_transport(self):
        (self.root / "source.txt").write_text("changed", encoding="utf-8")
        called = []
        with self.assertRaises(ValueError): self.model(lambda request: called.append(request)).propose({})
        self.assertFalse(called)
        self.assertEqual(self.journal.inspect()[0]["state"], "rejected")
    def test_transport_exception_does_not_persist_credentials(self):
        def broken(request): raise OSError("Echoed request: " + request.get_header("Authorization"))
        with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
            with self.assertRaises(RuntimeError) as error: self.model(broken).propose({})
        self.assertNotIn("fixture-secret-key", str(error.exception))
        self.assertNotIn("fixture-secret-key", json.dumps(self.journal.inspect()))
    def test_credentials_echoed_by_provider_are_not_retained(self):
        with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
            with self.assertRaises(ValueError): self.model(lambda request: completion(content='{"credential":"fixture-secret-key"}')).propose({})
        self.assertNotIn("fixture-secret-key", json.dumps(self.journal.inspect()))
    def test_escaped_credential_in_nested_response_is_not_retained(self):
        secret = 'fixture-secret-key'
        content = json.dumps({'credential': secret}).replace('fixture', '\\u0066ixture')
        response = completion(content=content)
        with patch.dict('os.environ', {'TEST_KEY': secret}):
            with self.assertRaises(ValueError): self.model(lambda request: response).propose({})
        record = self.journal.inspect()[0]
        self.assertNotIn(secret, json.dumps(record))
        self.assertNotIn('response_received', [event['state'] for event in record['events']])
        self.assertEqual(record['state'], 'failed')
    def test_input_changed_during_transport_is_not_accepted(self):
        def transport(request):
            (self.root / 'source.txt').write_text('changed during call', encoding='utf-8')
            return completion()
        with patch.dict('os.environ', {'TEST_KEY': 'fixture-secret-key'}):
            with self.assertRaises(ValueError): self.model(transport).propose({})
        record = self.journal.inspect()[0]
        self.assertEqual(record['state'], 'failed')
        self.assertIn('response_received', [event['state'] for event in record['events']])
    def test_journal_rows_cannot_be_overwritten(self):
        with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
            self.model(lambda request: completion()).propose({})
        for table in ("provider_invocation", "provider_event"):
            with self.assertRaises(sqlite3.IntegrityError):
                with self.graph.db: self.graph.db.execute("DELETE FROM " + table)
    def test_construction_review_schema_uses_separate_operation(self):
        findings = [{"layer": layer, "status": "pass", "reason": "Fixture only"} for layer in ("conceptual", "epistemic", "rhetorical_plan")]
        with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
            result = self.model(lambda request: completion(json.dumps({"findings": findings}))).assess_construction({})
        self.assertEqual(result, findings)
        self.assertEqual(self.journal.inspect()[0]["operation"], "construction_review")

if __name__ == "__main__": unittest.main()
