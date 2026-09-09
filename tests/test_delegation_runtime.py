#!/usr/bin/env python3
"""Lifecycle tests use copied runtime + fake adapters; never invoke model CLIs."""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "payload/harness/scripts"))
from thinker_delegation import adapters as real_adapters, routing

SOURCE = Path(__file__).resolve().parents[1] / "payload/harness/scripts/thinker_delegation/runtime.py"
FAKE_ADAPTER = '''import json, os, sys, time
from pathlib import Path
def build_command(profile, workspace, prompt_path):
    if profile.get("build_delay"):
        (Path(workspace) / "preflight-started").write_text("started")
        time.sleep(profile["build_delay"])
    code = "import json,time; time.sleep(" + repr(profile.get("delay", 0)) + "); print(" + repr(json.dumps({"text": profile.get("answer", "A reviewable proposal"), "model_reported": profile["model"], "usage": {"input_tokens": 7}, "session_id": "fake-session", "limitations": []})) + ")"
    if profile.get("fail"): code = "raise SystemExit(7)"
    if profile.get("child_marker"):
        code = "from pathlib import Path; Path(" + repr(profile["child_marker"]) + ").write_text('launched'); " + code
    return [sys.executable, "-c", code]
def safe_env(profile): return dict(os.environ)
def parse_result(profile, stdout, stderr, returncode): return json.loads(stdout)
'''


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="delegation-runtime-")
        self.root = Path(self.temporary.name).resolve()
        self.vault = self.root / "vault"
        self.vault.mkdir()
        (self.vault / "drafts").mkdir()
        (self.vault / "drafts/live.md").write_text("Human draft v1\n", encoding="utf-8")
        (self.vault / "AGENTS.md").write_text("Preserve originals.\n", encoding="utf-8")
        package = self.root / "fake-runtime"
        package.mkdir()
        shutil.copy(SOURCE, package / "runtime.py")
        (package / "adapters.py").write_text(FAKE_ADAPTER, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("fake_delegation_runtime", package / "runtime.py")
        self.runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runtime)
        self.state = self.root / "state"
        self.store = self.runtime.DelegationStore(self.vault, self.state)
        self.profile = {"provider": "fake", "model": "explicit-test-model", "effort": "low"}

    def tearDown(self):
        if self.state.exists():
            try:
                self.store.configure(enabled=False)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if all(job["state"] in self.runtime.TERMINAL for job in self.store.list_jobs()):
                        break
                    time.sleep(0.05)
            except self.runtime.DelegationError:
                pass
        self.temporary.cleanup()

    def enable(self, concurrency=2):
        self.store.configure(enabled=True, concurrency=concurrency)
        self.store.set_session("host-a", True, "auto")

    def submit(self, **kwargs):
        return self.store.submit("host-a", self.profile, "Review this draft; no original edits", ["drafts/live.md"], **kwargs)

    def wait(self, identifier, state=None, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.store.get(identifier)
            if job["state"] == state or (state is None and job["state"] in self.runtime.TERMINAL):
                return job
            time.sleep(0.03)
        self.fail(f"Job did not reach {state or 'terminal'} state: {job['state']}")

    def test_default_availability_does_not_create_state_or_launch(self):
        with mock.patch.object(self.runtime.subprocess, "Popen") as launch:
            status = self.store.status("host-a")
            self.assertTrue(status["enabled"])
            self.assertFalse(status["session_explicit"])
            self.assertEqual("auto", status["mode"])
            self.assertEqual([], self.store.list_jobs())
            launch.assert_not_called()
        self.assertFalse(self.state.exists())

    def test_session_requires_global_on_and_global_off_dominates(self):
        self.store.set_session("host-a", False)
        self.assertFalse(self.store.status("host-a")["enabled"])
        self.store.configure(enabled=True)
        self.assertFalse(self.store.status("host-a")["enabled"])
        self.store.set_session("host-a", True)
        status = self.store.status("host-a")
        self.assertTrue(status["enabled"])
        self.assertEqual(6, status["max_calls_session"])
        self.assertEqual(4, status["max_calls_provider"])
        self.store.configure(enabled=False)
        self.assertFalse(self.store.status("host-a")["enabled"])

    def test_global_off_revokes_all_sessions_before_one_is_reenabled(self):
        self.enable()
        self.store.set_session("host-a", True, profile="sonnet")
        self.store.set_session("host-b", True, "auto", profile="luna")
        self.store.configure(enabled=False)
        for session in ("host-a", "host-b"):
            self.assertFalse(self.store.status(session)["enabled"])
            self.assertFalse(self.store.status(session)["session_enabled"])
        self.store.configure(enabled=True)
        self.store.set_session("host-a", True)
        self.assertTrue(self.store.status("host-a")["enabled"])
        self.assertFalse(self.store.status("host-b")["enabled"])
        self.assertFalse(self.store.status("host-b")["session_enabled"])
        self.assertEqual("sonnet", self.store.status("host-a")["profile"])
        self.assertEqual("luna", self.store.status("host-b")["profile"])

    def test_legacy_global_off_remains_off_without_status_writes(self):
        self.state.mkdir()
        config = self.state / "config.json"
        config.write_text('{"enabled":false,"concurrency":2,"sessions":{}}')
        before = config.read_bytes()
        status = self.store.status("legacy")
        self.assertFalse(status["enabled"])
        self.assertFalse(status["session_enabled"])
        self.assertEqual(before, config.read_bytes())

    def test_submit_stores_bounded_explicit_routing_decision_without_identity_inference(self):
        self.enable()
        selected = real_adapters.resolve_profile("review")
        host = routing.principal("codex", "luna", "low")
        decision = routing.decide(selected, "review", host=host,
                                  benefit="independent critique", independent=True,
                                  quota={"availability": "available", "expires_at": 101}, now=100)
        job = self.wait(self.submit(routing=decision)["id"])
        self.assertEqual(decision, job["routing"])
        self.assertEqual("declared_not_verified", job["routing"]["principal_identity"])
        self.assertEqual("available", job["routing"]["quota"])

    def test_explicit_model_snapshot_and_output_isolation(self):
        self.enable()
        job = self.wait(self.submit(model_source="override", reason="bounded review")["id"])
        self.assertEqual("completed", job["state"])
        self.assertEqual("valid", job["validation"])
        self.assertEqual("pending", job["acceptance"])
        self.assertEqual("unknown", job["feedback"])
        self.assertEqual("explicit-test-model", job["result"]["model_reported"])
        self.assertEqual("override", job["model_source"])
        self.assertEqual("AGENTS.md", job["snapshot"]["instructions"][0]["path"])
        self.assertEqual("Human draft v1\n", (self.vault / "drafts/live.md").read_text())
        self.assertFalse((self.vault / "drafts/delegation").exists())
        self.assertFalse((self.state / "jobs" / job["id"] / ".stdout").exists())

    def test_empty_transport_success_is_invalid_and_not_acceptable(self):
        self.enable()
        self.profile["answer"] = "  "
        job = self.wait(self.submit()["id"])
        self.assertTrue(job["transport_success"])
        self.assertEqual("invalid", job["validation"])
        with self.assertRaises(self.runtime.DelegationError):
            self.store.accept(job["id"])

    def test_provider_failure_is_not_transport_success(self):
        self.enable()
        self.profile["fail"] = True
        job = self.wait(self.submit()["id"])
        self.assertEqual("failed", job["state"])
        self.assertFalse(job["transport_success"])
        self.assertNotIn("result", job)
        self.assertEqual("provider_command_failed", job["error_code"])

    def test_call_caps_are_atomic_and_bound_session_and_provider(self):
        self.enable()
        for number in range(4):
            self.store.submit("host-a", self.profile, f"Independent review {number}")
        with self.assertRaisesRegex(self.runtime.DelegationError, "Provider call cap"):
            self.store.submit("host-a", self.profile, "Different fifth fake provider call")
        other = {**self.profile, "provider": "other"}
        self.store.submit("host-a", other, "Other provider one")
        self.store.submit("host-a", other, "Other provider two")
        with self.assertRaisesRegex(self.runtime.DelegationError, "Session call cap"):
            self.store.submit("host-a", other, "Other provider three")

    def test_failed_attempts_need_diagnostic_reason_and_infrastructure_blocks_provider(self):
        self.enable()
        self.store.configure(max_calls_provider=6)
        self.profile["fail"] = True
        original = self.wait(self.submit()["id"])
        with self.assertRaisesRegex(self.runtime.DelegationError, "identical failed"):
            self.submit()
        with self.assertRaisesRegex(self.runtime.DelegationError, "explicit diagnostic"):
            self.store.retry(original["id"])
        current_routing = routing.decide(real_adapters.resolve_profile("review"), "review",
                                         benefit="independent retry review", independent=True)
        retried = self.store.retry(original["id"], reason="confirmed transient provider incident",
                                   routing=current_routing)
        self.assertEqual(current_routing, retried["routing"])
        self.assertEqual("failed", self.wait(retried["id"])["state"])

        adapter = self.root / "fake-runtime/adapters.py"
        adapter.write_text(FAKE_ADAPTER + '''
def diagnose_failure(profile, stdout, stderr, returncode):
    return {"code": "provider_limit", "message": "PRIVATE PROVIDER LOG"}
''')
        self.profile["fail"] = True
        limited = self.wait(self.store.submit("host-a", self.profile, "A distinct request")["id"])
        self.assertEqual("provider_limit", limited["error_code"])
        self.profile["fail"] = False
        with self.assertRaisesRegex(self.runtime.DelegationError, "Provider is blocked"):
            self.store.submit("host-a", self.profile, "Whitespace cannot bypass this distinct request")
        allowed = self.store.submit("host-a", self.profile, "Explicitly reviewed new request",
                                    retry_reason="quota was checked and is available")
        allowed = self.wait(allowed["id"])
        self.assertEqual("completed", allowed["state"])
        self.assertEqual("quota was checked and is available", allowed["retry_reason"])
        followup = self.store.submit("host-a", self.profile, "Provider is healthy after reviewed retry")
        self.assertEqual("completed", self.wait(followup["id"])["state"])

    def test_parse_failure_with_zero_exit_uses_sanitized_provider_diagnosis(self):
        adapter = self.root / "fake-runtime/adapters.py"
        adapter.write_text(FAKE_ADAPTER + '''
class AdapterError(ValueError): pass
def parse_result(profile, stdout, stderr, returncode):
    raise AdapterError("provider returned PRIVATE-TOKEN")
def diagnose_failure(profile, stdout, stderr, returncode):
    return {"code": "provider_limit", "message": "PRIVATE-TOKEN"}
''')
        self.enable()
        job = self.wait(self.submit()["id"])
        self.assertTrue(job["transport_success"])
        self.assertEqual("provider_limit", job["error_code"])
        self.assertEqual("provider_limit", job["diagnostic"]["classification"])
        self.assertNotIn("PRIVATE-TOKEN", json.dumps(job))

    def test_off_or_cancel_during_preflight_prevents_provider_launch(self):
        for action in ("off", "cancel"):
            with self.subTest(action=action):
                self.enable()
                child_marker = self.root / (action + "-child-launched")
                self.profile.update(build_delay=0.4, child_marker=str(child_marker))
                job = self.submit()
                preflight = self.state / "jobs" / job["id"] / "workspace/preflight-started"
                deadline = time.monotonic() + 5
                while not preflight.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(preflight.exists())
                if action == "off":
                    self.store.configure(enabled=False)
                else:
                    self.store.cancel(job["id"])
                result = self.wait(job["id"])
                self.assertEqual("cancelled", result["state"])
                self.assertFalse(child_marker.exists())
                self.assertNotIn("returncode", result)

    def test_nonzero_exit_keeps_safe_diagnosis_and_deletes_raw_logs(self):
        adapter = self.root / "fake-runtime/adapters.py"
        adapter.write_text(FAKE_ADAPTER + '''
def build_command(profile, workspace, prompt_path):
    return [sys.executable, "-c", "import sys; print('raw-stdout-secret'); print('raw-stderr-secret', file=sys.stderr); raise SystemExit(7)"]
def diagnose_failure(profile, stdout, stderr, returncode):
    assert 'raw-stdout-secret' in stdout and 'raw-stderr-secret' in stderr
    return {"code": "model_unavailable", "message": "O modelo solicitado não está disponível.", "raw": stdout + stderr}
''')
        self.enable()
        job = self.wait(self.submit()["id"])
        self.assertEqual("failed", job["state"])
        self.assertFalse(job["transport_success"])
        self.assertEqual("model_unavailable", job["error_code"])
        self.assertEqual("O modelo solicitado não está disponível.", job["error"])
        self.assertEqual(7, job["diagnostic"]["returncode"])
        self.assertEqual("model_unavailable", job["diagnostic"]["classification"])
        self.assertGreater(job["diagnostic"]["stdout"]["bytes"], 0)
        self.assertRegex(job["diagnostic"]["stdout"]["sha256"], r"^[0-9a-f]{64}$")
        saved = (self.state / "jobs" / job["id"] / "job.json").read_text()
        self.assertNotIn("raw-stdout-secret", saved)
        self.assertNotIn("raw-stderr-secret", saved)
        self.assertFalse((self.state / "jobs" / job["id"] / ".stdout").exists())
        self.assertFalse((self.state / "jobs" / job["id"] / ".stderr").exists())

    def test_parse_keeps_known_adapter_message_and_omits_arbitrary_exception_text(self):
        adapter = self.root / "fake-runtime/adapters.py"
        adapter.write_text(FAKE_ADAPTER + '''
class AdapterError(ValueError): pass
def parse_result(profile, stdout, stderr, returncode):
    if profile.get("known_error"):
        raise AdapterError("A entrega estruturada está incompleta.")
    raise ValueError("arbitrary-private-exception-text")
''')
        self.enable()
        self.profile["known_error"] = True
        known = self.wait(self.submit()["id"])
        self.assertEqual("A saída do provedor não passou na validação estrutural. A entrega não foi aceita.", known["error"])
        self.assertTrue(known["transport_success"])
        self.assertEqual("invalid", known["validation"])
        self.profile["known_error"] = False
        arbitrary = self.wait(self.submit(retry_reason="adapter parser was corrected")["id"])
        self.assertNotIn("arbitrary-private-exception-text", json.dumps(arbitrary))
        self.assertEqual("invalid_provider_output", arbitrary["error_code"])

    def test_timeout_and_cancellation(self):
        self.enable()
        self.profile["delay"] = 2
        job = self.wait(self.submit(timeout=0.1)["id"])
        self.assertEqual("timed_out", job["state"])
        job = self.submit()
        self.wait(job["id"], "running")
        self.store.cancel(job["id"])
        self.assertEqual("cancelled", self.wait(job["id"])["state"])

    def test_off_cancels_only_this_session_or_store(self):
        self.enable()
        self.store.set_session("host-b", True)
        self.profile["delay"] = 0.4
        own = self.submit()
        other = self.store.submit("host-b", self.profile, "Independent job")
        self.store.set_session("host-a", False)
        self.assertEqual("cancelled", self.wait(own["id"])["state"])
        self.assertEqual("completed", self.wait(other["id"])["state"])
        self.store.set_session("host-a", True)
        own = self.submit()
        self.store.configure(enabled=False)
        self.assertEqual("cancelled", self.wait(own["id"])["state"])

    def test_concurrent_submit_respects_limit_and_atomic_state(self):
        self.enable(concurrency=1)
        self.profile["delay"] = 0.3
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs = list(pool.map(lambda _: self.submit(), range(4)))
        self.assertEqual(4, len({job["id"] for job in jobs}))
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            current = self.store.list_jobs()
            self.assertLessEqual(sum(job["state"] == "running" for job in current), 1)
            if all(job["state"] in self.runtime.TERMINAL for job in current):
                self.assertTrue(all(job["state"] == "completed" for job in current))
                return
            time.sleep(0.03)
        self.fail("Concurrent jobs failed to finish")

    def test_stale_human_draft_is_preserved_and_acceptance_never_overwrites(self):
        self.enable()
        self.profile["delay"] = 0.15
        submitted = self.submit()
        (self.vault / "drafts/live.md").write_text("Human draft v2\n")
        job = self.wait(submitted["id"])
        self.assertTrue(job["stale"])
        accepted = self.store.accept(job["id"])
        self.assertTrue(accepted["accepted_stale"])
        proposal = Path(accepted["accepted_path"]).read_text()
        self.assertIn("A fonte mudou após o envio", proposal)
        self.assertIn("Perfil solicitado: explicit-test-model; modelo reportado: explicit-test-model; identidade servida não verificada.", proposal)
        self.assertEqual("Human draft v2\n", (self.vault / "drafts/live.md").read_text())
        with self.assertRaisesRegex(self.runtime.DelegationError, "already published"):
            self.store.accept(job["id"])

    def test_retry_has_new_identity_and_duplicate_retry_is_refused(self):
        self.enable()
        original = self.wait(self.submit()["id"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(self._try_retry, [original["id"], original["id"]]))
        retried = [value for value in outcomes if isinstance(value, dict)]
        self.assertEqual(1, len(retried))
        retry = self.wait(retried[0]["id"])
        self.assertNotEqual(original["id"], retry["id"])
        self.assertNotEqual(original["attempt_id"], retry["attempt_id"])
        self.assertEqual(original["id"], retry["retry_of"])

    def test_run_tracks_declared_principal_linear_handoffs_quota_and_final(self):
        self.enable()
        principal = {"provider": "codex", "model": "gpt-6-astra", "effort": "high", "source": "declared"}
        run = self.store.create_run("host-a", "chain", "Compare orchestration models", principal)
        self.assertEqual("declared_not_verified", run["principal"]["identity_status"])
        self.assertEqual([], run["quota"])
        first = self.wait(self.submit(run_id=run["id"], stage=1, role="author", handoff="full")["id"])
        second = self.wait(self.submit(run_id=run["id"], stage=2, role="reviewer",
                                      parent_job=first["id"], handoff="delta")["id"])
        self.assertEqual(first["id"], second["parent_job"])
        observed = self.store.record_quota(run["id"], "before", "quota_remaining", 80, "percent")
        self.assertEqual("account_snapshot_not_attributed", observed["quota"][0]["attribution"])
        with self.assertRaisesRegex(self.runtime.DelegationError, "previous stage"):
            self.submit(run_id=run["id"], stage=3, role="synthesizer",
                        parent_job=first["id"], handoff="synthesis")
        finished = self.store.finish_run(run["id"], final_job=second["id"])
        self.assertEqual("completed", finished["status"])
        self.assertEqual(second["id"], finished["final"]["job_id"])
        self.assertIn("Principal: codex / gpt-6-astra", self.store.history("host-a"))

    def test_run_retry_preserves_stage_and_old_standalone_jobs_remain_valid(self):
        self.enable()
        standalone = self.wait(self.submit()["id"])
        self.assertNotIn("run_id", standalone)
        run = self.store.create_run("host-a", "chain", "Retry safely")
        first = self.wait(self.submit(run_id=run["id"], stage=1, role="author", handoff="full")["id"])
        retry = self.wait(self.store.retry(first["id"])["id"])
        for key in ("run_id", "stage", "role", "parent_job", "handoff"):
            self.assertEqual(first.get(key), retry.get(key))
        with self.assertRaisesRegex(self.runtime.DelegationError, "already has an initial attempt"):
            self.submit(run_id=run["id"], stage=1, role="author", handoff="full")

    def test_malformed_run_state_fails_closed_without_rewriting_it(self):
        self.enable()
        run = self.store.create_run("host-a", "chain", "Preserve audit state")
        path = self.state / "runs" / (run["id"] + ".json")
        path.write_text('{"schema":999,"private":"sentinel"}')
        before = path.read_bytes()
        with self.assertRaisesRegex(self.runtime.DelegationError, "[Rr]un"):
            self.store.get_run(run["id"])
        self.assertEqual(before, path.read_bytes())

    def test_run_feedback_off_artifact_scope_and_concurrent_finish(self):
        self.enable()
        evaluation = self.store.create_run("host-a", "principal-eval", "Measure the principal")
        (self.vault / "outside.md").write_text("outside drafts")
        with self.assertRaisesRegex(self.runtime.DelegationError, "inside drafts"):
            self.store.finish_run(evaluation["id"], final_artifact="outside.md")
        finished_eval = self.store.finish_run(evaluation["id"], final_artifact="drafts/live.md")
        self.assertEqual("artifact", finished_eval["final"]["kind"])
        self.store.set_session("host-a", False)
        with self.assertRaisesRegex(self.runtime.DelegationError, "OFF"):
            self.store.feedback_run(evaluation["id"], "accepted")

        self.store.set_session("host-a", True)
        run = self.store.create_run("host-a", "chain", "Choose one final")
        first = self.wait(self.submit(run_id=run["id"], stage=1, role="author", handoff="full")["id"])
        second = self.wait(self.submit(run_id=run["id"], stage=2, role="reviewer",
                                      parent_job=first["id"], handoff="delta")["id"])
        def finish(job):
            try:
                return self.store.finish_run(run["id"], final_job=job["id"])
            except self.runtime.DelegationError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(finish, (first, second)))
        self.assertEqual(1, sum(value is not None for value in outcomes))
        self.assertIn(self.store.get_run(run["id"])["final"]["job_id"], {first["id"], second["id"]})

    def _try_retry(self, identifier):
        try:
            return self.store.retry(identifier)
        except self.runtime.DelegationError:
            return "refused"

    def test_rejects_traversal_symlinks_secret_paths_binary_and_oversize(self):
        self.enable()
        (self.vault / "secret.md").write_text("credential")
        (self.vault / "data.json").write_text("{}")
        (self.vault / "large.md").write_bytes(b"x" * (self.runtime.MAX_INPUT + 1))
        (self.vault / "binary.md").write_bytes(b"abc\x00")
        (self.vault / "link.md").symlink_to(self.vault / "drafts/live.md")
        for path in ("../outside.md", "secret.md", "data.json", "large.md", "binary.md", "link.md"):
            with self.subTest(path=path), self.assertRaises(self.runtime.DelegationError):
                self.store.submit("host-a", self.profile, "review", [path])
        self.assertEqual([], self.store.list_jobs())

    def test_history_keeps_feedback_unknown_and_omits_task_and_raw_content(self):
        self.enable()
        job = self.wait(self.submit(reason="Independent risk review", task_type="draft")["id"])
        self.store.record_local("host-a", "Private local task", "low ambiguity", task_type="context")
        history = self.store.history("host-a")
        self.assertIn("unknown", history)
        self.assertIn("local", history)
        self.assertIn("Independent risk review", history)
        self.assertIn("low ambiguity", history)
        self.assertIn("rascunho", history)
        self.assertIn("contexto", history)
        self.assertNotIn("Human draft", history)
        self.assertNotIn("Private local task", history)
        self.assertNotIn("Review this draft", history)
        self.store.acknowledge(job["id"])
        self.assertEqual("unknown", self.store.get(job["id"])["feedback"])
        self.store.feedback(job["id"], "useful", "Helped compare alternatives")
        self.assertEqual("useful", self.store.get(job["id"])["feedback"])
        history = self.store.history("host-a")
        self.assertIn("Helped compare alternatives", history)
        self.assertIn("úteis: 1", history)

    def test_history_reports_observed_duration_and_allowlisted_usage_with_scoped_feedback(self):
        self.enable()
        job = self.wait(self.submit(reason="Compare **risk**\n[link](https://example.invalid); api_key=sk-privatecredential123", model_source="override")["id"])
        self.store.feedback(job["id"], "useful", "Useful only for the opening paragraph")
        path = self.state / "jobs" / job["id"] / "job.json"
        value = json.loads(path.read_text())
        value.update(started_at="2026-09-06T12:00:00+00:00", finished_at="2026-09-06T12:00:02.500000+00:00",
                     task="never-render-private-task", error="never-render-private-error")
        value["profile"]["api_key"] = "never-render-profile-secret"
        value["result"].update(text="never-render-private-answer", model_reported="reported-alias",
                               usage={"input_tokens": 17, "output_tokens": 4,
                                      "secret": "never-render-usage-secret", "extra": "x" * 10000},
                               cost_estimate_usd=0.025)
        path.write_text(json.dumps(value))
        self.store.record_local("host-b", "private other-session task", "other-session rationale")
        history = self.store.history("host-a")
        for expected in ("2.50 s", "explicit-test-model", "reported-alias", "esforço low", "explícita (override)",
                         "entrada: 17 tokens", "saída: 4 tokens", "US$ 0.025; não é fatura",
                         "Useful only for the opening paragraph", "Compare \\*\\*risk\\*\\*", "\\[link\\]"):
            self.assertIn(expected, history)
        for forbidden in ("never-render", "other-session rationale", "sk-privatecredential123", "[link](", "x" * 100):
            self.assertNotIn(forbidden, history)
        self.assertIn("Incorporação pelo agente", history)
        self.assertIn("Avaliação humana", history)

    def test_history_bounds_recent_records_and_keeps_unknown_values_truthful(self):
        self.enable()
        for index in range(34):
            self.store.record_local("host-a", "raw private task", f"Local decision {index}", task_type="context")
        history = self.store.history("host-a")
        self.assertEqual(30, history.count("\n## "))
        self.assertIn("30 registros mais recentes de 34", history)
        self.assertIn("Local decision 33", history)
        self.assertNotIn("Local decision 0\n", history)
        self.assertNotIn("raw private task", history)
        self.assertIn("Resultado não medido", history)
        self.assertLess(len(history), 30000)
        job = self.wait(self.submit()["id"])
        path = self.state / "jobs" / job["id"] / "job.json"
        value = json.loads(path.read_text())
        value["result"].update(model_reported=None, usage=None)
        path.write_text(json.dumps(value))
        history = self.store.history("host-a")
        self.assertIn("Modelo informado pelo provedor: não informado", history)
        self.assertIn("Uso informado pelo provedor: não disponível. Custo não informado", history)

    def test_malformed_config_fails_closed_but_status_is_readable(self):
        self.enable()
        (self.state / "config.json").write_text("broken")
        self.assertFalse(self.store.status("host-a")["enabled"])
        self.assertIn("error", self.store.status("host-a"))
        with self.assertRaises(self.runtime.DelegationError):
            self.submit()
        self.store.configure(enabled=False)
        self.assertFalse(self.store.status("host-a")["global_enabled"])

    def test_detached_worker_finishes_after_submitting_process_exits(self):
        self.enable()
        code = "import sys; sys.path.insert(0, sys.argv[1]); from runtime import DelegationStore; s=DelegationStore(sys.argv[2],sys.argv[3]); print(s.submit('host-a',{'provider':'fake','model':'test','delay':0.5},'detached task')['id'])"
        completed = subprocess.run([sys.executable, "-c", code, str(self.root / "fake-runtime"), str(self.vault), str(self.state)], capture_output=True, text=True, timeout=5, check=True)
        job = self.wait(completed.stdout.strip())
        self.assertEqual("completed", job["state"])

    def test_orphan_recovery_marks_interrupted_without_signalling_pid(self):
        self.enable()
        with mock.patch.object(self.runtime.subprocess, "Popen"):
            job = self.submit()
        path = self.state / "jobs" / job["id"] / "job.json"
        value = json.loads(path.read_text())
        value.update(state="running", supervisor_pid=1)
        path.write_text(json.dumps(value))
        with mock.patch.object(self.runtime.os, "killpg") as kill:
            self.assertEqual("interrupted", self.store.get(job["id"])["state"])
            kill.assert_not_called()

    def test_state_inside_vault_is_refused(self):
        with self.assertRaisesRegex(self.runtime.DelegationError, "outside"):
            self.runtime.DelegationStore(self.vault, self.vault / "state")

    def test_off_prevents_incorporation_and_session_profile_survives_off(self):
        self.enable()
        self.store.set_session("host-a", True, profile="sonnet")
        job = self.wait(self.submit()["id"])
        self.store.set_session("host-a", False)
        self.assertEqual("sonnet", self.store.status("host-a")["profile"])
        with self.assertRaisesRegex(self.runtime.DelegationError, "OFF"):
            self.store.accept(job["id"])
        self.assertFalse((self.vault / "drafts/delegation").exists())

    def test_child_cannot_enable_submit_or_accept(self):
        self.enable()
        job = self.wait(self.submit()["id"])
        with mock.patch.dict(self.runtime.os.environ, {"THINKER_DELEGATION_CHILD": "1"}):
            for action in (lambda: self.store.configure(enabled=True), self.submit,
                           lambda: self.store.accept(job["id"])):
                with self.assertRaisesRegex(self.runtime.DelegationError, "children"):
                    action()

    def test_accept_refuses_symlink_destination_and_existing_file(self):
        self.enable()
        job = self.wait(self.submit()["id"])
        outside = self.root / "outside"
        outside.mkdir()
        target = self.vault / "drafts/delegation"
        target.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(self.runtime.DelegationError, "symlinks"):
            self.store.accept(job["id"])
        self.assertEqual([], list(outside.iterdir()))
        target.unlink()
        target.mkdir()
        draft = target / (job["id"] + ".md")
        draft.write_text("Human-owned comparison")
        with self.assertRaisesRegex(self.runtime.DelegationError, "overwrite"):
            self.store.accept(job["id"])
        self.assertEqual("Human-owned comparison", draft.read_text())


if __name__ == "__main__":
    unittest.main()
