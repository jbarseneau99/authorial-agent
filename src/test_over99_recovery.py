"""Offline recovery checks for the author-authorized strict >99% Pangram gate.

These are deterministic fixtures. They do not claim new Pangram calls,
human authorship, or repeatability of the original five observations.
"""
import math
import unittest

from pangram_check import DEFAULT_CONFIGURATION, PangramCheck, validate_configuration
from run_binding import paragraph_addendum, PARAGRAPH_OVER99_ADDENDUM


TEXT = " ".join(["fixture"] * 60) + "."
POLICY = "reported-over-99-human-v1"


def response(human, *, mixed=True):
    midpoint = len(TEXT) // 2
    windows = [
        {"text": TEXT[:midpoint], "label": "Human Written", "confidence": "Medium",
         "start_index": 0, "end_index": midpoint},
        {"text": TEXT[midpoint:], "label": "AI-Generated" if mixed else "Human Written",
         "confidence": "Medium", "start_index": midpoint, "end_index": len(TEXT)},
    ]
    return {
        "text": TEXT,
        "version": "4.1",
        "stage": "STAGE_SUCCESS",
        "prediction_short": "Mixed" if mixed else "Human",
        "fraction_human": human,
        "fraction_ai": 1.0 - human,
        "fraction_ai_assisted": 0.0,
        "windows": windows,
        "num_human_segments": 1 if mixed else 2,
        "num_ai_segments": 1 if mixed else 0,
        "num_ai_assisted_segments": 0,
    }


class RecoveredOver99Tests(unittest.TestCase):
    def setUp(self):
        config = dict(DEFAULT_CONFIGURATION, expected_version="4.1", policy=POLICY)
        self.config = validate_configuration(config)
        self.gate = PangramCheck.__new__(PangramCheck)
        self.gate.configuration = self.config

    def evaluate(self, result):
        return self.gate._success(result, {"text": TEXT})

    def test_recorded_qualified_fractions(self):
        for score in (1.0, 0.9988307952880859, 0.9999855160713196):
            with self.subTest(score=score):
                self.assertEqual(self.evaluate(response(score)), "passed")

    def test_strict_cutoff(self):
        for score in (0.0, 0.98, math.nextafter(0.99, 0.0), 0.99):
            with self.subTest(score=score):
                self.assertEqual(self.evaluate(response(score)), "flagged")
        self.assertEqual(self.evaluate(response(math.nextafter(0.99, 1.0))), "passed")

    def test_legacy_all_human_keeps_window_veto(self):
        self.gate.configuration = dict(self.config, policy="all-human-v1")
        self.assertEqual(self.evaluate(response(1.0, mixed=True)), "flagged")
        self.assertEqual(self.evaluate(response(1.0, mixed=False)), "passed")

    def test_bad_verdict_and_inconsistent_counts_rejected(self):
        bad = response(0.999)
        bad["prediction_short"] = "Unknown"
        with self.assertRaises(ValueError):
            self.evaluate(bad)
        bad = response(0.999)
        bad["num_ai_segments"] = 0
        with self.assertRaises(ValueError):
            self.evaluate(bad)

    def test_bound_procedure_registration(self):
        path, identity = paragraph_addendum({"procedure_addenda": [PARAGRAPH_OVER99_ADDENDUM]})
        self.assertEqual(path, PARAGRAPH_OVER99_ADDENDUM)
        self.assertEqual(identity["version"], "0.4")


if __name__ == "__main__":
    unittest.main()
