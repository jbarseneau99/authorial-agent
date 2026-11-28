"""Fixture transport checks for the bounded construction-binding operation."""
import copy
import json
import unittest
from unittest.mock import patch

from providers import JSONModel, PROFILE_TEMPLATES
from run_binding import ProviderJournal
from test_providers import completion
from test_run_binding import CONFIGURATION, fixture_binding


def repair_context():
    binding = {
        "rule_id": "rule-node", "rule_key": "R001",
        "exemplar_ids": ["example-node"], "exemplar_keys": ["E001"],
        "layer": "rhetorical", "application": "Frame a question after a concrete case.",
        "criterion": "The concrete case motivates the ensuing question.",
    }
    acts = [
        {"id": "00000000-0000-0000-0000-000000000001", "purpose": "Pose the question",
         "claim_ids": ["claim-one"], "voice_bindings": [copy.deepcopy(binding)]},
        {"id": "00000000-0000-0000-0000-000000000002", "purpose": "State the distinction",
         "claim_ids": ["claim-two"], "voice_bindings": [copy.deepcopy(binding)]},
    ]
    return {
        "execution_profile": "resolved-voice-v1", "plan": "fixed-plan",
        "intent": "Express the supplied distinction.", "acts": acts,
        "claims": [{"id": "claim-one", "text": "A route may be visible."},
                   {"id": "claim-two", "text": "Visibility does not establish safety."}],
        "evidence": [{"id": "subject-source", "payload": {"text": "Synthetic subject evidence."}}],
        "voice_catalog": {
            "rules": [{"id": "rule-node", "rule_id": "R001", "exemplar_ids": ["E001"],
                       "payload": {"status": "candidate"}}],
            "exemplars": [{"id": "example-node", "exemplar_id": "E001", "source_ids": ["voice-source"],
                           "payload": {"text": "The path is clear. Does that mean the route is safe?"}}],
            "sources": [{"id": "voice-source", "payload": {"text": "Synthetic spoken example context."}}],
            "grounding_records": [],
        },
        "written_calibration": [],
        "repair": {
            "attempt": 1, "previous_plan": "fixed-plan",
            "review": {
                "id": "failed-review", "plan": "fixed-plan", "state": "construction_review_required",
                "findings": [{"layer": "rhetorical_plan", "status": "fail",
                              "reason": "The second application's claimed question structure does not fit its act."}],
                "snapshot_sha256": "0" * 64,
            },
            "instruction": "Repair only the diagnosed voice bindings.",
        },
    }


class VoiceResolutionProviderTests(unittest.TestCase):
    def setUp(self):
        self.graph, self.binding, _ = fixture_binding(self)
        self.journal = ProviderJournal(self.graph, self.binding, "construction")

    def model(self, transport):
        return JSONModel(**CONFIGURATION, transport=transport, journal=self.journal)

    def test_fixed_context_and_review_are_journaled_before_binding_repair(self):
        context = repair_context()
        original = copy.deepcopy(context)
        response = {
            "status": "bindings",
            "acts": [{"id": act["id"], "voice_bindings": [{
                "rule_id": "R001", "exemplar_ids": ["E001"], "layer": "rhetorical",
                "application": "Use the demonstrated distinction where appropriate to this fixed act.",
                "criterion": "The question or distinction performs the fixed purpose.",
            }]} for act in context["acts"]],
        }

        def transport(request):
            record = self.journal.inspect()[-1]
            self.assertEqual(record["operation"], "voice_resolution")
            self.assertEqual(record["state"], "invoking")
            self.assertEqual(record["request"].encode("utf-8"), request.data)
            body = json.loads(request.data)
            self.assertEqual(json.loads(body["messages"][1]["content"]), original)
            template = JSONModel.prompt_templates()["profiles"]["resolved-voice-v1"]["voice_resolution"]
            self.assertIn(template["role"], body["messages"][0]["content"])
            self.assertIn(template["schema"], body["messages"][0]["content"])
            return completion(json.dumps(response))

        with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
            result = self.model(transport).resolve_voice(context)
        self.assertEqual(result, response)
        self.assertEqual(context, original)
        records = self.journal.inspect()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["events"][-1]["detail"]["parsed_output"], response)
        self.assertNotIn("fixture-secret-key", json.dumps(records))

    def test_reopen_preserves_target_layer_without_other_provider_operations(self):
        for layer in ("conceptual", "epistemic", "rhetorical_plan"):
            with self.subTest(layer=layer):
                response = {"status": "reopen", "layer": layer,
                            "reason": "The failed review requires a change to the fixed construction."}
                with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
                    result = self.model(lambda request: completion(json.dumps(response))).resolve_voice(repair_context())
                self.assertEqual(result, response)
        self.assertEqual([item["operation"] for item in self.journal.inspect()], ["voice_resolution"] * 3)

    def test_base_operation_is_declared_and_profile_prompt_is_frozen(self):
        context = repair_context()
        del context["execution_profile"]
        response = {"status": "reopen", "layer": "rhetorical_plan", "reason": "No grounded binding fits."}
        with patch.dict("os.environ", {"TEST_KEY": "fixture-secret-key"}):
            self.assertEqual(self.model(lambda request: completion(json.dumps(response))).resolve_voice(context), response)

        called = []
        with patch.dict(PROFILE_TEMPLATES["resolved-voice-v1"]["voice_resolution"], {"role": "Changed after binding"}):
            with self.assertRaises(ValueError):
                self.model(lambda request: called.append(request)).resolve_voice(repair_context())
        self.assertFalse(called)
        self.assertEqual(self.journal.inspect()[-1]["state"], "rejected")


if __name__ == "__main__":
    unittest.main()
