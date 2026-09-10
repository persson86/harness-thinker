"""Checks de integridade da fixture; nao simulam qualidade de um modelo."""
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "payload/harness/evals/knowledge-mini-v1"
MODULE = importlib.util.spec_from_file_location("model_eval_validate", ROOT / "payload/harness/scripts/model_eval_validate.py")
validator = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(validator)


class KnowledgeFixtureTests(unittest.TestCase):
    def test_case_spec_and_rubric_ids_agree(self):
        spec = validator.validate_spec(json.loads((FIXTURE / "spec.json").read_text()))
        case = (FIXTURE / "case.md").read_text()
        rubric = (FIXTURE / "rubric.md").read_text()
        self.assertEqual(spec["expected_ids"], re.findall(r"^## (C\d+)$", case, re.M))
        self.assertEqual(spec["allowed_evidence_ids"], re.findall(r"^(E\d+):", case, re.M))
        for identifier in spec["expected_ids"]:
            self.assertIn("| " + identifier + " |", rubric)
        self.assertEqual(set(spec["expected_ids"]), set(spec["expected_actions"]))

    def test_action_key_has_positive_controls_and_valid_surface(self):
        spec = validator.validate_spec(json.loads((FIXTURE / "spec.json").read_text()))
        findings = [{"id": identifier, "defect": "fixture", "evidence": ["E1"],
                     "epistemic_state": "nao avaliado", **actions}
                    for identifier, actions in spec["expected_actions"].items()]
        value = {"findings": findings}
        result = validator.evaluate(value, json.dumps(value), spec, "", "")
        self.assertTrue(result["structural_valid"])
        self.assertEqual((16, 16), (result["action_matches"], result["action_total"]))
        self.assertEqual(["C5", "C8"], [i for i, a in spec["expected_actions"].items() if a["claim_action"] == "promover"])
        # Mesmo com evidencia E1 inadequada em outros casos o formato passa:
        # a pertinencia da evidencia continua exigindo revisao semantica.


if __name__ == "__main__":
    unittest.main()
