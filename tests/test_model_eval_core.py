#!/usr/bin/env python3
"""Deterministic engine checks. Never starts a provider or paid model call."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "payload/harness/scripts"
sys.path.insert(0, str(SCRIPTS))
from thinker_model_eval import core


class FakeDelegate:
    def __init__(self, session="test-session"):
        self.session = session
        self.calls = []
        self.jobs = {}
        self.fail_submit = False
        self.enabled = True

    def call(self, command, *arguments):
        self.calls.append((command, arguments))
        if command == "status":
            return {"enabled": self.enabled, "concurrency": 2, "jobs": list(self.jobs.values())}
        if command in {"route", "submit"}:
            profile = {key: arguments[arguments.index("--" + key) + 1] for key in ("provider", "model", "effort")}
            if command == "route":
                return {**profile, "routing": {"action": "delegate"}}
            if self.fail_submit:
                raise core.EvalError("Interrupted after possible provider submission")
            identifier = str(uuid.uuid4())
            self.jobs[identifier] = {"id": identifier, "session": self.session, "state": "queued", "profile": profile,
                                     "reason": arguments[arguments.index("--reason") + 1],
                                     "created_at": "2026-01-01T00:00:00+00:00"}
            return copy.deepcopy(self.jobs[identifier])
        if command == "result":
            return copy.deepcopy(self.jobs[arguments[0]])
        if command == "ack":
            return copy.deepcopy(self.jobs[arguments[0]])
        raise AssertionError(command)

    def complete(self, *, response="Bounded answer", failure=False):
        for job in self.jobs.values():
            job.update(state="failed" if failure else "completed", started_at="2026-01-01T00:00:02+00:00",
                       finished_at="2026-01-01T00:00:05+00:00",
                       transport_success=True, validation="valid",
                       result={"text": response, "model_reported": None, "usage": None, "limitations": []})


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="thinker-eval-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.suite = self.root / "suite"
        (self.suite / "cases").mkdir(parents=True)
        (self.suite / "rubrics").mkdir()
        self.data = {"schema_version": 1, "id": "synthetic", "title": "Synthetic bounded screening", "cases": []}
        for number in range(2):
            identifier = "case-" + str(number)
            (self.suite / "cases" / (identifier + ".md")).write_text("Synthetic selected prompt " + str(number), encoding="utf-8")
            rubric = {"criteria": [{"id": "evidence", "description": "Preserve evidence", "critical": True}],
                      "reference_notes": "HIDDEN-RUBRIC-ANSWER"}
            self.write(self.suite / "rubrics" / (identifier + ".json"), rubric)
            self.data["cases"].append({"id": identifier, "family": "analysis", "prompt": "cases/" + identifier + ".md",
                                       "rubric": "rubrics/" + identifier + ".json", "max_words": 20,
                                       "split": "development" if number == 0 else "holdout"})
        self.write(self.suite / "suite.json", self.data)
        self.profiles = [{"id": "profile-one", "provider": "codex", "model": "gpt-synthetic", "effort": "high"}]
        self.transport = FakeDelegate()

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def plan(self, **changes):
        options = {"identifier": "experiment", "session": "test-session", "max_calls": 4, "repeats": 2}
        options.update(changes)
        return core.plan(self.vault, self.suite, self.profiles, ["case-0", "case-1"], **options)

    def experiment(self):
        return self.vault / "drafts/model-eval/experiment"

    def trials(self):
        return core.read_json(self.experiment() / "trials.json")

    def complete(self):
        self.plan(repeats=1)
        core.run(self.vault, "experiment", self.transport)
        self.transport.complete()
        core.collect(self.vault, "experiment", self.transport)

    def test_plan_never_invokes_transport_and_freezes_exact_inputs(self):
        with patch("subprocess.run", side_effect=AssertionError("No provider allowed")):
            result = self.plan()
            manifest = core.verify(self.vault, "experiment")
        self.assertEqual(4, result["planned_calls"])
        self.assertEqual("gpt-synthetic", manifest["profiles"][0]["model"])
        self.assertEqual([1, 2, 1, 2], [t["repeat"] for t in self.trials()])
        self.assertTrue(all(t["execution_seconds"] is None for t in self.trials()))
        # Editing original suite is harmless: selected inputs were copied.
        (self.suite / "cases/case-0.md").write_text("Changed original", encoding="utf-8")
        core.verify(self.vault, "experiment")

    def test_budget_invalid_boolean_and_duplicates_leave_no_plan(self):
        for changes in ({"max_calls": 3}, {"repeats": True}, {"timeout": 0}, {"concurrency": 9}):
            with self.assertRaises(core.EvalError):
                self.plan(**changes)
        self.assertFalse(self.experiment().exists())
        with self.assertRaises(core.EvalError):
            core.plan(self.vault, self.suite, self.profiles * 2, ["case-0"], identifier="bad", max_calls=2)
        with self.assertRaises(core.EvalError):
            core.plan(self.vault, self.suite, self.profiles, [], identifier="bad", max_calls=2)

    def test_safe_paths_reject_traversal_symlinks_and_runtime_escape(self):
        self.data["cases"][0]["prompt"] = "../outside.md"
        self.write(self.suite / "suite.json", self.data)
        with self.assertRaises(core.EvalError):
            self.plan()
        self.data["cases"][0]["prompt"] = "cases/case-0.md"
        self.write(self.suite / "suite.json", self.data)
        original = self.suite / "cases/case-0.md"
        original.unlink()
        original.symlink_to(self.suite / "cases/case-1.md")
        with self.assertRaises(core.EvalError):
            self.plan()
        original.unlink()
        original.write_text("Restored prompt", encoding="utf-8")
        (self.vault / "drafts").symlink_to(self.suite, target_is_directory=True)
        with self.assertRaises(core.EvalError):
            self.plan()
        self.assertFalse((self.suite / "model-eval").exists())

    def test_prompt_rubric_alias_cross_case_and_hardlink_overlap_refused(self):
        # Even valid rubric JSON must never become execution prompt context.
        self.data["cases"][0]["prompt"] = "rubrics/case-0.json"
        self.data["cases"][0]["rubric"] = "rubrics/./case-0.json"
        self.write(self.suite / "suite.json", self.data)
        with self.assertRaises(core.EvalError):
            self.plan()
        self.data["cases"][0]["rubric"] = "rubrics/case-0.json"
        self.data["cases"][0]["prompt"] = "rubrics/case-1.json"
        self.write(self.suite / "suite.json", self.data)
        with self.assertRaises(core.EvalError):
            self.plan()
        prompt = self.suite / "cases/case-0.md"
        prompt.unlink()
        os.link(self.suite / "rubrics/case-0.json", prompt)
        self.data["cases"][0]["prompt"] = "cases/case-0.md"
        self.write(self.suite / "suite.json", self.data)
        with self.assertRaises(core.EvalError):
            self.plan()

    def test_tamper_manifest_inputs_and_context_rejected_before_calls(self):
        (self.vault / "AGENTS.md").write_text("Context baseline", encoding="utf-8")
        self.plan()
        (self.vault / "AGENTS.md").write_text("Changed context", encoding="utf-8")
        with self.assertRaises(core.EvalError):
            core.run(self.vault, "experiment", self.transport)
        self.assertFalse(self.transport.calls)
        (self.vault / "AGENTS.md").write_text("Context baseline", encoding="utf-8")
        frozen = self.experiment() / "inputs/cases/case-0.md"
        frozen.write_text("Tampered", encoding="utf-8")
        with self.assertRaises(core.EvalError):
            core.verify(self.vault, "experiment")
        frozen.write_text("Synthetic selected prompt 0", encoding="utf-8")
        manifest_path = self.experiment() / "manifest.json"
        manifest_path.write_text(manifest_path.read_text() + " ", encoding="utf-8")
        with self.assertRaises(core.EvalError):
            core.verify(self.vault, "experiment")

    def test_run_slots_resume_collect_and_no_rubric_leakage(self):
        self.plan()
        progress = core.run(self.vault, "experiment", self.transport)
        self.assertEqual(2, progress["counts"]["queued"])
        self.assertEqual(2, progress["remaining"])
        core.run(self.vault, "experiment", self.transport)
        submits = [args for cmd, args in self.transport.calls if cmd == "submit"]
        self.assertEqual(2, len(submits))
        for arguments in submits:
            prompt = arguments[arguments.index("--prompt") + 1]
            self.assertNotIn("HIDDEN-RUBRIC", prompt)
            self.assertNotIn("manifest", prompt)
            self.assertNotIn("--file", arguments)
        self.transport.complete()
        core.collect(self.vault, "experiment", self.transport)
        first = self.trials()
        core.collect(self.vault, "experiment", self.transport)
        self.assertEqual(first, self.trials())
        self.assertEqual(3.0, first[0]["execution_seconds"])
        self.assertEqual(2.0, first[0]["queue_seconds"])
        self.assertIsNone(first[0]["model_reported"])
        self.assertIsNone(first[0]["cost_estimate"])
        self.assertEqual("unknown", first[0]["trajectory"]["status"])
        core.run(self.vault, "experiment", self.transport)
        self.assertEqual(4, len([1 for cmd, args in self.transport.calls if cmd == "submit"]))

    def test_ambiguous_submit_never_retried(self):
        self.plan()
        self.transport.fail_submit = True
        result = core.run(self.vault, "experiment", self.transport)
        self.assertTrue(result["blocked"])
        self.assertEqual("submitting", self.trials()[0]["status"])
        self.transport.fail_submit = False
        core.run(self.vault, "experiment", self.transport)
        self.assertEqual(1, len([1 for cmd, args in self.transport.calls if cmd == "submit"]))

    def test_failure_drains_existing_jobs_and_blocks_new(self):
        self.plan()
        core.run(self.vault, "experiment", self.transport)
        self.transport.complete()
        next(iter(self.transport.jobs.values()))["state"] = "timed_out"
        result = core.run(self.vault, "experiment", self.transport)
        self.assertTrue(result["blocked"])
        self.assertEqual(1, result["counts"]["completed"])
        self.assertEqual(2, result["remaining"])
        self.assertEqual(2, len([1 for cmd, args in self.transport.calls if cmd == "submit"]))

    def test_malformed_result_is_not_promoted_and_recovered_collect_clears_error(self):
        self.plan()
        core.run(self.vault, "experiment", self.transport)
        self.transport.complete()
        job = next(iter(self.transport.jobs.values()))
        job["result"]["text"] = {"malformed": True}
        core.collect(self.vault, "experiment", self.transport)
        self.assertEqual("queued", self.trials()[0]["status"])
        self.assertIsNone(self.trials()[0]["response"])
        self.assertIn("collection_error", self.trials()[0])
        job["result"]["text"] = "Recovered result"
        core.collect(self.vault, "experiment", self.transport)
        self.assertEqual("completed", self.trials()[0]["status"])
        self.assertNotIn("collection_error", self.trials()[0])

    def test_completed_missing_artifact_or_forged_checks_refused(self):
        self.complete()
        original = self.trials()
        for changes in ({"response": None}, {"response": " "}, {"checks": {"nonempty": False, "word_limit": True}}):
            trials = copy.deepcopy(original)
            trials[0].update(changes)
            self.write(self.experiment() / "trials.json", trials)
            with self.assertRaises(core.EvalError):
                core.blind(self.vault, "experiment")
            with self.assertRaises(core.EvalError):
                core.report(self.vault, "experiment")

    def test_unknown_transport_is_unresolved_instead_of_success(self):
        self.plan()
        core.run(self.vault, "experiment", self.transport)
        self.transport.complete()
        job = next(iter(self.transport.jobs.values()))
        job.pop("validation")
        core.collect(self.vault, "experiment", self.transport)
        self.assertEqual("queued", self.trials()[0]["status"])
        self.assertIn("collection_error", self.trials()[0])
        self.assertEqual(1, core.blind(self.vault, "experiment")["count"])

    def test_planned_reset_or_duplicate_job_cannot_resubmit(self):
        self.complete()
        original = self.trials()
        for change in ("planned", "duplicate"):
            trials = copy.deepcopy(original)
            if change == "planned":
                trials[0]["status"] = "planned"
            else:
                trials[1]["job_id"] = trials[0]["job_id"]
            self.write(self.experiment() / "trials.json", trials)
            with self.assertRaises(core.EvalError):
                core.run(self.vault, "experiment", self.transport)

    def test_disabled_delegation_no_activation_or_model_calls(self):
        self.plan()
        self.transport.enabled = False
        with self.assertRaises(core.EvalError):
            core.run(self.vault, "experiment", self.transport)
        self.assertEqual(["status"], [c for c, args in self.transport.calls])

    def test_concurrent_runs_do_not_duplicate_submission(self):
        self.plan()
        failures = []
        def execute():
            try:
                core.run(self.vault, "experiment", self.transport)
            except Exception as error:
                failures.append(error)
        threads = [threading.Thread(target=execute) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(failures)
        self.assertEqual(2, len(self.transport.jobs))

    def test_mutable_trial_mapping_refused(self):
        self.plan()
        trials = self.trials()
        trials[1]["id"] = trials[0]["id"]
        self.write(self.experiment() / "trials.json", trials)
        with self.assertRaises(core.EvalError):
            core.run(self.vault, "experiment", self.transport)
        self.assertFalse(self.transport.calls)

    def test_blind_packet_excludes_identity_and_is_stable(self):
        self.complete()
        result = core.blind(self.vault, "experiment")
        packet = core.read_json(result["packet"])
        for record in packet:
            self.assertEqual({"blind_id", "prompt", "rubric", "response"}, set(record))
            self.assertNotIn("gpt-synthetic", json.dumps(record))
        core.blind(self.vault, "experiment")
        self.assertEqual(packet, core.read_json(result["packet"]))

    def test_immutable_assessments_and_human_feedback_separate(self):
        self.complete()
        trial = self.trials()[0]
        grade = {"blind_id": trial["blind_id"], "evaluator": "principal", "quality": 3,
                 "id": "grade-first", "critical_failures": [], "notes": "Evidence preserved", "evidence": ["Bounded answer"],
                 "criteria": [{"id": "evidence", "status": "pass", "evidence": ["Bounded answer"]}],
                 "evaluator_config": {"kind": "human"}, "conflict_of_authorship": False,
                 "rubric_version": core.verify(self.vault, "experiment")["cases"][0]["rubric_version"]}
        source = self.root / "grade.json"
        self.write(source, [grade])
        core.import_assessments(self.vault, "experiment", "grade", source)
        self.assertEqual([], core.read_json(self.experiment() / "feedback.json"))
        with self.assertRaises(core.EvalError):
            core.import_assessments(self.vault, "experiment", "grade", source)
        for changes in ({"quality": True}, {"quality": float("nan")}, {"notes": " "}, {"evidence": []}, {"trial_id": "missing", "blind_id": None}):
            invalid = {**grade, **changes, "evaluator": "different"}
            self.write(source, [invalid])
            with self.assertRaises(core.EvalError):
                core.import_assessments(self.vault, "experiment", "grade", source)
        feedback = {"trial_id": trial["id"], "reviewer": "human", "preference": "revise", "review_minutes": None,
                    "corrections": None, "notes": "Explicit human judgment"}
        self.write(source, [feedback])
        core.import_assessments(self.vault, "experiment", "feedback", source)
        audit = {"trial_id": trial["id"], "evaluator": "audit", "status": "pass", "violations": [],
                 "notes": "Audited observable tool events"}
        self.write(source, [audit])
        core.import_assessments(self.vault, "experiment", "trajectory", source)
        self.assertEqual("unknown", self.trials()[0]["trajectory"]["status"])

    def test_cli_plan_and_verify_only_no_provider_process(self):
        profiles = self.root / "profiles.json"
        self.write(profiles, self.profiles)
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "model-eval.py"), "--vault", str(self.vault), "--json",
                                 "plan", "--suite", str(self.suite), "--profiles-file", str(profiles), "--case", "case-0",
                                 "--max-calls", "1", "--id", "cli"], capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, json.loads(result.stdout)["planned_calls"])
        core.verify(self.vault, "cli")

    def test_new_plans_enforce_high_and_inventory_refreshes_without_model_calls(self):
        for effort in ("low", "medium"):
            self.profiles[0]["effort"] = effort
            with self.assertRaises(core.EvalError):
                self.plan()
        self.profiles[0]["effort"] = "high"
        from thinker_delegation import adapters
        with patch.dict(adapters.PROFILES, {"new-profile": ("codex", "gpt-new-profile", "low")}):
            with patch("subprocess.run", side_effect=AssertionError("No model/CLI execution")):
                result = core.inventory(self.vault, self.profiles)
            indexed = {p["id"]: p for p in result["profiles"]}
            self.assertIn("new-profile", indexed)
            self.assertIn("profile-one", indexed)
            self.assertTrue(all(p["effort"] == "high" for p in result["profiles"]))
            self.assertTrue(all(p["availability"]["model_access"] == "unknown" for p in result["profiles"]))

    def test_doctor_only_observes_interface_and_unavailable_not_scored(self):
        class Doctor:
            def call(inner, command, *args):
                self.assertEqual("doctor", command)
                from thinker_delegation import adapters
                model = adapters.resolve_profile(explicit="luna", effort="high")["model"]
                return {"providers": [{"profile": "luna", "ready": True, "cli_version": "synthetic", "provider": "codex", "model_requested": model},
                                      {"profile": "grok", "ready": False, "error": "Synthetic incompatible CLI"}]}
        result = core.inventory(self.vault, doctor=True, transport=Doctor())
        indexed = {p["id"]: p for p in result["profiles"]}
        self.assertEqual("unknown", indexed["luna"]["availability"]["model_access"])
        self.assertFalse(indexed["grok"]["eligible"])
        unavailable = {"id": "excluded", "provider": "codex", "model": "gpt-excluded", "effort": "high",
                       "availability": {"interface": "unavailable", "model_access": "unknown", "effort_support": "unknown",
                                        "reason": "Synthetic CLI unavailable", "observed_at": "2026-01-01T00:00:00Z"}}
        self.profiles.append(unavailable)
        planned = self.plan()
        self.assertEqual(4, planned["planned_calls"])
        self.assertEqual(8, planned["inventory_trials"])
        self.assertEqual(4, sum(t["status"] == "unavailable" for t in self.trials()))
        core.run(self.vault, "experiment", self.transport)
        self.assertTrue(all(job["profile"]["model"] == "gpt-synthetic" for job in self.transport.jobs.values()))
        self.assertEqual([], core.read_json(self.experiment() / "grades.json"))

    def test_declared_large_prompt_and_policy_frozen_limits(self):
        (self.suite / "cases/case-0.md").write_text("context " * 1100, encoding="utf-8")
        with self.assertRaises(core.EvalError):
            self.plan()
        self.data["max_prompt_bytes"] = 20000
        self.write(self.suite / "suite.json", self.data)
        policy = {"comparison_policy": {"quality_margin": 1, "execution_seconds_margin": 15},
                  "action_weights": {"analysis": 2}, "minimum_requested_effort": "high"}
        self.plan(policy=policy)
        manifest = core.verify(self.vault, "experiment")
        self.assertEqual(20000, manifest["cases"][0]["max_prompt_bytes"])
        self.assertEqual(policy["comparison_policy"], manifest["comparison_policy"])
        self.assertFalse(manifest["evaluation_policy"]["allow_automatic_retry"])
        with self.assertRaises(core.EvalError):
            core.validate_policy({"allow_silent_downgrade": True})
        with self.assertRaises(core.EvalError):
            core.validate_policy({"action_weights": {"analysis": float("nan")}})
        with self.assertRaises(core.EvalError):
            core.validate_policy({"action_weights": {"analysis": 0}})
        with self.assertRaises(core.EvalError):
            core.validate_policy({"comparison_policy": {"personal_time_margin_minutes": True}})
        personal = core.validate_policy({"action_weights": {"analysis": 1}, "comparison_policy": {"personal_time_margin_minutes": 3}})
        self.assertEqual(3, personal["comparison_policy"]["personal_time_margin_minutes"])

    def grade(self, identifier="grade-first", **changes):
        trial = self.trials()[0]
        record = {"trial_id": trial["id"], "id": identifier, "evaluator": "principal", "quality": 2,
                  "critical_failures": [], "notes": "Observed partial answer", "evidence": ["Bounded answer"],
                  "criteria": [{"id": "evidence", "status": "partial", "evidence": ["Bounded answer"]}],
                  "evaluator_config": {"kind": "human"}, "conflict_of_authorship": False,
                  "rubric_version": core.verify(self.vault, "experiment")["cases"][0]["rubric_version"]}
        return {**record, **changes}

    def test_grade_revisions_same_evaluator_and_invalid_batch_is_atomic(self):
        self.complete()
        source = self.root / "grades-v2.json"
        self.write(source, [self.grade()])
        core.import_assessments(self.vault, "experiment", "grade", source)
        correction = self.grade("grade-corrected", supersedes="grade-first", quality=4,
                                criteria=[{"id": "evidence", "status": "pass", "evidence": ["Bounded answer"]}])
        self.write(source, [correction])
        core.import_assessments(self.vault, "experiment", "grade", source)
        history = core.read_json(self.experiment() / "grades.json")
        self.assertEqual([2, 4], [g["quality"] for g in history])
        self.assertEqual(["principal", "principal"], [g["evaluator"] for g in history])
        for changes in ({"supersedes": "grade-first"}, {"evaluator": "someone-else"},
                        {"evaluator_config": {"kind": "model", "provider": "codex", "model": "gpt-judge", "effort": "high"}}):
            invalid = {**correction, "id": "grade-third", **changes}
            self.write(source, [invalid])
            with self.assertRaises(core.EvalError):
                core.import_assessments(self.vault, "experiment", "grade", source)
            self.assertEqual(history, core.read_json(self.experiment() / "grades.json"))
        valid = {**correction, "id": "grade-third", "supersedes": "grade-corrected"}
        self.write(source, [valid, {**valid, "id": "bad-fourth", "supersedes": "unknown"}])
        with self.assertRaises(core.EvalError):
            core.import_assessments(self.vault, "experiment", "grade", source)
        self.assertEqual(history, core.read_json(self.experiment() / "grades.json"))

    def test_new_grades_require_literal_criteria_and_high_judge_configuration(self):
        self.complete()
        source = self.root / "grade-invalid.json"
        variants = ({"quality": 3.2}, {"id": ""}, {"rubric_version": "wrong"}, {"criteria": []},
                    {"criteria": [{"id": "evidence", "status": "pass", "evidence": ["invented quotation"]}]},
                    {"evaluator_config": {"kind": "model", "provider": "codex", "model": "gpt-judge", "effort": "medium"}})
        for changes in variants:
            self.write(source, [self.grade(**changes)])
            with self.assertRaises(core.EvalError):
                core.import_assessments(self.vault, "experiment", "grade", source)
        self.assertEqual([], core.read_json(self.experiment() / "grades.json"))

    def test_legacy_grades_readable_under_new_engine(self):
        self.complete()
        manifest = core.verify(self.vault, "experiment")
        manifest.pop("assessment_schema_version")
        self.write(self.experiment() / "manifest.json", manifest)
        (self.experiment() / "manifest.sha256").write_text(core._digest((self.experiment() / "manifest.json").read_bytes()) + "\n")
        source = self.root / "legacy.json"
        self.write(source, [{"trial_id": "t0001", "evaluator": "original", "quality": 3.5,
                             "critical_failures": [], "notes": "Legacy appraisal", "evidence": ["Historical evidence"]}])
        core.import_assessments(self.vault, "experiment", "grade", source)
        self.assertTrue(core.read_json(self.experiment() / "grades.json")[0]["id"].startswith("legacy-"))

    def test_human_effort_metrics_do_not_infer_acceptance(self):
        self.complete()
        source = self.root / "human.json"
        record = {"trial_id": "t0001", "reviewer": "human", "preference": "use", "notes": "Explicit review", "corrections": 1,
                  "review_minutes": 3, "preparation_minutes": 2, "integration_minutes": 4, "total_minutes": None,
                  "accepted_delivery_minutes": None}
        self.write(source, [record])
        core.import_assessments(self.vault, "experiment", "feedback", source)
        stored = core.read_json(self.experiment() / "feedback.json")[0]
        self.assertIsNone(stored["total_minutes"])
        self.assertNotIn("acceptance", stored)
        self.write(source, [{**record, "reviewer": "other", "accepted_delivery_minutes": 10}])
        with self.assertRaises(core.EvalError):
            core.import_assessments(self.vault, "experiment", "feedback", source)

    def test_pairwise_balanced_blind_packets_and_explicit_human_import(self):
        self.profiles.append({"id": "profile-two", "provider": "codex", "model": "gpt-other", "effort": "high"})
        self.plan(repeats=1)
        for _ in range(2):
            core.run(self.vault, "experiment", self.transport)
            self.transport.complete()
            core.collect(self.vault, "experiment", self.transport)
        result = core.pairwise(self.vault, "experiment")
        packet = core.read_json(result["packet"])
        self.assertEqual(4, len(packet))
        self.assertTrue(all(set(p) == {"pair_id", "prompt", "response_a", "response_b"} for p in packet))
        source = self.root / "pair-feedback.json"
        record = {"id": "human-pair-1", "pair_id": packet[0]["pair_id"], "reviewer": "human", "preference": "a",
                  "notes": "Explicit preference based on original answers", "review_minutes": None}
        self.write(source, [record])
        core.import_pairwise(self.vault, "experiment", source)
        observed = core.read_json(self.experiment() / "pairwise-feedback.json")
        self.assertEqual("profile_a", observed[0]["preference"])
        with self.assertRaises(core.EvalError):
            core.import_pairwise(self.vault, "experiment", source)

    def workflow(self):
        (self.suite / "workflows").mkdir()
        (self.suite / "fixtures").mkdir()
        (self.suite / "fixtures/input.md").write_text("Protected source: action authorized", encoding="utf-8")
        spec = {"schema_version": 1, "id": "host-case", "workspace": [{"path": "archive/input.md", "source": "fixtures/input.md"}],
                "writable": ["deliverables"], "artifacts": ["deliverables/result.json"],
                "checks": [{"id": "decision", "kind": "json", "path": "deliverables/result.json",
                            "assertions": [{"pointer": "/decision", "equals": "act"}]}]}
        self.write(self.suite / "workflows/host-case.json", spec)
        self.data["cases"][0]["workflow"] = "workflows/host-case.json"
        self.write(self.suite / "suite.json", self.data)

    def prepare_trial(self):
        result = core.prepare(self.vault, "experiment", "t0001")
        self.addCleanup(shutil.rmtree, result["workflow"]["workspace"], ignore_errors=True)
        return result

    def test_host_workflow_prepare_finish_observes_real_artifact_without_model_calls(self):
        self.workflow()
        self.plan()
        with patch("subprocess.run", side_effect=AssertionError("No model/code call allowed")):
            prepared = self.prepare_trial()
            self.assertIn("Synthetic selected prompt", prepared["workflow"]["case_prompt"])
            self.assertNotIn("HIDDEN-RUBRIC", json.dumps(prepared))
            workspace = Path(prepared["workflow"]["workspace"])
            self.write(workspace / "deliverables/result.json", {"decision": "act"})
            finished = core.finish(self.vault, "experiment", "t0001")
        self.assertEqual("completed", finished["status"])
        self.assertEqual("pass", finished["workflow"]["final_state_checks"]["status"])
        trial = core._load_trials(self.experiment(), core.verify(self.vault, "experiment"))[0]
        self.assertTrue(trial["host_result"])
        self.assertIsNone(trial["model_reported"])
        self.assertIsNone(trial["response"])
        self.assertEqual("unknown", trial["trajectory"]["status"])
        exported = core.artifact_texts(self.experiment(), trial)
        self.assertEqual("deliverables/result.json", exported[0]["name"])
        self.assertIn('"decision": "act"', exported[0]["text"])
        packet = core.read_json(core.blind(self.vault, "experiment")["packet"])
        self.assertIsNone(packet[0]["response"])
        self.assertEqual(exported, packet[0]["artifacts"])
        quote = '"decision": "act"'
        source = self.root / "artifact-grade.json"
        grade = self.grade(evidence=[quote], criteria=[{"id": "evidence", "status": "pass", "evidence": [quote]}])
        self.write(source, [grade])
        core.import_assessments(self.vault, "experiment", "grade", source)
        self.assertEqual(1, len(core.read_json(self.experiment() / "grades.json")))
        artifact = trial["artifacts"][0]
        (self.experiment() / artifact["path"]).write_text("Tampered captured outcome", encoding="utf-8")
        with self.assertRaises(core.EvalError):
            core.report(self.vault, "experiment")

    def test_host_workflow_run_never_submits_host_case_and_reset_is_refused(self):
        self.workflow()
        self.plan()
        core.run(self.vault, "experiment", self.transport)
        submitted_ids = [t["case_id"] for t in self.trials() if t.get("job_id")]
        self.assertEqual(["case-1", "case-1"], submitted_ids)
        self.prepare_trial()
        with self.assertRaises(core.EvalError):
            core.prepare(self.vault, "experiment", "t0001")

    def test_workflow_fixture_cannot_alias_hidden_rubric_or_hidden_test(self):
        self.workflow()
        fixture = self.suite / "fixtures/input.md"
        fixture.unlink()
        os.link(self.suite / "rubrics/case-1.json", fixture)
        with self.assertRaises(core.EvalError):
            self.plan()
        fixture.unlink()
        fixture.write_text("Protected source", encoding="utf-8")
        hidden = self.suite / "fixtures/hidden.json"
        os.link(fixture, hidden)
        spec_path = self.suite / "workflows/host-case.json"
        spec = core.read_json(spec_path)
        spec["checks"].append({"id": "hidden", "kind": "python-unittest", "source": "fixtures/hidden.json"})
        self.write(spec_path, spec)
        with self.assertRaises(core.EvalError):
            self.plan()

    def test_inventory_doctor_cannot_certify_an_explicit_alias_override(self):
        from thinker_delegation import adapters
        class Doctor:
            def call(inner, command, *args):
                actual = adapters.resolve_profile(explicit="luna", effort="high")
                return {"providers": [{"profile": "luna", "ready": True, "provider": actual["provider"], "model_requested": actual["model"]}]}
        overridden = {"id": "luna", "provider": "claude", "model": "different-model", "effort": "high"}
        result = core.inventory(self.vault, [overridden], doctor=True, transport=Doctor())
        profile = next(p for p in result["profiles"] if p["id"] == "luna")
        self.assertEqual("unknown", profile["availability"]["interface"])

    def test_host_known_configuration_mismatch_preserved_without_score(self):
        self.workflow()
        self.plan()
        prepared = self.prepare_trial()
        self.write(Path(prepared["workflow"]["workspace"]) / "deliverables/result.json", {"decision": "act"})
        core.finish(self.vault, "experiment", "t0001", identity={"model": "different-observed-model"})
        trial = self.trials()[0]
        self.assertEqual("failed", trial["status"])
        self.assertEqual("infrastructure", trial["failure_kind"])
        self.assertEqual("different-observed-model", trial["model_reported"])
        self.assertTrue(trial["configuration_mismatch"])
        self.assertEqual([], core.read_json(self.experiment() / "grades.json"))

    def test_host_timing_requires_observed_provenance_timezone_and_order(self):
        self.workflow()
        self.plan()
        prepared = self.prepare_trial()
        self.write(Path(prepared["workflow"]["workspace"]) / "deliverables/result.json", {"decision": "act"})
        trace = {"source": "host-observed", "events": [], "started_at": "2026-01-01T01:00:00Z", "finished_at": "2026-01-01T01:00:12Z", "queue_seconds": 3}
        for changes in ({"source": "candidate-self-report"}, {"finished_at": "2025-01-01T01:00:12Z"},
                        {"started_at": "2026-01-01T01:00:00"}, {"queue_seconds": True}, {"queue_seconds": float("nan")}):
            with self.assertRaises(core.EvalError):
                core.finish(self.vault, "experiment", "t0001", observed_trace={**trace, **changes})
            self.assertEqual("prepared", self.trials()[0]["status"])
        core.finish(self.vault, "experiment", "t0001", observed_trace=trace)
        self.assertEqual(12, self.trials()[0]["execution_seconds"])
        self.assertEqual(3, self.trials()[0]["queue_seconds"])
        self.assertEqual("host_observed_declared", self.trials()[0]["timing_provenance"])

    def ambiguous_submission(self):
        self.plan()
        original_call = self.transport.call
        def call(command, *arguments):
            result = original_call(command, *arguments)
            if command == "submit":
                result["session"] = "malformed-submit-session"
            return result
        self.transport.call = call
        core.run(self.vault, "experiment", self.transport)
        self.transport.call = original_call
        self.assertEqual("submitting", self.trials()[0]["status"])
        self.assertIsNone(self.trials()[0]["job_id"])
        self.assertTrue(self.trials()[0]["submitted_job_id"])
        return self.trials()[0]["submitted_job_id"]

    def test_reconcile_existing_submission_binds_validated_result_without_retry(self):
        job_id = self.ambiguous_submission()
        self.transport.complete()
        before_submits = sum(command == "submit" for command, args in self.transport.calls)
        result = core.reconcile(self.vault, "experiment", "t0001", "bind", "Verified existing supervisor receipt", transport=self.transport)
        self.assertEqual("completed", result["status"])
        self.assertEqual(0, result["model_calls"])
        self.assertEqual(job_id, self.trials()[0]["job_id"])
        self.assertTrue(self.trials()[0]["acknowledged"])
        self.assertEqual(before_submits, sum(command == "submit" for command, args in self.transport.calls))
        history = core.read_json(self.experiment() / "reconciliations.json")
        self.assertEqual(1, len(history))
        self.assertEqual("submitting", history[0]["previous_status"])
        self.assertEqual("bind", history[0]["action"])
        with self.assertRaises(core.EvalError):
            core.reconcile(self.vault, "experiment", "t0001", "bind", "Must not replay", transport=self.transport)

    def test_reconcile_refuses_wrong_session_profile_trial_reason_and_invalid_result(self):
        job_id = self.ambiguous_submission()
        self.transport.complete()
        original = copy.deepcopy(self.transport.jobs[job_id])
        for changes in ({"session": "foreign-session"}, {"reason": "Frozen model evaluation experiment trial t0002; no retry"},
                        {"profile": {"provider": "codex", "model": "gpt-other", "effort": "high"}},
                        {"reason": None}, {"result": {"text": None}}, {"validation": None}):
            self.transport.jobs[job_id] = {**original, **changes}
            with self.assertRaises(core.EvalError):
                core.reconcile(self.vault, "experiment", "t0001", "bind", "Explicit verification attempt", transport=self.transport)
            self.assertEqual("submitting", self.trials()[0]["status"])
            self.assertEqual([], core.read_json(self.experiment() / "reconciliations.json"))
        self.assertFalse(any(command == "ack" for command, args in self.transport.calls))

    def test_reconcile_abandon_retains_partial_workspace_and_captures_across_environment_drift(self):
        self.workflow()
        self.plan()
        prepared = self.prepare_trial()
        workspace = Path(prepared["workflow"]["workspace"])
        self.write(workspace / "deliverables/result.json", {"decision": "act"})
        partial = self.experiment() / "workflow-artifacts/t0001/partial.json"
        partial.parent.mkdir(parents=True)
        self.write(partial, {"partial_capture": True})
        trials = self.trials()
        trials[0]["status"] = "finishing"
        self.write(self.experiment() / "trials.json", trials)
        (self.vault / "AGENTS.md").write_text("New environment after update", encoding="utf-8")
        with patch("subprocess.run", side_effect=AssertionError("Abandon must start no process")):
            result = core.reconcile(self.vault, "experiment", "t0001", "abandon", "Close interrupted capture after upgrade")
        self.assertEqual("interrupted", result["status"])
        self.assertTrue(result["environment_drift"])
        self.assertTrue(partial.is_file())
        self.assertTrue((workspace / "deliverables/result.json").is_file())
        self.assertEqual("operational", self.trials()[0]["failure_kind"])
        self.assertEqual("finishing", core.read_json(self.experiment() / "reconciliations.json")[0]["previous_status"])
        with self.assertRaises(core.EvalError):
            core.prepare(self.vault, "experiment", "t0001")

    def test_reconcile_unknown_submit_abandon_keeps_unresolved_receipt_and_never_acks(self):
        job_id = self.ambiguous_submission()
        before = len(self.transport.calls)
        result = core.reconcile(self.vault, "experiment", "t0001", "abandon", "Close ambiguous attempt without inventing ownership", transport=self.transport)
        self.assertEqual(job_id, result["unresolved_delegate_job"])
        self.assertEqual(before, len(self.transport.calls))
        self.assertEqual("interrupted", self.trials()[0]["status"])
        self.assertIsNone(self.trials()[0]["job_id"])

    def test_host_result_cannot_bypass_text_trial_job_requirement(self):
        self.plan()
        trials = self.trials()
        trials[0].update(status="completed", host_result=True, final_state_checks={"status": "pass", "checks": []}, artifacts=[])
        self.write(self.experiment() / "trials.json", trials)
        with self.assertRaises(core.EvalError):
            core.report(self.vault, "experiment")
        with self.assertRaises(core.EvalError):
            core.blind(self.vault, "experiment")


if __name__ == "__main__":
    unittest.main()
