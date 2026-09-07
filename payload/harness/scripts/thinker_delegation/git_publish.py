#!/usr/bin/env python3
"""Deterministic, review-gated Git publication for an installed Thinker vault.

The module deliberately has no model or shell-command execution surface.  A caller
prepares a JSON plan, reviews that plan outside this module, and later executes the
same persisted plan.  Authorization references are audit labels supplied by the
caller; they are not cryptographic proof of chat authorization.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit


PLAN_SCHEMA = 1
_ACTIONS = {"commit", "push", "commit-push"}
_REQUIRED_VAULT_PATHS = (
    "vault.config.json",
    "wiki",
    "raw",
    ".claude/scripts/build-index.py",
    "harness/scripts/verify.sh",
)
_FORBIDDEN_ROOTS = {"raw", "harness", ".claude", ".grok", ".git"}
_SECRET_NAMES = {
    ".env", ".npmrc", ".pypirc", "credentials", "credentials.json",
    "secrets", "secrets.json", "id_rsa", "id_ed25519",
}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".log"}
_HEX_SHA = re.compile(r"^[0-9a-f]{40,64}$")
_HEX_256 = re.compile(r"^[0-9a-f]{64}$")


class PublicationError(RuntimeError):
    """A safe, classified refusal that can be rendered by the parent CLI."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _assert_parent_executor() -> None:
    if os.environ.get("THINKER_DELEGATION_CHILD") == "1":
        raise PublicationError(
            "child_git_forbidden", "Delegated child processes cannot prepare or execute Git publication."
        )


def _validate_timeout(timeout: float) -> None:
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not 0 < timeout <= 300):
        raise PublicationError("invalid_timeout", "Command timeout must be between 0 and 300 seconds.")


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str
    stderr: str


class _SubprocessRunner:
    def __call__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout: float,
        env: Mapping[str, str] | None = None,
    ) -> _CommandResult:
        completed = subprocess.run(
            list(argv), cwd=str(cwd), timeout=timeout, check=False,
            text=True, capture_output=True, env=dict(env) if env else None,
        )
        return _CommandResult(completed.returncode, completed.stdout, completed.stderr)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _clean_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise PublicationError("invalid_metadata", "Job metadata must be a JSON object.")
    allowed = {"job_id", "provider", "model", "effort"}
    if set(value) - allowed:
        raise PublicationError("invalid_metadata", "Job metadata contains unsupported fields.")
    cleaned: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(item, str) or not item or len(item.encode("utf-8")) > 256:
            raise PublicationError("invalid_metadata", "Job metadata values must be short strings.")
        if any(ord(char) < 32 for char in item):
            raise PublicationError("invalid_metadata", "Job metadata contains control data.")
        cleaned[key] = item
    return cleaned


def _write_plan(path: Path, plan: Mapping[str, Any]) -> None:
    path = path.expanduser()
    if path.exists() and path.is_symlink():
        raise PublicationError("unsafe_plan_path", "Plan path must not be a symlink.")
    if not path.parent.is_dir():
        raise PublicationError("missing_plan_store", "Plan store directory does not exist.")
    payload = json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".git-publication-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _load_plan(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PublicationError("invalid_plan_path", "Plan must be a regular file.")
    if path.stat().st_size > 4 * 1024 * 1024:
        raise PublicationError("invalid_plan", "Publication plan exceeds the size limit.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PublicationError("invalid_plan", "Plan is not readable JSON.") from exc
    if (not isinstance(value, dict)
            or set(value) != {"schema", "spec", "plan_digest", "outcome"}
            or value.get("schema") != PLAN_SCHEMA):
        raise PublicationError("invalid_plan", "Unsupported publication plan schema.")
    spec = value.get("spec")
    if not isinstance(spec, dict) or value.get("plan_digest") != _digest(spec):
        raise PublicationError("plan_tampered", "Plan contents no longer match its digest.")
    required_spec = {
        "repo", "target", "action", "authority", "message", "files", "snapshot",
        "remote_head", "push_commits", "job_metadata",
    }
    target = spec.get("target")
    authority = spec.get("authority")
    snapshot = spec.get("snapshot")
    files = snapshot.get("files") if isinstance(snapshot, dict) else None
    outcome = value.get("outcome")
    if (set(spec) != required_spec
            or not isinstance(target, dict)
            or set(target) != {"branch", "remote_name", "remote_url"}
            or not isinstance(authority, dict)
            or set(authority) != {"reference", "commit", "push"}
            or not isinstance(snapshot, dict)
            or set(snapshot) != {
                "head", "index_digest", "staged_paths", "dirty_paths", "files",
                "raw_fingerprint",
            }
            or not isinstance(files, list)
            or any(not isinstance(item, dict) or set(item) != {
                "path", "sha256", "git_blob", "size", "mode",
            } for item in files)
            or not isinstance(outcome, dict)):
        raise PublicationError("invalid_plan", "Publication plan structure is invalid.")
    allowed_outcome = {
        "status", "commit_sha", "remote_sha", "parity", "error",
        "integrated_before_retry", "integrated_before_push", "reconciled_after_timeout",
    }
    if (not set(outcome).issubset(allowed_outcome)
            or outcome.get("status") not in {
                "prepared", "commit_created", "commit_failed", "commit_unknown",
                "stage_cleanup_failed", "push_failed", "push_unknown", "complete",
            }):
        raise PublicationError("invalid_plan", "Plan outcome state is invalid.")
    message = spec.get("message")
    wants_commit = spec.get("action") in {"commit", "commit-push"}
    remote_head = spec.get("remote_head")
    if (spec.get("action") not in _ACTIONS
            or not isinstance(spec.get("repo"), str)
            or not all(isinstance(target.get(key), str)
                       for key in ("branch", "remote_name", "remote_url"))
            or not isinstance(authority.get("reference"), str)
            or not authority.get("reference", "").strip()
            or len(authority.get("reference", "").encode("utf-8")) > 256
            or any(ord(char) < 32 for char in authority.get("reference", ""))
            or not isinstance(authority.get("commit"), bool)
            or not isinstance(authority.get("push"), bool)
            or (wants_commit and (
                not isinstance(message, str) or not message.strip()
                or "\n" in message or "\r" in message
                or len(message.encode("utf-8")) > 512
                or any(ord(char) < 32 for char in message)
            ))
            or (not wants_commit and message is not None)
            or not isinstance(spec.get("files"), list)
            or not all(isinstance(item, str) for item in spec["files"])
            or len(spec["files"]) > 2048
            or spec["files"] != sorted(set(spec["files"]))
            or (wants_commit and not spec["files"])
            or (not wants_commit and spec["files"])
            or spec.get("files") != [item.get("path") for item in files]
            or not isinstance(snapshot.get("staged_paths"), list)
            or not isinstance(snapshot.get("dirty_paths"), list)
            or not all(isinstance(item, str) for item in snapshot["staged_paths"])
            or not all(isinstance(item, str) for item in snapshot["dirty_paths"])
            or snapshot["staged_paths"] != []
            or snapshot["dirty_paths"] != spec["files"]
            or not isinstance(snapshot.get("head"), str)
            or not _HEX_SHA.match(snapshot["head"])
            or not isinstance(snapshot.get("index_digest"), str)
            or not _HEX_256.match(snapshot["index_digest"])
            or not isinstance(snapshot.get("raw_fingerprint"), str)
            or not _HEX_256.match(snapshot["raw_fingerprint"])
            or any(not isinstance(item.get("path"), str)
                   or not isinstance(item.get("sha256"), str)
                   or not _HEX_256.match(item["sha256"])
                   or not isinstance(item.get("git_blob"), str)
                   or not _HEX_SHA.match(item["git_blob"])
                   or not isinstance(item.get("size"), int) or item["size"] < 0
                   or not isinstance(item.get("mode"), int)
                   for item in files)
            or not isinstance(spec.get("push_commits"), list)
            or not all(isinstance(item, str) and _HEX_SHA.match(item)
                       for item in spec["push_commits"])
            or (spec.get("action") == "push" and not spec["push_commits"])
            or ((spec.get("action") in {"push", "commit-push"})
                and (not isinstance(remote_head, str) or not _HEX_SHA.match(remote_head)))
            or (spec.get("action") == "commit" and remote_head is not None)
            or any(key in outcome and outcome[key] is not None
                   and not isinstance(outcome[key], str)
                   for key in ("commit_sha", "remote_sha", "error"))
            or any(key in outcome and outcome[key] is not None
                   and not isinstance(outcome[key], bool)
                   for key in ("parity", "integrated_before_retry",
                               "integrated_before_push", "reconciled_after_timeout"))
            or any(key in outcome and outcome[key] is not None
                   and not _HEX_SHA.match(outcome[key])
                   for key in ("commit_sha", "remote_sha"))):
        raise PublicationError("invalid_plan", "Publication plan values are invalid.")
    _clean_metadata(spec.get("job_metadata"))
    return value


class GitPublisher:
    """Prepare and execute publication plans against one explicit repository."""

    def __init__(self, repo: str | os.PathLike[str], *, timeout: float = 30,
                 _runner: Any = None):
        self.repo = Path(repo).expanduser().resolve()
        _validate_timeout(timeout)
        self.timeout = timeout
        self._runner = _runner or _SubprocessRunner()

    def _run(self, argv: Sequence[str], *, code: str, env: Mapping[str, str] | None = None,
             allow_failure: bool = False) -> _CommandResult:
        try:
            result = self._runner(argv, cwd=self.repo, timeout=self.timeout, env=env)
        except subprocess.TimeoutExpired as exc:
            raise PublicationError(code + "_timeout", "A bounded command timed out.") from exc
        except OSError as exc:
            raise PublicationError(code, "A required executable could not be started.") from exc
        if not allow_failure and result.returncode != 0:
            raise PublicationError(code, "A required command failed safely.")
        return result

    def _git(self, *args: str, code: str = "git_failed", allow_failure: bool = False,
             env: Mapping[str, str] | None = None) -> _CommandResult:
        return self._run(("git", *args), code=code, allow_failure=allow_failure, env=env)

    def _git_text(self, *args: str, code: str = "git_failed") -> str:
        return self._git(*args, code=code).stdout.strip()

    def _assert_repo_shape(self) -> None:
        if not self.repo.is_dir():
            raise PublicationError("missing_repo", "Repository directory does not exist.")
        root = Path(self._git_text("rev-parse", "--show-toplevel", code="not_git_repo")).resolve()
        if root != self.repo:
            raise PublicationError("repo_root_mismatch", "Repository must be its Git worktree root.")
        missing = [item for item in _REQUIRED_VAULT_PATHS if not (self.repo / item).exists()]
        if missing:
            raise PublicationError("not_installed_vault", "Required installed-vault files are missing.")
        for item in _REQUIRED_VAULT_PATHS:
            cursor = self.repo
            for part in PurePosixPath(item).parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    raise PublicationError(
                        "unsafe_vault_shape", "Installed-vault controls must not be symlinks."
                    )

    def _assert_identity(self, branch: str, remote: str, expected_url: str) -> None:
        current = self._git_text("symbolic-ref", "--quiet", "--short", "HEAD",
                                 code="detached_head")
        if current != branch:
            raise PublicationError("branch_mismatch", "Current branch differs from the reviewed branch.")
        fetch_url = self._git_text("remote", "get-url", remote, code="missing_remote")
        push_url = self._git_text("remote", "get-url", "--push", remote, code="missing_remote")
        if fetch_url != expected_url or push_url != expected_url:
            raise PublicationError("remote_mismatch", "Remote URL differs from the expected target.")

    def _validate_target_values(self, branch: str, remote: str, expected_url: str) -> None:
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", remote)
                or any(ord(char) < 32 for char in expected_url)):
            raise PublicationError("invalid_target", "Remote name or URL contains unsafe data.")
        parsed = urlsplit(expected_url)
        if parsed.password is not None or parsed.query or parsed.fragment:
            raise PublicationError(
                "credentialed_remote", "Remote URL must not embed credentials or query data."
            )
        checked = self._git(
            "check-ref-format", "--branch", branch,
            code="invalid_branch", allow_failure=True,
        )
        if checked.returncode != 0:
            raise PublicationError("invalid_branch", "Expected branch is not a valid Git branch name.")

    def _git_dir(self) -> Path:
        value = self._git_text("rev-parse", "--git-common-dir", code="not_git_repo")
        directory = Path(value)
        return directory.resolve() if directory.is_absolute() else (self.repo / directory).resolve()

    @contextmanager
    def lock(self):
        lock_path = self._git_dir() / "thinker-publication.lock"
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise PublicationError("repo_locked", "Another publication is active for this repository.") from exc
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _validate_path(self, value: str) -> str:
        if (not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024
                or "\x00" in value or "\\" in value):
            raise PublicationError("unsafe_path", "Reviewed paths must be non-empty POSIX paths.")
        pure = PurePosixPath(value)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise PublicationError("unsafe_path", "Reviewed paths must stay inside the repository.")
        parts = pure.parts
        lower = [part.lower() for part in parts]
        if parts[0] in _FORBIDDEN_ROOTS or value == "vault.config.json":
            raise PublicationError("forbidden_path", "Reviewed path belongs to protected vault infrastructure.")
        if any(part in {"config", "configs", "secret", "secrets", "credentials", "logs"}
               for part in lower):
            raise PublicationError("forbidden_path", "Reviewed path resembles config, secret, or log material.")
        name = lower[-1]
        if name in _SECRET_NAMES or any(name.endswith(suffix) for suffix in _SECRET_SUFFIXES):
            raise PublicationError("forbidden_path", "Reviewed path resembles secret or transient log material.")
        cursor = self.repo
        for part in parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise PublicationError("symlink_path", "Reviewed paths and their parents must not be symlinks.")
        if not cursor.is_file():
            raise PublicationError("not_regular_file", "Reviewed paths must exist as regular files.")
        try:
            cursor.resolve().relative_to(self.repo)
        except ValueError as exc:
            raise PublicationError("unsafe_path", "Reviewed path resolves outside the repository.") from exc
        return pure.as_posix()

    def _zpaths(self, *args: str, code: str = "git_status_failed") -> list[str]:
        output = self._git(*args, code=code).stdout
        return sorted(item for item in output.split("\0") if item)

    def _dirty_paths(self) -> tuple[list[str], list[str]]:
        staged = set(self._zpaths("diff", "--cached", "--name-only", "-z"))
        index_check = self._git(
            "diff-index", "--cached", "--quiet", "HEAD", "--",
            code="index_status_failed", allow_failure=True,
        )
        if index_check.returncode not in {0, 1}:
            raise PublicationError("index_status_failed", "Git index state could not be verified.")
        if index_check.returncode == 1 and not staged:
            raise PublicationError(
                "preexisting_stage", "The Git index contains intent-to-add or hidden staged state."
            )
        unmerged = self._zpaths("ls-files", "--unmerged", "-z")
        if unmerged:
            raise PublicationError("unmerged_index", "The Git index contains unmerged entries.")
        unstaged = set(self._zpaths("diff", "--name-only", "-z"))
        untracked = set(self._zpaths("ls-files", "--others", "--exclude-standard", "-z"))
        return sorted(staged), sorted(unstaged | untracked)

    def _index_digest(self) -> str:
        data = self._git("ls-files", "--stage", "-z", code="index_snapshot_failed").stdout
        return hashlib.sha256(data.encode("utf-8", "surrogateescape")).hexdigest()

    def _file_record(self, relative: str) -> dict[str, Any]:
        path = self.repo / relative
        stat = path.stat()
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(block)
        return {
            "path": relative,
            "sha256": hasher.hexdigest(),
            "git_blob": self._git_text("hash-object", "--", relative,
                                        code="file_snapshot_failed"),
            "size": stat.st_size,
            "mode": stat.st_mode & 0o777,
        }

    def _raw_fingerprint(self) -> str:
        """Cheaply detect raw-tree drift without reading immutable source bodies."""
        entries: list[tuple[Any, ...]] = []
        raw = self.repo / "raw"
        for directory, names, files in os.walk(raw, followlinks=False):
            names.sort()
            files.sort()
            base = Path(directory)
            for name in names + files:
                path = base / name
                stat = path.lstat()
                link = os.readlink(path) if path.is_symlink() else None
                entries.append((
                    path.relative_to(raw).as_posix(), stat.st_mode, stat.st_size,
                    stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, link,
                ))
        return _digest(entries)

    def _snapshot(self, reviewed_paths: Sequence[str]) -> dict[str, Any]:
        staged, dirty = self._dirty_paths()
        return {
            "head": self._git_text("rev-parse", "HEAD", code="missing_head"),
            "index_digest": self._index_digest(),
            "staged_paths": staged,
            "dirty_paths": dirty,
            "files": [self._file_record(path) for path in reviewed_paths],
            "raw_fingerprint": self._raw_fingerprint(),
        }

    def _validate_vault(self) -> None:
        checks = (
            ("python3", ".claude/scripts/build-index.py", "check"),
            ("bash", "harness/scripts/verify.sh"),
            ("git", "diff", "--check"),
        )
        for argv in checks:
            self._run(argv, code="vault_validation_failed")
        raw_tracked = self._zpaths("diff", "--name-only", "-z", "--", "raw")
        raw_untracked = self._zpaths(
            "ls-files", "--others", "--exclude-standard", "-z", "--", "raw"
        )
        if raw_tracked or raw_untracked:
            raise PublicationError("raw_changed", "The immutable raw tree contains pending changes.")

    def _fetch(self, remote: str, branch: str) -> str:
        destination = f"refs/remotes/{remote}/{branch}"
        self._git(
            "fetch", "--no-tags", remote, f"refs/heads/{branch}:{destination}",
            code="fetch_failed",
        )
        return self._git_text("rev-parse", destination, code="missing_remote_branch")

    def _push_commits(self, remote_head: str) -> list[str]:
        ancestor = self._git(
            "merge-base", "--is-ancestor", remote_head, "HEAD",
            code="remote_diverged", allow_failure=True,
        )
        if ancestor.returncode != 0:
            raise PublicationError("remote_diverged", "Remote history is ahead or divergent.")
        return self._git_text(
            "rev-list", "--reverse", f"{remote_head}..HEAD", code="commit_range_failed"
        ).splitlines()

    def prepare(
        self,
        *,
        plan_path: str | os.PathLike[str],
        expected_branch: str,
        remote_name: str,
        expected_remote_url: str,
        action: str,
        authority: Mapping[str, Any],
        files: Sequence[str] = (),
        message: str | None = None,
        authorized_existing_commits: Sequence[str] | None = None,
        job_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if action not in _ACTIONS:
            raise PublicationError("invalid_action", "Action must be commit, push, or commit-push.")
        wants_commit = action in {"commit", "commit-push"}
        wants_push = action in {"push", "commit-push"}
        reference = authority.get("reference") if isinstance(authority, Mapping) else None
        if not isinstance(reference, str) or not reference.strip():
            raise PublicationError("missing_authority", "A non-empty authority reference is required.")
        if (len(reference.encode("utf-8")) > 256
                or any(ord(char) < 32 for char in reference)):
            raise PublicationError("invalid_authority", "Authority reference must be a short audit label.")
        if wants_commit and authority.get("commit") is not True:
            raise PublicationError("commit_not_authorized", "Commit authority is required independently.")
        if wants_push and authority.get("push") is not True:
            raise PublicationError("push_not_authorized", "Push authority is required independently.")
        if not expected_branch or not remote_name or not expected_remote_url:
            raise PublicationError("missing_target", "Branch, remote name, and remote URL are required.")
        if wants_commit:
            if not isinstance(message, str) or not message.strip() or "\n" in message or "\r" in message:
                raise PublicationError("invalid_message", "Commit message must be one non-empty line.")
            if len(message.encode("utf-8")) > 512 or any(ord(char) < 32 for char in message):
                raise PublicationError("invalid_message", "Commit message contains unsafe control data.")
        elif message is not None:
            raise PublicationError("unexpected_message", "Push-only plans do not accept a commit message.")

        metadata = _clean_metadata(job_metadata)
        if isinstance(files, (str, bytes)) or len(files) > 2048:
            raise PublicationError("invalid_scope", "Reviewed files must be a bounded path list.")
        normalized = sorted({self._validate_path(item) for item in files})
        if len(normalized) != len(files):
            raise PublicationError("duplicate_path", "Reviewed file paths must be unique.")
        if wants_commit and not normalized:
            raise PublicationError("empty_commit", "Commit actions require reviewed changed files.")
        if not wants_commit and normalized:
            raise PublicationError("unexpected_files", "Push-only plans require a clean worktree.")

        plan_file = Path(plan_path).expanduser().resolve()
        try:
            plan_file.relative_to(self.repo)
        except ValueError:
            pass
        else:
            raise PublicationError("unsafe_plan_path", "Publication plans must live outside the repository.")

        with self.lock():
            self._assert_repo_shape()
            self._validate_target_values(expected_branch, remote_name, expected_remote_url)
            self._assert_identity(expected_branch, remote_name, expected_remote_url)
            staged, dirty = self._dirty_paths()
            if staged:
                raise PublicationError("preexisting_stage", "The Git index already contains staged changes.")
            if dirty != normalized:
                raise PublicationError("scope_mismatch", "Pending paths differ from the explicitly reviewed files.")
            remote_head = None
            push_commits: list[str] = []
            if wants_push:
                remote_head = self._fetch(remote_name, expected_branch)
                push_commits = self._push_commits(remote_head)
                if authorized_existing_commits is not None and list(authorized_existing_commits) != push_commits:
                    raise PublicationError("unauthorized_commit_range", "Local commits differ from the authorized range.")
                if action == "push" and not push_commits:
                    raise PublicationError("nothing_to_push", "No local commits are pending publication.")
            self._validate_vault()
            snapshot = self._snapshot(normalized)
            if snapshot["staged_paths"] or snapshot["dirty_paths"] != normalized:
                raise PublicationError("snapshot_drift", "Repository changed while preparing the plan.")

        spec = {
            "repo": str(self.repo),
            "target": {
                "branch": expected_branch,
                "remote_name": remote_name,
                "remote_url": expected_remote_url,
            },
            "action": action,
            "authority": {
                "reference": reference.strip(),
                "commit": authority.get("commit") is True,
                "push": authority.get("push") is True,
            },
            "message": message,
            "files": normalized,
            "snapshot": snapshot,
            "remote_head": remote_head,
            "push_commits": push_commits,
            "job_metadata": metadata,
        }
        plan: dict[str, Any] = {
            "schema": PLAN_SCHEMA,
            "spec": spec,
            "plan_digest": _digest(spec),
            "outcome": {"status": "prepared"},
        }
        _write_plan(plan_file, plan)
        return plan

    def _persist_outcome(self, path: Path, plan: dict[str, Any], **outcome: Any) -> dict[str, Any]:
        plan["outcome"] = outcome
        _write_plan(path, plan)
        return plan

    def _assert_snapshot(self, expected: Mapping[str, Any]) -> None:
        current = self._snapshot(expected.get("dirty_paths", []))
        if current != expected:
            raise PublicationError("plan_stale", "HEAD, index, paths, or reviewed file contents changed after review.")

    def _remote_tip(self, remote: str, branch: str) -> str | None:
        result = self._git(
            "ls-remote", "--heads", remote, f"refs/heads/{branch}",
            code="remote_probe_failed", allow_failure=True,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1] == f"refs/heads/{branch}" and _HEX_SHA.match(fields[0]):
                return fields[0]
        return None

    def execute(
        self,
        plan_path: str | os.PathLike[str],
        *,
        execution_guard: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if execution_guard is not None and not callable(execution_guard):
            raise PublicationError("invalid_execution_guard", "Execution guard must be callable.")
        path = Path(plan_path).expanduser().resolve()
        plan = _load_plan(path)
        spec = plan["spec"]
        repo_value = spec.get("repo")
        if not isinstance(repo_value, str) or Path(repo_value).resolve() != self.repo:
            raise PublicationError("repo_mismatch", "Plan belongs to a different repository.")
        action = spec.get("action")
        if action not in _ACTIONS:
            raise PublicationError("invalid_plan", "Plan action is invalid.")
        wants_commit = action in {"commit", "commit-push"}
        wants_push = action in {"push", "commit-push"}
        authority = spec.get("authority")
        if not isinstance(authority, dict):
            raise PublicationError("invalid_plan", "Plan authority is invalid.")
        if wants_commit and authority.get("commit") is not True:
            raise PublicationError("commit_not_authorized", "Plan lacks independent commit authority.")
        if wants_push and authority.get("push") is not True:
            raise PublicationError("push_not_authorized", "Plan lacks independent push authority.")
        target = spec.get("target")
        if (not isinstance(target, dict)
                or not all(isinstance(target.get(key), str)
                           for key in ("branch", "remote_name", "remote_url"))):
            raise PublicationError("invalid_plan", "Plan target is invalid.")
        files = spec.get("files")
        snapshot = spec.get("snapshot")
        push_commits = spec.get("push_commits")
        if (not isinstance(files, list) or not all(isinstance(item, str) for item in files)
                or not isinstance(snapshot, dict)
                or not isinstance(snapshot.get("raw_fingerprint"), str)
                or not isinstance(push_commits, list)
                or not all(isinstance(item, str) and _HEX_SHA.match(item)
                           for item in push_commits)):
            raise PublicationError("invalid_plan", "Plan scope or snapshots are invalid.")
        normalized = sorted({self._validate_path(item) for item in files})
        if normalized != files:
            raise PublicationError("invalid_plan", "Plan paths are not normalized and unique.")
        if wants_commit and not isinstance(spec.get("message"), str):
            raise PublicationError("invalid_plan", "Commit plan has no message.")
        remote_head = spec.get("remote_head")
        if wants_push and (not isinstance(remote_head, str) or not _HEX_SHA.match(remote_head)):
            raise PublicationError("invalid_plan", "Push plan has no valid remote snapshot.")

        with self.lock():
            self._assert_repo_shape()
            self._validate_target_values(
                target["branch"], target["remote_name"], target["remote_url"]
            )
            self._assert_identity(target["branch"], target["remote_name"], target["remote_url"])
            outcome = plan.get("outcome") or {}
            status = outcome.get("status")
            commit_sha = outcome.get("commit_sha")

            if status == "complete":
                if commit_sha and self._git_text("rev-parse", "HEAD") != commit_sha:
                    raise PublicationError("completed_plan_drift", "Completed plan no longer matches local HEAD.")
                if wants_push:
                    remote_tip = self._remote_tip(target["remote_name"], target["branch"])
                    if remote_tip != self._git_text("rev-parse", "HEAD"):
                        raise PublicationError("completed_plan_drift", "Completed plan no longer has remote parity.")
                return plan

            committed = (wants_commit
                         and status in {"commit_created", "push_failed", "push_unknown"}
                         and bool(commit_sha))
            if committed:
                head = self._git_text("rev-parse", "HEAD", code="missing_head")
                if head != commit_sha:
                    raise PublicationError("post_commit_drift", "Local HEAD moved after the plan created its commit.")
                staged, dirty = self._dirty_paths()
                if staged or dirty:
                    raise PublicationError("post_commit_drift", "Worktree changed after the plan created its commit.")
            else:
                self._assert_snapshot(spec["snapshot"])
            if self._raw_fingerprint() != spec["snapshot"]["raw_fingerprint"]:
                raise PublicationError("raw_changed", "The immutable raw tree changed after plan review.")

            current_remote = None
            if wants_push:
                current_remote = self._fetch(target["remote_name"], target["branch"])
                current_head = self._git_text("rev-parse", "HEAD", code="missing_head")
                if ((committed and current_remote == commit_sha)
                        or (action == "push" and current_remote == current_head)):
                    return self._persist_outcome(
                        path, plan, status="complete", commit_sha=commit_sha or current_head,
                        remote_sha=current_remote, parity=True,
                        integrated_before_retry=True,
                    )
                if current_remote != spec["remote_head"]:
                    raise PublicationError("remote_changed", "Remote branch changed after plan review.")
                current_existing = self._push_commits(current_remote)
                expected_existing = list(spec["push_commits"])
                if committed:
                    expected_existing.append(commit_sha)
                if current_existing != expected_existing:
                    raise PublicationError("unauthorized_commit_range", "Local commits differ from the reviewed range.")

            self._validate_vault()
            if self._raw_fingerprint() != spec["snapshot"]["raw_fingerprint"]:
                raise PublicationError("raw_changed", "The immutable raw tree changed during validation.")

            if wants_commit and not committed:
                self._assert_snapshot(spec["snapshot"])
                if execution_guard is not None:
                    execution_guard()
                self._git("add", "--", *spec["files"], code="stage_failed")
                staged = self._zpaths("diff", "--cached", "--name-only", "-z")
                if staged != sorted(spec["files"]):
                    raise PublicationError("stage_scope_mismatch", "Staged paths differ from the reviewed scope.")
                self._git("diff", "--cached", "--check", code="staged_validation_failed")
                if execution_guard is not None:
                    try:
                        execution_guard()
                    except Exception:
                        cleanup = self._git(
                            "restore", "--staged", "--", *spec["files"],
                            code="stage_cleanup_failed", allow_failure=True,
                        )
                        if cleanup.returncode != 0:
                            self._persist_outcome(
                                path, plan, status="stage_cleanup_failed",
                                error="stage_cleanup_failed",
                            )
                        raise
                commit_result = self._git(
                    "commit", "--no-gpg-sign", "--only", "-m", spec["message"],
                    "--", *spec["files"],
                    code="commit_failed", allow_failure=True,
                )
                if commit_result.returncode != 0:
                    self._persist_outcome(path, plan, status="commit_failed", error="commit_failed")
                    raise PublicationError("commit_failed", "Git commit failed; no push was attempted.")
                commit_sha = self._git_text("rev-parse", "HEAD", code="missing_commit")
                parent = self._git_text("rev-parse", f"{commit_sha}^", code="unexpected_commit")
                if parent != spec["snapshot"]["head"]:
                    self._persist_outcome(path, plan, status="commit_unknown", commit_sha=commit_sha)
                    raise PublicationError("unexpected_commit", "Created commit does not have the reviewed parent.")
                changed = self._zpaths(
                    "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", commit_sha,
                    code="commit_scope_failed",
                )
                if changed != sorted(spec["files"]):
                    self._persist_outcome(path, plan, status="commit_unknown", commit_sha=commit_sha)
                    raise PublicationError("commit_scope_failed", "Created commit differs from the reviewed paths.")
                expected_blobs = {
                    item["path"]: item["git_blob"] for item in spec["snapshot"]["files"]
                }
                for relative, expected_blob in expected_blobs.items():
                    actual_blob = self._git_text(
                        "rev-parse", f"{commit_sha}:{relative}",
                        code="commit_content_failed",
                    )
                    if actual_blob != expected_blob:
                        self._persist_outcome(
                            path, plan, status="commit_unknown", commit_sha=commit_sha
                        )
                        raise PublicationError(
                            "commit_content_failed", "Created commit content differs from review."
                        )
                self._persist_outcome(path, plan, status="commit_created", commit_sha=commit_sha)
                committed = True
                if not wants_push:
                    return self._persist_outcome(
                        path, plan, status="complete", commit_sha=commit_sha,
                        remote_sha=None, parity=None,
                    )

            if wants_push:
                head = self._git_text("rev-parse", "HEAD", code="missing_head")
                expected_commits = list(spec["push_commits"])
                if wants_commit:
                    expected_commits.append(commit_sha)
                actual_commits = self._push_commits(spec["remote_head"])
                if actual_commits != expected_commits:
                    raise PublicationError("unauthorized_commit_range", "Push range differs from the reviewed commits.")
                if execution_guard is not None:
                    execution_guard()
                dry_run = self._git(
                    "push", "--dry-run", target["remote_name"],
                    f"HEAD:refs/heads/{target['branch']}",
                    code="push_dry_run_failed", allow_failure=True,
                )
                if dry_run.returncode != 0:
                    self._persist_outcome(path, plan, status="push_failed", commit_sha=head,
                                          error="push_dry_run_failed")
                    raise PublicationError("push_dry_run_failed", "Push dry-run failed; no push was attempted.")
                tip_before = self._remote_tip(target["remote_name"], target["branch"])
                if tip_before == head:
                    return self._persist_outcome(
                        path, plan, status="complete", commit_sha=head,
                        remote_sha=head, parity=True, integrated_before_push=True,
                    )
                if tip_before != spec["remote_head"]:
                    raise PublicationError("remote_changed", "Remote changed immediately before push.")
                if execution_guard is not None:
                    execution_guard()
                try:
                    push = self._git(
                        "push", target["remote_name"], f"HEAD:refs/heads/{target['branch']}",
                        code="push_failed", allow_failure=True,
                    )
                except PublicationError as exc:
                    if exc.code != "push_failed_timeout":
                        raise
                    tip_after = self._remote_tip(target["remote_name"], target["branch"])
                    if tip_after == head:
                        return self._persist_outcome(
                            path, plan, status="complete", commit_sha=head,
                            remote_sha=head, parity=True, reconciled_after_timeout=True,
                        )
                    state = "push_failed" if tip_after == spec["remote_head"] else "push_unknown"
                    self._persist_outcome(path, plan, status=state, commit_sha=head,
                                          remote_sha=tip_after, parity=False, error=exc.code)
                    raise PublicationError(state, "Push timed out and was reconciled without retrying.")
                if push.returncode != 0:
                    tip_after = self._remote_tip(target["remote_name"], target["branch"])
                    state = "push_failed" if tip_after == spec["remote_head"] else "push_unknown"
                    self._persist_outcome(path, plan, status=state, commit_sha=head,
                                          remote_sha=tip_after, parity=False, error="push_failed")
                    raise PublicationError(state, "Push failed and was not retried.")
                tip_after = self._remote_tip(target["remote_name"], target["branch"])
                if tip_after != head:
                    self._persist_outcome(path, plan, status="push_unknown", commit_sha=head,
                                          remote_sha=tip_after, parity=False)
                    raise PublicationError("push_unknown", "Push returned but remote parity could not be proved.")
                return self._persist_outcome(
                    path, plan, status="complete", commit_sha=head,
                    remote_sha=tip_after, parity=True,
                )

            raise PublicationError("invalid_plan_state", "Plan has no executable operation.")

def prepare_plan(*, repo: str | os.PathLike[str], plan_path: str | os.PathLike[str],
                 timeout: float = 30, _runner: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Prepare and persist a reviewable publication plan."""
    _assert_parent_executor()
    _validate_timeout(timeout)
    return GitPublisher(repo, timeout=timeout, _runner=_runner).prepare(
        plan_path=plan_path, **kwargs
    )


def execute_plan(plan_path: str | os.PathLike[str], *, timeout: float = 30,
                 execution_guard: Callable[[], None] | None = None,
                 _runner: Any = None) -> dict[str, Any]:
    """Execute one previously persisted plan after the parent review gate."""
    _assert_parent_executor()
    _validate_timeout(timeout)
    plan = _load_plan(Path(plan_path).expanduser().resolve())
    repo = plan.get("spec", {}).get("repo")
    if not isinstance(repo, str) or not repo:
        raise PublicationError("invalid_plan", "Plan has no repository target.")
    return GitPublisher(repo, timeout=timeout, _runner=_runner).execute(
        plan_path, execution_guard=execution_guard
    )
