"""Judge calibration is measured against attributed references, never invented people."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "payload/harness/scripts"))
from thinker_model_eval import core, judging


class JudgingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="eval-judge-")
        self.addCleanup(temporary.cleanup)
        self.vault = Path(temporary.name)
        core.plan(self.vault, ROOT / "payload/harness/evals/workload-v1/suite.json",
                  [{"id": "candidate", "provider": "codex", "model": "gpt-fixture", "effort": "high"}],
                  ["retrieval-current-decision"], identifier="trial", max_calls=1)
        self.experiment = self.vault / "drafts/model-eval/trial"
        self.profile = {"id": "judge-fixture", "provider": "codex", "model": "gpt-judge-fixture", "effort": "high", "conflict_of_authorship": False}
        self.reference = {"evaluator": self.profile,
                          "reference_set": {"id": "anchors", "provenance": "synthetic", "reviewer": "fixture-author",
                            "items": [{"id": "good", "criteria": [{"id": "fact", "status": "pass"}], "critical_failures": []},
                                      {"id": "bad", "criteria": [{"id": "fact", "status": "fail"}], "critical_failures": ["fact"]}]},
                          "assessments": [{"reference_id": "good", "criteria": [{"id": "fact", "status": "pass"}], "critical_failures": []},
                                          {"reference_id": "bad", "criteria": [{"id": "fact", "status": "fail"}], "critical_failures": ["fact"]}]}

    def file(self, data, name="input.json"):
        path = self.vault / name
        path.write_text(json.dumps(data))
        return path

    def test_synthetic_agreement_is_not_human_or_automatic_qualification(self):
        result = judging.calibrate(self.vault, "trial", self.file(self.reference))
        self.assertEqual(result["agreement_rate"], 1)
        self.assertEqual(result["status"], "agreement_on_supplied_references")
        self.assertEqual(result["human_preference"], "unknown")
        self.assertFalse(result["automatic_qualification"])
        self.assertEqual(result["model_calls"], 0)
        self.assertTrue(Path(result["path"]).exists())

    def test_missing_and_unknown_cannot_be_perfect_calibration(self):
        self.reference["assessments"] = self.reference["assessments"][:1]
        self.reference["assessments"][0]["criteria"][0]["status"] = "unknown"
        result = judging.calibrate(self.vault, "trial", self.file(self.reference))
        self.assertIsNone(result["agreement_rate"])
        self.assertEqual(result["missing_references"], ["bad"])
        self.assertEqual(result["status"], "needs_review")

    def test_critical_disagreement_is_visible_separate_from_criterion_agreement(self):
        self.reference["assessments"][1]["critical_failures"] = []
        result = judging.calibrate(self.vault, "trial", self.file(self.reference))
        self.assertEqual(result["agreement_rate"], 1)
        self.assertFalse(result["observations"][1]["critical_agreement"])
        self.assertEqual(result["status"], "needs_review")

    def test_human_reference_requires_explicit_evidence(self):
        self.reference["reference_set"]["provenance"] = "human"
        with self.assertRaises(core.EvalError):
            judging.calibrate(self.vault, "trial", self.file(self.reference))

    def test_invalid_duplicate_foreign_ids_and_effort_refused(self):
        variants = []
        x = copy.deepcopy(self.reference); x["assessments"].append(x["assessments"][0]); variants.append(x)
        x = copy.deepcopy(self.reference); x["assessments"][0]["reference_id"] = "alien"; variants.append(x)
        x = copy.deepcopy(self.reference); x["evaluator"]["effort"] = "medium"; variants.append(x)
        x = copy.deepcopy(self.reference); x["assessments"][0]["criteria"][0]["id"] = "alien"; variants.append(x)
        x = copy.deepcopy(self.reference); x["assessments"][0]["critical_failures"] = ["alien"]; variants.append(x)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(core.EvalError):
                judging.calibrate(self.vault, "trial", self.file(value))

    def test_repeated_calibration_preserves_both_inputs(self):
        a = judging.calibrate(self.vault, "trial", self.file(self.reference))
        self.reference["assessments"][0]["criteria"][0]["status"] = "fail"
        b = judging.calibrate(self.vault, "trial", self.file(self.reference))
        self.assertNotEqual(a["path"], b["path"])
        self.assertEqual(json.loads(Path(a["path"]).read_text())["agreement_rate"], 1)
        self.assertEqual(b["agreement_rate"], .5)

    def test_packet_preserves_original_and_excludes_candidate_identity(self):
        path = self.experiment / "trials.json"
        trials = core.read_json(path)
        trials[0].update(status="completed", job_id="00000000-0000-4000-8000-000000000001", response="Original answer. Unrequested notice retained.",
                         execution_seconds=99, model_reported="SECRET-CANDIDATE-MODEL", checks={"nonempty": True, "word_limit": True})
        core._write(path, trials)
        packet = judging.judge_packet(self.vault, "trial", self.file(self.profile))
        content = Path(packet["packet"]).read_text()
        data = json.loads(content)
        self.assertEqual(data["items"][0]["response"], trials[0]["response"])
        self.assertNotIn("SECRET-CANDIDATE-MODEL", content)
        self.assertNotIn("execution_seconds", content)
        self.assertNotIn("trial_id", data["items"][0])
        self.assertEqual(data["evaluator"]["effort"], "high")
        item = data["items"][0]
        grade = {"id": "grade-fixture", "blind_id": item["blind_id"], "evaluator": self.profile["id"],
                 "evaluator_config": {"kind": "model", **{k: self.profile[k] for k in ("provider", "model", "effort")}},
                 "rubric_version": item["rubric_version"], "conflict_of_authorship": False,
                 "quality": 3, "notes": "Schema roundtrip fixture, not semantic scoring.",
                 "evidence": [trials[0]["response"]], "critical_failures": [],
                 "criteria": [{"id": c["id"], "status": "pass", "evidence": [trials[0]["response"]]}
                              for c in item["rubric"]["criteria"]]}
        imported = core.import_assessments(self.vault, "trial", "grade", self.file([grade], "grades-input.json"))
        self.assertEqual(imported["added"], 1)

    def test_large_complete_response_refused_instead_of_truncated(self):
        path = self.experiment / "trials.json"
        trials = core.read_json(path)
        trials[0].update(status="completed", job_id="00000000-0000-4000-8000-000000000001",
                         response="word " * 3000, checks={"nonempty": True, "word_limit": False})
        core._write(path, trials)
        self.profile["max_packet_bytes"] = 8192
        with self.assertRaisesRegex(core.EvalError, "exceeds judge packet budget"):
            judging.judge_packet(self.vault, "trial", self.file(self.profile))

    def test_large_batch_is_split_without_dropping_or_repeating_items(self):
        profiles = [{"id": name, "provider": "codex", "model": "gpt-fixture", "effort": "high"}
                    for name in ("candidate-a", "candidate-b")]
        core.plan(self.vault, ROOT / "payload/harness/evals/workload-v1/suite.json", profiles,
                  ["retrieval-current-decision"], identifier="batch", max_calls=2)
        path = self.vault / "drafts/model-eval/batch/trials.json"
        trials = core.read_json(path)
        for number, trial in enumerate(trials, 1):
            trial.update(status="completed", job_id=f"00000000-0000-4000-8000-{number:012d}",
                         response="x " * 4000, checks={"nonempty": True, "word_limit": False})
        core._write(path, trials)
        self.profile["max_packet_bytes"] = 16384
        result = judging.judge_packet(self.vault, "batch", self.file(self.profile))
        self.assertIsNone(result["packet"])
        self.assertEqual(len(result["packets"]), 2)
        exported = []
        for filename in result["packets"]:
            self.assertLessEqual(Path(filename).stat().st_size, 16384)
            exported.extend(json.loads(Path(filename).read_text())["items"])
        self.assertCountEqual([t["blind_id"] for t in trials], [i["blind_id"] for i in exported])

    def test_packet_and_calibration_respect_frozen_integrity_and_path_boundary(self):
        escaped = self.vault / "outside"; escaped.mkdir()
        (self.experiment / "judging").symlink_to(escaped, target_is_directory=True)
        with self.assertRaises(core.EvalError):
            judging.calibrate(self.vault, "trial", self.file(self.reference))
        self.assertEqual(list(escaped.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
