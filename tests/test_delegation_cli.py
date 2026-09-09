#!/usr/bin/env python3
"""Installed CLI integration with fake local binaries; no accounts or model calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAKE_PROVIDER = '''import json, sys, time
if "--help" in sys.argv:
    print("--safe-mode --restricted --tools --json-schema --output-format --ignore-user-config --ignore-rules --json --sandbox --prompt-file --no-subagents")
elif "--version" in sys.argv:
    print("fake-provider 1.0")
elif sys.argv[1:3] == ["login", "status"]:
    print("Logged in using ChatGPT")
elif sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai"}))
else:
    prompt = sys.stdin.read()
    if not prompt:
        raise SystemExit(8)
    time.sleep(0.1)
    text = "Contribuição recebeu stdin: " + prompt
    if sys.argv[0].endswith("codex"):
        print(json.dumps({"type":"thread.started","thread_id":"fake-thread"}))
        print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":text}}))
        print(json.dumps({"type":"turn.completed","usage":{"input_tokens":12,"output_tokens":7}}))
    else:
        print(json.dumps({"subtype":"success","is_error":False,"session_id":"fake-session","model":"sonnet","structured_output":{"text":text,"limitations":[]},"usage":{"input_tokens":12,"output_tokens":7}}))
'''


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="delegation-cli-")
        self.root = Path(self.temporary.name).resolve()
        self.vault = self.root / "vault"
        scripts = self.vault / "harness/scripts"
        scripts.mkdir(parents=True)
        shutil.copy(ROOT / "payload/harness/scripts/delegate.py", scripts / "delegate.py")
        shutil.copytree(ROOT / "payload/harness/scripts/thinker_delegation", scripts / "thinker_delegation",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.cli_path = scripts / "delegate.py"
        (self.vault / "drafts").mkdir()
        (self.vault / "drafts/live.md").write_text("draft-original-marker\n", encoding="utf-8")
        (self.vault / "brief.md").write_text("CLI-brief-marker: compare alternatives\n", encoding="utf-8")
        (self.vault / "AGENTS.md").write_text("Preserve originals.\n", encoding="utf-8")
        binary_dir = self.root / "bin"
        binary_dir.mkdir()
        for name in ("claude", "codex"):
            binary = binary_dir / name
            binary.write_text("#!" + sys.executable + "\n" + FAKE_PROVIDER, encoding="utf-8")
            binary.chmod(0o700)
        self.state = self.root / "state"
        self.env = {"PATH": str(binary_dir), "HOME": str(self.root), "LANG": "en_US.UTF-8",
                    "TMPDIR": str(self.root), "PYTHONDONTWRITEBYTECODE": "1"}

    def tearDown(self):
        if self.state.exists():
            self.cli("off", "--all", session=None)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                jobs = self.cli("status", session=None)["jobs"]
                if all(j["state"] not in {"queued", "running"} for j in jobs):
                    break
                time.sleep(0.05)
        self.temporary.cleanup()

    def command(self, *args, session="host-a", json_output=True):
        if args and args[0] == "submit" and "--benefit" not in args:
            args = (*args, "--benefit", "Independent synthetic contribution", "--independent")
        if args and args[0] == "retry" and "--reason" not in args:
            args = (*args, "--reason", "Synthetic diagnosis completed")
        command = [sys.executable, "-B", str(self.cli_path), "--state-dir", str(self.state)]
        if session is not None:
            command += ["--session", session]
        if json_output:
            command += ["--json"]
        return subprocess.run(command + list(args), cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=10)

    def cli(self, *args, session="host-a"):
        result = self.command(*args, session=session)
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)

    def refused(self, *args, session="host-a"):
        result = self.command(*args, session=session)
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        error = json.loads(result.stderr)
        self.assertTrue(error.get("error"))
        return error

    def enable(self, session="host-a"):
        return self.cli("on", "--model", "sonnet", session=session)

    def test_api_options_are_not_exposed_and_do_not_create_state(self):
        result = self.command("route", "--model", "sonnet", "--auth", "api", "--api-budget-usd", "1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)
        self.assertFalse(self.state.exists())

    def submit(self, session="host-a", *extra):
        return self.cli("submit", "--brief", "brief.md", "--file", "drafts/live.md",
                        "--reason", "Compare an isolated contribution", *extra, session=session)

    def completed(self, job):
        result = self.cli("wait", job["id"], "--seconds", "5", session=job["session"])
        self.assertEqual("completed", result["state"], result)
        self.assertTrue(result["transport_success"])
        self.assertEqual("valid", result["validation"])
        return result

    def test_default_available_status_and_route_create_no_state(self):
        status = self.cli("status", session=None)
        self.assertTrue(status["enabled"])
        self.assertEqual([], status["jobs"])
        self.assertFalse(self.state.exists())
        route = self.cli("route", "--task", "git")
        self.assertEqual("gpt-5.6-luna", route["model"])
        self.assertEqual("low", route["effort"])
        self.assertEqual("default", route["model_source"])
        self.assertEqual("local", route["routing"]["action"])
        self.assertFalse(self.state.exists())
        self.cli("off")
        self.refused("submit", "--prompt", "blocked", "--reason", "test")
        self.assertEqual([], self.cli("status")["jobs"])

    def test_routing_requires_benefit_and_tracks_principal_and_quota(self):
        self.cli("session-context", "--provider", "codex", "--model", "sol", "--effort", "high")
        result = self.cli("route", "--model", "sol")
        self.assertTrue(result["routing"]["same_model"])
        self.assertEqual("local", result["routing"]["action"])
        self.refused("submit", "--model", "sol", "--prompt", "repeat", "--reason", "repeat", "--benefit", "")
        result = self.cli("route", "--model", "sonnet", "--benefit", "Separate evidence review", "--critical-review")
        self.assertEqual("delegate", result["routing"]["action"])
        self.cli("quota", "--provider", "claude", "--availability", "blocked", "--reason", "Observed fixture limit")
        result = self.cli("route", "--model", "sonnet", "--benefit", "Review", "--critical-review")
        self.assertEqual("blocked", result["routing"]["action"])
        self.assertEqual([], self.cli("status")["jobs"])

    def test_limits_are_bounded_and_global_off_is_not_reversed_by_local_on(self):
        self.cli("limits", "--session-calls", "3", "--provider-calls", "2")
        self.assertEqual(3, self.cli("status")["max_calls_session"])
        self.refused("limits", "--session-calls", "0")
        self.cli("off", "--all")
        self.cli("on")
        self.assertFalse(self.cli("status", session="unseen")["enabled"])

    def test_available_quota_submits_but_blocked_quota_refuses_retry(self):
        self.enable()
        self.cli("quota", "--provider", "claude", "--availability", "available", "--reason", "Observed fixture capacity")
        job = self.completed(self.submit())
        self.cli("quota", "--provider", "claude", "--availability", "blocked", "--reason", "Observed fixture limit")
        refusal = self.refused("retry", job["id"], "--reason", "Earlier failure reviewed")
        self.assertIn("provider_quota_blocked", refusal["error"])
        self.assertEqual(1, len(self.cli("status")["jobs"]))

    def test_malformed_optional_policy_fields_fail_without_traceback(self):
        self.enable()
        for field, invalid in (("principals", []), ("quotas", []), ("quotas", {"claude": {"availability": "available"}})):
            (self.state / "policy.json").write_text(json.dumps({"defaults": {}, "decisions": [], field: invalid}))
            self.refused("route")
        (self.state / "policy.json").write_text(json.dumps({"defaults": {}, "decisions": []}))

    def test_session_preference_and_explicit_override_do_not_change_defaults(self):
        self.enable()
        route = self.cli("route", "--task", "draft")
        self.assertEqual("sonnet", route["model"])
        self.assertEqual("session", route["model_source"])
        explicit = self.cli("route", "--task", "draft", "--model", "luna")
        self.assertEqual("gpt-5.6-luna", explicit["model"])
        self.assertEqual("explicit", explicit["model_source"])
        self.assertEqual("sonnet", self.cli("status")["profile"])
        self.assertFalse((self.state / "policy.json").exists())
        self.assertEqual("sonnet", self.cli("route", "--task", "draft")["model"])

    def test_submit_sends_stdin_and_returns_normalized_result(self):
        self.enable()
        submitted = self.submit()
        self.assertIn("attempt_id", submitted)
        self.completed(submitted)
        result = self.cli("result", submitted["id"])
        self.assertIn("CLI-brief-marker", result["result"]["text"])
        self.assertIn("draft-original-marker", result["result"]["text"])
        self.assertEqual(12, result["result"]["usage"]["input_tokens"])
        self.assertNotIn("snapshot", result)
        self.assertFalse(list(self.vault.rglob("__pycache__")))

    def test_explicit_luna_runs_fake_codex_without_replacing_session_preference(self):
        self.enable()
        job = self.cli("submit", "--prompt", "CLI-brief-marker: small check", "--reason", "Explicit comparison",
                       "--model", "luna", "--task", "context")
        result = self.completed(job)
        self.assertEqual("gpt-5.6-luna", result["profile"]["model"])
        self.assertEqual("low", result["profile"]["effort"])
        self.assertEqual("explicit", result["model_source"])
        self.assertEqual("sonnet", self.cli("route")["model"])

    def test_fable_route_and_doctor_all_profiles_are_honest(self):
        route = self.cli("route", "--model", "fable")
        self.assertEqual(("claude", "fable", "high"),
                         (route["provider"], route["model"], route["effort"]))
        report = self.cli("doctor", "--all-profiles", session=None)
        self.assertEqual({"astra", "fable", "grok", "luna", "opus", "sol", "sonnet", "terra"},
                         {item["profile"] for item in report["providers"]})
        for item in report["providers"]:
            if item["ready"]:
                self.assertEqual("not_tested", item["model_access"])

    def test_run_cli_links_stages_and_materializes_only_final(self):
        self.enable()
        run = self.cli("run", "start", "--kind", "chain", "--objective", "Compare principals",
                       "--principal-provider", "claude", "--principal-model", "sonnet",
                       "--principal-effort", "high")
        self.assertEqual("unavailable", run["principal_usage"])
        first = self.completed(self.submit("host-a", "--run", run["id"], "--stage", "1",
                                           "--role", "author", "--handoff", "full"))
        second = self.completed(self.submit("host-a", "--run", run["id"], "--stage", "2",
                                            "--role", "reviewer", "--handoff", "delta",
                                            "--parent-job", first["id"]))
        self.assertIn("return only material deltas", self.cli("result", second["id"])["result"]["text"])
        self.cli("run", "quota", run["id"], "--when", "before", "--metric", "remaining",
                 "--value", "75", "--unit", "percent")
        self.assertFalse((self.vault / "drafts/delegation" / (first["id"] + ".md")).exists())
        finished = self.cli("run", "finish", run["id"], "--final-job", second["id"])
        self.assertEqual("completed", finished["status"])
        self.assertTrue((self.vault / "drafts/delegation" / (second["id"] + ".md")).is_file())
        self.assertFalse((self.vault / "drafts/delegation" / (first["id"] + ".md")).exists())
        shown = self.cli("run", "show", run["id"][:8])
        self.assertEqual([1, 2], [job["stage"] for job in shown["jobs"]])
        self.assertEqual(0, shown["retry_count"])
        self.assertGreaterEqual(shown["calendar_duration_seconds"], 0)
        self.assertEqual(2, len(shown["usage_by_provider"]["claude"]))
        self.assertIn("nenhum total comparável", shown["usage_note"])
        self.cli("off")
        self.assertEqual("completed", self.cli("run", "show", run["id"])["status"])
        self.refused("run", "quota", run["id"], "--when", "after", "--metric", "remaining",
                     "--value", "70", "--unit", "percent")

    def test_accept_reports_path_and_preserves_changed_live_draft(self):
        self.enable()
        job = self.completed(self.submit())
        live = self.vault / "drafts/live.md"
        live.write_text("Human changed live draft\n")
        result = self.cli("accept", job["id"])
        self.assertEqual("agent_accepted_draft", result["acceptance_action"])
        self.assertEqual("unknown", result["feedback"])
        destination = Path(result["accepted_path"])
        self.assertEqual(self.vault / "drafts/delegation" / (job["id"] + ".md"), destination)
        self.assertIn("A fonte mudou após o envio", destination.read_text())
        self.assertEqual("Human changed live draft\n", live.read_text())
        output = self.command("result", job["id"], json_output=False)
        self.assertEqual(0, output.returncode)
        self.refused("accept", job["id"])

    def test_brief_is_hashed_and_changes_mark_result_stale(self):
        self.enable()
        job = self.completed(self.submit())
        (self.vault / "brief.md").write_text("A changed instruction")
        self.assertTrue(self.cli("result", job["id"])["stale"])

    def test_history_local_and_delegated_feedback_remains_unknown(self):
        self.enable()
        self.completed(self.submit())
        self.cli("record", "--task", "context", "--reason", "Small enough to handle locally")
        history = self.cli("history")["markdown"]
        self.assertIn("Rota: local", history)
        self.assertIn("Rota: delegada (delegated)", history)
        self.assertIn("Small enough to handle locally", history)
        self.assertIn("unknown", history)
        self.assertNotIn("CLI-brief-marker", history)

    def test_ack_removes_inbox_item_without_implying_usefulness(self):
        self.enable()
        job = self.completed(self.submit())
        self.assertEqual([job["id"]], [j["id"] for j in self.cli("inbox")["jobs"]])
        result = self.cli("ack", job["id"][:8])
        self.assertEqual("unknown", result["feedback"])
        self.assertEqual([], self.cli("inbox")["jobs"])

    def test_off_prevents_retry_accept_and_history_incorporation(self):
        self.enable()
        job = self.completed(self.submit())
        self.cli("off")
        self.refused("accept", job["id"])
        self.refused("retry", job["id"])
        self.refused("history", "--export")
        self.assertFalse((self.vault / "drafts/delegation").exists())
        self.assertEqual(1, len(self.cli("status")["jobs"]))

    def test_two_sessions_cannot_mutate_each_others_jobs(self):
        self.enable()
        job = self.completed(self.submit())
        self.enable("host-b")
        self.assertEqual([], self.cli("inbox", session="host-b")["jobs"])
        for command in ("accept", "retry", "cancel", "ack"):
            with self.subTest(command=command):
                self.refused(command, job["id"], session="host-b")
                self.refused(command, job["id"], session=None)
        self.refused("feedback", job["id"], "--value", "useful", session="host-b")
        self.refused("feedback", job["id"], "--value", "useful", session=None)
        self.cli("off", session="host-b")
        self.assertTrue(self.cli("status")["enabled"])
        self.cli("off", "--all", session=None)
        self.assertFalse(self.cli("status")["enabled"])
        self.assertFalse(self.cli("status", session="host-b")["enabled"])

    def test_empty_missing_invalid_and_ambiguous_ids_refuse_cleanly(self):
        self.enable()
        first = self.completed(self.submit())
        self.refused("result", "")
        self.refused("result", "not-an-id")
        self.refused("result", "00000000-0000-0000-0000-000000000000")
        # Give a second completed attempt the same prefix in isolated persisted
        # fixture state; this tests the actual resolver's collision branch.
        original = self.state / "jobs" / first["id"]
        second_id = first["id"][:-1] + ("0" if first["id"][-1] != "0" else "1")
        second = self.state / "jobs" / second_id
        shutil.copytree(original, second)
        value = json.loads((second / "job.json").read_text())
        value["id"] = second_id
        (second / "job.json").write_text(json.dumps(value))
        self.refused("result", first["id"][:8])
        missing = self.command("result")
        self.assertEqual(2, missing.returncode)
        self.assertNotIn("Traceback", missing.stderr)

    def test_enabled_history_export_is_separate_and_rejects_symlink(self):
        self.enable()
        export = Path(self.cli("history", "--export")["history_path"])
        self.assertTrue(export.is_file())
        second = Path(self.cli("history", "--export")["history_path"])
        self.assertNotEqual(export, second)
        shutil.rmtree(export.parent)
        outside = self.root / "outside"
        outside.mkdir()
        export.parent.symlink_to(outside, target_is_directory=True)
        self.refused("history", "--export")
        self.assertEqual([], list(outside.iterdir()))

    def test_invalid_model_and_missing_session_return_structured_errors(self):
        self.refused("on", session=None)
        self.enable()
        self.refused("route", "--model", "unknown-model")
        self.assertEqual([], self.cli("status")["jobs"])

    def local_command(self, *args, cwd=None):
        result = subprocess.run(list(args), cwd=cwd or self.vault, env=self.env,
                                capture_output=True, text=True, timeout=45)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result.stdout.strip()

    def prepare_git_vault(self):
        # Only these integration cases add ordinary OS tools. Fake model
        # executables remain first, and no external Git remote is configured.
        self.env["PATH"] += os.pathsep + os.defpath
        self.vault = self.root / "git-vault"
        self.local_command(str(ROOT / "install.sh"), "--init", str(self.vault), cwd=self.root)
        self.cli_path = self.vault / "harness/scripts/delegate.py"
        self.local_command("git", "init", "-b", "main")
        self.local_command("git", "config", "user.name", "CLI Fixture")
        self.local_command("git", "config", "user.email", "cli-fixture@example.invalid")
        self.local_command("git", "config", "commit.gpgsign", "false")
        self.local_command("git", "add", "-A")
        self.local_command("git", "commit", "--no-gpg-sign", "-m", "Initial synthetic vault")
        remote = self.root / "remote.git"
        self.local_command("git", "init", "--bare", str(remote), cwd=self.root)
        self.local_command("git", "remote", "add", "origin", str(remote))
        self.local_command("git", "push", "-u", "origin", "main")
        readme = self.vault / "README.md"
        readme.write_text(readme.read_text() + "\nA scoped CLI test change.\n")
        return remote

    def test_git_model_review_prepare_execute_and_history_prove_actual_parity(self):
        remote = self.prepare_git_vault()
        self.enable()
        job = self.completed(self.cli("submit", "--task", "git", "--model", "luna",
                                      "--prompt", "Review the explicit README-only publication scope",
                                      "--file", "README.md", "--reason", "Bounded Git review"))
        args = ("git", "prepare", "--action", "commit-push", "--authority-reference", "synthetic-test-turn",
                "--authorize-commit", "--authorize-push", "--expected-branch", "main",
                "--expected-remote", str(remote), "--file", "README.md", "--message", "Publish synthetic README",
                "--job", job["id"])
        before_head = self.local_command("git", "rev-parse", "HEAD")
        denial = self.refused(*(item for item in args if item != "--authorize-push"))
        self.assertEqual("push_not_authorized", denial["code"])
        self.assertEqual(before_head, self.local_command("git", "rev-parse", "HEAD"))
        prepared = self.cli(*args)
        self.assertEqual("prepared", prepared["plan"]["outcome"]["status"])
        before = self.cli("history")["markdown"]
        self.assertIn("Resultado registrado: `prepared`", before)
        self.assertIn("Commit: `não confirmado`", before)
        self.enable("host-b")
        self.refused("git", "execute", prepared["plan_id"], session="host-b")
        self.assertNotIn(prepared["plan_id"], self.cli("history", session="host-b")["markdown"])
        result = self.cli("git", "execute", prepared["plan_id"])
        outcome = result["outcome"]
        self.assertEqual("complete", outcome["status"])
        self.assertTrue(outcome["parity"])
        local = self.local_command("git", "rev-parse", "HEAD")
        remote_head = self.local_command("git", "rev-parse", "refs/heads/main", cwd=remote)
        self.assertEqual(local, remote_head)
        self.assertEqual(local, outcome["commit_sha"])
        self.assertEqual(local, outcome["remote_sha"])
        history = self.cli("history")["markdown"]
        self.assertIn("Execução Git determinística", history)
        self.assertIn("gpt-5.6-luna (low)", history)
        self.assertIn("Paridade: confirmada", history)
        self.assertIn(local, history)
        self.assertEqual("", self.local_command("git", "status", "--porcelain"))

    def test_git_without_model_is_not_counted_as_a_model_execution(self):
        remote = self.prepare_git_vault()
        self.enable()
        prepared = self.cli("git", "prepare", "--action", "commit", "--authority-reference", "synthetic-local-only",
                            "--authorize-commit", "--expected-branch", "main", "--expected-remote", str(remote),
                            "--file", "README.md", "--message", "Local deterministic publication")
        self.cli("git", "execute", prepared["plan_id"])
        history = self.cli("history")["markdown"]
        self.assertIn("Sem contribuição de modelo vinculada", history)
        self.assertIn("SHA remoto: `não solicitado`", history)
        self.assertNotIn("Contribuição vinculada:", history)
        self.assertEqual([], self.cli("status")["jobs"])


if __name__ == "__main__":
    unittest.main()
