"""Installed CLI acceptance checks; provider execution is forbidden in this suite."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstalledEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="installed-eval-")
        cls.vault = Path(cls.temporary.name).resolve() / "vault"
        installed = subprocess.run(
            ["bash", str(ROOT / "install.sh"), "--init", str(cls.vault)],
            capture_output=True, text=True, timeout=60,
        )
        if installed.returncode:
            raise RuntimeError(installed.stdout + installed.stderr)
        cls.script = cls.vault / "harness/scripts/model-eval.py"
        # Replacing only the disposable installation makes any accidental
        # provider interaction observable, including a seemingly harmless probe.
        (cls.vault / "harness/scripts/delegate.py").write_text(
            "raise RuntimeError('Evaluation planning must not invoke delegation')\n"
        )

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def cli(self, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(self.script), "--vault", str(self.vault), "--json", *args],
            capture_output=True, text=True, timeout=15,
        )
        return result, json.loads(result.stdout or result.stderr)

    def plan(self, identifier):
        return self.cli(
            "plan", "--id", identifier,
            "--suite", str(self.vault / "harness/evals/workload-v1/suite.json"),
            "--profile", "luna:high", "--profile", "sonnet:high",
            "--case", "retrieval-current-decision",
            "--case", "analysis-intervention-result", "--max-calls", "4",
        )

    def test_installed_plan_blind_and_incomplete_report_without_models(self):
        result, planned = self.plan("installed-lifecycle")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(planned["planned_calls"], 4)
        run = Path(planned["path"])
        self.assertEqual(self.cli("verify", "--id", planned["id"])[0].returncode, 0)
        result, packet = self.cli("blind", "--id", planned["id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(Path(packet["packet"]).read_text()), [])
        result, output = self.cli("report", "--id", planned["id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(Path(output["json"]).read_text())
        self.assertEqual(report["counts"]["planned"], 4)
        self.assertEqual(report["counts"]["completed"], 0)
        self.assertIsNone(report["recommendation"]["general_winner"])
        for profile in report["profiles"]:
            for family in profile["families"]:
                self.assertEqual(family["status"], "inconclusive")
                self.assertEqual(family["human_feedback"]["status"], "unknown")
        self.assertEqual(json.loads((run / "feedback.json").read_text()), [])

    def test_installed_frozen_input_tamper_blocks_report(self):
        result, planned = self.plan("installed-tamper")
        self.assertEqual(result.returncode, 0, result.stderr)
        run = Path(planned["path"])
        manifest = json.loads((run / "manifest.json").read_text())
        rubric = run / manifest["cases"][0]["rubric"]
        rubric.write_text(rubric.read_text() + " ")
        for command in ("verify", "blind", "report"):
            result, error = self.cli(command, "--id", planned["id"])
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("changed", error["error"])
        self.assertFalse((run / "report.md").exists())

    def test_budget_refused_before_experiment_created(self):
        result, error = self.cli(
            "plan", "--id", "over-budget",
            "--suite", str(self.vault / "harness/evals/workload-v1/suite.json"),
            "--profile", "luna:high", "--profile", "sonnet:high",
            "--case", "retrieval-current-decision", "--max-calls", "1",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("exceed", error["error"])
        self.assertFalse((self.vault / "drafts/model-eval/over-budget").exists())

    def test_inventory_and_high_minimum_without_provider_calls(self):
        result, inventory = self.cli("inventory")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreaterEqual(len(inventory["profiles"]), 2)
        self.assertTrue(all(p["effort"] == "high" for p in inventory["profiles"]))
        result, error = self.cli(
            "plan", "--id", "low-refused", "--suite", str(self.vault / "harness/evals/workload-v1/suite.json"),
            "--profile", "luna:medium", "--case", "retrieval-current-decision", "--max-calls", "1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("high", error["error"])
        self.assertFalse((self.vault / "drafts/model-eval/low-refused").exists())

    def test_all_configured_profiles_can_be_frozen_without_calls(self):
        result, planned = self.cli(
            "plan", "--id", "all-inventory", "--suite", str(self.vault / "harness/evals/workload-v1/suite.json"),
            "--all-profiles", "--case", "retrieval-current-decision", "--max-calls", "32")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((Path(planned["path"]) / "manifest.json").read_text())
        self.assertGreaterEqual(len(manifest["profiles"]), 2)
        self.assertTrue(all(p["effort"] == "high" for p in manifest["profiles"]))

    def test_installed_calibration_and_empty_judge_packet_are_offline(self):
        result, planned = self.plan("judge-calibration")
        self.assertEqual(result.returncode, 0, result.stderr)
        judge = {"id": "judge", "provider": "codex", "model": "gpt-test", "effort": "high", "conflict_of_authorship": False}
        profile_file = self.vault / "judge-profile.json"
        profile_file.write_text(json.dumps(judge))
        result, error = self.cli("judge-packet", "--id", planned["id"], "--file", str(profile_file))
        self.assertEqual(result.returncode, 2)
        self.assertIn("completed", error["error"])
        calibration_file = self.vault / "judge-calibration.json"
        calibration_file.write_text(json.dumps({"evaluator": judge,
            "reference_set": {"id": "synthetic-ref", "provenance": "synthetic", "reviewer": "fixture",
                "items": [{"id": "r1", "criteria": [{"id": "fact", "status": "pass"}], "critical_failures": []}]},
            "assessments": []}))
        result, report = self.cli("calibrate", "--id", planned["id"], "--file", str(calibration_file))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(report["agreement_rate"])
        self.assertEqual(report["human_preference"], "unknown")
        self.assertFalse(report["automatic_qualification"])
        self.assertEqual(report["model_calls"], 0)

    def test_installed_workspace_final_state_and_artifact_only_blind_packet(self):
        result, planned = self.cli(
            "plan", "--id", "workspace-lifecycle", "--suite", str(self.vault / "harness/evals/workload-v2/suite.json"),
            "--profile", "luna:high", "--case", "retrieval-pilot-decision-v2", "--max-calls", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        result, prepared = self.cli("prepare", "--id", planned["id"], "--trial", "t0001")
        self.assertEqual(result.returncode, 0, result.stderr)
        workspace = Path(prepared["workflow"]["workspace"])
        self.addCleanup(shutil.rmtree, workspace, True)
        self.assertFalse(workspace.resolve().is_relative_to(self.vault.resolve()))
        self.assertFalse((workspace / "rubrics").exists())
        reference = json.loads((self.vault / "harness/evals/workload-v2/calibration/retrieval-pilot-decision-v2/good.json").read_text())
        for relative, text in reference["artifacts"].items():
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        result, finished = self.cli("finish", "--id", planned["id"], "--trial", "t0001")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(finished["workflow"]["final_state_checks"]["status"], "pass")
        self.assertIsNone(finished["workflow"]["response"])
        result, blinded = self.cli("blind", "--id", planned["id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = json.loads(Path(blinded["packet"]).read_text())
        self.assertEqual(len(packet[0]["artifacts"]), 2)
        self.assertTrue(any("continue_40" in (a.get("text") or "") for a in packet[0]["artifacts"]))
        result, output = self.cli("report", "--id", planned["id"])
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(Path(output["json"]).read_text())
        self.assertIsNone(report["recommendation"]["general_winner"])
        self.assertEqual(report["profiles"][0]["families"][0]["human_feedback"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
