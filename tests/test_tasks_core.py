#!/usr/bin/env python3
"""Independent task CLI boundary tests; synthetic files, no providers or accounts.

Every operation crosses a fresh process boundary. Tests assert public behavior,
preserved artifacts and error contracts, never call the store's internal methods.
These checks establish E1 evidence only, not agent quality or human time savings.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "payload/harness/scripts/task.py"
FIXTURES = ROOT / "tests/fixtures/tasks"


def digest_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_manifest(root):
    """Do not follow symlinks while checking an owned temporary tree."""
    result = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            result[str(path.relative_to(root))] = ("symlink", os.readlink(path))
        elif path.is_file():
            result[str(path.relative_to(root))] = ("file", digest_file(path))
    return result


class TaskCLIBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="thinker-task-boundary-")
        self.root = Path(self.temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(mode=0o700)
        for name in ("source-a.md", "source-b.md", "historical.md"):
            shutil.copyfile(FIXTURES / name, self.workspace / name)
        self.state = self.root / "state"
        self.inputs = self.root / "inputs"
        self.inputs.mkdir(mode=0o700)
        self.input_number = 0
        self.provider_marker = self.root / "provider-was-launched"
        binary_dir = self.root / "bin"
        binary_dir.mkdir(mode=0o700)
        # Any accidental provider invocation has a visible, local-only effect.
        for name in ("codex", "claude", "grok"):
            binary = binary_dir / name
            binary.write_text(
                "#!" + sys.executable + "\nfrom pathlib import Path\n"
                + "Path(" + repr(str(self.provider_marker)) + ").write_text('unexpected')\n"
                + "raise SystemExit(97)\n", encoding="utf-8")
            binary.chmod(0o700)
        directories = {name: self.root / name for name in
                       ("home", "xdg-state", "xdg-config", "xdg-cache", "tmp",
                        "native-codex", "native-claude", "native-grok")}
        for path in directories.values():
            path.mkdir(mode=0o700)
        # Do not inherit credentials, native configuration, sessions or API keys.
        self.env = {
            "PATH": str(binary_dir), "HOME": str(directories["home"]),
            "XDG_STATE_HOME": str(directories["xdg-state"]),
            "XDG_CONFIG_HOME": str(directories["xdg-config"]),
            "XDG_CACHE_HOME": str(directories["xdg-cache"]),
            "CODEX_HOME": str(directories["native-codex"]),
            "CLAUDE_CONFIG_DIR": str(directories["native-claude"]),
            "GROK_HOME": str(directories["native-grok"]),
            "TMPDIR": str(directories["tmp"]), "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        self.original_sources = file_manifest(self.workspace)

    def tearDown(self):
        try:
            self.assertFalse(self.provider_marker.exists(), "Task CLI invoked a provider")
        finally:
            self.temporary.cleanup()

    def command(self, *args, workspace=None, state=None, extra_env=None, process_umask=-1):
        environment = dict(self.env)
        if extra_env:
            environment.update(extra_env)
        return subprocess.run(
            [sys.executable, "-B", str(CLI), "--workspace", str(workspace or self.workspace),
             "--state-dir", str(state or self.state), *map(str, args)],
            cwd=self.workspace, env=environment, capture_output=True, text=True,
            encoding="utf-8", timeout=15, umask=process_umask)

    def decode(self, completed):
        self.assertNotIn("Traceback", completed.stderr, completed.stderr)
        self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
        value = json.loads(completed.stdout)
        self.assertIsInstance(value, dict)
        return value

    def cli(self, *args, **kwargs):
        return self.decode(self.command(*args, **kwargs))

    def refused(self, *args, code=None, exit_code=None, **kwargs):
        completed = self.command(*args, **kwargs)
        self.assertNotEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertNotIn("Traceback", completed.stderr, completed.stderr)
        if exit_code is not None:
            self.assertEqual(exit_code, completed.returncode, completed.stderr)
        value = json.loads(completed.stderr)
        self.assertIsInstance(value.get("error"), dict)
        self.assertIsInstance(value["error"].get("code"), str)
        self.assertTrue(value["error"].get("message"))
        if code is not None:
            self.assertEqual(code, value["error"]["code"], value)
        return value["error"]

    def create(self, title="Synthetic task A", objective="A_OBJECTIVE: investigate without writing.",
               request_id=None):
        args = ["create", "--title", title, "--objective", objective]
        if request_id is not None:
            args += ["--request-id", request_id]
        return self.cli(*args)

    def checkpoint_input(self, fixture_or_value):
        if isinstance(fixture_or_value, str):
            value = json.loads((FIXTURES / fixture_or_value).read_text(encoding="utf-8"))
        else:
            value = fixture_or_value
        self.input_number += 1
        path = self.inputs / ("checkpoint-" + str(self.input_number) + ".json")
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def checkpoint(self, task, fixture_or_value, request_id="checkpoint-request"):
        return self.cli("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                        "--file", self.checkpoint_input(fixture_or_value),
                        "--request-id", request_id)

    def task_snapshot(self, task_id):
        tasks = self.cli("snapshot")["tasks"]
        return next(task for task in tasks if task["task_id"] == task_id)

    def resume(self, task, budget=32768):
        return self.cli("resume", task["task_id"], "--budget-bytes", budget)

    def task_document(self, task):
        return self.state / "tasks" / (task["task_id"] + ".json")

    def assert_sources_preserved(self):
        self.assertEqual(self.original_sources, file_manifest(self.workspace))

    def corrected_task(self):
        task = self.checkpoint(self.create(), "task-a.initial.json", "initial")
        return self.checkpoint(task, "task-a.corrected.json", "human-correction")

    def test_empty_snapshot_and_create_need_no_provider_or_workspace_write(self):
        snapshot = self.cli("snapshot")
        self.assertEqual(([], []), (snapshot["tasks"], snapshot["attention"]))
        task = self.create()
        self.assertEqual(task["id"], task["task_id"])
        self.assertEqual((1, 1, "open", None),
                         (task["revision"], task["generation"], task["state"], task["checkpoint"]))
        self.assertEqual(1, len(self.cli("snapshot")["tasks"]))
        self.assert_sources_preserved()

    def test_two_interleaved_tasks_resume_explicit_id_not_most_recent(self):
        task_a = self.corrected_task()
        task_b = self.checkpoint(self.create(task_a["title"], "B_OBJECTIVE: unrelated work."),
                                 "task-b.json", "b-checkpoint")
        self.assertNotEqual(task_a["task_id"], task_b["task_id"])
        packet_a, packet_b = self.resume(task_a), self.resume(task_b)
        self.assertEqual(task_a["task_id"], packet_a["task_id"])
        self.assertIn("A_REFUSAL_CURRENT", packet_a["text"])
        self.assertNotIn("B_MORE_RECENT", packet_a["text"])
        self.assertIn("B_MORE_RECENT", packet_b["text"])
        self.assertNotIn("A_REFUSAL_CURRENT", packet_b["text"])
        self.assert_sources_preserved()

    def test_unknown_explicit_task_never_falls_back_to_an_existing_recent_task(self):
        self.corrected_task()
        before = file_manifest(self.state)
        self.refused("resume", "00000000-0000-4000-8000-000000000001", "--budget-bytes", 32768,
                     code="not_found", exit_code=4)
        self.assertEqual(before, file_manifest(self.state))

    def test_checkpoint_to_fresh_process_resume_preserves_correction_and_authority(self):
        task = self.corrected_task()
        packet = self.resume(task)
        self.assertTrue(packet["ready"])
        self.assertIn(task["task_id"], packet["text"])
        self.assertIn("A_REFUSAL_CURRENT", packet["text"])
        self.assertIn("A_ANALYSIS_ONLY", packet["text"])
        self.assertNotIn("A_APPROVAL_OLD", packet["text"])
        self.assertIn("a-approval", packet["text"], "Correction lost its supersedes pointer")
        self.assertEqual(len(packet["text"].encode("utf-8")), packet["used_bytes"])
        self.assert_sources_preserved()

    def test_later_checkpoint_cannot_silently_drop_active_correction_or_constraint(self):
        task = self.checkpoint(self.corrected_task(), "task-a.later.json", "later")
        packet = self.resume(task)
        self.assertIn("A_LATER_UNRELATED", packet["text"])
        self.assertIn("A_REFUSAL_CURRENT", packet["text"])
        self.assertIn("A_ANALYSIS_ONLY", packet["text"])
        self.assertNotIn("A_APPROVAL_OLD", packet["text"])

    def test_proposal_is_not_accepted_and_origin_is_declared(self):
        task = self.checkpoint(self.create(), "task-a.initial.json")
        current = self.task_snapshot(task["task_id"])
        decisions = {item["id"]: item for item in current["checkpoint"]["decisions"]}
        self.assertEqual("proposed", decisions["a-unaccepted"]["status"])
        self.assertEqual("accepted", decisions["a-approval"]["status"])
        packet = self.resume(task)
        self.assertIn("principal_reported", packet["text"])
        self.assertIn("proposed", packet["text"])
        self.assertNotIn('"feedback": "useful"', json.dumps(current))

    def test_checkpoint_cannot_forge_host_supervisor_or_local_verification_provenance(self):
        task = self.checkpoint(self.create(), "task-a.initial.json")
        before = file_manifest(self.state)
        number = 0
        for origin in ("host_event", "supervisor_observed", "local_verification"):
            for group in (None, "decisions", "corrections", "pending", "constraints"):
                with self.subTest(origin=origin, group=group):
                    value = {"schema": 1, "state": "Untrusted provenance claim."}
                    if group is None:
                        value["origin"] = origin
                    else:
                        item = {"id": "untrusted-" + group, "text": "Synthetic report.", "origin": origin}
                        if group == "corrections":
                            item["supersedes"] = "a-approval"
                        value[group] = [item]
                    number += 1
                    path = self.checkpoint_input(value)
                    self.refused("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                                 "--file", path, "--request-id", "untrusted-origin-" + str(number),
                                 code="invalid_input", exit_code=2)
                    self.assertEqual(before, file_manifest(self.state))

    def test_new_provider_sessions_link_to_same_task_without_observed_execution(self):
        task = self.create()
        for provider, external_id in (("synthetic-codex", "thread-1"),
                                      ("synthetic-claude", "thread-2")):
            task = self.cli("link", task["task_id"], "--kind", "session",
                            "--external-id", external_id, "--provider", provider,
                            "--expected-revision", task["revision"],
                            "--request-id", external_id)
        current = self.task_snapshot(task["task_id"])
        self.assertEqual(2, len(current["links"]))
        self.assertEqual({"unknown"}, {link["execution_state"] for link in current["links"]})
        self.assertEqual(task["task_id"], self.resume(task)["task_id"])

    def test_hash_match_is_byte_identity_only_not_truth_or_current_authority(self):
        task = self.checkpoint(self.create(), "task-a.initial.json")
        packet = self.resume(task)
        self.assertTrue(packet["ready"])
        self.assertEqual({"unchanged"}, {source["status"] for source in packet["sources"]})
        self.assertEqual({"byte_identity_only"},
                         {source["verification_scope"] for source in packet["sources"]})
        self.assertNotIn("SOURCE_A_NOT_A_FACT", packet["text"])
        self.assertNotIn("SOURCE_A_UNTRUSTED_INSTRUCTION", packet["text"])
        self.assert_sources_preserved()

    def test_changed_source_blocks_ready_and_export_without_changing_captured_hash(self):
        task = self.checkpoint(self.create(), "task-a.initial.json")
        original_hash = digest_file(self.workspace / "source-a.md")
        (self.workspace / "source-a.md").write_text("SYNTHETIC_CHANGED_SOURCE\n", encoding="utf-8")
        packet = self.resume(task)
        source = next(item for item in packet["sources"] if item["path"] == "source-a.md")
        self.assertFalse(packet["ready"])
        self.assertEqual("changed", source["status"])
        self.assertEqual(original_hash, source["sha256"])
        self.assertNotEqual(source["sha256"], source["current_sha256"])
        self.refused("export", task["task_id"], "--name", "changed-handoff.md")
        self.assertFalse((self.state / "exports/changed-handoff.md").exists())

    def test_omitting_critical_evidence_does_not_clear_source_changed_until_explicit_refresh(self):
        task = self.checkpoint(self.create(), "task-a.initial.json")
        original_hash = digest_file(self.workspace / "source-a.md")
        (self.workspace / "source-a.md").write_text("CHANGED_BEFORE_UNRELATED_CHECKPOINT\n", encoding="utf-8")
        task = self.checkpoint(task, {"schema": 1, "state": "Unrelated update, no source reconciliation."},
                               "omit-source-reference")
        packet = self.resume(task)
        self.assertFalse(packet["ready"])
        source = next(item for item in packet["sources"] if item["path"] == "source-a.md")
        self.assertEqual(("changed", original_hash), (source["status"], source["sha256"]))
        task = self.checkpoint(task, {
            "schema": 1, "state": "Explicit reference refresh; byte identity is not truth.",
            "evidence": [{"path": "source-a.md", "role": "canonical", "critical": True}],
        }, "explicit-reference-refresh")
        refreshed = self.resume(task)
        self.assertTrue(refreshed["ready"])
        source = next(item for item in refreshed["sources"] if item["path"] == "source-a.md")
        self.assertEqual("unchanged", source["status"])
        self.assertNotEqual(original_hash, source["sha256"])
        self.assertEqual("byte_identity_only", source["verification_scope"])

    def test_missing_source_is_not_empty_success_or_unchanged(self):
        task = self.checkpoint(self.create(), "task-a.initial.json")
        (self.workspace / "source-a.md").unlink()
        packet = self.resume(task)
        source = next(item for item in packet["sources"] if item["path"] == "source-a.md")
        self.assertFalse(packet["ready"])
        self.assertEqual("missing", source["status"])
        self.assertIsNone(source["current_sha256"])
        self.assertTrue(packet["attention"])

    def test_source_replaced_by_external_symlink_is_unverifiable(self):
        task = self.checkpoint(self.create(), "task-a.initial.json")
        outside = self.root / "outside-source.md"
        outside.write_text("OUTSIDE_CONTENT_MUST_NOT_ENTER_PACKET\n", encoding="utf-8")
        (self.workspace / "source-a.md").unlink()
        (self.workspace / "source-a.md").symlink_to(outside)
        packet = self.resume(task)
        source = next(item for item in packet["sources"] if item["path"] == "source-a.md")
        self.assertFalse(packet["ready"])
        self.assertEqual("unverifiable", source["status"])
        self.assertNotIn("OUTSIDE_CONTENT_MUST_NOT_ENTER_PACKET", json.dumps(packet))

    def test_critical_overflow_fails_without_partial_packet_or_export(self):
        task = self.corrected_task()
        before = file_manifest(self.state)
        error = self.refused("resume", task["task_id"], "--budget-bytes", 1,
                             code="budget_exceeded", exit_code=5)
        self.assertGreater(error["details"]["required_bytes"], 1)
        self.refused("export", task["task_id"], "--name", "too-small.md",
                     "--budget-bytes", 1, code="budget_exceeded", exit_code=5)
        self.assertEqual(before, file_manifest(self.state))

    def test_optional_overflow_is_disclosed_while_critical_context_survives(self):
        task = self.corrected_task()
        minimum = self.resume(task)["used_bytes"]
        checkpoint = {
            "schema": 1, "state": "Short unrelated update.",
            "decisions": [{"id": "optional-long", "text": "OPTIONAL_LONG_MARKER " + "z" * 12000,
                           "status": "proposed", "critical": False}],
            "evidence": [{"path": "source-a.md", "role": "canonical", "critical": True}],
        }
        task = self.checkpoint(task, checkpoint, "optional-update")
        packet = self.resume(task, minimum + 1024)
        self.assertLessEqual(packet["used_bytes"], minimum + 1024)
        self.assertIn("A_REFUSAL_CURRENT", packet["text"])
        self.assertIn("A_ANALYSIS_ONLY", packet["text"])
        self.assertNotIn("OPTIONAL_LONG_MARKER", packet["text"])
        self.assertIn("optional-long", json.dumps(packet["omitted"]))
        self.assertTrue(packet["omitted"])

    def test_utf8_budget_measures_bytes_not_characters_or_provider_tokens(self):
        objective = "UTF8_OBJECTIVE: correção, autorização e ação. 🧪 " * 12
        task = self.create(objective=objective)
        task = self.checkpoint(task, {"schema": 1, "state": "Pronto para análise sintética."})
        packet = self.resume(task)
        self.assertGreater(packet["used_bytes"], len(packet["text"]))
        self.assertEqual(len(packet["text"].encode("utf-8")), packet["used_bytes"])
        self.assertLessEqual(packet["used_bytes"], packet["budget_bytes"])

    def test_reset_forget_excludes_previous_generation_without_history_fallback(self):
        task = self.corrected_task()
        task = self.cli("link", task["task_id"], "--kind", "session",
                        "--external-id", "pre-reset-thread", "--provider", "synthetic",
                        "--expected-revision", task["revision"], "--request-id", "old-link")
        reset = self.cli("reset", task["task_id"], "--expected-revision", task["revision"],
                         "--request-id", "forget-cut")
        self.assertEqual(task["generation"] + 1, reset["generation"])
        packet = self.resume(reset)
        self.assertFalse(packet["ready"])
        self.assertNotIn("A_REFUSAL_CURRENT", packet["text"])
        self.assertNotIn("A_ANALYSIS_ONLY", packet["text"])
        self.assertNotIn("pre-reset-thread", packet["text"])
        current = self.task_snapshot(reset["task_id"])
        self.assertIsNone(current["checkpoint"])
        self.assertEqual([], current["links"])
        renewed = self.checkpoint(reset, {"schema": 1, "state": "NEW_GENERATION_ONLY"}, "new-context")
        self.assertIn("NEW_GENERATION_ONLY", self.resume(renewed)["text"])
        self.assertNotIn("A_REFUSAL_CURRENT", self.resume(renewed)["text"])

    def test_same_request_is_idempotent_even_after_later_revision(self):
        task = self.create()
        checkpoint_path = self.checkpoint_input("task-a.initial.json")
        args = ("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                "--file", checkpoint_path, "--request-id", "repeat-me")
        first = self.cli(*args)
        later = self.checkpoint(first, "task-a.corrected.json", "later-request")
        repeated = self.cli(*args)
        self.assertEqual(first, repeated)
        current = self.task_snapshot(task["task_id"])
        self.assertEqual(later["revision"], current["revision"])
        self.assertIn("A_REFUSAL_CURRENT", self.resume(later)["text"])

    def test_request_id_reused_with_different_payload_is_conflict_without_effect(self):
        task = self.create()
        first = self.checkpoint(task, {"schema": 1, "state": "FIRST_PAYLOAD"}, "same-id")
        before = file_manifest(self.state)
        path = self.checkpoint_input({"schema": 1, "state": "DIFFERENT_PAYLOAD"})
        self.refused("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                     "--file", path, "--request-id", "same-id", code="request_conflict", exit_code=3)
        self.assertEqual(before, file_manifest(self.state))
        self.assertEqual(first["revision"], self.task_snapshot(task["task_id"])["revision"])

    def test_create_idempotency_preserves_existing_task_after_checkpoint(self):
        first = self.create(request_id="create-once")
        later = self.checkpoint(first, {"schema": 1, "state": "CURRENT_CHECKPOINT"})
        repeated = self.create(request_id="create-once")
        self.assertEqual(first, repeated)
        self.assertEqual(1, len(self.cli("snapshot")["tasks"]))
        self.assertEqual(later["revision"], self.task_snapshot(first["task_id"])["revision"])

    def test_two_processes_with_same_revision_have_one_winner_and_one_conflict(self):
        task = self.create()
        paths = [self.checkpoint_input({"schema": 1, "state": value})
                 for value in ("RACE_A", "RACE_B")]
        def run(index):
            return self.command("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                                "--file", paths[index], "--request-id", "race-" + str(index))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, (0, 1)))
        self.assertEqual([0, 3], sorted(result.returncode for result in results))
        winner = next(result for result in results if result.returncode == 0)
        loser = next(result for result in results if result.returncode != 0)
        winning_record = self.decode(winner)
        self.assertEqual("revision_conflict", json.loads(loser.stderr)["error"]["code"])
        current = self.task_snapshot(task["task_id"])
        self.assertEqual(task["revision"] + 1, current["revision"])
        self.assertEqual(winning_record["checkpoint"]["state"], current["checkpoint"]["state"])

    def test_two_processes_repeating_same_request_get_one_effect(self):
        task = self.create()
        path = self.checkpoint_input({"schema": 1, "state": "EXACTLY_ONE_METADATA_EFFECT"})
        args = ("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                "--file", path, "--request-id", "parallel-identical")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.command(*args), (0, 1)))
        records = [self.decode(result) for result in results]
        self.assertEqual(records[0], records[1])
        self.assertEqual(task["revision"] + 1, self.task_snapshot(task["task_id"])["revision"])

    def test_busy_store_reports_unavailable_within_bounded_wait_not_empty_success(self):
        self.create()
        before = file_manifest(self.state)
        code = ("import fcntl,os,sys\n"
                "fd=os.open(sys.argv[1],os.O_RDONLY)\n"
                "fcntl.flock(fd,fcntl.LOCK_EX)\n"
                "print('LOCKED',flush=True)\n"
                "sys.stdin.read(1)\n")
        with subprocess.Popen([sys.executable, "-B", "-c", code, str(self.state / ".lock")],
                              cwd=self.workspace, env=self.env, stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding="utf-8") as holder:
            try:
                self.assertTrue(select.select([holder.stdout], [], [], 3)[0], "Lock holder did not start")
                self.assertEqual("LOCKED", holder.stdout.readline().strip())
                started = time.monotonic()
                self.refused("snapshot", code="state_busy", exit_code=2)
                self.assertLess(time.monotonic() - started, 5, "Unavailable state hung instead of reporting busy")
                self.assertEqual(before, file_manifest(self.state))
            finally:
                holder.stdin.write("release\n")
                holder.stdin.flush()
                holder.stdin.close()
                try:
                    holder.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    holder.kill()
                    holder.wait(timeout=5)

    def test_process_crash_before_atomic_replace_preserves_last_committed_revision(self):
        task = self.checkpoint(self.create(), "task-a.initial.json", "committed-before-crash")
        document = self.task_document(task)
        before = document.read_bytes()
        probe_directory = self.root / "fault-probe"
        probe_directory.mkdir(mode=0o700)
        shutil.copyfile(FIXTURES / "fault-before-replace.py", probe_directory / "sitecustomize.py")
        marker = self.root / "fault-was-injected"
        checkpoint = self.checkpoint_input("task-a.corrected.json")
        args = ("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                "--file", checkpoint, "--request-id", "retry-interrupted-commit")
        interrupted = self.command(*args, extra_env={
            "PYTHONPATH": str(probe_directory), "TASK_TEST_FAULT_TARGET": str(document),
            "TASK_TEST_FAULT_MARKER": str(marker),
        })
        self.assertEqual(86, interrupted.returncode,
                         "Expected observed injected process crash: " + interrupted.stderr)
        self.assertTrue(marker.exists(), "Atomic replacement was not reached")
        self.assertEqual(before, document.read_bytes())
        recovered = self.task_snapshot(task["task_id"])
        self.assertEqual(task["revision"], recovered["revision"])
        self.assertNotIn("A_REFUSAL_CURRENT", self.resume(task)["text"])
        retried = self.cli(*args)
        self.assertEqual(task["revision"] + 1, retried["revision"])
        self.assertEqual(retried, self.cli(*args))
        self.assertIn("A_REFUSAL_CURRENT", self.resume(retried)["text"])
        self.assert_sources_preserved()

    def test_seen_deduplicates_only_that_event_and_does_not_resolve_condition(self):
        task = self.checkpoint(self.create(), "task-a.initial.json")
        (self.workspace / "source-a.md").write_text("CHANGED_ONCE\n", encoding="utf-8")
        snapshot = self.cli("snapshot")
        attention = next(item for item in snapshot["attention"] if item["kind"] == "source_changed")
        key = attention["key"]
        seen = self.cli("seen", task["task_id"], "--key", key,
                        "--expected-revision", task["revision"], "--request-id", "seen-first")
        current = next(item for item in self.cli("snapshot")["attention"] if item["key"] == key)
        self.assertIsNotNone(current["seen_at"])
        self.assertFalse(current["resolved"])
        self.assertFalse(self.resume(seen)["ready"])
        (self.workspace / "source-a.md").write_text("CHANGED_AGAIN\n", encoding="utf-8")
        later = [item for item in self.cli("snapshot")["attention"] if item["kind"] == "source_changed"]
        self.assertTrue(any(item["key"] != key and item["seen_at"] is None for item in later))

    def test_unknown_job_and_closed_task_never_imply_job_cancel_or_human_acceptance(self):
        task = self.create()
        task = self.cli("link", task["task_id"], "--kind", "job", "--external-id", "synthetic-job",
                        "--provider", "synthetic", "--expected-revision", task["revision"],
                        "--request-id", "job-link")
        current = self.task_snapshot(task["task_id"])
        self.assertEqual("unknown", current["links"][0]["execution_state"])
        self.assertTrue(any(item["kind"] == "job_state_unknown" for item in self.cli("snapshot")["attention"]))
        closed = self.cli("close", task["task_id"], "--expected-revision", task["revision"],
                          "--request-id", "close")
        self.assertEqual("closed", closed["state"])
        self.assertEqual("unknown", self.task_snapshot(task["task_id"])["links"][0]["execution_state"])
        reopened = self.cli("reopen", task["task_id"], "--expected-revision", closed["revision"],
                            "--request-id", "reopen")
        self.assertEqual(("open", closed["revision"] + 1), (reopened["state"], reopened["revision"]))

    def test_evidence_traversal_absolute_and_symlink_paths_are_refused_without_mutation(self):
        task = self.create()
        outside = self.root / "outside-evidence.md"
        outside.write_text("SYNTHETIC_OUTSIDE_ONLY\n", encoding="utf-8")
        (self.workspace / "external-link.md").symlink_to(outside)
        outside_dir = self.root / "outside-directory"
        outside_dir.mkdir()
        (outside_dir / "nested.md").write_text("SYNTHETIC_PARENT_ESCAPE\n", encoding="utf-8")
        (self.workspace / "linked-parent").symlink_to(outside_dir, target_is_directory=True)
        before = file_manifest(self.state)
        for index, path in enumerate(("../outside-evidence.md", str(outside),
                                      "external-link.md", "linked-parent/nested.md")):
            with self.subTest(path=path):
                checkpoint = self.checkpoint_input({"schema": 1, "state": "UNSAFE_SOURCE",
                                                    "evidence": [{"path": path}]})
                self.refused("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                             "--file", checkpoint, "--request-id", "unsafe-" + str(index),
                             code="unsafe_path")
                self.assertEqual(before, file_manifest(self.state))

    def test_state_inside_workspace_or_containing_workspace_is_refused(self):
        before = file_manifest(self.root)
        for state in (self.workspace / "state", self.root):
            with self.subTest(state=state):
                self.refused("create", "--title", "Unsafe", "--objective", "No writes.",
                             state=state, code="unsafe_path")
                self.assertEqual(before, file_manifest(self.root))

    def test_case_aliases_cannot_hide_workspace_state_overlap(self):
        workspace_alias = self.root / self.workspace.name.swapcase()
        ancestor_alias = self.root.parent / self.root.name.swapcase()
        if not (workspace_alias.exists() and ancestor_alias.exists()
                and os.path.samefile(workspace_alias, self.workspace)
                and os.path.samefile(ancestor_alias, self.root)):
            self.skipTest("Filesystem has no case aliases for the controlled temporary fixture")
        before = file_manifest(self.root)
        for state in (workspace_alias / "state", ancestor_alias):
            with self.subTest(state=state):
                self.refused("create", "--title", "Alias overlap", "--objective", "No workspace writes.",
                             state=state, code="unsafe_path")
                self.assertEqual(before, file_manifest(self.root))

    def test_state_symlink_and_symlink_ancestor_are_refused_before_writing(self):
        destination = self.root / "actual-state"
        destination.mkdir(mode=0o700)
        direct = self.root / "state-link"
        direct.symlink_to(destination, target_is_directory=True)
        parent = self.root / "parent-link"
        parent.symlink_to(destination, target_is_directory=True)
        before = file_manifest(destination)
        for state in (direct, parent / "nested-state"):
            with self.subTest(state=state):
                self.refused("create", "--title", "Unsafe", "--objective", "No writes.",
                             state=state, code="unsafe_path")
                self.assertEqual(before, file_manifest(destination))

    def test_existing_state_cannot_be_silently_rebound_to_another_workspace(self):
        self.create()
        other = self.root / "different-workspace"
        other.mkdir(mode=0o700)
        before = file_manifest(self.state)
        self.refused("snapshot", workspace=other)
        self.assertEqual(before, file_manifest(self.state))

    def test_task_id_cannot_escape_document_directory(self):
        self.create()
        before = file_manifest(self.root)
        self.refused("resume", "../outside-task", "--budget-bytes", 32768)
        self.assertEqual(before, file_manifest(self.root))

    def test_unknown_task_schema_fails_closed_and_is_not_overwritten(self):
        task = self.create()
        path = self.task_document(task)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["schema"] = 99
        path.write_text(json.dumps(document), encoding="utf-8")
        before = file_manifest(self.state)
        self.refused("snapshot", code="incompatible_schema")
        self.refused("close", task["task_id"], "--expected-revision", task["revision"],
                     "--request-id", "should-not-downgrade", code="incompatible_schema")
        self.assertEqual(before, file_manifest(self.state))

    def test_unknown_workspace_schema_fails_closed_without_reinitializing(self):
        self.create()
        path = self.state / "workspace.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["schema"] = 99
        path.write_text(json.dumps(document), encoding="utf-8")
        before = file_manifest(self.state)
        self.refused("snapshot", code="incompatible_schema")
        self.refused("create", "--title", "No downgrade", "--objective", "Preserve future state.",
                     code="incompatible_schema")
        self.assertEqual(before, file_manifest(self.state))

    def test_corrupt_task_or_registry_is_unavailable_not_an_empty_snapshot(self):
        task = self.create()
        for path in (self.task_document(task), self.state / "workspace.json"):
            with self.subTest(path=path.name):
                valid = path.read_bytes()
                path.write_bytes(b'{"schema":1,"truncated":')
                before = file_manifest(self.state)
                self.refused("snapshot", code="state_unavailable")
                self.refused("resume", task["task_id"], "--budget-bytes", 32768,
                             code="state_unavailable")
                self.assertEqual(before, file_manifest(self.state))
                path.write_bytes(valid)

    def test_valid_json_with_invalid_record_shape_is_unavailable_without_repair(self):
        task = self.create()
        path = self.task_document(task)
        valid = path.read_bytes()
        document = json.loads(valid)
        for field, value in (("revision", "not-an-integer"), ("generation", -1),
                             ("state", "executed-and-accepted"), ("receipts", [])):
            with self.subTest(field=field):
                corrupted = dict(document)
                corrupted[field] = value
                path.write_text(json.dumps(corrupted), encoding="utf-8")
                before = file_manifest(self.state)
                self.refused("snapshot", code="state_unavailable")
                self.assertEqual(before, file_manifest(self.state))
                path.write_bytes(valid)

    def test_unknown_checkpoint_schema_does_not_modify_valid_task(self):
        task = self.create()
        path = self.checkpoint_input({"schema": 99, "state": "FUTURE_CHECKPOINT"})
        before = file_manifest(self.state)
        self.refused("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                     "--file", path, "--request-id", "future-input", code="incompatible_schema")
        self.assertEqual(before, file_manifest(self.state))

    def test_export_is_portable_external_and_never_overwrites_existing_file(self):
        task = self.corrected_task()
        exported = self.cli("export", task["task_id"], "--name", "portable-handoff.md")
        path = self.state / "exports/portable-handoff.md"
        self.assertEqual(path, Path(exported["path"]))
        text = path.read_text(encoding="utf-8")
        self.assertIn(task["task_id"], text)
        self.assertIn("A_REFUSAL_CURRENT", text)
        self.assertIn("A_ANALYSIS_ONLY", text)
        self.assertEqual(digest_file(path), exported["sha256"])
        self.assertEqual(len(path.read_bytes()), exported["bytes"])
        before = path.read_bytes()
        self.refused("export", task["task_id"], "--name", "portable-handoff.md")
        self.assertEqual(before, path.read_bytes())
        self.assert_sources_preserved()

    def test_state_and_export_are_private_even_under_permissive_process_umask(self):
        task = self.cli("create", "--title", "Private metadata", "--objective", "Synthetic only.",
                        process_umask=0)
        path = self.checkpoint_input({"schema": 1, "state": "PRIVATE_SYNTHETIC_STATE"})
        task = self.cli("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                        "--file", path, "--request-id", "private-checkpoint", process_umask=0)
        self.cli("export", task["task_id"], "--name", "private-handoff.md", process_umask=0)
        for path in (self.state, self.state / "tasks", self.state / "workspace.json",
                     self.task_document(task), self.state / "exports", self.state / "exports/private-handoff.md"):
            with self.subTest(path=path.name):
                self.assertEqual(0, path.stat().st_mode & 0o077, "Task state is accessible to another user")

    def test_preexisting_shared_state_directory_is_refused_without_repair(self):
        self.state.mkdir(mode=0o755)
        self.state.chmod(0o755)
        before = self.state.stat().st_mode
        self.refused("create", "--title", "Unsafe permissions", "--objective", "No shared state.")
        self.assertEqual([], list(self.state.iterdir()))
        self.assertEqual(before, self.state.stat().st_mode)

    def test_export_traversal_absolute_and_symlink_destination_are_refused(self):
        task = self.corrected_task()
        outside = self.root / "outside-export.md"
        outside.write_text("DO_NOT_OVERWRITE\n", encoding="utf-8")
        exports = self.state / "exports"
        exports.mkdir(mode=0o700, exist_ok=True)
        (exports / "linked.md").symlink_to(outside)
        before = file_manifest(self.root)
        for name in ("../escaped.md", "folder/nested.md", str(outside), "linked.md"):
            with self.subTest(name=name):
                self.refused("export", task["task_id"], "--name", name, code="unsafe_path")
                self.assertEqual(before, file_manifest(self.root))

    def test_export_directory_symlink_cannot_redirect_handoff_outside_state(self):
        task = self.corrected_task()
        outside = self.root / "outside-exports"
        outside.mkdir(mode=0o700)
        exports = self.state / "exports"
        if exports.exists():
            exports.rmdir()
        exports.symlink_to(outside, target_is_directory=True)
        before = file_manifest(self.root)
        self.refused("export", task["task_id"], "--name", "escaped.md", code="unsafe_path")
        self.assertEqual(before, file_manifest(self.root))


if __name__ == "__main__":
    unittest.main()
