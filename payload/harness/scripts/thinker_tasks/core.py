"""Private task records and deterministic, evidence-aware continuity packets.

Only the explicitly selected state directory is writable. References are opened
relative to the workspace with O_NOFOLLOW at each hop. Nothing executes a job,
imports a provider, scans conversations, or writes to the workspace.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import time
import uuid

SCHEMA = 1
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_INPUT_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
DEFAULT_BUDGET = 32768
LOCK_TIMEOUT_SECONDS = 2.0
# The RC has no host/supervisor observation adapter. Manual input cannot claim
# an observed origin. File checks generate local_verification internally.
ORIGINS = {"principal_reported", "unknown"}
ROLES = {"canonical", "dialogue", "artifact", "test", "instructions"}
REPLACEMENT_FIELDS = ("replaces", "replacement_reason", "replaced_source", "replacement_at",
                      "replacement_sha256", "replacement_origin")
TASK_STATES = {"open", "paused", "closed"}
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


class TaskError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.message, self.details = code, message, details
        self.exit_code = {"revision_conflict": 3, "request_conflict": 3,
                          "not_found": 4, "attention_not_found": 4,
                          "budget_exceeded": 5, "state_limit_exceeded": 5}.get(code, 2)

    def as_dict(self):
        error = {"code": self.code, "message": self.message}
        if self.details is not None:
            error["details"] = self.details
        return {"error": error}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _text(value, field, limit=32768):
    if (not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > limit
            or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise TaskError("invalid_input", field + " must be nonempty bounded text.")
    return value


def _identifier(value, field="identifier"):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise TaskError("invalid_input", field + " contains unsupported characters or is too long.")
    return value


def _uuid(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise TaskError("invalid_input", "Task ID must be a canonical UUID.") from None
    return value


def _integer(value, field, minimum=1):
    if type(value) is not int or value < minimum:
        raise TaskError("invalid_input", field + " must be an integer >= " + str(minimum) + ".")
    return value


def _schema(value):
    if not isinstance(value, dict):
        raise TaskError("state_unavailable", "Expected a JSON object.")
    if type(value.get("schema")) is not int or value["schema"] != SCHEMA:
        raise TaskError("incompatible_schema", "Only task schema 1 is supported.")


def _absolute(value):
    path = Path(value).expanduser()
    if ".." in path.parts:
        raise TaskError("unsafe_path", "Parent traversal is forbidden.")
    path = path.absolute()
    # macOS owns these two aliases. User-created aliases remain forbidden.
    if len(path.parts) > 1 and path.parts[1] in {"tmp", "var"}:
        alias = Path("/") / path.parts[1]
        if alias.is_symlink() and alias.resolve() == Path("/private") / path.parts[1]:
            path = Path("/private").joinpath(*path.parts[1:])
    for part in (path, *path.parents):
        if part.is_symlink():
            raise TaskError("unsafe_path", "Symlinks are forbidden in selected paths.")
    return path


def _relative(value):
    if (not isinstance(value, str) or not value or "\\" in value or "\x00" in value
            or len(value.encode("utf-8")) > 1024):
        raise TaskError("unsafe_path", "Evidence requires a bounded relative path.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"..", "."} for p in value.split("/")):
        raise TaskError("unsafe_path", "Evidence must stay inside the selected workspace.")
    if not path.parts or any(not p for p in value.split("/")):
        raise TaskError("unsafe_path", "Evidence requires a regular relative path.")
    return path.as_posix()


def _overlap(left, right):
    """Check lexical and physical ancestry on case-insensitive filesystems.

    resolve() does not canonicalize pathname case on macOS. Compare each
    existing ancestor to the other root, rather than comparing common ancestors
    (which would incorrectly make every two absolute paths overlap at /).
    """
    if left == right or left in right.parents or right in left.parents:
        return True
    for root, candidate in ((left, right), (right, left)):
        if not root.exists():
            continue
        for ancestor in (candidate, *candidate.parents):
            if ancestor.exists() and os.path.samefile(root, ancestor):
                return True
    return False


def _private(fd):
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise TaskError("unsafe_path", "State must be owned by the current user and private.")


def _directory(path, create=False, private=False):
    """Open every component without following a user-controlled symlink."""
    path = _absolute(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:]:
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        if private:
            _private(fd)
        return fd
    except OSError as exc:
        os.close(fd)
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise TaskError("unsafe_path", "A selected directory is unsafe.") from None
        raise
    except BaseException:
        os.close(fd)
        raise


def _child_dir(parent, name, create=False):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError:
        if not create:
            raise
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR}:
            raise TaskError("unsafe_path", "State directory must not be a symlink.") from None
        raise
    try:
        _private(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_at(directory, name, missing=False):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        if missing:
            return None
        raise TaskError("not_found", "The requested state record does not exist.") from None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise TaskError("unsafe_path", "State records must not be symlinks.") from None
        raise
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise TaskError("unsafe_path", "State records must be regular files.")
        _private(stream.fileno())
        if info.st_size > MAX_DOCUMENT_BYTES:
            raise TaskError("state_limit_exceeded", "State document exceeds the supported byte limit.")
        data = stream.read(MAX_DOCUMENT_BYTES + 1)
    try:
        value = json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise TaskError("state_unavailable", "State is malformed; no change was made.") from None
    if not isinstance(value, dict):
        raise TaskError("state_unavailable", "State is not a JSON object.")
    return value


def _atomic_at(directory, name, value):
    data = _bytes(value) + b"\n"
    if len(data) > MAX_DOCUMENT_BYTES:
        raise TaskError("state_limit_exceeded", "State document is full; export/archive explicitly.",
                        {"required_bytes": len(data), "limit_bytes": MAX_DOCUMENT_BYTES})
    temporary = ".write-" + str(uuid.uuid4())
    fd = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise TaskError("unsafe_path", "Refusing to replace a non-regular state record.")
        except FileNotFoundError:
            pass
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def read_checkpoint_file(path):
    if path == "-":
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    else:
        path = _absolute(path)
        directory = _directory(path.parent)
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise TaskError("unsafe_path", "Checkpoint input must be a regular file.")
                data = stream.read(MAX_INPUT_BYTES + 1)
        finally:
            os.close(directory)
    if len(data) > MAX_INPUT_BYTES:
        raise TaskError("invalid_input", "Checkpoint input is too large.")
    try:
        return json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise TaskError("invalid_input", "Checkpoint input is not valid JSON.") from None


def normalize_checkpoint(value):
    _schema(value)
    allowed = {"schema", "state", "origin", "author", "decisions", "corrections", "pending", "constraints", "evidence"}
    if set(value) - allowed:
        raise TaskError("invalid_input", "Unknown checkpoint fields.", {"fields": sorted(set(value) - allowed)})
    origin = value.get("origin", "principal_reported")
    if origin not in ORIGINS:
        raise TaskError("invalid_input", "Unknown checkpoint origin.")
    result = {"schema": 1, "state": _text(value.get("state"), "state"), "origin": origin,
              "author": _text(value.get("author", "principal"), "author", 256)}
    ids = set()
    for group in ("decisions", "corrections", "pending", "constraints"):
        items = value.get(group, [])
        if not isinstance(items, list) or len(items) > 128:
            raise TaskError("invalid_input", group + " must contain at most 128 items.")
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                raise TaskError("invalid_input", "Checkpoint items must be objects.")
            fields = {"id", "text", "origin", "critical"}
            if group in {"decisions", "pending"}:
                fields.add("status")
            if group == "corrections":
                fields.add("supersedes")
            if set(item) - fields:
                raise TaskError("invalid_input", "Unknown " + group + " item fields.")
            identifier = _identifier(item.get("id"), "item id")
            if identifier in ids:
                raise TaskError("invalid_input", "Checkpoint item IDs must be unique.")
            ids.add(identifier)
            item_origin = item.get("origin", origin)
            if item_origin not in ORIGINS:
                raise TaskError("invalid_input", "Unknown item origin.")
            critical = item.get("critical", group in {"corrections", "constraints"})
            if type(critical) is not bool or (group == "corrections" and not critical):
                raise TaskError("invalid_input", "Critical must be boolean; corrections are always critical.")
            record = {"id": identifier, "text": _text(item.get("text"), "item text"),
                      "origin": item_origin, "critical": critical}
            if group == "corrections":
                record["supersedes"] = _identifier(item.get("supersedes"), "supersedes")
            if group in {"decisions", "pending"}:
                states = {"proposed", "accepted", "rejected"} if group == "decisions" else {"open", "blocked", "resolved"}
                status = item.get("status", "proposed" if group == "decisions" else "open")
                if status not in states:
                    raise TaskError("invalid_input", "Unknown item status.")
                record["status"] = status
            normalized.append(record)
        result[group] = normalized
    evidence = value.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) > 64:
        raise TaskError("invalid_input", "Evidence must contain at most 64 references.")
    result["evidence"] = []
    paths = set()
    for item in evidence:
        if not isinstance(item, dict) or set(item) - {"path", "role", "critical", "replaces", "replacement_reason"}:
            raise TaskError("invalid_input", "Evidence accepts path, role, critical, replaces and replacement_reason only.")
        path, role = _relative(item.get("path")), item.get("role", "artifact")
        if role not in ROLES or path in paths or type(item.get("critical", False)) is not bool:
            raise TaskError("invalid_input", "Invalid or duplicate evidence reference.")
        paths.add(path)
        source = {"path": path, "role": role, "critical": item.get("critical", False)}
        if "replaces" in item or "replacement_reason" in item:
            if not {"replaces", "replacement_reason"} <= set(item):
                raise TaskError("invalid_replacement", "Evidence replacement requires both replaces and replacement_reason.")
            source["replaces"] = _relative(item["replaces"])
            source["replacement_reason"] = _text(item["replacement_reason"], "replacement_reason", 4096)
            if source["replaces"] == path:
                raise TaskError("invalid_replacement", "Replacement must have a different path.")
        result["evidence"].append(source)
    return result


class TaskStore:
    def __init__(self, workspace, state_dir):
        self.workspace, self.state = _absolute(workspace), _absolute(state_dir)
        fd = _directory(self.workspace)
        os.close(fd)
        if _overlap(self.workspace, self.state):
            raise TaskError("unsafe_path", "Workspace and state directory must not overlap.")
        if self.state.exists():
            fd = _directory(self.state, private=True)
            os.close(fd)

    @contextlib.contextmanager
    def _lock(self, create=False):
        try:
            root = _directory(self.state, create=create, private=True)
        except FileNotFoundError:
            yield None
            return
        lock = None
        try:
            lock = os.open(".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                           0o600, dir_fd=root)
            if not stat.S_ISREG(os.fstat(lock).st_mode):
                raise TaskError("unsafe_path", "State lock must be a regular file.")
            _private(lock)
            deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TaskError("state_busy", "Task state is busy; no change was made.") from None
                    time.sleep(0.02)
            yield root
        finally:
            if lock is not None:
                os.close(lock)
            os.close(root)

    def _registry(self, root, create=False):
        if root is None:
            return None
        value = _read_at(root, "workspace.json", missing=True)
        if value is None:
            if any(name != ".lock" for name in os.listdir(root)):
                raise TaskError("state_unavailable", "Workspace registry is missing from nonempty state.")
            if not create:
                # Orphaned task documents are corruption, not an empty state.
                if "tasks" in os.listdir(root):
                    raise TaskError("state_unavailable", "Workspace registry is missing.")
                return None
            value = {"schema": 1, "workspace_id": str(uuid.uuid4()),
                     "root": str(self.workspace), "created_at": now()}
            _atomic_at(root, "workspace.json", value)
        _schema(value)
        try:
            _uuid(value.get("workspace_id"))
        except TaskError:
            raise TaskError("state_unavailable", "Workspace registry is malformed.") from None
        if value.get("root") != str(self.workspace):
            raise TaskError("workspace_mismatch", "State belongs to a different workspace.")
        return value

    def _load(self, root, task_id, registry):
        _uuid(task_id)
        if root is None or registry is None:
            raise TaskError("not_found", "Task does not exist.")
        try:
            directory = _child_dir(root, "tasks")
        except FileNotFoundError:
            raise TaskError("not_found", "Task does not exist.") from None
        try:
            value = _read_at(directory, task_id + ".json")
        finally:
            os.close(directory)
        _schema(value)
        try:
            if (value.get("id") != task_id or value.get("task_id") != task_id
                    or value.get("workspace_id") != registry["workspace_id"]
                    or value.get("state") not in TASK_STATES):
                raise ValueError()
            _integer(value.get("revision"), "revision")
            _integer(value.get("generation"), "generation")
            _text(value.get("title"), "title", 512)
            _text(value.get("objective"), "objective")
            for field, kind in (("links", list), ("history", list), ("receipts", dict), ("seen", dict)):
                if not isinstance(value.get(field), kind):
                    raise ValueError()
            checkpoint = value.get("checkpoint")
            if checkpoint is not None:
                if not isinstance(checkpoint, dict) or checkpoint.get("generation") != value["generation"]:
                    raise ValueError()
                _text(checkpoint.get("state"), "checkpoint state")
                for field in ("decisions", "corrections", "constraints", "pending", "evidence"):
                    if not isinstance(checkpoint.get(field), list):
                        raise ValueError()
                editable = {key: checkpoint[key] for key in
                            ("schema", "state", "origin", "author", "decisions", "corrections", "constraints", "pending")}
                editable["evidence"] = [{key: source[key] for key in
                                         ("path", "role", "critical", "replaces", "replacement_reason") if key in source}
                                        for source in checkpoint["evidence"]]
                if normalize_checkpoint(editable) != editable:
                    raise ValueError()
                _uuid(checkpoint.get("id"))
                _integer(checkpoint.get("base_revision"), "base_revision")
                if checkpoint["base_revision"] >= value["revision"]:
                    raise ValueError()
                known = {item["id"] for group in ("decisions", "constraints") for item in checkpoint[group]}
                superseded = set()
                for correction in checkpoint["corrections"]:
                    if correction["supersedes"] not in known or correction["supersedes"] in superseded:
                        raise ValueError()
                    known.add(correction["id"])
                    superseded.add(correction["supersedes"])
                for source in checkpoint["evidence"]:
                    _relative(source["path"])
                    if source.get("role") not in ROLES:
                        raise ValueError()
                    digest = source.get("sha256")
                    if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
                        raise ValueError()
                    if "replaces" in source:
                        retired = source.get("replaced_source")
                        if (not isinstance(retired, dict) or retired.get("path") != source["replaces"]
                                or retired.get("role") not in ROLES or type(retired.get("critical")) is not bool
                                or (retired["critical"] and not source["critical"])
                                or source.get("replacement_origin") not in ORIGINS):
                            raise ValueError()
                        retired_hash = retired.get("sha256")
                        if retired_hash is not None and (not isinstance(retired_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", retired_hash)):
                            raise ValueError()
                        verified_hash = source.get("replacement_sha256")
                        if not isinstance(verified_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", verified_hash):
                            raise ValueError()
                        _text(source.get("replacement_at"), "replacement_at", 128)
                        _text(retired.get("recorded_at"), "recorded_at", 128)
                    elif any(field in source for field in REPLACEMENT_FIELDS):
                        raise ValueError()
            for link in value["links"]:
                if (not isinstance(link, dict) or link.get("kind") not in {"session", "run", "job", "artifact"}
                        or link.get("generation") != value["generation"] or link.get("execution_state") != "unknown"
                        or link.get("origin") != "principal_reported" or link.get("capabilities") != []):
                    raise ValueError()
                _uuid(link.get("id"))
                _identifier(link.get("provider"), "provider")
                _text(link.get("external_id"), "external_id", 1024)
                _text(link.get("created_at"), "created_at", 128)
            for key, observed in value["seen"].items():
                if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
                    raise ValueError()
                _text(observed, "seen_at", 128)
            for receipt in value["receipts"].values():
                if not isinstance(receipt, dict) or not isinstance(receipt.get("result"), dict) or not isinstance(receipt.get("fingerprint"), str):
                    raise ValueError()
        except (TaskError, KeyError, TypeError, ValueError):
            raise TaskError("state_unavailable", "Task state is malformed; no change was made.") from None
        return value

    def _save(self, root, task):
        directory = _child_dir(root, "tasks", create=True)
        try:
            _atomic_at(directory, task["id"] + ".json", task)
        finally:
            os.close(directory)

    def _public(self, task):
        return copy.deepcopy({k: v for k, v in task.items() if k not in {"history", "receipts", "seen"}})

    def create(self, title, objective, request_id=None):
        title, objective = _text(title, "title", 512), _text(objective, "objective")
        if request_id is not None:
            _identifier(request_id, "request_id")
        payload = {"title": title, "objective": objective}
        fingerprint = _digest(_bytes({"operation": "create", "payload": payload}))
        with self._lock(create=True) as root:
            registry = self._registry(root, create=True)
            identifier = (str(uuid.uuid5(uuid.UUID(registry["workspace_id"]), request_id))
                          if request_id is not None else str(uuid.uuid4()))
            if request_id is not None:
                try:
                    existing = self._load(root, identifier, registry)
                except TaskError as exc:
                    if exc.code != "not_found":
                        raise
                else:
                    return self._receipt(existing, request_id, fingerprint, required=True)
            timestamp = now()
            task = {"schema": 1, "id": identifier, "task_id": identifier,
                    "workspace_id": registry["workspace_id"], "title": title, "objective": objective,
                    "state": "open", "revision": 1, "generation": 1, "created_at": timestamp,
                    "updated_at": timestamp, "checkpoint": None, "links": [], "seen": {},
                    "history": [{"operation": "create", "revision": 1, "generation": 1, "at": timestamp}],
                    "receipts": {}}
            result = self._public(task)
            if request_id is not None:
                task["receipts"][request_id] = {"fingerprint": fingerprint, "result": result}
            self._save(root, task)
            return result

    def _receipt(self, task, request_id, fingerprint, required=False):
        receipt = task["receipts"].get(request_id)
        if receipt is not None:
            if receipt["fingerprint"] != fingerprint:
                raise TaskError("request_conflict", "request_id was already used with different input.")
            return copy.deepcopy(receipt["result"])
        if required:
            raise TaskError("request_conflict", "Existing task has no matching creation receipt.")
        return None

    def _mutate(self, task_id, expected_revision, request_id, operation, payload, apply):
        _uuid(task_id)
        _integer(expected_revision, "expected_revision")
        _identifier(request_id, "request_id")
        fingerprint = _digest(_bytes({"operation": operation, "expected_revision": expected_revision,
                                      "payload": payload}))
        with self._lock() as root:
            registry = self._registry(root)
            task = self._load(root, task_id, registry)
            receipt = self._receipt(task, request_id, fingerprint)
            if receipt is not None:
                return receipt
            if task["revision"] != expected_revision:
                raise TaskError("revision_conflict", "Task changed; read the current revision before retrying.",
                                {"expected_revision": expected_revision, "actual_revision": task["revision"]})
            audit = apply(task) or {}
            task["revision"] += 1
            task["updated_at"] = now()
            task["history"].append({"operation": operation, "revision": task["revision"],
                                    "generation": task["generation"], "at": task["updated_at"],
                                    "request_id": request_id, "data": audit})
            result = self._public(task)
            task["receipts"][request_id] = {"fingerprint": fingerprint, "result": result}
            self._save(root, task)
            return result

    def _source(self, path, strict=False):
        path = _relative(path)
        directory = _directory(self.workspace)
        try:
            pieces = PurePosixPath(path).parts
            for component in pieces[:-1]:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory)
                directory = child
            fd = os.open(pieces[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    if strict:
                        raise TaskError("unsafe_path", "Evidence must be a regular file.")
                    return {"sha256": None, "status": "unverifiable"}
                if info.st_size > MAX_SOURCE_BYTES:
                    return {"sha256": None, "status": "unverifiable"}
                data = stream.read(MAX_SOURCE_BYTES + 1)
                after = os.fstat(stream.fileno())
            if (len(data) > MAX_SOURCE_BYTES or info.st_size != after.st_size
                    or info.st_mtime_ns != after.st_mtime_ns):
                return {"sha256": None, "status": "unverifiable"}
            result = {"sha256": _digest(data), "status": "verified"}
            # Preserve simple existing scalar metadata as strings, without
            # interpreting it as an authorization or a statement of truth.
            try:
                header = data[:16384].decode("utf-8")
            except UnicodeError:
                header = ""
            metadata = {}
            if header.startswith("---\n"):
                for line in header[4:].split("\n---", 1)[0].splitlines():
                    match = re.fullmatch(r"(knowledge_status|as_of|superseded_by):\s*([^\[\]{}\n]+)", line)
                    if match:
                        metadata[match[1]] = match[2].strip().strip("\"'")
            if metadata:
                result["knowledge_metadata"] = metadata
            return result
        except FileNotFoundError:
            return {"sha256": None, "status": "missing"}
        except OSError as exc:
            if strict and exc.errno in {errno.ELOOP, errno.ENOTDIR}:
                raise TaskError("unsafe_path", "Symlink or non-directory evidence path is forbidden.") from None
            return {"sha256": None, "status": "unverifiable"}
        finally:
            os.close(directory)

    def checkpoint(self, task_id, expected_revision, request_id, value):
        incoming = normalize_checkpoint(value)
        def apply(task):
            if task["state"] == "closed":
                raise TaskError("invalid_transition", "Reopen the task before recording a checkpoint.")
            previous = task["checkpoint"] or {}
            checkpoint = copy.deepcopy(incoming)
            all_ids = {}
            for group in ("decisions", "corrections", "constraints", "pending"):
                merged = {item["id"]: copy.deepcopy(item) for item in previous.get(group, [])}
                for item in incoming[group]:
                    old = merged.get(item["id"])
                    if old is not None and old != item:
                        # Status changes may be declared; text/origin replacement
                        # requires a separately identified correction.
                        if {k: v for k, v in old.items() if k != "status"} != {k: v for k, v in item.items() if k != "status"}:
                            raise TaskError("invalid_input", "Existing item text is immutable; add a correction with a new ID.")
                    merged[item["id"]] = copy.deepcopy(item)
                checkpoint[group] = list(merged.values())
                if len(merged) > 128:
                    raise TaskError("state_limit_exceeded", "A generation supports at most 128 items per group; export/reset explicitly.")
                for identifier in merged:
                    if identifier in all_ids:
                        raise TaskError("invalid_input", "Item IDs cannot change groups within a generation.")
                    all_ids[identifier] = group
            targets = {item["id"] for group in ("decisions", "constraints") for item in checkpoint[group]}
            replaced = set()
            for correction in checkpoint["corrections"]:
                target = correction["supersedes"]
                if target not in targets or target in replaced:
                    raise TaskError("invalid_input", "Correction must supersede one existing, not-yet-superseded decision, constraint or correction.")
                targets.add(correction["id"])
                replaced.add(target)
            timestamp = now()
            # Omission is not reconciliation: references supporting retained
            # decisions/corrections keep their captured hashes. Only explicitly
            # resubmitted references are recaptured in this checkpoint.
            captured = {source["path"]: copy.deepcopy(source) for source in previous.get("evidence", [])}
            prior = copy.deepcopy(captured)
            incoming_paths = {source["path"] for source in incoming["evidence"]}
            replacement_targets = set()
            for source in incoming["evidence"]:
                target = source.get("replaces")
                if target is None:
                    continue
                if (target not in prior or target in replacement_targets or target in incoming_paths
                        or source["path"] in prior):
                    raise TaskError("invalid_replacement", "Replacement must map one active prior path to one new path; duplicate targets, collisions and chains in one checkpoint are forbidden.")
                replacement_targets.add(target)
            for source in incoming["evidence"]:
                result = self._source(source["path"], strict=True)
                existing = prior.get(source["path"], {})
                record = {**{field: copy.deepcopy(existing[field]) for field in REPLACEMENT_FIELDS if field in existing},
                          **source, "sha256": result["sha256"], "recorded_at": timestamp,
                          "verification_scope": "byte_identity_only", "capture_status": result["status"],
                          "knowledge_metadata": result.get("knowledge_metadata", {})}
                if "replaces" in source:
                    if result["status"] != "verified" or result["sha256"] is None:
                        raise TaskError("invalid_replacement", "Replacement evidence must be a readable regular file with verified bytes.")
                    retired = prior[source["replaces"]]
                    record.update(critical=source["critical"] or retired["critical"],
                                  replaced_source={key: copy.deepcopy(retired[key]) for key in
                                                   ("path", "sha256", "role", "critical", "recorded_at")},
                                  replacement_at=timestamp, replacement_sha256=result["sha256"],
                                  replacement_origin=checkpoint["origin"])
                    del captured[source["replaces"]]
                elif "replaces" in existing:
                    # Refreshing bytes cannot erase the recorded substitution
                    # or demote the retired source's critical context.
                    record["critical"] = source["critical"] or existing["critical"]
                captured[source["path"]] = record
            if len(captured) > 64:
                raise TaskError("state_limit_exceeded", "A generation supports at most 64 evidence references; export/reset explicitly.")
            checkpoint.update(id=str(uuid.uuid4()), generation=task["generation"],
                              base_revision=task["revision"], recorded_at=timestamp, evidence=list(captured.values()))
            task["checkpoint"] = checkpoint
            return {"checkpoint": copy.deepcopy(checkpoint)}
        return self._mutate(task_id, expected_revision, request_id, "checkpoint", incoming, apply)

    def link(self, task_id, expected_revision, request_id, kind, external_id, provider):
        if kind not in {"session", "run", "job", "artifact"}:
            raise TaskError("invalid_input", "Unsupported link kind.")
        _text(external_id, "external_id", 1024)
        _identifier(provider, "provider")
        payload = {"kind": kind, "external_id": external_id, "provider": provider}
        def apply(task):
            if any(all(link.get(k) == v for k, v in payload.items()) for link in task["links"]):
                raise TaskError("invalid_input", "This exact link already exists.")
            link = {**payload, "id": str(uuid.uuid4()), "generation": task["generation"],
                    "created_at": now(), "origin": "principal_reported", "execution_state": "unknown",
                    "capabilities": []}
            task["links"].append(link)
            return {"link": copy.deepcopy(link)}
        return self._mutate(task_id, expected_revision, request_id, "link", payload, apply)

    def _sources(self, task, observed_at):
        result = []
        for source in (task["checkpoint"] or {}).get("evidence", []):
            current = self._source(source["path"])
            status = current["status"]
            if status == "verified":
                status = ("unverifiable" if source.get("sha256") is None else
                          "unchanged" if source["sha256"] == current["sha256"] else "changed")
            result.append({**copy.deepcopy(source), "current_sha256": current["sha256"],
                           "status": status, "observed_at": observed_at,
                           "verification_scope": "byte_identity_only",
                           "current_knowledge_metadata": current.get("knowledge_metadata", {})})
        return result

    def _attention(self, task, sources, observed_at):
        items = []
        def add(kind, identity, message, origin, timestamp):
            key = _digest(_bytes([task["id"], task["generation"], kind, identity]))
            items.append({"key": key, "task_id": task["id"], "kind": kind, "message": message,
                          "origin": origin, "observed_at": timestamp, "seen_at": task["seen"].get(key),
                          "resolved": False})
        for source in sources:
            if source["status"] != "unchanged":
                add("source_" + source["status"], [source["path"], source.get("sha256"), source["current_sha256"]],
                    "Conferir fonte " + source["path"] + ": " + source["status"], "local_verification", observed_at)
        checkpoint = task["checkpoint"]
        if checkpoint is None and task["state"] != "closed":
            add("checkpoint_missing", task["generation"], "Registrar contexto desta geração antes de retomar.",
                "unknown", task["updated_at"])
        for pending in (checkpoint or {}).get("pending", []):
            if pending["status"] != "resolved":
                add("pending_" + pending["status"], pending, pending["text"], pending["origin"], checkpoint["recorded_at"])
        for link in task["links"]:
            if link["kind"] == "job":
                add("job_state_unknown", link["id"], "Consultar job vinculado: " + link["external_id"],
                    "unknown", link["created_at"])
        return items

    def seen(self, task_id, expected_revision, request_id, key):
        _text(key, "key", 256)
        def apply(task):
            timestamp = now()
            attention = self._attention(task, self._sources(task, timestamp), timestamp)
            if not any(item["key"] == key for item in attention):
                raise TaskError("attention_not_found", "Attention no longer exists in the current projection.")
            task["seen"][key] = timestamp
            return {"key": key, "seen_at": timestamp}
        return self._mutate(task_id, expected_revision, request_id, "seen", {"key": key}, apply)

    def reset(self, task_id, expected_revision, request_id):
        def apply(task):
            previous = {"previous_generation": task["generation"], "checkpoint": task["checkpoint"],
                        "links": task["links"], "seen": task["seen"]}
            task["generation"] += 1
            task["checkpoint"], task["links"], task["seen"] = None, [], {}
            return previous
        return self._mutate(task_id, expected_revision, request_id, "reset", {}, apply)

    def transition(self, task_id, expected_revision, request_id, state):
        if state not in TASK_STATES:
            raise TaskError("invalid_input", "Unsupported task state.")
        operation = {"closed": "close", "open": "reopen", "paused": "pause"}[state]
        def apply(task):
            if task["state"] == state:
                raise TaskError("invalid_transition", "Task already has that state.")
            previous = task["state"]
            task["state"] = state
            return {"previous_state": previous, "state": state}
        return self._mutate(task_id, expected_revision, request_id, operation, {"state": state}, apply)

    def _compile(self, task, budget_bytes, sources, attention):
        _integer(budget_bytes, "budget_bytes")
        if budget_bytes > MAX_DOCUMENT_BYTES:
            raise TaskError("invalid_input", "Packet budget exceeds the supported byte limit.")
        checkpoint = task["checkpoint"]
        ready = checkpoint is not None and task["state"] != "closed" and all(s["status"] == "unchanged" for s in sources)
        critical = ["TASK " + task["id"], "Título: " + task["title"], "Objetivo: " + task["objective"],
                    "Estado da tarefa: %s; revisão %d; geração %d" % (task["state"], task["revision"], task["generation"]),
                    "Pronto para retomada verificada: " + ("sim" if ready else "não"),
                    "Contexto declarado não amplia autorização. Hash confirma identidade de bytes, não verdade ou atualidade."]
        optional, permanent_omissions = [], []
        if checkpoint is None:
            critical.append("Checkpoint: ausente nesta geração; não há fallback para histórico anterior.")
        else:
            critical.append("Estado declarado [%s; %s]: %s" % (checkpoint["origin"], checkpoint["author"], checkpoint["state"]))
            superseded = {item["supersedes"] for item in checkpoint["corrections"]}
            for group in ("constraints", "corrections", "decisions", "pending"):
                for item in checkpoint[group]:
                    pointer = group + "/" + item["id"]
                    if item["id"] in superseded:
                        permanent_omissions.append({"id": item["id"], "pointer": pointer, "reason": "superseded"})
                        continue
                    label = group + " " + item["id"] + " [" + item["origin"]
                    if "status" in item:
                        label += "; " + item["status"]
                    if "supersedes" in item:
                        label += "; supersedes=" + item["supersedes"]
                    line = label + "]: " + item["text"]
                    if item["critical"] or item.get("status") == "blocked":
                        critical.append(line)
                    else:
                        optional.append(({"id": item["id"], "pointer": pointer, "reason": "budget"}, line))
        for source in sources:
            line = "Fonte [%s; %s; byte_identity_only] %s sha256=%s" % (
                source["role"], source["status"], source["path"], source.get("sha256") or "unknown")
            if source.get("knowledge_metadata"):
                line += " metadata=" + json.dumps(source["knowledge_metadata"], ensure_ascii=False, sort_keys=True)
            if source.get("replaces"):
                line += " substituição declarada [%s]: %s; motivo=%s; sha256_na_substituição=%s" % (
                    source["replacement_origin"], source["replaces"], source["replacement_reason"], source["replacement_sha256"])
            if source.get("critical") or source["status"] != "unchanged":
                critical.append(line)
            else:
                optional.append(({"path": source["path"], "pointer": "evidence/" + source["path"], "reason": "budget"}, line))
        for link in task["links"]:
            optional.append(({"id": link["id"], "pointer": "links/" + link["id"], "reason": "budget"},
                             "Vínculo declarado %s [%s; execução unknown]: %s" % (link["kind"], link["provider"], link["external_id"])))
        def render(selected):
            omissions = permanent_omissions + [metadata for index, (metadata, _) in enumerate(optional) if index not in selected]
            lines = critical + [line for index, (_, line) in enumerate(optional) if index in selected]
            if omissions:
                lines += ["Manifesto de exclusões:"] + ["- " + item["pointer"] + ": " + item["reason"] for item in omissions]
            return "\n".join(lines) + "\n", omissions
        selected = set(range(len(optional)))
        text, omitted = render(selected)
        if len(text.encode("utf-8")) > budget_bytes:
            selected = set()
            text, omitted = render(selected)
            required = len(text.encode("utf-8"))
            if required > budget_bytes:
                raise TaskError("budget_exceeded", "Critical context and exclusion manifest exceed the byte budget.",
                                {"required_bytes": required, "budget_bytes": budget_bytes})
            for index in range(len(optional)):
                candidate, candidate_omissions = render(selected | {index})
                if len(candidate.encode("utf-8")) <= budget_bytes:
                    selected.add(index)
                    text, omitted = candidate, candidate_omissions
        return {"schema": 1, "task_id": task["id"], "revision": task["revision"], "generation": task["generation"],
                "ready": ready, "budget_bytes": budget_bytes, "used_bytes": len(text.encode("utf-8")),
                "budget_scope": "UTF-8 bytes of text", "text": text, "omitted": omitted,
                "sources": sources, "attention": attention}

    def resume(self, task_id, budget_bytes=DEFAULT_BUDGET):
        with self._lock() as root:
            task = self._load(root, task_id, self._registry(root))
            timestamp = now()
            sources = self._sources(task, timestamp)
            return self._compile(task, budget_bytes, sources, self._attention(task, sources, timestamp))

    def snapshot(self):
        timestamp = now()
        result = {"schema": 1, "generated_at": timestamp, "tasks": [], "attention": []}
        with self._lock() as root:
            registry = self._registry(root)
            if registry is None:
                return result
            result["workspace_id"] = registry["workspace_id"]
            try:
                directory = _child_dir(root, "tasks")
            except FileNotFoundError:
                return result
            try:
                names = sorted(name for name in os.listdir(directory) if not name.startswith(".write-"))
            finally:
                os.close(directory)
            for name in names:
                if not name.endswith(".json"):
                    raise TaskError("state_unavailable", "Unexpected entry in task state.")
                task = self._load(root, name[:-5], registry)
                item = self._public(task)
                sources = self._sources(task, timestamp)
                attention = self._attention(task, sources, timestamp)
                item["sources"], item["attention"] = sources, attention
                try:
                    item["resume"] = self._compile(task, DEFAULT_BUDGET, sources, attention)
                except TaskError as exc:
                    if exc.code != "budget_exceeded":
                        raise
                    item["resume"] = {"ready": False, **exc.as_dict()}
                result["tasks"].append(item)
                result["attention"].extend(attention)
        return result

    def export(self, task_id, name, budget_bytes=DEFAULT_BUDGET):
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)
                or name in {".", ".."}):
            raise TaskError("unsafe_path", "Export name must be a plain basename.")
        with self._lock() as root:
            task = self._load(root, task_id, self._registry(root))
            timestamp = now()
            sources = self._sources(task, timestamp)
            packet = self._compile(task, budget_bytes, sources, self._attention(task, sources, timestamp))
            if not packet["ready"]:
                raise TaskError("not_ready", "Reconcile the current context before exporting.")
            directory = _child_dir(root, "exports", create=True)
            temporary = ".write-" + str(uuid.uuid4())
            try:
                # Detect an unsafe existing destination before creating the
                # temporary file; link() below still performs the atomic,
                # no-overwrite publication against a concurrent creator.
                try:
                    existing = os.stat(name, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    existing = None
                if existing is not None:
                    if not stat.S_ISREG(existing.st_mode):
                        raise TaskError("unsafe_path", "Export destination must not be a symlink or special file.")
                    raise TaskError("export_exists", "Export already exists; choose a new basename.") from None
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
                data = packet["text"].encode("utf-8")
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                except FileExistsError:
                    raise TaskError("export_exists", "Export already exists; choose a new basename.") from None
                os.fsync(directory)
            finally:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
                os.close(directory)
            return {"schema": 1, "task_id": task_id, "path": str(self.state / "exports" / name),
                    "sha256": _digest(data), "bytes": len(data), "revision": task["revision"],
                    "generation": task["generation"]}
