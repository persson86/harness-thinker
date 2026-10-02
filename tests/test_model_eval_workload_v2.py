"""Fixture coverage and instrument calibration against actual final disk state."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import sys

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "payload/harness/evals/workload-v2"
sys.path.insert(0, str(REPO / "payload/harness/scripts"))
from thinker_model_eval import workflows as wf


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class WorkflowV2FixtureTests(unittest.TestCase):
    def setUp(self):
        self.suite = load("suite.json")
        self.cases = self.suite["cases"]
        self.calibration = load("calibration.json")

    def test_twelve_cases_balanced_by_family_and_split(self):
        families = {"retrieval", "ingestion", "analysis", "research", "code", "communication"}
        self.assertEqual(len(self.cases), 12)
        self.assertEqual(len({c["id"] for c in self.cases}), 12)
        self.assertEqual(Counter((c["family"], c["split"]) for c in self.cases),
                         Counter({(f, s): 1 for f in families for s in ("development", "holdout")}))
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["execution"], "host-managed")
                prompt = ROOT / case["prompt"]
                self.assertLessEqual(len(prompt.read_bytes()), case["max_prompt_bytes"])
                self.assertLessEqual(case["max_prompt_bytes"], 30000)
                self.assertLessEqual(case["max_words"], 700 if case["family"] == "code" else 450)
                self.assertTrue(wf.validate_workflow(ROOT, case))
                self.assertGreater(len(load(case["workflow"])["workspace"]), 1)

    def test_calibration_has_good_bad_and_valid_alternative_for_every_case(self):
        self.assertEqual({c["case_id"] for c in self.calibration["cases"]}, {c["id"] for c in self.cases})
        for entry in self.calibration["cases"]:
            self.assertEqual({r["label"] for r in entry["references"]}, {"good", "bad", "valid-alternative"})
            for reference in entry["references"]:
                data = load(reference["file"])
                self.assertEqual(data["case_id"], entry["case_id"])
                self.assertEqual(data["expected_final_state"], reference["expected_final_state"])
                self.assertIn("not observed", data["notes"])
                self.assertIsInstance(data["artifacts"], dict)
                self.assertTrue(data["artifacts"])

    def test_noncode_references_calibrate_trusted_checks_against_final_state(self):
        """Thirty real fixture executions; models and arbitrary code never run."""
        for source_case in (c for c in self.cases if c["family"] != "code"):
            entry = next(e for e in self.calibration["cases"] if e["case_id"] == source_case["id"])
            for reference in entry["references"]:
                with self.subTest(case=source_case["id"], reference=reference["label"]), tempfile.TemporaryDirectory(dir=os.path.realpath(tempfile.gettempdir())) as temporary:
                    experiment = Path(temporary)
                    frozen = wf.validate_workflow(ROOT, source_case)
                    hashes = {}
                    for name, content in frozen.items():
                        output = experiment / "inputs" / name
                        output.parent.mkdir(parents=True, exist_ok=True)
                        output.write_bytes(content)
                        hashes["inputs/" + name] = hashlib.sha256(content).hexdigest()
                    case = dict(source_case, workflow="inputs/" + source_case["workflow"])
                    data = json.dumps({"hashes": hashes, "cases": [case]}).encode()
                    (experiment / "manifest.json").write_bytes(data)
                    (experiment / "manifest.sha256").write_text(hashlib.sha256(data).hexdigest())
                    trial = {"id": "calibration"}
                    workspace = Path(wf.prepare(experiment, case, trial)["workspace"])
                    self.addCleanup(shutil.rmtree, workspace, True)
                    for name, content in load(reference["file"])["artifacts"].items():
                        target = workspace / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(content, encoding="utf-8")
                    with patch.object(wf.subprocess, "run") as launch:
                        result = wf.finish(experiment, case, trial, response="not used to score disk state")
                        launch.assert_not_called()
                    self.assertEqual(result["final_state_checks"]["status"], reference["expected_final_state"])
                    self.assertEqual(result["trajectory"]["status"], "unknown")
                    for artifact in result["artifacts"]:
                        self.assertEqual(hashlib.sha256((experiment / artifact["path"]).read_bytes()).hexdigest(), artifact["sha256"])

    def test_hidden_code_vectors_cover_errors_order_copy_and_path_aliases(self):
        for case in (c for c in self.cases if c["family"] == "code"):
            spec = load(case["workflow"])
            check = next(c for c in spec["checks"] if c["kind"] == "python-unittest")
            self.assertNotIn(check["source"], {e["source"] for e in spec["workspace"]})
            vectors = load(check["source"])
            self.assertGreaterEqual(len(vectors["cases"]), 10)
            self.assertEqual(len({c["id"] for c in vectors["cases"]}), len(vectors["cases"]))
            self.assertTrue(any(c["expected"].get("error") == "ValueError" for c in vectors["cases"]))
            self.assertTrue(any("value" in c["expected"] for c in vectors["cases"]))
            if vectors["protocol"] == "merge-scores":
                self.assertTrue(any(c.get("mutate_return") for c in vectors["cases"]))
                self.assertTrue(any(c["id"].startswith("duplicate") for c in vectors["cases"]))
            else:
                scenarios = {c["scenario"] for c in vectors["cases"]}
                self.assertTrue({"symlink-directory", "symlink-file", "root-alias", "empty-component"} <= scenarios)
        compile(wf.CODE_RUNNER, "trusted-stimulus-runner", "exec")  # syntax only, no execution

    def test_rubrics_preserve_gravity_and_style_freedom(self):
        for case in self.cases:
            rubric = load(case["rubric"])
            self.assertEqual(rubric["rubric_version"], "2.0")
            for criterion in rubric["criteria"]:
                self.assertIn(criterion["severity"], {"critical", "material", "minor", "unknown"})
                if criterion["dimension"] in {"style", "format", "length"}:
                    self.assertFalse(criterion["critical"])
                    self.assertNotEqual(criterion["severity"], "critical")
            self.assertIn("workflow fixture", rubric["scope"])

    def test_hidden_sources_are_not_candidate_material_and_public_scope_is_honest(self):
        hidden = {ROOT / c["rubric"] for c in self.cases}
        hidden |= {ROOT / r["file"] for c in self.calibration["cases"] for r in c["references"]}
        for case in self.cases:
            spec = load(case["workflow"])
            hidden |= {ROOT / c["source"] for c in spec["checks"] if c["kind"] == "python-unittest"}
        hidden_identity = {(p.stat().st_dev, p.stat().st_ino) for p in hidden}
        for case in self.cases:
            spec = load(case["workflow"])
            for entry in spec["workspace"]:
                source = wf._safe(ROOT, entry["source"], file=True)
                self.assertNotIn((source.stat().st_dev, source.stat().st_ino), hidden_identity)
            self.assertNotIn(load(case["rubric"])["reference_notes"], (ROOT / case["prompt"]).read_text())
        readme = (ROOT / "README.md").read_text()
        self.assertIn("não são secretos", readme)
        self.assertIn("novos casos privados", readme)
        self.assertIn("sem qualificar qualidade visual", readme)
        self.assertIn("não são", readme)
        for path in ROOT.rglob("*"):
            if path.is_file():
                self.assertFalse(path.is_symlink())
                self.assertNotRegex(path.read_text(), r"/(?:Users|home|private)/|https?://")


if __name__ == "__main__":
    unittest.main()
