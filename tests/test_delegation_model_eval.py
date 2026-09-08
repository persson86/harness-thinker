#!/usr/bin/env python3
"""Deterministic checks for the model-eval response validator."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "payload/harness/scripts/model_eval_validate.py"


class ModelEvalValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="model-eval-")
        self.root = Path(self.temporary.name)
        self.spec = {
            "expected_ids": ["S1", "S2"],
            "allowed_evidence_ids": ["E1", "E2"],
            "max_words": 100,
            "action_fields": {
                "claim_action": ["promover", "somente source", "descartar"],
                "corrected_evidence_action": ["promover", "somente source", "descartar"],
            },
            "expected_actions": {
                "S1": {
                    "claim_action": "descartar",
                    "corrected_evidence_action": "promover",
                }
            },
        }
        self.response = {
            "findings": [
                {
                    "id": "S1",
                    "defect": "Plano tratado como resultado",
                    "evidence": ["E1"],
                    "epistemic_state": "plano",
                    "claim_action": "descartar",
                    "corrected_evidence_action": "promover",
                },
                {
                    "id": "S2",
                    "defect": "Fonte duplicada",
                    "evidence": ["E2"],
                    "epistemic_state": "relato",
                    "claim_action": "somente source",
                    "corrected_evidence_action": "somente source",
                },
            ]
        }
        self.spec_path = self.root / "spec.json"
        self.response_path = self.root / "response.json"
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        self.response_path.write_text(json.dumps(self.response), encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def run_validator(self, *args, input_text=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--spec", str(self.spec_path), *args],
            input=input_text, capture_output=True, text=True, timeout=15,
        )

    def test_valid_response_passes(self):
        result = self.run_validator("--response", str(self.response_path))
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["structural_valid"])
        self.assertTrue(report["word_limit_valid"])
        self.assertEqual(2, report["action_matches"])
        self.assertEqual(2, report["action_total"])

    def test_delegate_result_json_is_supported(self):
        outer = json.dumps({"result": {"text": json.dumps(self.response)}})
        result = self.run_validator("--result-json", "-", input_text=outer)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(2, json.loads(result.stdout)["finding_count"])

    def test_invalid_ids_actions_and_evidence_fail(self):
        bad = json.loads(json.dumps(self.response))
        bad["findings"] = bad["findings"][:1]
        bad["findings"][0]["evidence"] = ["E9"]
        bad["findings"][0]["claim_action"] = "inventar"
        self.response_path.write_text(json.dumps(bad), encoding="utf-8")
        result = self.run_validator("--response", str(self.response_path))
        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertFalse(report["structural_valid"])
        self.assertEqual(["S2"], report["missing_ids"])
        self.assertEqual("E9", report["invalid_evidence_ids"][0]["evidence"])

    def test_word_limit_is_separate_from_structure(self):
        self.spec["max_words"] = 1
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        result = self.run_validator("--response", str(self.response_path))
        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertTrue(report["structural_valid"])
        self.assertFalse(report["word_limit_valid"])

    def test_invalid_gold_action_is_a_spec_error(self):
        self.spec["expected_actions"]["S1"]["claim_action"] = "inventar"
        self.spec_path.write_text(json.dumps(self.spec), encoding="utf-8")
        result = self.run_validator("--response", str(self.response_path))
        self.assertEqual(2, result.returncode)
        self.assertIn("not an allowed action", json.loads(result.stdout)["fatal_error"])

    def test_spec_requires_cases_evidence_and_both_action_fields(self):
        variants = (
            ({**self.spec, "expected_ids": []}, "expected_ids must not be empty"),
            ({key: value for key, value in self.spec.items() if key != "allowed_evidence_ids"},
             "allowed_evidence_ids is required"),
            ({**self.spec, "allowed_evidence_ids": []}, "allowed_evidence_ids must not be empty"),
            ({key: value for key, value in self.spec.items() if key != "action_fields"},
             "action_fields is required"),
            ({**self.spec, "action_fields": {"claim_action": ["descartar"]}},
             "corrected_evidence_action"),
        )
        for spec, message in variants:
            with self.subTest(message=message):
                self.spec_path.write_text(json.dumps(spec), encoding="utf-8")
                result = self.run_validator("--response", str(self.response_path))
                self.assertEqual(2, result.returncode)
                self.assertIn(message, json.loads(result.stdout)["fatal_error"])

    def test_response_requires_semantic_fields_and_non_empty_evidence(self):
        bad = json.loads(json.dumps(self.response))
        del bad["findings"][0]["defect"]
        del bad["findings"][0]["epistemic_state"]
        del bad["findings"][0]["claim_action"]
        del bad["findings"][0]["corrected_evidence_action"]
        bad["findings"][0]["evidence"] = []
        self.response_path.write_text(json.dumps(bad), encoding="utf-8")

        result = self.run_validator("--response", str(self.response_path))
        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertFalse(report["structural_valid"])
        self.assertIn("S1.defect must be a non-empty string", report["errors"])
        self.assertIn("S1.epistemic_state must be a non-empty string", report["errors"])
        self.assertIn("S1.evidence must be a non-empty string list", report["errors"])
        invalid_fields = {item["field"] for item in report["invalid_actions"]}
        self.assertEqual(
            {"claim_action", "corrected_evidence_action"},
            invalid_fields,
        )


if __name__ == "__main__":
    unittest.main()
