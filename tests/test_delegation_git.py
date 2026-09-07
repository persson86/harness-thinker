#!/usr/bin/env python3
"""Black-box Git publication tests using installed synthetic vaults only."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "payload/harness/scripts"))

from thinker_delegation.git_publish import (  # noqa: E402
    GitPublisher,
    PublicationError,
    execute_plan,
    prepare_plan,
)


def run(*argv, cwd, check=True):
    completed = subprocess.run(
        list(argv), cwd=str(cwd), text=True, capture_output=True, check=False,
    )
    if check and completed.returncode:
        raise AssertionError(
            "command failed: %r\nstdout=%s\nstderr=%s"
            % (argv, completed.stdout, completed.stderr)
        )
    return completed


class DelegationGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "vault"
        install = run(str(SOURCE_ROOT / "install.sh"), "--init", str(self.repo),
                      cwd=SOURCE_ROOT)
        self.assertEqual(install.returncode, 0)
        run("git", "init", "-b", "main", cwd=self.repo)
        run("git", "config", "user.name", "Synthetic Test", cwd=self.repo)
        run("git", "config", "user.email", "synthetic@example.invalid", cwd=self.repo)
        run("git", "add", "-A", cwd=self.repo)
        run("git", "commit", "--no-gpg-sign", "-m", "initial vault", cwd=self.repo)
        self.remote = self.root / "remote.git"
        run("git", "init", "--bare", str(self.remote), cwd=self.root)
        run("git", "remote", "add", "origin", str(self.remote), cwd=self.repo)
        run("git", "push", "-u", "origin", "main", cwd=self.repo)
        self.plan = self.root / "plans" / "publication.json"
        self.plan.parent.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, relative="README.md", text="\nreviewed change\n"):
        path = self.repo / relative
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")
        return relative

    def authority(self, *, commit=False, push=False):
        return {"reference": "session:test-turn", "commit": commit, "push": push}

    def prepare(self, action, files=(), message=None, authority=None, **extra):
        return prepare_plan(
            repo=self.repo,
            plan_path=self.plan,
            expected_branch="main",
            remote_name="origin",
            expected_remote_url=str(self.remote),
            action=action,
            authority=authority or self.authority(
                commit=action in {"commit", "commit-push"},
                push=action in {"push", "commit-push"},
            ),
            files=files,
            message=message,
            **extra,
        )

    def head(self, cwd=None):
        return run("git", "rev-parse", "HEAD", cwd=cwd or self.repo).stdout.strip()

    def remote_head(self):
        return run("git", "rev-parse", "refs/heads/main", cwd=self.remote).stdout.strip()

    def assert_error(self, code, function, *args, **kwargs):
        with self.assertRaises(PublicationError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_commit_push_validates_commits_and_proves_parity(self):
        changed = self.edit()
        prepared = self.prepare("commit-push", [changed], "publish reviewed note")
        self.assertEqual(prepared["spec"]["push_commits"], [])
        complete = execute_plan(self.plan)
        self.assertEqual(complete["outcome"]["status"], "complete")
        self.assertTrue(complete["outcome"]["parity"])
        self.assertEqual(self.head(), self.remote_head())
        self.assertEqual(run("git", "status", "--porcelain", cwd=self.repo).stdout, "")

    def test_commit_only_never_contacts_inaccessible_remote(self):
        unreachable = self.root / "does-not-exist.git"
        run("git", "remote", "set-url", "origin", str(unreachable), cwd=self.repo)
        changed = self.edit()
        prepare_plan(
            repo=self.repo, plan_path=self.plan, expected_branch="main",
            remote_name="origin", expected_remote_url=str(unreachable), action="commit",
            authority=self.authority(commit=True), files=[changed], message="local only",
        )
        before_remote = self.remote_head()
        result = execute_plan(self.plan)
        self.assertEqual(result["outcome"]["status"], "complete")
        self.assertIsNone(result["outcome"]["parity"])
        self.assertEqual(self.remote_head(), before_remote)

    def test_push_only_publishes_exact_reviewed_commit_range(self):
        self.edit()
        run("git", "add", "README.md", cwd=self.repo)
        run("git", "commit", "--no-gpg-sign", "-m", "local reviewed commit", cwd=self.repo)
        local = self.head()
        plan = self.prepare("push")
        self.assertEqual(plan["spec"]["push_commits"], [local])
        result = execute_plan(self.plan)
        self.assertEqual(result["outcome"]["remote_sha"], local)

    def test_commit_and_push_authority_are_independent(self):
        changed = self.edit()
        self.assert_error(
            "push_not_authorized", self.prepare, "commit-push", [changed], "message",
            self.authority(commit=True, push=False),
        )
        self.assertFalse(self.plan.exists())

    def test_rejects_preexisting_stage_and_unrelated_dirty_file(self):
        changed = self.edit()
        run("git", "add", changed, cwd=self.repo)
        self.assert_error("preexisting_stage", self.prepare, "commit", [changed], "message")
        run("git", "restore", "--staged", changed, cwd=self.repo)
        self.edit("vault-heuristics.md")
        self.assert_error("scope_mismatch", self.prepare, "commit", [changed], "message")

    def test_rejects_hidden_intent_to_add_index_state(self):
        changed = "wiki/reference/draft.md"
        (self.repo / changed).write_text("draft\n", encoding="utf-8")
        run("git", "add", "--intent-to-add", changed, cwd=self.repo)
        self.assert_error("preexisting_stage", self.prepare, "commit", [changed], "message")

    def test_rejects_raw_config_secret_log_and_installed_harness(self):
        cases = (
            ("raw/source.md", "source"),
            ("vault.config.json", "{}"),
            ("wiki/reference/credentials.json", "{}"),
            ("wiki/reference/debug.log", "trace"),
            ("harness/contract.md", "changed"),
        )
        for relative, content in cases:
            with self.subTest(relative=relative):
                path = self.repo / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                self.assert_error(
                    "forbidden_path", self.prepare, "commit", [relative], "message"
                )
                run("git", "restore", "--", relative, cwd=self.repo, check=False)
                if path.exists() and relative in {"raw/source.md", "wiki/reference/credentials.json",
                                                  "wiki/reference/debug.log"}:
                    path.unlink()

    def test_rejects_symlink_and_path_traversal(self):
        outside = self.root / "outside.md"
        outside.write_text("secret", encoding="utf-8")
        link = self.repo / "wiki/reference/link.md"
        link.symlink_to(outside)
        self.assert_error("symlink_path", self.prepare, "commit", ["wiki/reference/link.md"], "m")
        self.assert_error("unsafe_path", self.prepare, "commit", ["../outside.md"], "m")

    def test_plan_is_invalidated_by_reviewed_content_drift(self):
        changed = self.edit()
        self.prepare("commit", [changed], "message")
        self.edit(text="more drift\n")
        self.assert_error("plan_stale", execute_plan, self.plan)
        self.assertEqual(self.head(), json.loads(self.plan.read_text())["spec"]["snapshot"]["head"])

    def test_plan_is_invalidated_by_ignored_raw_tree_drift(self):
        raw = self.repo / "raw/source.txt"
        raw.write_text("immutable source", encoding="utf-8")
        changed = self.edit()
        self.prepare("commit", [changed], "message")
        raw.write_text("mutated source", encoding="utf-8")
        self.assert_error("plan_stale", execute_plan, self.plan)

    def test_remote_change_after_plan_is_rejected_before_commit(self):
        changed = self.edit()
        self.prepare("commit-push", [changed], "message")
        other = self.root / "other"
        run("git", "clone", str(self.remote), str(other), cwd=self.root)
        run("git", "config", "user.name", "Other", cwd=other)
        run("git", "config", "user.email", "other@example.invalid", cwd=other)
        (other / "remote-change.md").write_text("remote", encoding="utf-8")
        run("git", "add", "remote-change.md", cwd=other)
        run("git", "commit", "--no-gpg-sign", "-m", "remote change", cwd=other)
        run("git", "push", "origin", "main", cwd=other)
        before = self.head()
        self.assert_error("remote_changed", execute_plan, self.plan)
        self.assertEqual(self.head(), before)

    def test_divergent_remote_is_rejected_during_prepare(self):
        other = self.root / "other-divergent"
        run("git", "clone", str(self.remote), str(other), cwd=self.root)
        run("git", "config", "user.name", "Other", cwd=other)
        run("git", "config", "user.email", "other@example.invalid", cwd=other)
        (other / "remote-change.md").write_text("remote", encoding="utf-8")
        run("git", "add", "remote-change.md", cwd=other)
        run("git", "commit", "--no-gpg-sign", "-m", "remote side", cwd=other)
        run("git", "push", "origin", "main", cwd=other)
        self.edit()
        run("git", "add", "README.md", cwd=self.repo)
        run("git", "commit", "--no-gpg-sign", "-m", "local side", cwd=self.repo)
        self.assert_error("remote_diverged", self.prepare, "push")

    def test_local_commit_outside_plan_is_rejected(self):
        self.edit()
        run("git", "add", "README.md", cwd=self.repo)
        run("git", "commit", "--no-gpg-sign", "-m", "authorized pending", cwd=self.repo)
        self.prepare("push")
        self.edit("vault-heuristics.md")
        run("git", "add", "vault-heuristics.md", cwd=self.repo)
        run("git", "commit", "--no-gpg-sign", "-m", "not in plan", cwd=self.repo)
        self.assert_error("plan_stale", execute_plan, self.plan)
        self.assertNotEqual(self.remote_head(), self.head())

    def test_pending_push_already_integrated_finishes_without_duplicate(self):
        self.edit()
        run("git", "add", "README.md", cwd=self.repo)
        run("git", "commit", "--no-gpg-sign", "-m", "pending", cwd=self.repo)
        self.prepare("push")
        local = self.head()
        run("git", "push", "origin", "main", cwd=self.repo)
        result = execute_plan(self.plan)
        self.assertEqual(result["outcome"]["status"], "complete")
        self.assertTrue(result["outcome"].get("integrated_before_retry"))
        self.assertEqual(self.remote_head(), local)

    def test_repository_lock_refuses_parallel_execution(self):
        changed = self.edit()
        publisher = GitPublisher(self.repo)
        with publisher.lock():
            self.assert_error("repo_locked", self.prepare, "commit", [changed], "message")

    def test_hook_failure_is_persisted_and_never_pushes(self):
        changed = self.edit()
        self.prepare("commit-push", [changed], "message")
        before = self.head()
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook.chmod(0o755)
        self.assert_error("commit_failed", execute_plan, self.plan)
        outcome = json.loads(self.plan.read_text(encoding="utf-8"))["outcome"]
        self.assertEqual(outcome["status"], "commit_failed")
        self.assertEqual(self.head(), before)
        self.assertEqual(self.remote_head(), before)

    def test_push_timeout_persists_commit_and_retry_does_not_duplicate_it(self):
        changed = self.edit()
        self.prepare("commit-push", [changed], "one commit only")

        class TimeoutActualPush:
            def __init__(self):
                self.actual_pushes = 0

            def __call__(inner, argv, *, cwd, timeout, env=None):
                if (list(argv[:2]) == ["git", "push"] and "--dry-run" not in argv):
                    inner.actual_pushes += 1
                    raise subprocess.TimeoutExpired(argv, timeout)
                return subprocess.run(
                    list(argv), cwd=str(cwd), timeout=timeout, check=False,
                    text=True, capture_output=True, env=dict(env) if env else None,
                )

        runner = TimeoutActualPush()
        self.assert_error("push_failed", execute_plan, self.plan, _runner=runner)
        first_commit = self.head()
        persisted = json.loads(self.plan.read_text(encoding="utf-8"))["outcome"]
        self.assertEqual(persisted["status"], "push_failed")
        self.assertEqual(persisted["commit_sha"], first_commit)
        self.assertEqual(runner.actual_pushes, 1)
        completed = execute_plan(self.plan)
        self.assertEqual(completed["outcome"]["status"], "complete")
        self.assertEqual(self.head(), first_commit)
        self.assertEqual(self.remote_head(), first_commit)

    def test_plan_digest_rejects_authority_tampering(self):
        changed = self.edit()
        self.prepare("commit", [changed], "message")
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        plan["spec"]["authority"]["push"] = True
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        self.assert_error("plan_tampered", execute_plan, self.plan)

    def test_child_process_is_refused_before_commands_or_plan_reads(self):
        class BombRunner:
            def __init__(self):
                self.calls = 0

            def __call__(inner, *args, **kwargs):
                inner.calls += 1
                raise AssertionError("runner must not be called")

        runner = BombRunner()
        missing = self.root / "missing-plan.json"
        with patch.dict(os.environ, {"THINKER_DELEGATION_CHILD": "1"}):
            self.assert_error(
                "child_git_forbidden", prepare_plan,
                repo=self.repo, plan_path=missing, expected_branch="main",
                remote_name="origin", expected_remote_url=str(self.remote),
                action="commit", authority=self.authority(commit=True),
                files=["README.md"], message="blocked", _runner=runner,
            )
            self.assert_error(
                "child_git_forbidden", execute_plan, missing, _runner=runner,
            )
        self.assertEqual(runner.calls, 0)
        self.assertFalse(missing.exists())

    def test_forged_schema_action_and_extra_envelope_fields_are_rejected(self):
        changed = self.edit()
        self.prepare("commit", [changed], "message")
        original = json.loads(self.plan.read_text(encoding="utf-8"))

        forged = json.loads(json.dumps(original))
        forged["unexpected"] = True
        self.plan.write_text(json.dumps(forged), encoding="utf-8")
        self.assert_error("invalid_plan", execute_plan, self.plan)

        forged = json.loads(json.dumps(original))
        forged["schema"] = 999
        self.plan.write_text(json.dumps(forged), encoding="utf-8")
        self.assert_error("invalid_plan", execute_plan, self.plan)

        forged = json.loads(json.dumps(original))
        forged["spec"]["action"] = "force-push"
        canonical = json.dumps(
            forged["spec"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        forged["plan_digest"] = hashlib.sha256(canonical).hexdigest()
        self.plan.write_text(json.dumps(forged), encoding="utf-8")
        self.assert_error("invalid_plan", execute_plan, self.plan)

    def test_invalid_timeout_is_rejected_before_repository_or_plan_access(self):
        missing = self.root / "missing-plan.json"
        self.assert_error("invalid_timeout", execute_plan, missing, timeout=0)
        self.assert_error(
            "invalid_timeout", prepare_plan,
            repo=self.root / "missing-repo", plan_path=missing,
            expected_branch="main", remote_name="origin",
            expected_remote_url=str(self.remote), action="push",
            authority=self.authority(push=True), timeout=False,
        )

    def test_execution_guard_closes_after_validation_before_commit(self):
        changed = self.edit()
        self.prepare("commit", [changed], "guarded commit")
        before = self.head()
        commands = []

        class GuardClosed(RuntimeError):
            pass

        def recording_runner(argv, *, cwd, timeout, env=None):
            commands.append(tuple(argv))
            return subprocess.run(
                list(argv), cwd=str(cwd), timeout=timeout, check=False,
                text=True, capture_output=True, env=dict(env) if env else None,
            )

        def guard():
            self.assertIn(
                ("python3", ".claude/scripts/build-index.py", "check"), commands
            )
            raise GuardClosed("feature disabled")

        with self.assertRaises(GuardClosed):
            execute_plan(self.plan, execution_guard=guard, _runner=recording_runner)
        self.assertEqual(self.head(), before)
        self.assertEqual(
            run("git", "diff", "--cached", "--name-only", cwd=self.repo).stdout, ""
        )
        outcome = json.loads(self.plan.read_text(encoding="utf-8"))["outcome"]
        self.assertEqual(outcome, {"status": "prepared"})

    def test_execution_guard_after_commit_preserves_outcome_and_skips_push(self):
        changed = self.edit()
        self.prepare("commit-push", [changed], "persist before guard")
        remote_before = self.remote_head()
        checks = 0

        class GuardClosed(RuntimeError):
            pass

        def guard():
            nonlocal checks
            checks += 1
            if checks == 3:
                raise GuardClosed("feature disabled after commit")

        with self.assertRaises(GuardClosed):
            execute_plan(self.plan, execution_guard=guard)
        committed = self.head()
        self.assertNotEqual(committed, remote_before)
        self.assertEqual(self.remote_head(), remote_before)
        outcome = json.loads(self.plan.read_text(encoding="utf-8"))["outcome"]
        self.assertEqual(outcome["status"], "commit_created")
        self.assertEqual(outcome["commit_sha"], committed)
        self.assertEqual(checks, 3)

    def test_explicit_authorized_existing_range_must_match(self):
        self.edit()
        run("git", "add", "README.md", cwd=self.repo)
        run("git", "commit", "--no-gpg-sign", "-m", "pending", cwd=self.repo)
        self.assert_error(
            "unauthorized_commit_range", self.prepare, "push",
            authorized_existing_commits=[],
        )


if __name__ == "__main__":
    unittest.main()
