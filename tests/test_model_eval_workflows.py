"""Workflow boundary tests, with real disk state and no model/code execution."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import types
import unittest
import uuid
from unittest.mock import patch
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "payload/harness/scripts"))
from thinker_model_eval import workflows as wf

SUITE = REPO / "payload/harness/evals/workload-v2"


def freeze(root, case):
    root.mkdir()
    inputs = root / "inputs"
    inputs.mkdir()
    files = wf.validate_workflow(SUITE, case)
    hashes = {}
    for relative, content in files.items():
        output = inputs / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
        hashes["inputs/" + relative] = hashlib.sha256(content).hexdigest()
    case = dict(case, workflow="inputs/" + case["workflow"])
    data = (json.dumps({"hashes": hashes, "cases": [case]}) + "\n").encode()
    (root / "manifest.json").write_bytes(data)
    (root / "manifest.sha256").write_text(hashlib.sha256(data).hexdigest())
    return case


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.path.realpath(tempfile.gettempdir()))
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.cases = json.loads((SUITE / "suite.json").read_text())["cases"]

    def setup_case(self, family="retrieval", trial_id="t0001"):
        source = next(c for c in self.cases if c["family"] == family and c["split"] == "development")
        experiment = self.base / (family + trial_id)
        case = freeze(experiment, source)
        trial = {"id": trial_id}
        prepared = wf.prepare(experiment, case, trial)
        self.addCleanup(shutil.rmtree, prepared["workspace"], True)
        return experiment, case, trial, Path(prepared["workspace"])

    def write_reference(self, workspace, case, label="good"):
        reference = json.loads((SUITE / "calibration" / case["id"] / (label + ".json")).read_text())
        for path, content in reference["artifacts"].items():
            output = workspace / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(content)

    def test_clean_workspace_per_trial_without_hidden_material_or_replay(self):
        experiment, case, trial, workspace = self.setup_case()
        self.assertFalse(workspace.is_relative_to(experiment))
        self.assertEqual(workspace.stat().st_mode & 0o777, 0o700)
        self.assertEqual(wf.load_receipt(experiment, trial["id"])["workspace"], str(workspace))
        self.assertFalse(any(p.suffix == ".json" for p in workspace.rglob("*")))
        (workspace / "archive/01-decision.md").write_text("candidate edit")
        other = Path(wf.prepare(experiment, case, {"id": "t0002"})["workspace"])
        self.addCleanup(shutil.rmtree, other, True)
        self.assertNotEqual((other / "archive/01-decision.md").read_text(), "candidate edit")
        with self.assertRaises(wf.WorkflowError):
            wf.prepare(experiment, case, trial)

    def test_external_workspace_has_no_vault_ancestor_or_hidden_siblings(self):
        source = next(c for c in self.cases if c["family"] == "retrieval" and c["split"] == "development")
        vault = self.base / "vault"
        experiment = vault / "drafts/model-eval/probe"
        experiment.parent.mkdir(parents=True)
        (vault / "AGENTS.md").write_text("private vault instruction")
        case = freeze(experiment, source)
        workspace = Path(wf.prepare(experiment, case, {"id":"outside"})["workspace"])
        self.addCleanup(shutil.rmtree, workspace, True)
        self.assertFalse(workspace.is_relative_to(vault))
        self.assertNotIn(vault, workspace.parents)
        self.assertFalse((workspace.parent / "inputs").exists())
        with patch.object(wf.tempfile, "gettempdir", return_value=str(vault)):
            with self.assertRaises(wf.WorkflowError):
                wf.prepare(experiment, case, {"id":"bad-temp-root"})

    def test_self_report_cannot_replace_actual_artifacts(self):
        experiment, case, trial, workspace = self.setup_case()
        result = wf.finish(experiment, case, trial, response="All files written; all tests passed")
        self.assertEqual(result["final_state_checks"]["status"], "fail")
        self.assertEqual(result["artifacts"], [])
        self.assertEqual(result["trajectory"]["status"], "unknown")
        self.assertIsNone(result["observed_identity"])

    def test_actual_good_and_alternative_state_pass_bad_state_fails(self):
        for label, expected in (("good", "pass"), ("bad", "fail"), ("valid-alternative", "pass")):
            with self.subTest(label=label):
                experiment, case, trial, workspace = self.setup_case(trial_id=label)
                self.write_reference(workspace, case, label)
                result = wf.finish(experiment, case, trial)
                self.assertEqual(result["final_state_checks"]["status"], expected)
                self.assertEqual(result["trajectory"]["status"], "unknown")

    def test_protected_edits_and_scope_writes_fail_observed_state(self):
        experiment, case, trial, workspace = self.setup_case()
        self.write_reference(workspace, case)
        (workspace / "archive/01-decision.md").write_text("changed")
        (workspace / "outside.txt").write_text("unexpected")
        result = wf.finish(experiment, case, trial)
        self.assertEqual(result["final_state_checks"]["status"], "fail")
        self.assertEqual(result["trajectory"]["status"], "fail")
        self.assertTrue(any("Protected fixture" in v for v in result["trajectory"]["violations"]))
        self.assertTrue(any("outside.txt" in v for v in result["trajectory"]["violations"]))

    def test_symlink_artifact_cannot_read_or_capture_outside_workspace(self):
        experiment, case, trial, workspace = self.setup_case()
        self.write_reference(workspace, case)
        outside = self.base / "secret.json"
        outside.write_text('{"secret":"do not capture"}')
        artifact = workspace / "deliverables/result.json"
        artifact.unlink()
        artifact.symlink_to(outside)
        result = wf.finish(experiment, case, trial)
        self.assertEqual(result["final_state_checks"]["status"], "fail")
        self.assertFalse(any(a["path"].endswith("result.json") for a in result["artifacts"]))
        self.assertEqual(outside.read_text(), '{"secret":"do not capture"}')

    def test_tampered_inputs_receipts_and_manifest_are_rejected(self):
        for kind in ("input", "receipt", "manifest"):
            with self.subTest(kind=kind):
                experiment, case, trial, workspace = self.setup_case(trial_id=kind)
                self.write_reference(workspace, case)
                if kind == "input":
                    source = next((experiment / "inputs/fixtures").rglob("*.md"))
                    source.write_text("tampered")
                elif kind == "receipt":
                    receipt = experiment / "workflow-receipts" / (trial["id"] + ".json")
                    data = json.loads(receipt.read_text()); data["initial_hashes"] = {}
                    receipt.write_text(json.dumps(data))
                else:
                    with (experiment / "manifest.json").open("a") as stream: stream.write(" ")
                with self.assertRaises(wf.WorkflowError):
                    wf.finish(experiment, case, trial)

    def test_capture_and_checks_share_snapshot_and_no_implicit_replay(self):
        experiment, case, trial, workspace = self.setup_case()
        self.write_reference(workspace, case)
        result = wf.finish(experiment, case, trial)
        self.assertEqual(result["final_state_checks"]["status"], "pass")
        captured = next(a for a in result["artifacts"] if a["path"].endswith("result.json"))
        snapshot_text = (experiment / captured["path"]).read_bytes()
        (workspace / "deliverables/result.json").write_text("late edit")
        self.assertEqual((experiment / captured["path"]).read_bytes(), snapshot_text)
        self.assertEqual(hashlib.sha256(snapshot_text).hexdigest(), captured["sha256"])
        with self.assertRaises(wf.WorkflowError):
            wf.finish(experiment, case, trial)

    def test_trace_has_provenance_but_does_not_imply_audit_pass(self):
        experiment, case, trial, workspace = self.setup_case()
        self.write_reference(workspace, case)
        with self.assertRaises(wf.WorkflowError):
            wf.finish(experiment, case, trial, observed_trace={"source": "candidate-self-report", "events": []})
        result = wf.finish(experiment, case, trial, observed_trace={"source": "host-observed", "events": [{"action": "write"}]})
        self.assertEqual(result["trajectory"]["status"], "unknown")

    def test_code_gate_and_missing_docker_never_execute_candidate_on_host(self):
        experiment, case, trial, workspace = self.setup_case("code")
        self.write_reference(workspace, case)
        with patch.object(wf.subprocess, "run") as execute:
            result = wf.finish(experiment, case, trial)
            execute.assert_not_called()
        self.assertEqual(result["final_state_checks"]["status"], "unavailable")
        experiment, case, trial, workspace = self.setup_case("code", "missing")
        self.write_reference(workspace, case)
        with patch.object(wf.shutil, "which", return_value=None), patch.object(wf.subprocess, "run") as execute:
            result = wf.finish(experiment, case, trial, allow_code_execution=True)
            execute.assert_not_called()
        self.assertEqual(result["final_state_checks"]["status"], "unavailable")

    def test_docker_hidden_expectations_stay_outside_and_exit_zero_needs_results(self):
        experiment, case, trial, workspace = self.setup_case("code")
        self.write_reference(workspace, case)
        spec = json.loads((experiment / case["workflow"]).read_text())
        check = next(c for c in spec["checks"] if c["kind"] == "python-unittest")
        vectors = json.loads((experiment / "inputs" / check["source"]).read_text())
        expected = {"protocol_version": 1, "results": [{"id": x["id"], **x["expected"]} for x in vectors["cases"]]}
        seen = []
        def fake(command, **kwargs):
            seen.append((command, kwargs))
            if command[1:3] == ["image", "inspect"]:
                return types.SimpleNamespace(returncode=0, stdout=json.dumps([{"Id": "sha256:" + "a" * 64}]).encode())
            if command[1] == "run":
                Path(command[command.index("--cidfile") + 1]).write_text("b" * 64)
                self.assertNotIn("expected", json.loads(kwargs["input"])["cases"][0])
                kwargs["stdout"].write(json.dumps(expected).encode())
            if command[1] == "inspect":
                return types.SimpleNamespace(returncode=0, stdout=json.dumps({"StartedAt":"2026-01-01T00:00:00Z","Running":False,"ExitCode":0}).encode())
            return types.SimpleNamespace(returncode=0)
        with patch.object(wf.shutil, "which", return_value="docker"), patch.object(wf.subprocess, "run", side_effect=fake):
            result = wf._code_check(workspace, experiment / "inputs", check, True)
        self.assertEqual(result["status"], "pass")
        command = next(cmd for cmd, _ in seen if cmd[1] == "run")
        self.assertIn("sha256:" + "a" * 64, command)
        self.assertEqual(command.count("--mount"), 1)
        self.assertIn("none", command)
        self.assertIn("--read-only", command)
        self.assertIn("--interactive", command)  # JSON stimuli must reach container stdin.
        self.assertFalse(any("trusted/" in arg or "rubric" in arg for arg in command))
        def no_results(command, **kwargs):
            if command[1:3] == ["image", "inspect"]: return types.SimpleNamespace(returncode=0, stdout=json.dumps([{"Id":"sha256:"+"a"*64}]).encode())
            if command[1] == "run": Path(command[command.index("--cidfile") + 1]).write_text("b" * 64)
            if command[1] == "inspect": return types.SimpleNamespace(returncode=0, stdout=json.dumps({"StartedAt":"2026-01-01T00:00:00Z","Running":False,"ExitCode":0}).encode())
            return types.SimpleNamespace(returncode=0)
        with patch.object(wf.shutil, "which", return_value="docker"), patch.object(wf.subprocess, "run", side_effect=no_results):
            self.assertEqual(wf._code_check(workspace, experiment / "inputs", check, True)["status"], "fail")

    def test_docker_infrastructure_exit_is_unavailable(self):
        experiment, case, trial, workspace = self.setup_case("code")
        check = next(c for c in json.loads((experiment / case["workflow"]).read_text())["checks"] if c["kind"] == "python-unittest")
        def fake(command, **kwargs):
            if command[1:3] == ["image", "inspect"]: return types.SimpleNamespace(returncode=0, stdout=json.dumps([{"Id":"sha256:"+"a"*64}]).encode())
            return types.SimpleNamespace(returncode=125 if command[1] == "run" else 0)
        with patch.object(wf.shutil, "which", return_value="docker"), patch.object(wf.subprocess, "run", side_effect=fake):
            self.assertEqual(wf._code_check(workspace, experiment / "inputs", check, True)["status"], "unavailable")

    def test_candidate_exit_125_126_127_is_failure_after_container_started(self):
        experiment, case, trial, workspace = self.setup_case("code")
        check = next(c for c in json.loads((experiment / case["workflow"]).read_text())["checks"] if c["kind"] == "python-unittest")
        for exit_code in (125, 126, 127):
            def fake(command, **kwargs):
                if command[1:3] == ["image", "inspect"]: return types.SimpleNamespace(returncode=0, stdout=json.dumps([{"Id":"sha256:"+"a"*64}]).encode())
                if command[1] == "run":
                    Path(command[command.index("--cidfile") + 1]).write_text("b" * 64)
                    return types.SimpleNamespace(returncode=exit_code)
                if command[1] == "inspect": return types.SimpleNamespace(returncode=0, stdout=json.dumps({"StartedAt":"2026-01-01T00:00:00Z","Running":False,"ExitCode":exit_code}).encode())
                return types.SimpleNamespace(returncode=0)
            with self.subTest(exit_code=exit_code), patch.object(wf.shutil, "which", return_value="docker"), patch.object(wf.subprocess, "run", side_effect=fake):
                result = wf._code_check(workspace, experiment / "inputs", check, True)
                self.assertEqual(result["status"], "fail")
                self.assertEqual(result["adversarial_detection"], "limited")

    def test_candidate_capture_violations_return_failure_without_stalling_finish(self):
        for kind in ("oversized", "count", "colon", "backslash"):
            with self.subTest(kind=kind):
                experiment, case, trial, workspace = self.setup_case(trial_id=kind)
                self.write_reference(workspace, case)
                if kind == "oversized": (workspace / "deliverables/large.txt").write_bytes(b"x" * (wf.MAX_FILE_BYTES + 1))
                elif kind == "count":
                    for number in range(510): (workspace / "deliverables" / f"file-{number}.txt").write_text("x")
                else: (workspace / "deliverables" / ("bad:name" if kind == "colon" else "bad\\name")).write_text("x")
                result = wf.finish(experiment, case, trial)
                self.assertEqual(result["final_state_checks"]["status"], "fail")
                self.assertEqual(result["trajectory"]["status"], "fail")
                self.assertLessEqual(len(result["trajectory"]["violations"]), 40)

    def test_nested_scope_ancestors_and_exact_output_file(self):
        for scope in ("out/reports", "out/reports/final.json"):
            experiment, case, trial, workspace = self.setup_case(trial_id="nested-" + str(len(scope)))
            # A new frozen fixture configuration is legitimate test setup, not
            # candidate tampering or an implicit reprepare of an existing trial.
            shutil.rmtree(workspace)
            (experiment / "workflow-receipts" / (trial["id"] + ".json")).unlink()
            (experiment / "workflow-receipts" / (trial["id"] + ".sha256")).unlink()
            spec_path = experiment / case["workflow"]
            spec = json.loads(spec_path.read_text())
            spec.update(writable=[scope], artifacts=["out/reports/final.json"], checks=[{"id":"nonempty","kind":"text","path":"out/reports/final.json"}])
            spec_path.write_text(json.dumps(spec))
            manifest = json.loads((experiment / "manifest.json").read_text())
            manifest["hashes"][case["workflow"]] = hashlib.sha256(spec_path.read_bytes()).hexdigest()
            raw = json.dumps(manifest).encode(); (experiment / "manifest.json").write_bytes(raw)
            (experiment / "manifest.sha256").write_text(hashlib.sha256(raw).hexdigest())
            workspace = Path(wf.prepare(experiment, case, trial)["workspace"])
            self.addCleanup(shutil.rmtree, workspace, True)
            final = workspace / "out/reports/final.json"
            self.assertFalse(final.exists())
            final.write_text('{"done":true}')
            self.assertEqual(wf.finish(experiment, case, trial)["final_state_checks"]["status"], "pass")

    @unittest.skipUnless(shutil.which("docker"), "Docker unavailable; no candidate execution on host")
    def test_live_docker_exit_and_basic_monkeypatch_cannot_fake_success(self):
        experiment, case, trial, workspace = self.setup_case("code")
        check = next(c for c in json.loads((experiment / case["workflow"]).read_text())["checks"] if c["kind"] == "python-unittest")
        reference = json.loads((SUITE / "calibration" / case["id"] / "good.json").read_text())["artifacts"]["src/scores.py"]
        attacks = ["import os\nos._exit(0)\n", reference + '\nimport __main__, copy\n__main__.encode=lambda value: []\ncopy.deepcopy=lambda value:value\n_original=merge_scores\ndef merge_scores(existing,incoming):\n    result=_original(existing,incoming)\n    if existing: existing[0]["score"]=99\n    return result\n']
        for source, expected_status in [(reference, "pass"), *((attack, "fail") for attack in attacks)]:
            (workspace / "src/scores.py").write_text(source)
            # Docker sees a readable isolated capture, not the 0700 host root.
            snapshot = self.base / ("docker-" + uuid.uuid4().hex)
            shutil.copytree(workspace, snapshot); os.chmod(snapshot, 0o755)
            result = wf._code_check(snapshot, experiment / "inputs", check, True)
            if result["status"] == "unavailable": self.skipTest(result["reason"])
            self.assertEqual(result["status"], expected_status)

    def test_lexical_and_symlink_confinement(self):
        for value in ("../x", "/x", "a//x", "a/./x", "a\\x", "a:x", None):
            with self.subTest(value=value), self.assertRaises(wf.WorkflowError): wf._safe(self.base, value)
        (self.base / "link").symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(wf.WorkflowError): wf._safe(self.base, "link/x")


if __name__ == "__main__":
    unittest.main()
