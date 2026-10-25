"""Autonomy admission and lifecycle, with local fake processes only."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

import test_delegation_runtime as fixtures


class ConsultationRuntimeTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    tearDown = fixtures.RuntimeTests.tearDown
    enable = fixtures.RuntimeTests.enable
    wait = fixtures.RuntimeTests.wait

    def admit(self, **changes):
        data = dict(session="host-a", role="advisor", delivery="delivery-a", initiation="auto",
                    provider="codex", model="model-a", reason="Compare unresolved approaches")
        data.update(changes)
        return self.store.admit_consultation(**data)

    def external(self, **changes):
        data = dict(session="host-a", profile=self.profile, task="Review evidence", reason="Find unsupported claims",
                    consult_role="reviewer", delivery="delivery-a", initiation="auto")
        data.update(changes)
        return self.store.submit(**data)

    def marker(self, path, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if path.exists():
                return
            time.sleep(.02)
        self.fail("Fake child did not reach expected marker")

    def test_status_is_readonly_default_on_and_never_starts_host(self):
        with mock.patch.object(self.runtime.subprocess, "Popen") as launch:
            status = self.store.autonomy_status("host-a")
            self.assertTrue(status["enabled"])
            self.assertEqual([], status["calls"])
            self.assertIsNone(status["cost"])
            self.assertIn("cooperative", status["native_enforcement"])
            self.assertFalse(self.state.exists())
            launch.assert_not_called()

    def test_native_admission_and_start_do_not_spawn_and_off_blocks_reserved(self):
        with mock.patch.object(self.runtime.subprocess, "Popen") as launch:
            call = self.admit()
            self.assertEqual("reserved", call["state"])
            self.store.set_autonomy("host-a", False)
            with self.assertRaises(self.runtime.DelegationError):
                self.store.start_consultation("host-a", call["id"])
            launch.assert_not_called()
        self.assertEqual("cancelled", self.store.autonomy_status("host-a")["calls"][0]["state"])

    def test_explicit_request_is_one_shot_without_reenabling_autonomy(self):
        self.store.set_autonomy("host-a", False)
        with self.assertRaisesRegex(self.runtime.DelegationError, "Autonomy is OFF"):
            self.admit()
        call = self.admit(initiation="explicit")
        self.store.start_consultation("host-a", call["id"])
        self.store.finish_consultation("host-a", call["id"], "completed")
        self.assertFalse(self.store.autonomy_status("host-a")["enabled"])

    def test_request_mode_blocks_auto_even_if_toggle_on(self):
        self.store.set_session("host-a", True, "request")
        with self.assertRaisesRegex(self.runtime.DelegationError, "Autonomy is OFF"):
            self.admit()
        self.assertEqual("reserved", self.admit(initiation="explicit")["state"])

    def test_hard_off_blocks_explicit_but_finish_still_records(self):
        call = self.admit()
        self.store.start_consultation("host-a", call["id"])
        self.store.configure(enabled=False)
        with self.assertRaisesRegex(self.runtime.DelegationError, "Delegation is OFF"):
            self.admit(delivery="another", initiation="explicit")
        self.assertEqual("completed", self.store.finish_consultation("host-a", call["id"], "completed")["state"])

    def test_hard_off_invalidates_native_reservations_before_reenable(self):
        for global_off, initiation in ((False, "auto"), (True, "explicit")):
            with self.subTest(global_off=global_off, initiation=initiation):
                self.store.configure(enabled=True)
                self.store.set_session("host-a", True, "auto")
                call = self.admit(delivery="global" if global_off else "session", initiation=initiation)
                if global_off:
                    self.store.configure(enabled=False)
                    self.store.configure(enabled=True)
                else:
                    self.store.set_session("host-a", False)
                self.store.set_session("host-a", True, "auto")
                with self.assertRaisesRegex(self.runtime.DelegationError, "not reserved"):
                    self.store.start_consultation("host-a", call["id"])
                record = next(c for c in self.store.autonomy_status("host-a")["calls"] if c["id"] == call["id"])
                self.assertEqual(("cancelled", True), (record["state"], record["cancel_requested"]))

    def test_hard_off_requests_native_running_cancellation_without_claiming_stop(self):
        call = self.admit(initiation="explicit")
        self.store.start_consultation("host-a", call["id"])
        self.store.set_session("host-a", False)
        state = self.store.autonomy_status("host-a")["calls"][0]
        self.assertEqual(("running", True), (state["state"], state["cancel_requested"]))
        self.store.finish_consultation("host-a", call["id"], "cancelled")

    def test_global_off_revokes_old_overrides_and_persists_after_restart(self):
        self.store.set_autonomy("host-a", True)
        self.store.set_autonomy("host-b", True)
        self.store.set_autonomy(None, False, scope="all")
        restarted = self.runtime.DelegationStore(self.vault, self.state)
        for sid in ("host-a", "host-b", "new-session"):
            self.assertFalse(restarted.autonomy_status(sid)["enabled"])
        restarted.set_autonomy("host-a", True)
        self.assertTrue(restarted.autonomy_status("host-a")["enabled"])
        self.assertFalse(restarted.autonomy_status("host-b")["enabled"])

    def test_default_changes_preserve_known_sessions_and_no_launch(self):
        call = self.admit()
        self.store.set_session("host-b", True, "auto")
        self.store.set_autonomy(None, False, scope="default")
        self.assertTrue(self.store.autonomy_status("host-a")["enabled"])
        self.assertTrue(self.store.autonomy_status("host-b")["enabled"])
        self.assertFalse(self.store.autonomy_status("new-session")["enabled"])
        self.assertEqual("running", self.store.start_consultation("host-a", call["id"])["state"])

    def test_running_native_continues_unless_cancel_requested(self):
        call = self.admit()
        self.store.start_consultation("host-a", call["id"])
        self.store.set_autonomy("host-a", False)
        state = self.store.autonomy_status("host-a")["calls"][0]
        self.assertEqual(("running", False), (state["state"], state["cancel_requested"]))
        self.store.set_autonomy("host-a", False, cancel=True)
        state = self.store.autonomy_status("host-a")["calls"][0]
        self.assertEqual(("running", True), (state["state"], state["cancel_requested"]))
        self.store.finish_consultation("host-a", call["id"], "cancelled")

    def test_only_same_provider_advisor_and_other_provider_reviewer_when_known(self):
        self.admit(principal_provider="codex")
        for changes in (dict(role="reviewer"), dict(provider="claude")):
            with self.assertRaisesRegex(self.runtime.DelegationError, "Advisor requires"):
                self.admit(delivery="other", principal_provider="codex", **changes)
        with self.assertRaisesRegex(self.runtime.DelegationError, "Reviewer requires external"):
            self.admit(role="reviewer", provider="claude", principal_provider="codex")
        call = self.external(profile={**self.profile, "provider": "claude"}, principal_provider="codex")
        self.assertEqual("codex", call["principal_provider"])
        self.wait(call["id"])

    def test_global_on_changes_legacy_request_mode_without_reviving_hard_off(self):
        self.store.set_session("host-a", True, "request")
        self.store.set_session("host-b", False, "request")
        self.store.set_autonomy(None, True, scope="all")
        self.assertTrue(self.store.autonomy_status("host-a")["enabled"])
        self.assertFalse(self.store.autonomy_status("host-b")["enabled"])

    def test_explicit_retry_preserves_role_delivery_and_does_not_reenable_autonomy(self):
        job = self.external()
        self.wait(job["id"])
        with self.assertRaisesRegex(self.runtime.DelegationError, "budget reached"):
            self.store.retry(job["id"], reason="A materially new requested examination")
        self.store.set_autonomy("host-a", False)
        retry = self.store.retry(job["id"], reason="User requested a second examination",
                                 initiation="explicit", principal_provider="codex")
        self.assertEqual(("reviewer", "delivery-a", "explicit", "codex"),
                         (retry["consult_role"], retry["delivery"], retry["initiation"], retry["principal_provider"]))
        self.assertEqual("completed", self.wait(retry["id"])["state"])
        self.assertFalse(self.store.autonomy_status("host-a")["enabled"])

    def test_explicit_original_does_not_authorize_another_retry_with_autonomy_off(self):
        original = self.external(initiation="explicit")
        self.wait(original["id"])
        self.store.set_autonomy("host-a", False)
        with self.assertRaisesRegex(self.runtime.DelegationError, "Autonomy is OFF"):
            self.store.retry(original["id"], reason="Additional round without a new user request")
        self.assertNotIn("retry_job", self.store.get(original["id"]))
        self.assertEqual(1, len(self.store.list_jobs("host-a")))
        retry = self.store.retry(original["id"], reason="User explicitly requested this new round",
                                 initiation="explicit")
        self.assertEqual("completed", self.wait(retry["id"])["state"])
        self.assertFalse(self.store.autonomy_status("host-a")["enabled"])

    def test_role_budget_is_atomic_and_does_not_reset_with_model(self):
        def attempt(model):
            try:
                return self.admit(model=model)["id"]
            except self.runtime.DelegationError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ["model-a", "model-b"]))
        self.assertEqual(1, sum(result is not None for result in results))
        self.store.set_autonomy("host-a", False)
        self.store.set_autonomy("host-a", True)
        with self.assertRaisesRegex(self.runtime.DelegationError, "budget reached"):
            self.admit(model="model-c")
        self.assertEqual("reviewer", self.external()["consult_role"])

    def test_role_transport_mismatch_fails_without_creating_calls_or_jobs(self):
        for operation in (lambda: self.admit(role="reviewer"),
                          lambda: self.external(consult_role="advisor")):
            with self.assertRaisesRegex(self.runtime.DelegationError, "Advisor requires native"):
                operation()
            self.assertEqual([], self.store.autonomy_status("host-a")["calls"])
            self.assertEqual([], self.store.list_jobs("host-a"))

    def test_native_and_external_share_session_and_provider_budget(self):
        self.store.configure(max_calls_session=2, max_calls_provider=1)
        self.admit(provider="fake")
        with self.assertRaisesRegex(self.runtime.DelegationError, "Provider call cap"):
            self.external()
        self.admit(delivery="other", provider="codex")
        with self.assertRaisesRegex(self.runtime.DelegationError, "Session call cap"):
            self.external()

    def test_native_and_external_share_concurrency(self):
        self.store.configure(concurrency=1)
        marker = self.root / "launched"
        self.profile.update(delay=.35, child_marker=str(marker))
        external = self.external()
        self.marker(marker)
        native = self.admit()
        with self.assertRaisesRegex(self.runtime.DelegationError, "concurrency"):
            self.store.start_consultation("host-a", native["id"])
        self.wait(external["id"])
        self.assertEqual("running", self.store.start_consultation("host-a", native["id"])["state"])

    def test_external_preflight_off_prevents_child_even_if_reenabled(self):
        marker = self.root / "not-launched"
        self.profile.update(build_delay=.3, child_marker=str(marker))
        job = self.external()
        started = self.state / "jobs" / job["id"] / "workspace/preflight-started"
        self.marker(started)
        self.store.set_autonomy("host-a", False)
        self.store.set_autonomy("host-a", True)
        self.assertEqual("cancelled", self.wait(job["id"])["state"])
        self.assertFalse(marker.exists())

    def test_external_already_launched_continues_after_toggle_off(self):
        marker = self.root / "launched"
        self.profile.update(delay=.3, child_marker=str(marker))
        job = self.external()
        self.marker(marker)
        self.store.set_autonomy("host-a", False)
        self.assertEqual("completed", self.wait(job["id"])["state"])
        self.assertFalse(self.store.autonomy_status("host-a")["enabled"])

    def test_legacy_missing_role_flags_cannot_bypass_autonomy_off(self):
        self.store.set_autonomy("host-a", False)
        with self.assertRaisesRegex(self.runtime.DelegationError, "Autonomy is OFF"):
            self.store.submit("host-a", self.profile, "Legacy review")
        job = self.store.submit("host-a", self.profile, "Requested legacy review", initiation="explicit")
        self.assertEqual("completed", self.wait(job["id"])["state"])

    def test_malformed_state_fails_closed_and_does_not_spawn(self):
        self.state.mkdir(mode=0o700)
        (self.state / "consultations.json").write_text(json.dumps({"schema": 1, "default_enabled": "yes"}))
        with mock.patch.object(self.runtime.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(self.runtime.DelegationError, "Malformed consultation"):
                self.admit()
            launch.assert_not_called()

    def test_reviewer_fallback_is_native_same_provider_and_labeled(self):
        with self.assertRaisesRegex(self.runtime.DelegationError, "declared --fallback"):
            self.admit(role="reviewer")
        with self.assertRaisesRegex(self.runtime.DelegationError, "Fallback applies only"):
            self.admit(fallback="codex quota blocked")
        with self.assertRaisesRegex(self.runtime.DelegationError, "host provider"):
            self.admit(role="reviewer", provider="claude", principal_provider="codex", fallback="claude quota blocked")
        call = self.admit(role="reviewer", principal_provider="codex", fallback="claude quota blocked")
        self.assertEqual("same_provider_fallback", call["independence"])
        self.assertEqual("claude quota blocked", call["fallback_reason"])
        with self.assertRaisesRegex(self.runtime.DelegationError, "fallback already used"):
            self.admit(role="reviewer", fallback="still blocked")

    def test_reviewer_fallback_reuses_slot_only_after_unavailable_external(self):
        job = self.external()
        self.wait(job["id"])
        with self.assertRaisesRegex(self.runtime.DelegationError, "budget reached"):
            self.admit(role="reviewer", fallback="Other provider looked busy")
        other = self.external(delivery="delivery-b")
        self.wait(other["id"])
        path = self.state / "jobs" / other["id"] / "job.json"
        with self.store._lock():
            failed = json.loads(path.read_text())
            failed.update(state="failed", error_code="provider_limit")
            self.runtime._atomic(path, failed)
        call = self.admit(role="reviewer", delivery="delivery-b", fallback="provider_limit on external review")
        self.assertEqual("reserved", call["state"])
        with self.assertRaisesRegex(self.runtime.DelegationError, "fallback already used"):
            self.admit(role="reviewer", delivery="delivery-b", fallback="again")

    def test_invalid_external_output_does_not_free_reviewer_slot(self):
        job = self.external()
        self.wait(job["id"])
        path = self.state / "jobs" / job["id"] / "job.json"
        with self.store._lock():
            failed = json.loads(path.read_text())
            failed.update(state="failed", error_code="invalid_provider_output")
            self.runtime._atomic(path, failed)
        with self.assertRaisesRegex(self.runtime.DelegationError, "budget reached"):
            self.admit(role="reviewer", fallback="Other provider answered unparseably")

    def test_damaged_state_keeps_status_readable_and_rejects_bad_start_time(self):
        call = self.admit()
        self.store.start_consultation("host-a", call["id"])
        with self.store._lock():
            value = json.loads((self.state / "consultations.json").read_text())
            value["calls"][call["id"]]["started_at"] = 123
            self.runtime._atomic(self.state / "consultations.json", value)
        status = self.store.autonomy_status("host-a")
        self.assertTrue(status["consultations_damaged"])
        self.assertFalse(status["enabled"])
        self.assertTrue(self.store.status("host-a")["enabled"])
        with self.assertRaisesRegex(self.runtime.DelegationError, "Malformed consultation"):
            self.admit(delivery="other")

    def test_unfinished_native_stops_holding_concurrency_once_stale(self):
        self.store.configure(concurrency=1)
        first = self.admit()
        self.store.start_consultation("host-a", first["id"])
        second = self.admit(delivery="other")
        with self.assertRaisesRegex(self.runtime.DelegationError, "concurrency"):
            self.store.start_consultation("host-a", second["id"])
        with self.store._lock():
            value = json.loads((self.state / "consultations.json").read_text())
            value["calls"][first["id"]]["started_at"] = "2026-01-01T00:00:00+00:00"
            self.runtime._atomic(self.state / "consultations.json", value)
        self.assertEqual("running", self.store.start_consultation("host-a", second["id"])["state"])
        calls = {call["id"]: call for call in self.store.autonomy_status("host-a")["calls"]}
        self.assertTrue(calls[first["id"]]["stale"])
        self.assertEqual("running", calls[first["id"]]["state"])

    def test_damaged_state_after_launch_does_not_strand_jobs_or_hard_off(self):
        marker = self.root / "launched"
        self.profile.update(delay=.3, child_marker=str(marker))
        job = self.external()
        self.marker(marker)
        (self.state / "consultations.json").write_text("{}")
        self.assertEqual("completed", self.wait(job["id"])["state"])
        self.store.configure(enabled=False)
        self.assertFalse(self.store.status("host-a")["enabled"])

    def test_pre_rc14_running_job_is_not_cancelled_by_autonomy_off(self):
        marker = self.root / "launched"
        self.profile.update(delay=.3, child_marker=str(marker))
        job = self.store.submit("host-a", self.profile, "Legacy in-flight review")
        self.marker(marker)
        path = self.state / "jobs" / job["id"] / "job.json"
        with self.store._lock():
            legacy = json.loads(path.read_text())
            legacy.pop("initiation", None)
            legacy.pop("provider_started", None)
            self.runtime._atomic(path, legacy)
        self.store.set_autonomy("host-a", False)
        self.assertEqual("completed", self.wait(job["id"])["state"])

    def test_finish_requires_owned_started_call_and_preserves_terminal_state(self):
        call = self.admit()
        with self.assertRaises(self.runtime.DelegationError):
            self.store.finish_consultation("host-a", call["id"], "completed")
        self.store.start_consultation("host-a", call["id"])
        with self.assertRaises(self.runtime.DelegationError):
            self.store.finish_consultation("host-b", call["id"], "completed")
        self.store.finish_consultation("host-a", call["id"], "completed")
        with self.assertRaises(self.runtime.DelegationError):
            self.store.finish_consultation("host-a", call["id"], "failed")

# Use installed CLI copies with local fake binaries, without the legacy helper's
# explicit-call normalization: omission must remain observable as automatic.
import test_delegation_cli as cli_fixtures


class ConsultationCLITests(unittest.TestCase):
    setUp = cli_fixtures.CLITests.setUp
    tearDown = cli_fixtures.CLITests.tearDown
    cli = cli_fixtures.CLITests.cli
    refused = cli_fixtures.CLITests.refused
    completed = cli_fixtures.CLITests.completed

    def command(self, *args, session="host-a", json_output=True):
        command = [sys.executable, "-B", str(self.cli_path), "--state-dir", str(self.state)]
        if session is not None:
            command += ["--session", session]
        if json_output:
            command += ["--json"]
        return subprocess.run(command + list(args), cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=10)

    def test_fresh_status_does_not_create_private_state(self):
        self.assertTrue(self.cli("autonomy", "status")["enabled"])
        self.assertFalse(self.state.exists())

    def test_explicit_submit_remains_available_with_autonomy_off(self):
        self.cli("autonomy", "off")
        args = ["submit", "--model", "sonnet", "--prompt", "Review this source", "--reason", "Check factual claims",
                "--critical-review", "--benefit", "Independent evidence examination"]
        self.assertIn("Autonomy is OFF", self.refused(*args)["error"])
        job = self.cli(*args, "--initiation", "explicit", "--consult-role", "reviewer", "--delivery", "one")
        self.completed(job)
        self.assertFalse(self.cli("autonomy", "status")["enabled"])

    def test_native_protocol_checks_provider_and_records_terminal_after_hard_off(self):
        self.cli("session-context", "--provider", "codex", "--model", "sol", "--effort", "high")
        args = ["consult", "admit", "--consult-role", "advisor", "--delivery", "one", "--initiation", "auto",
                "--provider", "codex", "--model", "sol", "--reason", "Compare two approaches"]
        call = self.cli(*args)
        self.cli("consult", "start", call["id"])
        self.cli("off")
        finished = self.cli("consult", "finish", call["id"], "--state", "completed")
        self.assertEqual("completed", finished["state"])
        report = self.cli("native", "report", "--id", "native-test", "--model", "sol", "--state", "completed", "--task", "Review")
        self.assertEqual("completed", report["state"])

    def test_board_projects_roles_native_consultations_and_autonomy(self):
        self.cli("session-context", "--provider", "codex", "--model", "sol", "--effort", "high")
        advisor = self.cli("consult", "admit", "--consult-role", "advisor", "--delivery", "one", "--initiation", "auto",
                           "--provider", "codex", "--model", "astra", "--reason", "Compare two approaches")
        self.cli("consult", "start", advisor["id"])
        fallback = self.cli("consult", "admit", "--consult-role", "reviewer", "--fallback", "claude quota blocked",
                            "--delivery", "one", "--initiation", "explicit", "--provider", "codex",
                            "--model", "sol", "--reason", "Contest the proposal")
        job = self.cli("submit", "--model", "sonnet", "--prompt", "Review this source", "--reason", "Check claims",
                       "--critical-review", "--benefit", "Independent evidence examination",
                       "--initiation", "explicit", "--consult-role", "reviewer", "--delivery", "two")
        self.completed(job)
        self.cli("autonomy", "off")
        board = self.cli("board", "--all-sessions")
        row = [j for j in board["jobs"] if j["id"] == job["id"]][0]
        self.assertEqual(("reviewer", "two", "explicit"), (row["consult_role"], row["consult_delivery"], row["initiation"]))
        consultations = board["consultations"]
        self.assertTrue(consultations["available"])
        self.assertFalse(consultations["autonomy"]["host-a"])
        native = {c["id"]: c for c in consultations["native"]}
        self.assertEqual(("advisor", "running"), (native[advisor["id"]]["consult_role"], native[advisor["id"]]["state"]))
        self.assertEqual("same_provider_fallback", native[fallback["id"]]["independence"])

    def test_request_mode_and_explicit_toggle_on_have_clear_effect(self):
        self.cli("on")
        self.assertFalse(self.cli("autonomy", "status")["enabled"])
        self.cli("autonomy", "on")
        self.assertTrue(self.cli("autonomy", "status")["enabled"])

    def test_plain_output_separates_initiative_from_capability(self):
        result = self.command("autonomy", "off", json_output=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Autonomia desligada", result.stdout)
        self.assertIn("Capacidade de delegação ligada", result.stdout)
        self.assertIn("protocolo cooperativo", result.stdout)

    def test_retry_cli_does_not_inherit_explicit_original_authorization(self):
        job = self.cli("submit", "--model", "sonnet", "--prompt", "Review this source", "--reason", "Check factual claims",
                       "--critical-review", "--benefit", "Independent evidence examination", "--initiation", "explicit")
        self.completed(job)
        self.cli("autonomy", "off")
        error = self.refused("retry", job["id"], "--reason", "A new round without a user instruction")
        self.assertIn("Autonomy is OFF", error["error"])
        original = json.loads((self.state / "jobs" / job["id"] / "job.json").read_text())
        self.assertNotIn("retry_job", original)
        retry = self.cli("retry", job["id"], "--reason", "User requested a second review", "--initiation", "explicit")
        self.completed(retry)
        self.assertFalse(self.cli("autonomy", "status")["enabled"])


if __name__ == "__main__":
    unittest.main()
