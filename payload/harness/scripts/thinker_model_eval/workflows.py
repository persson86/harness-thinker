"""Native/host workflow bridge, with trusted final-state checks.

The workspace is a scope boundary, not a security sandbox for a host agent.
This module never starts a model, changes delegation, or executes candidate
Python on the host. Code tests require an explicit gate and isolated Docker.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

try:
    import resource
except ImportError:  # Fail closed on hosts without a bounded output mechanism.
    resource = None


class WorkflowError(ValueError):
    pass


MAX_FILE_BYTES = 2 * 1024 * 1024
DOCKER_IMAGE = "python:3.12-alpine"

# This runner contains stimuli/operations only, never expected results. The
# candidate and runner are untrusted as evidence: the HOST compares their
# bounded JSON envelope to frozen expectations which never enter the container.
CODE_RUNNER = r'''
def run():
    import contextlib, importlib.util, json, math, pathlib, sys, tempfile
    def decode(v):
        if isinstance(v,dict) and set(v)=={"$float"}: return float(v["$float"])
        if isinstance(v,dict): return {k:decode(x) for k,x in v.items()}
        if isinstance(v,list): return [decode(x) for x in v]
        return v
    def encode(v):
        if isinstance(v,float) and not math.isfinite(v): return {"$float":str(v)}
        if isinstance(v,dict): return {k:encode(x) for k,x in v.items()}
        if isinstance(v,list): return [encode(x) for x in v]
        return v
    request=json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        spec=importlib.util.spec_from_file_location("candidate","/workspace/"+request["module"])
        candidate=importlib.util.module_from_spec(spec); spec.loader.exec_module(candidate)
    results=[]
    for item in request["cases"]:
        result={"id":item["id"]}
        with contextlib.redirect_stdout(sys.stderr):
            if request["protocol"]=="merge-scores":
                args=decode(item["args"]); before=encode(args)
                try:
                    value=candidate.merge_scores(*args)
                    result["value"]=encode(value)
                    result["args_unchanged"]=encode(args)==before
                    if item.get("mutate_return"):
                        for row in value: row["score"]=99
                        result["return_independent"]=encode(args)==before
                except Exception as error:
                    result.update(error=type(error).__name__,args_unchanged=encode(args)==before)
            else:
                with tempfile.TemporaryDirectory() as tmp:
                    root=pathlib.Path(tmp); (root/"a").mkdir(); (root/"a"/"x.txt").write_text("x")
                    (root/"link").symlink_to(root/"a",target_is_directory=True)
                    (root/"filelink").symlink_to(root/"a"/"x.txt")
                    alias=root/"rootlink"; alias.symlink_to(root,target_is_directory=True)
                    names={"normal":"a/x.txt","root-alias":"a/x.txt","parent":"../x","absolute":"/x",
                           "empty-component":"a//x.txt","dot":"a/./x.txt","parent-inside":"a/../a/x.txt",
                           "backslash":"a\\x.txt","colon":"a:x","none":None,"empty":"",
                           "directory":"a","symlink-directory":"link/x.txt","symlink-file":"filelink"}
                    try:
                        value=candidate.validate_input_file(alias if item["scenario"]=="root-alias" else root,names[item["scenario"]])
                        result.update(value=str(value.relative_to(root)),is_path=isinstance(value,pathlib.Path))
                    except Exception as error: result["error"]=type(error).__name__
        results.append(result)
    json.dump({"protocol_version":1,"results":results},sys.stdout,allow_nan=False)
run()
'''


def _slug(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise WorkflowError("Invalid workflow/trial ID")
    return value


def _relative(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise WorkflowError("Expected a confined lexical relative path")
    return value


def _safe(root, relative, *, file=False):
    current = Path(root)
    for component in _relative(relative).split("/"):
        current /= component
        if current.is_symlink():
            raise WorkflowError("Symlink refused in workflow")
    if not current.resolve().is_relative_to(Path(root).resolve()):
        raise WorkflowError("Workflow path escapes root")
    if file and not current.is_file():
        raise WorkflowError(f"Missing regular workflow file: {relative}")
    return current


def _root(path):
    root = Path(path).absolute()
    if not root.is_dir() or any(p.is_symlink() for p in (root, *root.parents)):
        raise WorkflowError("Workflow root must be a real directory without symlink ancestors")
    return root


def _bytes(path):
    if path.stat().st_size > MAX_FILE_BYTES:
        raise WorkflowError("Workflow file exceeds trusted size limit")
    return path.read_bytes()


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def _json(path):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise WorkflowError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(_bytes(path).decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(WorkflowError("Nonfinite JSON")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise WorkflowError(f"Invalid workflow JSON: {error}") from None


def _write(path, value):
    if path.is_symlink():
        raise WorkflowError("Symlink output refused")
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".workflow-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _spec(root, relative):
    spec = _json(_safe(root, relative, file=True))
    if not isinstance(spec, dict) or type(spec.get("schema_version")) is not int or spec["schema_version"] != 1:
        raise WorkflowError("Workflow schema_version must be 1")
    _slug(spec.get("id"))
    if not isinstance(spec.get("workspace"), list) or not spec["workspace"]:
        raise WorkflowError("Workflow requires initial workspace files")
    if not isinstance(spec.get("writable"), list) or not spec["writable"]:
        raise WorkflowError("Workflow requires explicit writable scope")
    if not isinstance(spec.get("artifacts"), list) or not spec["artifacts"]:
        raise WorkflowError("Workflow requires output artifacts")
    if not isinstance(spec.get("checks"), list) or not spec["checks"]:
        raise WorkflowError("Workflow requires trusted final-state checks")
    paths, sources = set(), {relative}
    for entry in spec["workspace"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "source"}:
            raise WorkflowError("Invalid workspace entry")
        name = _relative(entry["path"])
        if name in paths:
            raise WorkflowError("Duplicate workspace path")
        paths.add(name)
        sources.add(_relative(entry["source"]))
    for name in spec["writable"] + spec["artifacts"]:
        _relative(name)
    if len(set(spec["artifacts"])) != len(spec["artifacts"]):
        raise WorkflowError("Duplicate artifact")
    if any(not _writable(name, spec["writable"]) for name in spec["artifacts"]):
        raise WorkflowError("Artifacts must be inside writable scope")
    checks = set()
    for check in spec["checks"]:
        if not isinstance(check, dict) or check.get("kind") not in {"json", "text", "python-unittest"}:
            raise WorkflowError("Unknown trusted workflow check")
        identifier = _slug(check.get("id"))
        if identifier in checks:
            raise WorkflowError("Duplicate check ID")
        checks.add(identifier)
        if check["kind"] == "python-unittest":
            sources.add(_relative(check.get("source")))
        else:
            _relative(check.get("path"))
        if check["kind"] == "json":
            assertions = check.get("assertions")
            if not isinstance(assertions, list) or not assertions:
                raise WorkflowError("JSON check requires assertions")
            for assertion in assertions:
                if (not isinstance(assertion, dict) or not isinstance(assertion.get("pointer"), str)
                        or not assertion["pointer"].startswith("/")
                        or not set(assertion) <= {"pointer", "equals", "one_of", "contains", "min", "max"}
                        or len(assertion) < 2):
                    raise WorkflowError("Invalid JSON assertion")
    # Trusted expectations/tests never enter the candidate workspace.
    hidden_sources = {c["source"] for c in spec["checks"] if c["kind"] == "python-unittest"}
    if hidden_sources & {e["source"] for e in spec["workspace"]} or relative in {e["source"] for e in spec["workspace"]}:
        raise WorkflowError("Trusted checks must stay outside candidate workspace")
    return spec, sources


def _writable(path, allowed):
    return any(path == prefix or path.startswith(prefix + "/") for prefix in allowed)


def validate_workflow(suite_root, case):
    """Return all additional source bytes the engine must freeze, suite-relative."""
    root = _root(suite_root)
    relative = _relative(case.get("workflow"))
    _, sources = _spec(root, relative)
    return {name: _bytes(_safe(root, name, file=True)) for name in sources}


def _frozen(experiment, case):
    experiment = _root(experiment)
    relative = _relative(case.get("workflow"))
    if not relative.startswith("inputs/"):
        raise WorkflowError("Workflow spec must be in frozen experiment inputs")
    root = _root(_safe(experiment, "inputs"))
    spec, sources = _spec(root, relative[len("inputs/"):])
    manifest_path = _safe(experiment, "manifest.json", file=True)
    expected_manifest = _bytes(_safe(experiment, "manifest.sha256", file=True)).decode("ascii").strip()
    if _digest(_bytes(manifest_path)) != expected_manifest:
        raise WorkflowError("Frozen workflow manifest changed")
    manifest = _json(manifest_path)
    if not any(c.get("id") == case.get("id") and c.get("workflow") == relative for c in manifest.get("cases", [])):
        raise WorkflowError("Workflow case differs from frozen manifest")
    hashes = manifest.get("hashes", {})
    for name in sources:
        if hashes.get("inputs/" + name) != _digest(_bytes(_safe(root, name, file=True))):
            raise WorkflowError(f"Frozen workflow input changed or missing hash: {name}")
    return experiment, root, spec


def prepare(experiment_path, case, trial):
    """Create a clean candidate workspace; never start a model or a service."""
    experiment, inputs, spec = _frozen(experiment_path, case)
    trial_id = _slug(trial["id"])
    receipt_path = _safe(experiment, "workflow-receipts/" + trial_id + ".json")
    seal_path = _safe(experiment, "workflow-receipts/" + trial_id + ".sha256")
    if receipt_path.exists() or seal_path.exists():
        raise WorkflowError("Workspace already prepared; no implicit reset or replay")
    # Real, private temp root prevents automatic inheritance of vault documents
    # and hidden evaluation siblings. This still is NOT a host security sandbox.
    temp_root = Path(tempfile.gettempdir()).resolve()
    vault_root = (experiment.parent.parent.parent if experiment.parent.name == "model-eval"
                  and experiment.parent.parent.name == "drafts" else experiment)
    if temp_root.is_relative_to(vault_root):
        raise WorkflowError("Temporary namespace must be outside the vault and experiment")
    workspace = Path(tempfile.mkdtemp(prefix="thinker-workflow-", dir=temp_root)).resolve()
    os.chmod(workspace, 0o700)
    initial = {}
    for entry in spec["workspace"]:
        output = _safe(workspace, entry["path"])
        output.parent.mkdir(parents=True, exist_ok=True)
        content = _bytes(_safe(inputs, entry["source"], file=True))
        output.write_bytes(content)
        initial[entry["path"]] = _digest(content)
    for prefix in spec["writable"]:
        # An exact artifact scope is a file, including when it does not yet exist.
        target = _safe(workspace, prefix)
        if prefix in spec["artifacts"]:
            target.parent.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.mkdir(parents=True)
    receipt = {"schema_version": 1, "trial_id": trial_id, "case_id": case["id"],
               "workflow_id": spec["id"], "spec_hash": _digest(_bytes(_safe(inputs, case["workflow"][7:], file=True))),
               "initial_hashes": initial, "writable": spec["writable"], "workspace": str(workspace),
               "workspace_namespace": str(temp_root), "layout_version": 2}
    _write(receipt_path, receipt)
    seal_path.write_text(_digest(_bytes(receipt_path)) + "\n", encoding="ascii")
    return {"workspace": str(workspace), "receipt": str(receipt_path), "execution_source": "host-managed",
            "security_boundary": "workspace scope only; host agent is not security-sandboxed",
            "task": "Execute the frozen case using tools in this workspace. Do not read grading inputs outside it.",
            "writable": spec["writable"], "artifacts_expected": spec["artifacts"],
            "code_execution": "gated Docker only; never execute candidate code on host"}


def load_receipt(experiment_path, trial_id, *, require_workspace=False):
    """Validate private operational receipt; not attack security against principal."""
    experiment = _root(experiment_path)
    trial_id = _slug(trial_id)
    path = _safe(experiment, "workflow-receipts/" + trial_id + ".json", file=True)
    seal = _safe(experiment, "workflow-receipts/" + trial_id + ".sha256", file=True)
    if _digest(_bytes(path)) != _bytes(seal).decode("ascii").strip():
        raise WorkflowError("Workflow receipt changed")
    receipt = _json(path)
    if receipt.get("layout_version") != 2 or receipt.get("trial_id") != trial_id:
        raise WorkflowError("Legacy or mismatched receipt requires explicit reconciliation")
    value, namespace = receipt.get("workspace"), receipt.get("workspace_namespace")
    if not isinstance(value, str) or not isinstance(namespace, str):
        raise WorkflowError("Invalid workspace receipt")
    workspace, temp_root = Path(value), Path(namespace)
    if (not workspace.is_absolute() or not temp_root.is_absolute()
            or workspace.parent != temp_root or not workspace.name.startswith("thinker-workflow-")
            or workspace.is_relative_to(experiment) or value != str(workspace.resolve())
            or namespace != str(temp_root.resolve())):
        raise WorkflowError("Workspace receipt must bind a canonical external temp namespace")
    if require_workspace:
        _root(workspace)
    return receipt


def _pointer(value, pointer):
    for key in pointer[1:].split("/"):
        key = key.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def _assert(value, assertion):
    actual = _pointer(value, assertion["pointer"])
    if "equals" in assertion and (type(actual) is not type(assertion["equals"]) or actual != assertion["equals"]):
        return False
    if "one_of" in assertion and not any(type(actual) is type(item) and actual == item for item in assertion["one_of"]):
        return False
    if "contains" in assertion and (not isinstance(actual, list) or any(item not in actual for item in assertion["contains"])):
        return False
    for key in ("min", "max"):
        if key in assertion:
            if type(actual) not in (int, float) or not math.isfinite(actual):
                return False
            if (key == "min" and actual < assertion[key]) or (key == "max" and actual > assertion[key]):
                return False
    return True


def _same(actual, expected):
    """JSON comparison preserving booleans while accepting int/float equality."""
    if type(actual) in (int, float) and type(expected) in (int, float):
        return actual == expected
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(_same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def _snapshot(experiment, workspace, trial_id):
    snapshot = _safe(experiment, "workflow-snapshots/" + trial_id)
    if snapshot.exists():
        raise WorkflowError("Final-state snapshot already exists; no implicit replay")
    snapshot.mkdir(parents=True)
    violations, observed, total_bytes = [], {}, 0
    for number, path in enumerate(workspace.rglob("*")):
        if number >= 500:
            violations.append("Workspace exceeds 500-entry capture budget")
            break
        name = path.relative_to(workspace).as_posix()
        try:
            _relative(name)
        except WorkflowError:
            violations.append("Invalid candidate filename: " + name[:200])
            continue
        if path.is_symlink():
            violations.append("Symlink in final workspace: " + name)
        elif path.is_dir():
            _safe(snapshot, name).mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            try:
                content = _bytes(_safe(workspace, name, file=True))
            except (WorkflowError, FileNotFoundError, PermissionError) as error:
                violations.append("Candidate capture violation: " + name[:200] + ": " + str(error)[:200])
                continue
            total_bytes += len(content)
            if total_bytes > 64 * 1024 * 1024:
                violations.append("Workspace exceeds 64 MiB capture budget")
                break
            observed[name] = _digest(content)
            target = _safe(snapshot, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        else:
            violations.append("Unsupported file type in final workspace: " + name)
    # Detect ordinary concurrent edits during capture. Checks and artifacts use
    # ONLY this captured state; this is not an atomic filesystem snapshot.
    for name, digest in observed.items():
        try:
            unchanged = _digest(_bytes(_safe(workspace, name, file=True))) == digest
        except (WorkflowError, FileNotFoundError, PermissionError):
            unchanged = False
        if not unchanged:
            violations.append("Workspace changed during capture: " + name)
    return snapshot, violations[:20]


def _bound_docker_output():
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))


def _container_state(docker, cidfile):
    """Inspect actual Docker lifecycle; candidate exit values are not launch errors."""
    if not cidfile.is_file() or cidfile.is_symlink():
        return None
    try:
        identifier = cidfile.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return None
    if not re.fullmatch(r"[a-f0-9]{64}", identifier):
        return None
    try:
        result = subprocess.run([docker, "inspect", "--format", "{{json .State}}", identifier],
                                capture_output=True, timeout=10)
        state = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired):
        return None
    if (not isinstance(state, dict) or not isinstance(state.get("StartedAt"), str)
            or not state["StartedAt"] or state["StartedAt"].startswith("0001-01-01")):
        return None
    return state


def _code_check(workspace, inputs, check, allow):
    if not allow:
        return {"status": "unavailable", "reason": "Candidate code execution requires explicit gate"}
    docker = shutil.which("docker")
    if not docker:
        return {"status": "unavailable", "reason": "Docker unavailable; candidate code was not executed"}
    if resource is None:
        return {"status": "unavailable", "reason": "Host cannot bound Docker output; no code execution fallback"}
    # Do not pull/install anything implicitly. Image availability is a precondition.
    try:
        probe = subprocess.run([docker, "image", "inspect", DOCKER_IMAGE], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unavailable", "reason": "Docker backend unavailable"}
    if probe.returncode:
        return {"status": "unavailable", "reason": "Trusted Docker image unavailable; no image pulled"}
    try:
        image_id = json.loads(probe.stdout)[0]["Id"]
        if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
            raise ValueError()
    except (ValueError, KeyError, IndexError, TypeError):
        return {"status": "unavailable", "reason": "Docker image identity not observable"}
    vectors = _json(_safe(inputs, check["source"], file=True))
    if (not isinstance(vectors, dict) or vectors.get("schema_version") != 1
            or vectors.get("protocol") not in {"merge-scores", "confined-file"}
            or not isinstance(vectors.get("cases"), list) or not 1 <= len(vectors["cases"]) <= 100):
        raise WorkflowError("Invalid trusted black-box test vectors")
    _relative(vectors.get("module"))
    ids = [item.get("id") for item in vectors["cases"]]
    if len(set(ids)) != len(ids) or not all(isinstance(x, str) for x in ids):
        raise WorkflowError("Invalid trusted test IDs")
    request = {"protocol": vectors["protocol"], "module": vectors["module"],
               "cases": [{k: v for k, v in item.items() if k != "expected"} for item in vectors["cases"]]}
    name = "thinker-eval-" + uuid.uuid4().hex
    lifecycle = tempfile.TemporaryDirectory(prefix="thinker-code-", dir=Path(tempfile.gettempdir()).resolve())
    cidfile = Path(lifecycle.name) / "container.cid"
    command = [docker, "run", "--interactive", "--cidfile", str(cidfile), "--name", name, "--network", "none", "--read-only",
               "--pids-limit", "64", "--memory", "256m", "--cpus", "1", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--user", "65534:65534",
               "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m", "--log-driver", "none",
               "--mount", f"type=bind,source={workspace},target=/workspace,readonly",
               image_id, "python", "-I", "-B", "-c", CODE_RUNNER]
    try:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            result = subprocess.run(command, input=json.dumps(request).encode("utf-8"), stdout=output, stderr=errors,
                                    timeout=30, preexec_fn=_bound_docker_output)
            output.seek(0)
            text = output.read(128 * 1024).decode("utf-8", errors="replace")
            errors.seek(0)
            diagnostics = errors.read(128 * 1024).decode("utf-8", errors="replace")
        state = _container_state(docker, cidfile)
        if state is None:
            return {"status": "unavailable", "returncode": result.returncode,
                    "reason": "Docker launch/lifecycle not observed; candidate code outcome unknown"}
        try:
            actual = json.loads(text)
            expected = {"protocol_version": 1, "results": [{"id": item["id"], **item["expected"]} for item in vectors["cases"]]}
            passed = (result.returncode == 0 and state.get("Running") is False
                      and type(state.get("ExitCode")) is int and state["ExitCode"] == 0 and _same(actual, expected))
        except (ValueError, TypeError):
            actual, passed = None, False
        return {"status": "pass" if passed else "fail", "returncode": result.returncode,
                "evidence": {"actual": actual, "diagnostics": diagnostics}, "backend": "docker-blackbox",
                "image": DOCKER_IMAGE, "image_id": image_id, "container_state": state,
                "adversarial_detection": "limited",
                "limitation": "Expectations remain on host and empty success cannot pass. The worker shares an interpreter with candidate code: introspection/monkeypatch can undermine memory-mutation observations. This is behavior testing, not proof against malicious test-specific implementations."}
    except subprocess.TimeoutExpired:
        state = _container_state(docker, cidfile)
        return {"status": "fail" if state is not None else "unavailable",
                "reason": "Isolated code test timeout" if state is not None else "Docker lifecycle timeout; no candidate outcome observed",
                "backend": "docker", "container_state": state}
    except OSError:
        return {"status": "unavailable", "reason": "Docker launch failed; no host execution fallback"}
    finally:
        try:
            subprocess.run([docker, "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        lifecycle.cleanup()


def finish(experiment_path, case, trial, response=None, *, execution_source="host-managed", identity=None,
           observed_trace=None, allow_code_execution=False):
    """Verify actual final files, capture immutable copies, preserve unknown audit."""
    experiment, inputs, spec = _frozen(experiment_path, case)
    trial_id = _slug(trial["id"])
    receipt = load_receipt(experiment, trial_id, require_workspace=True)
    workspace = _root(receipt["workspace"])
    expected_initial = {e["path"]: _digest(_bytes(_safe(inputs, e["source"], file=True))) for e in spec["workspace"]}
    if (receipt.get("trial_id") != trial_id or receipt.get("case_id") != case["id"]
            or receipt.get("workflow_id") != spec["id"] or receipt.get("initial_hashes") != expected_initial
            or receipt.get("writable") != spec["writable"]
            or receipt.get("spec_hash") != _digest(_bytes(_safe(inputs, case["workflow"][7:], file=True)))):
        raise WorkflowError("Workflow receipt changed")
    if execution_source not in {"host-managed", "native-agent"}:
        raise WorkflowError("Execution source must be explicitly host-managed or native-agent")
    if identity is not None and not isinstance(identity, dict):
        raise WorkflowError("Observed identity must be structured or unknown")
    if observed_trace is not None and (not isinstance(observed_trace, dict)
            or observed_trace.get("source") != "host-observed" or not isinstance(observed_trace.get("events"), list)):
        raise WorkflowError("Trace requires explicit host-observed provenance; self-report is not audit")
    snapshot, violations = _snapshot(experiment, workspace, trial_id)
    checks = []
    for path, digest in expected_initial.items():
        if _writable(path, spec["writable"]):
            continue
        try:
            unchanged = _digest(_bytes(_safe(snapshot, path, file=True))) == digest
        except (WorkflowError, OSError):
            unchanged = False
        checks.append({"id": "protected:" + path, "status": "pass" if unchanged else "fail"})
        if not unchanged:
            violations.append("Protected fixture changed: " + path)
    initial_dirs = {parent.as_posix() for name in [*expected_initial, *spec["writable"], *spec["artifacts"]]
                    for parent in Path(name).parents if parent.as_posix() != "."}
    for path in snapshot.rglob("*"):
        relative = path.relative_to(snapshot).as_posix()
        if (path.is_file() and relative not in expected_initial and not _writable(relative, spec["writable"])) or (
                path.is_dir() and relative not in initial_dirs and not _writable(relative, spec["writable"])):
            violations.append("Write outside declared scope: " + relative)
    if violations:
        checks.append({"id": "workspace-scope", "status": "fail", "evidence": list(violations)})
    artifacts = []
    for name in spec["artifacts"]:
        try:
            source = _safe(snapshot, name, file=True)
            content = _bytes(source)
            output = _safe(experiment, "workflow-artifacts/" + trial_id + "/" + name)
            if output.exists():
                raise WorkflowError("Final artifact already captured; no implicit replacement")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
            artifacts.append({"path": output.relative_to(experiment).as_posix(), "sha256": _digest(content), "bytes": len(content)})
            checks.append({"id": "artifact:" + name, "status": "pass"})
        except WorkflowError as error:
            checks.append({"id": "artifact:" + name, "status": "fail", "reason": str(error)})
    for check in spec["checks"]:
        try:
            if check["kind"] == "python-unittest":
                result = _code_check(snapshot, inputs, check, allow_code_execution and not violations)
            elif check["kind"] == "text":
                text = _bytes(_safe(snapshot, check["path"], file=True)).decode("utf-8")
                result = {"status": "pass" if text.strip() else "fail", "evidence": "Observed nonempty UTF-8 artifact; semantic/visual quality needs review"}
            else:
                value = _json(_safe(snapshot, check["path"], file=True))
                passed = [_assert(value, assertion) for assertion in check["assertions"]]
                result = {"status": "pass" if all(passed) else "fail", "assertions_passed": passed}
        except (WorkflowError, OSError, UnicodeError, KeyError, IndexError, TypeError, ValueError, OverflowError) as error:
            result = {"status": "fail", "reason": str(error)}
        checks.append({"id": check["id"], **result})
    statuses = {check["status"] for check in checks}
    status = "fail" if "fail" in statuses else "unavailable" if "unavailable" in statuses else "pass"
    return {"response": response, "execution_source": execution_source, "observed_identity": identity,
            "final_state_checks": {"status": status, "checks": checks}, "artifacts": artifacts,
            "trajectory": {"status": "fail" if violations else "unknown", "violations": violations},
            "observed_trace": observed_trace,
            "limitations": ["Final-state checks are independent of candidate self-report; semantic rubric review remains required.",
                            "Host workspace is not a security sandbox; native tools/actions need host observation.",
                            "Checks and artifacts use the captured state. Stop the host agent before finish; capture is not an atomic filesystem snapshot.",
                            "Missing identity and trajectory observations remain unknown; HTML/text checks do not prove rendered visual quality."]}
