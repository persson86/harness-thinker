"""Freeze, execute and audit bounded text experiments using delegate.py only."""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

FAMILIES = {"retrieval", "ingestion", "analysis", "research", "code", "communication"}
ACTIVE = {"queued", "running", "submitting"}
FAILURES = {"failed", "cancelled", "timed_out", "interrupted"}
STATES = ACTIVE | FAILURES | {"planned", "completed", "unavailable", "preparing", "prepared", "finishing"}
HIGH_EFFORTS = {"high", "xhigh", "max", "ultra"}


class EvalError(ValueError):
    """An experiment refused an unsafe or ambiguous operation."""


def slug(value, label="id"):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise EvalError(f"Invalid {label}: use a short safe slug")
    return value


def positive(value, label, maximum=1000):
    if type(value) is not int or not 1 <= value <= maximum:
        raise EvalError(f"{label} must be an integer from 1 to {maximum}")
    return value


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvalError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(EvalError("Nonfinite JSON number")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvalError(f"Cannot read JSON {path}: {error}") from None


def _safe(root, relative, *, file=False):
    """Reject traversal and symlinks, including ancestors inside root."""
    root = Path(root)
    if not isinstance(relative, (str, Path)):
        raise EvalError("Paths must be relative text")
    # Path normalizes lexical dots/repeated separators; reject aliases first.
    if any(component in {"", ".", ".."} for component in str(relative).split("/")):
        raise EvalError("Path aliases/traversal are refused")
    part = Path(relative)
    if part.is_absolute() or not part.parts or any(p in {"..", "."} for p in part.parts):
        raise EvalError("Paths must be relative and confined to their root")
    current = root
    for component in part.parts:
        current = current / component
        if current.is_symlink():
            raise EvalError(f"Symlink path refused: {current}")
    if not current.resolve().is_relative_to(root.resolve()):
        raise EvalError("Path escapes root")
    if file and not current.is_file():
        raise EvalError(f"Expected regular file: {current}")
    return current


def _root(vault, create=False):
    vault = Path(vault).expanduser().absolute()
    if not vault.is_dir() or vault.is_symlink():
        raise EvalError("Vault must be an existing real directory")
    # OS prefixes such as macOS /var may be aliases. Confine writes to the
    # canonical real vault, while rejecting vault/drafts/experiment symlinks.
    vault = vault.resolve()
    root = _safe(vault, "drafts/model-eval")
    if create:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def _experiment(vault, identifier):
    root = _root(vault)
    path = _safe(root, slug(identifier))
    if not path.is_dir():
        raise EvalError("Experiment not found")
    return path


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _write(path, value, *, text=False):
    path = Path(path)
    if path.is_symlink():
        raise EvalError("Refusing symlink output")
    data = value.encode("utf-8") if text else _json_bytes(value)
    fd, temporary = tempfile.mkstemp(prefix=".eval-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


CONTEXT_FILES = ("AGENTS.md", "CLAUDE.md", "harness/contract.md", "vault-heuristics.md")
EXECUTOR_FILES = ("delegate.py", "thinker_delegation/adapters.py", "thinker_delegation/runtime.py",
                  "thinker_delegation/routing.py", "model-eval.py", "thinker_model_eval/core.py",
                  "thinker_model_eval/report.py", "thinker_model_eval/workflows.py", "thinker_model_eval/judging.py")


def _environment_hashes(vault):
    scripts = Path(__file__).resolve().parents[1]
    def snapshot(root, names):
        values = {}
        for name in names:
            path = _safe(root, name)
            if path.exists() and not path.is_file():
                raise EvalError(f"Environment input must be a regular file: {path}")
            values[name] = _digest(path.read_bytes()) if path.is_file() else None
        return values
    return {"context_hashes": snapshot(Path(vault).absolute(), CONTEXT_FILES),
            "executor_hashes": snapshot(scripts, EXECUTOR_FILES)}


def validate_suite(suite):
    suite = Path(suite).expanduser().absolute()
    if suite.is_dir():
        if suite.is_symlink():
            raise EvalError("Suite root is a symlink")
        suite = suite / "suite.json"
    root = suite.parent
    if root.is_symlink():
        raise EvalError("Suite root is a symlink")
    root = root.resolve()
    suite = _safe(root, suite.name, file=True)
    data = read_json(suite)
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise EvalError("Suite schema_version must be 1")
    slug(data.get("id"), "suite id")
    _text(data.get("title"), "suite title")
    prompt_ceiling = positive(data.get("max_prompt_bytes", 6000), "suite max_prompt_bytes", 30000)
    output_ceiling = positive(data.get("max_output_words", 700), "suite max_output_words", 4000)
    cases = data.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
        raise EvalError("Suite must contain 1 to 200 cases")
    seen, files = set(), {"suite.json": suite.read_bytes()}
    prompt_files, rubric_files, workflow_files = set(), set(), set()
    exposed_workflow_files, trusted_workflow_files = set(), set()
    suite_identity = suite.stat().st_dev, suite.stat().st_ino
    for case in cases:
        if not isinstance(case, dict):
            raise EvalError("Each case must be an object")
        identifier = slug(case.get("id"), "case id")
        if identifier in seen:
            raise EvalError("Duplicate case id")
        seen.add(identifier)
        if not isinstance(case.get("family"), str) or case["family"] not in FAMILIES or not isinstance(case.get("split"), str) or case["split"] not in {"development", "holdout"}:
            raise EvalError("Case family/split is invalid")
        case_prompt_ceiling = positive(case.get("max_prompt_bytes", prompt_ceiling), "case max_prompt_bytes", prompt_ceiling)
        if "word_limit_hard" in case and type(case["word_limit_hard"]) is not bool:
            raise EvalError("word_limit_hard must be boolean")
        if case.get("deadline_seconds") is not None:
            _number(case["deadline_seconds"], "case deadline_seconds", maximum=86400)
        positive(case.get("max_words", 450), "max_words", output_ceiling if "max_output_words" in data else
                 (700 if case["family"] == "code" else 450))
        for field in ("prompt", "rubric"):
            source = _safe(root, case.get(field, ""), file=True)
            if source == suite:
                raise EvalError("Prompt, rubric and suite must be separate files")
            identity = source.stat().st_dev, source.stat().st_ino
            if identity == suite_identity:
                raise EvalError("Prompt/rubric may not alias suite manifest, including hardlinks")
            (prompt_files if field == "prompt" else rubric_files).add(identity)
            files[case[field]] = source.read_bytes()
        prompt = files[case["prompt"]]
        try:
            text = prompt.decode("utf-8")
        except UnicodeError:
            raise EvalError("Prompt must be UTF-8") from None
        if not text.strip() or len(prompt) > case_prompt_ceiling:
            raise EvalError(f"Prompt must be nonempty and at most {case_prompt_ceiling} UTF-8 bytes")
        rubric = read_json(_safe(root, case["rubric"], file=True))
        validate_rubric(rubric)
        if case.get("workflow"):
            from . import workflows
            for name, content in workflows.validate_workflow(root, case).items():
                source = _safe(root, name, file=True)
                identity = source.stat().st_dev, source.stat().st_ino
                workflow_files.add(identity)
                if identity in rubric_files or identity == suite_identity:
                    raise EvalError("Workflow context overlaps hidden rubric/suite")
                if not isinstance(content, bytes) or content != source.read_bytes():
                    raise EvalError("Workflow source receipt does not match input file")
                files[name] = content
            spec_path = _safe(root, case["workflow"], file=True)
            spec = read_json(spec_path)
            trusted_workflow_files.add((spec_path.stat().st_dev, spec_path.stat().st_ino))
            for entry in spec["workspace"]:
                source = _safe(root, entry["source"], file=True)
                exposed_workflow_files.add((source.stat().st_dev, source.stat().st_ino))
            for check in spec["checks"]:
                if check["kind"] == "python-unittest":
                    source = _safe(root, check["source"], file=True)
                    trusted_workflow_files.add((source.stat().st_dev, source.stat().st_ino))
    if prompt_files & rubric_files:
        raise EvalError("Prompt and hidden rubric overlap, including hardlinks/cross-case aliases")
    if workflow_files & rubric_files:
        raise EvalError("Workflow fixture/check overlaps hidden rubric")
    if (exposed_workflow_files | prompt_files) & (trusted_workflow_files | rubric_files | {suite_identity}):
        raise EvalError("Candidate workflow input aliases hidden expectations/tests/rubric")
    return data, files


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise EvalError(f"{label} requires nonempty text")
    return value


def validate_rubric(rubric):
    if not isinstance(rubric, dict) or not isinstance(rubric.get("criteria"), list) or not rubric["criteria"]:
        raise EvalError("Rubric requires criteria")
    seen = set()
    for criterion in rubric["criteria"]:
        if not isinstance(criterion, dict):
            raise EvalError("Invalid rubric criterion")
        identifier = slug(criterion.get("id"), "criterion id")
        if identifier in seen or type(criterion.get("critical")) is not bool:
            raise EvalError("Duplicate criterion or invalid critical flag")
        seen.add(identifier)
        _text(criterion.get("description"), "criterion description")
        if criterion.get("severity", "unknown") not in {"critical", "material", "minor", "unknown"}:
            raise EvalError("Invalid frozen criterion severity")
        if criterion.get("dimension", "unknown") not in {"factual", "omission", "style", "size", "scope", "other", "unknown"}:
            raise EvalError("Invalid frozen criterion dimension")
    if not isinstance(rubric.get("reference_notes"), str):
        raise EvalError("Rubric reference_notes must be text")


def validate_profiles(profiles, *, minimum_high=True):
    from thinker_delegation import adapters
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 32:
        raise EvalError("Select 1 to 32 profiles")
    result, seen = [], set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise EvalError("Profiles must be objects")
        identifier = slug(profile.get("id"), "profile id")
        if identifier in seen:
            raise EvalError("Duplicate profile id")
        seen.add(identifier)
        effort = profile.get("effort")
        if not isinstance(effort, str) or effort not in adapters.EFFORTS or (minimum_high and effort not in HIGH_EFFORTS):
            raise EvalError("New evaluations require explicit effort high or above")
        model = profile.get("model", identifier)
        _text(model, "requested model")
        try:
            selected = adapters.resolve_profile(explicit=model, provider=profile.get("provider"), effort=effort)
        except adapters.AdapterError as error:
            if effort == "ultra" and (profile.get("provider") == "claude" or model in adapters.PROFILES and adapters.PROFILES[model][0] == "claude"):
                selected = adapters.resolve_profile(explicit=model, provider=profile.get("provider"), effort="high")
                selected["effort"] = effort
                availability = {"interface": "incompatible", "model_access": "unknown", "effort_support": "incompatible",
                                "reason": str(error), "observed_at": _now(), "source": "executor validation"}
            else:
                raise EvalError(str(error)) from None
        else:
            availability = profile.get("availability", {"interface": "unknown", "model_access": "unknown",
                                                        "effort_support": "unknown", "reason": "Not probed", "observed_at": _now(),
                                                        "source": "not observed"})
        if not isinstance(availability, dict) or not isinstance(availability.get("interface"), str) or availability["interface"] not in {"ready", "unknown", "unavailable", "incompatible"}:
            raise EvalError("Availability requires an explicit interface observation")
        availability = dict(availability)
        if not isinstance(availability.get("model_access", "unknown"), str) or availability.get("model_access", "unknown") not in {"unknown", "confirmed", "unavailable"}:
            raise EvalError("Invalid model access observation")
        availability.setdefault("model_access", "unknown")
        availability.setdefault("effort_support", "unknown")
        if not isinstance(availability["effort_support"], str) or availability["effort_support"] not in {"unknown", "confirmed", "incompatible"}:
            raise EvalError("Invalid effort support observation")
        _text(availability.get("reason"), "availability reason")
        _text(availability.get("observed_at"), "availability observed_at")
        eligible = availability["interface"] in {"ready", "unknown"} and availability["model_access"] != "unavailable" and availability["effort_support"] != "incompatible"
        result.append({"id": identifier, **{k: selected[k] for k in ("provider", "model", "effort")},
                       "availability": availability, "eligible": eligible, "effort_confirmed": None})
    return result


def inventory(vault, profiles=None, *, doctor=False, transport=None):
    """Configured aliases are discovered dynamically; probes never confirm model access."""
    from thinker_delegation import adapters
    configured = {name: {"id": name, "effort": "high"} for name in sorted(adapters.PROFILES)}
    for profile in profiles or []:
        if not isinstance(profile, dict):
            raise EvalError("Explicit inventory profiles must be objects")
        configured[slug(profile.get("id"), "profile id")] = profile
    result = validate_profiles(list(configured.values()))
    if doctor:
        transport = transport or DelegateTransport(vault, "eval-inventory")
        observations = transport.call("doctor", "--all-profiles").get("providers")
        if not isinstance(observations, list):
            raise EvalError("Malformed doctor observations")
        indexed = {p.get("profile"): p for p in observations if isinstance(p, dict)}
        for profile in result:
            observation = indexed.get(profile["id"])
            if observation is None or profile["id"] not in adapters.PROFILES:
                continue
            if profile["availability"]["effort_support"] == "incompatible":
                continue
            configured_profile = adapters.resolve_profile(explicit=profile["id"], effort=profile["effort"])
            if any(configured_profile[k] != profile[k] for k in ("provider", "model")):
                continue
            if observation.get("ready") is True and any(observation.get(k) != profile[field]
                                                        for k, field in (("provider", "provider"), ("model_requested", "model"))):
                continue
            profile["availability"] = {"interface": "ready" if observation.get("ready") is True else "unavailable",
                                       "model_access": "unknown", "effort_support": "unknown", "observed_at": _now(),
                                       "reason": observation.get("error") or "CLI interface checked; model/effort access not tested",
                                       "source": "delegate.py doctor", "cli_version": observation.get("cli_version")}
            profile["eligible"] = observation.get("ready") is True
    return {"profiles": result, "eligible_profiles": sum(p["eligible"] for p in result),
            "limitation": "CLI readiness does not establish access, requested effort support or served identity"}


def validate_policy(policy):
    if policy is None:
        policy = {}
    if not isinstance(policy, dict):
        raise EvalError("Evaluation policy must be an object")
    policy = dict(policy)
    if not isinstance(policy.get("minimum_requested_effort", "high"), str) or policy.get("minimum_requested_effort", "high") not in HIGH_EFFORTS:
        raise EvalError("Policy cannot lower minimum requested effort below high")
    for flag in ("allow_silent_downgrade", "allow_silent_substitution", "allow_automatic_retry"):
        if policy.get(flag, False) is not False:
            raise EvalError(f"Evaluation policy requires {flag}=false")
        policy[flag] = False
    policy.setdefault("minimum_requested_effort", "high")
    comparison = policy.get("comparison_policy")
    if comparison is not None:
        if not isinstance(comparison, dict):
            raise EvalError("comparison_policy must be an object")
        allowed_margins = {"quality_margin", "execution_seconds_margin", "personal_time_margin_minutes"}
        if any(name not in allowed_margins for name in comparison):
            raise EvalError("Unknown practical comparison margin")
        for name, value in comparison.items():
            _number(value, name, maximum=1000000)
    weights = policy.get("action_weights")
    if weights is not None:
        if not isinstance(weights, dict) or any(name not in FAMILIES for name in weights):
            raise EvalError("action_weights must map known families")
        for value in weights.values():
            _number(value, "action weight", maximum=1000000)
        if not any(value > 0 for value in weights.values()):
            raise EvalError("Declared action_weights require at least one positive weight")
    if policy.get("deadline_seconds") is not None:
        _number(policy["deadline_seconds"], "deadline_seconds", maximum=86400)
    return policy


def plan(vault, suite, profiles, case_ids, *, identifier, session=None, mode="candidate",
         repeats=1, max_calls=12, timeout=180, concurrency=2, all_profiles=False, doctor=False, policy=None):
    """Freeze selected input bytes without consulting a provider or submitting work."""
    _root(vault)
    identifier = slug(identifier)
    positive(repeats, "repeats", 20)
    positive(max_calls, "max_calls", 1000)
    positive(timeout, "timeout", 3600)
    positive(concurrency, "concurrency", 8)
    if mode not in {"screening", "candidate", "regression"}:
        raise EvalError("Invalid evaluation mode")
    if session is None:
        session = "eval-" + uuid.uuid4().hex
    if not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", session):
        raise EvalError("Invalid delegation session")
    data, files = validate_suite(suite)
    if all_profiles:
        profiles = inventory(vault, profiles, doctor=doctor)["profiles"]
    elif doctor:
        selected_ids = {p.get("id") for p in profiles}
        profiles = [p for p in inventory(vault, profiles, doctor=True)["profiles"] if p["id"] in selected_ids]
    else:
        profiles = validate_profiles(profiles)
    policy = validate_policy(policy)
    ranks = {name: number for number, name in enumerate(("high", "xhigh", "max", "ultra"))}
    if any(ranks[p["effort"]] < ranks[policy["minimum_requested_effort"]] for p in profiles):
        raise EvalError("Candidate effort is below the frozen policy minimum")
    if not isinstance(case_ids, list) or not case_ids or len(set(case_ids)) != len(case_ids):
        raise EvalError("Select unique explicit case IDs; no implicit holdout selection")
    indexed = {case["id"]: case for case in data["cases"]}
    if any(identifier not in indexed for identifier in case_ids):
        raise EvalError("Unknown selected case")
    selected = [dict(indexed[identifier]) for identifier in case_ids]
    total = len(selected) * sum(profile["eligible"] for profile in profiles) * repeats
    if total > max_calls:
        raise EvalError(f"Planned calls ({total}) exceed max_calls ({max_calls})")
    copied = {"inputs/suite.json": files["suite.json"]}
    for case in selected:
        case.setdefault("max_words", 450)
        case["execution_mode"] = "host-managed" if case.get("workflow") else "text"
        case.setdefault("max_prompt_bytes", data.get("max_prompt_bytes", 6000))
        rubric = json.loads(files[case["rubric"]].decode("utf-8"))
        case["rubric_version"] = _digest(files[case["rubric"]])
        case["criteria_metadata"] = [{"id": c["id"], "critical": c["critical"], "severity": c.get("severity", "unknown"),
                                      "dimension": c.get("dimension", "unknown")} for c in rubric["criteria"]]
        for field in ("prompt", "rubric"):
            relative = "inputs/" + case[field]
            copied[relative] = files[case[field]]
            case[field] = relative
        if case.get("workflow"):
            # Freeze the complete selected workflow, including trusted checks.
            from . import workflows
            suite_root = Path(suite) if Path(suite).is_dir() else Path(suite).parent
            for name, content in workflows.validate_workflow(suite_root.resolve(), case | {"prompt": case["prompt"][7:], "rubric": case["rubric"][7:]}).items():
                copied["inputs/" + name] = content
            case["workflow"] = "inputs/" + case["workflow"]
    manifest = {"schema_version": 1, "id": identifier, "created_at": _now(), "suite_id": data["id"],
                "session": session, "mode": mode, "profiles": profiles, "cases": selected,
                "repeats": repeats, "max_calls": max_calls, "timeout": timeout, "concurrency": concurrency,
                "hashes": {name: _digest(content) for name, content in copied.items()},
                "environment": {"python": platform.python_version(), "platform": platform.platform(),
                                "execution": "delegate.py only", "screening": "bounded text; not end-to-end qualification"},
                "quality_floor": 3, "minimum_trials": 3, "assessment_schema_version": 2,
                "evaluation_policy": policy, "planned_calls": total,
                "excluded_profiles": [p["id"] for p in profiles if not p["eligible"]]}
    for name in ("comparison_policy", "action_weights", "deadline_seconds"):
        if name in policy:
            manifest[name] = policy[name]
    manifest["environment"].update(_environment_hashes(vault))
    # Historical evidence survives routine changes to live harness/context.
    for kind, base in (("context_hashes", Path(vault).resolve()),
                       ("executor_hashes", Path(__file__).resolve().parents[1])):
        for name, digest in manifest["environment"][kind].items():
            if digest is not None:
                content = _safe(base, name, file=True).read_bytes()
                if _digest(content) != digest:
                    raise EvalError("Execution environment changed while freezing")
                relative = "inputs/environment/" + kind + "/" + name
                copied[relative] = content
                manifest["hashes"][relative] = digest
    trials = []
    for case in selected:
        for profile in profiles:
            for repeat in range(1, repeats + 1):
                trials.append({"id": f"t{len(trials)+1:04d}", "blind_id": "b-" + uuid.uuid4().hex,
                               "case_id": case["id"], "family": case["family"], "profile_id": profile["id"],
                               "repeat": repeat, "status": "planned" if profile["eligible"] else "unavailable", "job_id": None, "response": None,
                               "execution_seconds": None, "queue_seconds": None, "model_reported": None,
                               "usage": None, "cost_estimate": None,
                               "checks": {"nonempty": False, "word_limit": False},
                               "trajectory": {"status": "unknown", "violations": []}, "limitations": [],
                               "failure_kind": None if profile["eligible"] else "unavailable"})
    root = _root(vault, create=True)
    target = _safe(root, identifier)
    if target.exists():
        raise EvalError("Experiment ID already exists; frozen plans are immutable")
    temporary = Path(tempfile.mkdtemp(prefix=".plan-", dir=root))
    try:
        for name, content in copied.items():
            output = _safe(temporary, name)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        _write(temporary / "manifest.json", manifest)
        _write(temporary / "manifest.sha256", _digest((temporary / "manifest.json").read_bytes()) + "\n", text=True)
        for name, value in (("trials.json", trials), ("grades.json", []), ("feedback.json", []), ("trajectory.json", []), ("pairwise-feedback.json", []), ("reconciliations.json", [])):
            _write(temporary / name, value)
        os.rename(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {"id": identifier, "path": str(target), "session": session, "planned_calls": total,
            "inventory_trials": len(trials), "excluded_profiles": manifest["excluded_profiles"],
            "message": "Frozen evaluation; no model calls made, unavailable profiles retained without scores"}


def verify(vault, identifier):
    path = _experiment(vault, identifier)
    manifest_path = _safe(path, "manifest.json", file=True)
    expected = _safe(path, "manifest.sha256", file=True).read_text(encoding="utf-8").strip()
    if _digest(manifest_path.read_bytes()) != expected:
        raise EvalError("Frozen manifest changed")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("id") != identifier or manifest.get("schema_version") != 1:
        raise EvalError("Invalid frozen manifest")
    for name, expected_hash in manifest.get("hashes", {}).items():
        if _digest(_safe(path, name, file=True).read_bytes()) != expected_hash:
            raise EvalError(f"Frozen input changed: {name}")
    return manifest


def _verify_environment(vault, manifest):
    actual = _environment_hashes(vault)
    for name in ("context_hashes", "executor_hashes"):
        if manifest.get("environment", {}).get(name) != actual[name]:
            raise EvalError(f"Live execution environment changed: {name}; create a reconciled new plan")


@contextmanager
def _locked(vault, identifier):
    path = _experiment(vault, identifier)
    lock = _safe(path, ".lock")
    with lock.open("a") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield path, verify(vault, identifier)


def _load_trials(path, manifest):
    path = Path(path).resolve()
    trials = read_json(_safe(path, "trials.json", file=True))
    expected = [(case["id"], profile["id"], repeat, case["family"])
                for case in manifest["cases"] for profile in manifest["profiles"]
                for repeat in range(1, manifest["repeats"] + 1)]
    if not isinstance(trials, list) or len(trials) != len(expected):
        raise EvalError("Trials no longer match frozen plan")
    seen_blind, seen_jobs = set(), set()
    cases = {case["id"]: case for case in manifest["cases"]}
    for number, (trial, planned) in enumerate(zip(trials, expected), 1):
        if (not isinstance(trial, dict) or trial.get("id") != f"t{number:04d}"
                or tuple(trial.get(k) for k in ("case_id", "profile_id", "repeat", "family")) != planned
                or type(trial.get("repeat")) is not int or not isinstance(trial.get("status"), str) or trial["status"] not in STATES):
            raise EvalError("Invalid trial record")
        blind_id = slug(trial.get("blind_id"), "blind id")
        if blind_id in seen_blind:
            raise EvalError("Duplicate blind id")
        seen_blind.add(blind_id)
        job = trial.get("job_id")
        if job is not None:
            try:
                if str(uuid.UUID(job)) != job:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise EvalError("Invalid delegate job id") from None
            if job in seen_jobs:
                raise EvalError("Duplicate delegate job id")
            seen_jobs.add(job)
        if trial["status"] == "planned" and (job is not None or trial.get("response") is not None or trial.get("acknowledged")):
            raise EvalError("Planned trial contains execution evidence; reconcile instead of resubmitting")
        if "host_result" in trial and type(trial["host_result"]) is not bool:
            raise EvalError("host_result must be boolean")
        if trial["status"] in {"queued", "running", "completed"} and not job and not trial.get("host_result"):
            raise EvalError("Executed trial missing job id")
        response = trial.get("response")
        if response is not None and not isinstance(response, str):
            raise EvalError("Trial response must be text or null")
        checks = {"nonempty": bool(response and response.strip()),
                  "word_limit": isinstance(response, str) and len(response.split()) <= cases[trial["case_id"]]["max_words"]}
        if not isinstance(trial.get("checks"), dict) or any(type(trial["checks"].get(k)) is not bool or trial["checks"][k] != v
                                                           for k, v in checks.items()):
            raise EvalError("Trial checks disagree with stored response")
        if trial.get("host_result"):
            case = cases[trial["case_id"]]
            if not case.get("workflow") or case.get("execution_mode", "host-managed") != "host-managed":
                raise EvalError("Text trials cannot claim host workflow execution")
            from . import workflows
            try:
                receipt = workflows.load_receipt(path, trial["id"])
            except (ValueError, OSError) as error:
                raise EvalError("Invalid host preparation receipt: " + str(error)) from None
            if (receipt.get("trial_id") != trial["id"] or receipt.get("case_id") != case["id"]
                    or receipt.get("spec_hash") != manifest["hashes"].get(case["workflow"])):
                raise EvalError("Host execution receipt does not match frozen workflow/trial")
            if not isinstance(trial.get("final_state_checks"), dict):
                raise EvalError("Host workflow missing final state validation")
            artifacts = trial.get("artifacts", [])
            if not isinstance(artifacts, list):
                raise EvalError("Host artifacts must be a receipt array")
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    raise EvalError("Invalid artifact receipt")
                if not isinstance(artifact.get("path"), str) or not artifact["path"].startswith("workflow-artifacts/" + trial["id"] + "/"):
                    raise EvalError("Artifact receipt does not belong to this host trial")
                content = _safe(path, artifact.get("path"), file=True).read_bytes()
                if _digest(content) != artifact.get("sha256") or len(content) != artifact.get("bytes"):
                    raise EvalError("Host artifact changed after final state audit")
        if trial["status"] == "completed" and not checks["nonempty"] and not trial.get("host_result"):
            raise EvalError("Completed trial has no response artifact")
    return trials


def artifact_texts(path, trial):
    """Export intact bounded UTF-8 deliveries, without trial/model labels."""
    texts, total = [], 0
    prefix = "workflow-artifacts/" + trial["id"] + "/"
    for artifact in trial.get("artifacts", []):
        if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str) or not artifact["path"].startswith(prefix):
            raise EvalError("Artifact receipt does not belong to the selected trial")
        source = _safe(path, artifact["path"], file=True)
        if source.stat().st_size > 2 * 1024 * 1024:
            raise EvalError("Captured artifact exceeds safe receipt size")
        content = source.read_bytes()
        if _digest(content) != artifact.get("sha256") or len(content) != artifact.get("bytes"):
            raise EvalError("Captured artifact changed before semantic grading")
        text, limitations = None, []
        if len(content) > 256 * 1024 or total + len(content) > 512 * 1024:
            limitations.append("Artifact exceeds literal text packet limit; omitted intact, never truncated")
        else:
            try:
                text = content.decode("utf-8")
                if "\x00" in text:
                    text = None
                    limitations.append("Binary artifact requires separate visual/content review")
                else:
                    total += len(content)
            except UnicodeError:
                limitations.append("Non-UTF-8 artifact requires separate visual/content review")
        texts.append({"name": artifact["path"][len(prefix):], "text": text, "sha256": artifact["sha256"], "limitations": limitations})
    return texts


def _evidence_texts(path, trials):
    return {trial["id"]: [text for text in [trial.get("response"), *[a["text"] for a in artifact_texts(path, trial)]]
                           if isinstance(text, str)] for trial in trials}


class DelegateTransport:
    """All provider operations remain in the existing delegation executable."""
    def __init__(self, vault, session):
        self.base = [sys.executable, "-B", str(Path(__file__).resolve().parents[1] / "delegate.py"),
                     "--vault", str(Path(vault).resolve()), "--session", session, "--json"]

    def call(self, command, *arguments):
        try:
            result = subprocess.run([*self.base, command, *arguments], capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise EvalError(f"Delegation transport interrupted: {error}") from None
        if result.returncode:
            raise EvalError(f"Delegation {command} refused: {result.stderr.strip() or result.stdout.strip()}")
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise EvalError("Delegation returned invalid JSON") from None
        if not isinstance(data, dict) or data.get("error"):
            raise EvalError("Delegation returned an error")
        return data


def _seconds(start, finish):
    if not isinstance(start, str) or not isinstance(finish, str):
        return None
    try:
        delta = (dt.datetime.fromisoformat(finish.replace("Z", "+00:00")) -
                 dt.datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
        return delta if math.isfinite(delta) and delta >= 0 else None
    except (ValueError, TypeError):
        return None


def _collect(path, manifest, trials, transport):
    cases = {case["id"]: case for case in manifest["cases"]}
    profiles = {profile["id"]: profile for profile in manifest["profiles"]}
    for trial in trials:
        if not trial.get("job_id") or trial["status"] not in ACTIVE | {"completed"} | FAILURES:
            continue
        if trial["status"] in {"completed"} | FAILURES and trial.get("acknowledged"):
            continue
        try:
            job = transport.call("result", trial["job_id"])
            if job.get("id") != trial["job_id"] or job.get("session") != manifest["session"]:
                raise EvalError("Delegate result does not belong to trial/session")
            profile = profiles[trial["profile_id"]]
            if any((job.get("profile") or {}).get(k) != profile[k] for k in ("model", "provider", "effort")):
                raise EvalError("Delegate result requested profile differs from frozen trial")
            state = job.get("state")
            if state not in STATES - {"submitting", "planned"}:
                raise EvalError("Unknown delegate result state")
            candidate = dict(trial)
            candidate["execution_profile"] = job.get("profile")
            candidate["transport"] = {"success": job.get("transport_success"), "validation": job.get("validation"),
                                  "stale": job.get("stale"), "error_code": job.get("error_code")}
            if state == "completed" and (type(job.get("transport_success")) is not bool or job.get("validation") is None):
                raise EvalError("Completed job lacks observable transport/validation; success remains unresolved")
            if state == "completed" and (job.get("transport_success") is False or
                                         job.get("validation") != "valid" or job.get("stale") is True):
                state = "failed"
                candidate["error"] = "Delegate completed with invalid transport/validation or stale context"
            candidate["status"] = state
            candidate["execution_seconds"] = _seconds(job.get("started_at"), job.get("finished_at"))
            candidate["queue_seconds"] = _seconds(job.get("created_at"), job.get("started_at"))
            result = job.get("result") or {}
            if not isinstance(result, dict):
                raise EvalError("Malformed delegate result")
            response = result.get("text")
            if response is not None and not isinstance(response, str):
                raise EvalError("Malformed response text")
            if state == "completed" and not (response and response.strip()):
                raise EvalError("Completed delegate job has no response artifact")
            candidate["response"] = response
            candidate["model_reported"] = result.get("model_reported") if isinstance(result.get("model_reported"), str) else None
            candidate["model_reported_source"] = result.get("model_reported_source")
            candidate["usage"] = result.get("usage")
            candidate["checks"] = {"nonempty": bool(response and response.strip()),
                               "word_limit": isinstance(response, str) and len(response.split()) <= cases[trial["case_id"]]["max_words"]}
            candidate["limitations"] = list(result.get("limitations", [])) if isinstance(result.get("limitations", []), list) else []
            candidate["limitations"].append("Served identity is unknown unless emitted by provider; text screening only")
            cost = result.get("cost_estimate_usd")
            candidate["cost_estimate"] = ({"provider": profiles[trial["profile_id"]]["provider"], "currency": "USD",
                                       "amount": cost, "provenance": result["cost_source"]}
                                      if type(cost) in (int, float) and 0 <= cost < 100000 and math.isfinite(cost)
                                      and isinstance(result.get("cost_source"), str) and result["cost_source"].strip() else None)
            if state in FAILURES:
                candidate["error"] = candidate.get("error") or job.get("error") or state
                candidate["failure_kind"] = "timeout" if state == "timed_out" else "infrastructure"
            # A malformed result never promotes the old queued/running trial.
            trial.update(candidate)
            _write(path / "trials.json", trials)
            if state in {"completed"} | FAILURES:
                transport.call("ack", trial["job_id"])
                trial["acknowledged"] = True
            trial.pop("collection_error", None)
            _write(path / "trials.json", trials)
        except EvalError as error:
            # Preserve/drain every other already submitted job, never retry a model.
            trial["collection_error"] = str(error)
            _write(path / "trials.json", trials)
    return trials


def _progress(vault, manifest, trials):
    counts = {state: sum(t["status"] == state for t in trials) for state in sorted(STATES)}
    blocked = any(t["status"] in FAILURES | {"submitting", "preparing", "finishing"} or t.get("collection_error") for t in trials)
    return {"id": manifest["id"], "session": manifest["session"], "counts": counts,
            "planned_calls": manifest.get("planned_calls", len(trials)), "inventory_trials": len(trials),
            "remaining": counts["planned"], "blocked": blocked,
            "host_workflows": [t["id"] for t in trials if t["status"] == "prepared"],
            "reconciliation_trials": [t["id"] for t in trials if t["status"] in {"submitting", "preparing", "finishing"}],
            "board_command": [sys.executable, "harness/scripts/delegate.py", "--vault", str(Path(vault).resolve()),
                              "--session", manifest["session"], "board"],
            "next_command": [sys.executable, "harness/scripts/model-eval.py", "--vault", str(Path(vault).resolve()),
                             "collect" if any(t["status"] in ACTIVE for t in trials) else "run", "--id", manifest["id"]],
            "message": "No retries. Use reconcile with explicit trial/action/reason for ambiguous submission or stranded workflow; failures stop new calls." if blocked
                       else "Repeat collect/run to advance bounded work; no background evaluation service"}


def collect(vault, identifier, transport=None):
    with _locked(vault, identifier) as (path, manifest):
        trials = _load_trials(path, manifest)
        transport = transport or DelegateTransport(vault, manifest["session"])
        _collect(path, manifest, trials, transport)
        return _progress(vault, manifest, trials)


def _reconcile_job(manifest, trial, job, job_id):
    """Validate an explicit join before it can acquire a result or acknowledgement."""
    profile = next(p for p in manifest["profiles"] if p["id"] == trial["profile_id"])
    if not isinstance(job, dict) or job.get("id") != job_id or job.get("session") != manifest["session"]:
        raise EvalError("Reconciliation job/session does not match the frozen trial")
    if not isinstance(job.get("profile"), dict) or any(job["profile"].get(k) != profile[k] for k in ("provider", "model", "effort")):
        raise EvalError("Reconciliation requested profile does not match the frozen trial")
    expected_reason = f"Frozen model evaluation {manifest['id']} trial {trial['id']}; no retry"
    if job.get("reason") != expected_reason:
        raise EvalError("Reconciliation requires the exact supervisor-recorded experiment/trial reason")
    state = job.get("state")
    if not isinstance(state, str) or state not in {"queued", "running", "completed"} | FAILURES:
        raise EvalError("Reconciliation job state is unknown")
    result = job.get("result")
    if result is not None and (not isinstance(result, dict) or result.get("text") is not None and not isinstance(result["text"], str)):
        raise EvalError("Reconciliation result payload is malformed")
    response = result.get("text") if isinstance(result, dict) else None
    if state == "completed" and (job.get("transport_success") is not True or job.get("validation") != "valid"
                                  or job.get("stale") is True or not isinstance(response, str) or not response.strip()):
        raise EvalError("Completed reconciliation job lacks a validated nonempty usable result")
    return state


def reconcile(vault, identifier, trial_id, action, reason, *, job_id=None, transport=None):
    """Close a stranded trial or explicitly bind an already submitted job; never retry."""
    _text(reason, "reconciliation reason")
    if action not in {"bind", "abandon"}:
        raise EvalError("Reconciliation action must be bind or abandon")
    with _locked(vault, identifier) as (path, manifest):
        trials = _load_trials(path, manifest)
        trial = next((t for t in trials if t["id"] == trial_id), None)
        if trial is None or trial["status"] not in {"submitting", "preparing", "prepared", "finishing"}:
            raise EvalError("Reconciliation requires an ambiguous submission or stranded host workflow")
        previous = trial["status"]
        if action == "bind":
            if previous != "submitting" or next(c for c in manifest["cases"] if c["id"] == trial["case_id"]).get("workflow"):
                raise EvalError("Only an ambiguous text submission can bind a delegate job")
            known = trial.get("submitted_job_id")
            if known is not None and job_id is not None and known != job_id:
                raise EvalError("Explicit job differs from the known submission receipt")
            job_id = known or job_id
            try:
                if not isinstance(job_id, str) or str(uuid.UUID(job_id)) != job_id:
                    raise ValueError()
            except (ValueError, TypeError):
                raise EvalError("Bind requires a known or explicitly identified full delegate job UUID") from None
            if any(t is not trial and t.get("job_id") == job_id for t in trials):
                raise EvalError("Delegate job is already bound to another trial")
            transport = transport or DelegateTransport(vault, manifest["session"])
            result = transport.call("result", job_id)
            state = _reconcile_job(manifest, trial, result, job_id)
        else:
            if job_id is not None:
                raise EvalError("Abandon does not bind or acknowledge a job")
            state = "interrupted"
        # Current evidence is recorded, but executor drift never authorizes new
        # submissions or finishing a partial capture with different checks.
        frozen = {name: manifest["environment"].get(name) for name in ("context_hashes", "executor_hashes")}
        try:
            current = _environment_hashes(vault)
            drift, observation_error = current != frozen, None
        except (ValueError, OSError) as error:
            current, drift, observation_error = None, None, str(error)
        audit_path = _safe(path, "reconciliations.json")
        history = read_json(audit_path) if audit_path.exists() else []
        if not isinstance(history, list):
            raise EvalError("Invalid reconciliation audit ledger")
        event = {"id": "reconcile-" + uuid.uuid4().hex, "trial_id": trial_id, "action": action, "reason": reason,
                 "created_at": _now(), "previous_status": previous, "result_status": state,
                 "job_id": job_id if action == "bind" else trial.get("job_id") or trial.get("submitted_job_id"),
                 "frozen_environment_hashes": frozen, "observed_environment_hashes": current,
                 "environment_drift": drift, "environment_observation_error": observation_error}
        _write(audit_path, history + [event])
        trial["reconciliation_id"] = event["id"]
        if action == "bind":
            trial.update(job_id=job_id, submitted_job_id=job_id, status=state)
            trial.pop("submission_error", None)
            trial.pop("collection_error", None)
            # Persist the join before collection. If collection is interrupted,
            # collect resumes this same job; it can never resubmit it.
            trial["status"] = "queued" if state == "completed" else state
            _write(path / "trials.json", trials)
            _collect(path, manifest, trials, transport)
        else:
            trial.update(status="interrupted", failure_kind="operational", error="Explicitly abandoned: " + reason,
                         abandonment_reason=reason, unresolved_delegate_job=trial.get("job_id") or trial.get("submitted_job_id"))
            trial.pop("collection_error", None)
            _write(path / "trials.json", trials)
        return {"id": identifier, "trial_id": trial_id, "action": action, "status": trial["status"],
                "audit": str(audit_path), "reconciliation_id": event["id"], "environment_drift": drift,
                "retained_workspace": (trial.get("workflow_preparation") or {}).get("workspace"),
                "retained_artifact_directory": str(_safe(path, "workflow-artifacts/" + trial_id)),
                "unresolved_delegate_job": trial.get("unresolved_delegate_job"), "model_calls": 0,
                "message": "Existing job joined and collected; no retry" if action == "bind" else
                           "Trial closed; workspace and partial captures retained. Inspect/drain any unresolved delegate job separately; use a new plan for further execution."}


def run(vault, identifier, transport=None):
    with _locked(vault, identifier) as (path, manifest):
        trials = _load_trials(path, manifest)
        _verify_environment(vault, manifest)
        transport = transport or DelegateTransport(vault, manifest["session"])
        _collect(path, manifest, trials, transport)
        status = transport.call("status")
        if status.get("enabled") is not True:
            raise EvalError("Delegation is disabled; activate explicitly for manifest session")
        if type(status.get("concurrency")) is not int or status["concurrency"] < manifest["concurrency"]:
            raise EvalError("Delegation concurrency is incompatible; no limits were changed")
        if any(t["status"] in FAILURES | {"submitting"} or t.get("collection_error") for t in trials):
            return _progress(vault, manifest, trials)
        jobs = status.get("jobs", [])
        if not isinstance(jobs, list):
            raise EvalError("Malformed delegation status jobs")
        active = sum(t["status"] in ACTIVE for t in trials)
        other = sum(j.get("state") in {"queued", "running"} and j.get("id") not in {t.get("job_id") for t in trials} for j in jobs)
        slots = max(0, manifest["concurrency"] - active - other)
        profiles = {p["id"]: p for p in manifest["profiles"]}
        cases = {c["id"]: c for c in manifest["cases"]}
        for trial in trials:
            if slots <= 0:
                break
            if trial["status"] != "planned":
                continue
            profile, case = profiles[trial["profile_id"]], cases[trial["case_id"]]
            if case.get("workflow") or profile.get("eligible") is False:
                continue
            arguments = ["--task", "review", "--model", profile["model"], "--provider", profile["provider"],
                         "--effort", profile["effort"], "--benefit", "Independent frozen bounded text evaluation sample",
                         "--independent"]
            route = transport.call("route", *arguments)
            if (route.get("routing", {}).get("action") != "delegate" or
                    any(route.get(k) != profile[k] for k in ("model", "provider", "effort"))):
                raise EvalError("Delegation route did not preserve the frozen explicit profile")
            prompt = _safe(path, case["prompt"], file=True).read_text(encoding="utf-8")
            prompt += f"\n\nOutput limit: at most {case['max_words']} words. Deliver text only; do not execute tools."
            trial["status"] = "submitting"
            verify(vault, identifier)
            _verify_environment(vault, manifest)
            _write(path / "trials.json", trials)
            try:
                job = transport.call("submit", *arguments, "--prompt", prompt, "--timeout", str(manifest["timeout"]),
                                     "--reason", f"Frozen model evaluation {manifest['id']} trial {trial['id']}; no retry")
                identifier_job = job.get("id")
                if not isinstance(identifier_job, str) or str(uuid.UUID(identifier_job)) != identifier_job:
                    raise EvalError("Submit returned no valid job ID; reconciliation required")
                trial["submitted_job_id"] = identifier_job
                _write(path / "trials.json", trials)
                if job.get("session") != manifest["session"] or job.get("state") not in {"queued", "running"} | FAILURES | {"completed"}:
                    raise EvalError("Unexpected submission result; reconciliation required")
                trial["job_id"], trial["status"] = identifier_job, job["state"]
                slots -= 1
            except (EvalError, ValueError, TypeError) as error:
                trial["submission_error"] = str(error)
                _write(path / "trials.json", trials)
                break
            _write(path / "trials.json", trials)
            if trial["status"] in FAILURES:
                break
        return _progress(vault, manifest, trials)


def blind(vault, identifier):
    with _locked(vault, identifier) as (path, manifest):
        trials = _load_trials(path, manifest)
        cases = {c["id"]: c for c in manifest["cases"]}
        packet = []
        ordering = list(trials)
        random.Random(_digest(_json_bytes(manifest))).shuffle(ordering)
        for trial in ordering:
            if trial["status"] != "completed" or trial.get("collection_error"):
                continue
            case = cases[trial["case_id"]]
            packet.append({"blind_id": trial["blind_id"],
                           "prompt": _safe(path, case["prompt"], file=True).read_text(encoding="utf-8"),
                           "rubric": read_json(_safe(path, case["rubric"], file=True)), "response": trial["response"]})
            if case.get("workflow"):
                packet[-1]["artifacts"] = artifact_texts(path, trial)
        _write(path / "blind.json", packet)
        _write(path / "blind-mapping.json", [{"blind_id": t["blind_id"], "trial_id": t["id"]} for t in trials])
        return {"packet": str(path / "blind.json"), "count": len(packet),
                "limitation": "Procedural blinding only; local disk access can reveal mapping"}


def pairwise(vault, identifier):
    """Pairs share case/repeat; both display orders permit explicit human comparison."""
    import itertools
    with _locked(vault, identifier) as (path, manifest):
        trials = _load_trials(path, manifest)
        completed = [t for t in trials if t["status"] == "completed" and not t.get("collection_error")]
        groups = {}
        for trial in completed:
            groups.setdefault((trial["case_id"], trial["repeat"]), []).append(trial)
        cases = {c["id"]: c for c in manifest["cases"]}
        packet, mapping = [], []
        for key, members in sorted(groups.items()):
            for first, second in itertools.combinations(sorted(members, key=lambda t: t["profile_id"]), 2):
                for left, right in ((first, second), (second, first)):
                    pair_id = "pair-" + _digest(_json_bytes([manifest["id"], left["blind_id"], right["blind_id"]]))[:24]
                    case = cases[key[0]]
                    packet.append({"pair_id": pair_id, "prompt": _safe(path, case["prompt"], file=True).read_text(encoding="utf-8"),
                                   "response_a": left["response"], "response_b": right["response"]})
                    if case.get("workflow"):
                        packet[-1]["artifacts_a"] = artifact_texts(path, left)
                        packet[-1]["artifacts_b"] = artifact_texts(path, right)
                    mapping.append({"pair_id": pair_id, "case_id": key[0], "repeat": key[1],
                                    "trial_a": left["id"], "trial_b": right["id"],
                                    "profile_a": left["profile_id"], "profile_b": right["profile_id"]})
        random.Random(_digest(_json_bytes(manifest))).shuffle(packet)
        _write(path / "pairwise.json", packet)
        _write(path / "pairwise-mapping.json", mapping)
        return {"packet": str(path / "pairwise.json"), "count": len(packet),
                "limitation": "Both orders are displayed; correlated order checks are not independent human preferences"}


def import_pairwise(vault, identifier, source):
    with _locked(vault, identifier) as (path, manifest):
        trials = _load_trials(path, manifest)
        indexed = {t["id"]: t for t in trials}
        mapping = {p["pair_id"]: p for p in read_json(_safe(path, "pairwise-mapping.json", file=True))}
        target = _safe(path, "pairwise-feedback.json")
        existing = read_json(target) if target.exists() else []
        records = read_json(source)
        if not isinstance(existing, list) or not isinstance(records, list):
            raise EvalError("Pairwise preferences must be an array")
        seen_ids = {p["id"] for p in existing}
        seen_pairs = {(p["pair_id"], p["reviewer"]) for p in existing}
        additions = []
        for record in records:
            if not isinstance(record, dict):
                raise EvalError("Pairwise preference must be an object")
            preference_id = slug(record.get("id"), "pairwise assessment id")
            pair_id = record.get("pair_id")
            if not isinstance(pair_id, str) or pair_id not in mapping:
                raise EvalError("Unknown blind pair ID")
            pair = mapping[pair_id]
            reviewer = _text(record.get("reviewer"), "explicit human reviewer")
            notes = _text(record.get("notes"), "human preference justification")
            if preference_id in seen_ids or (pair_id, reviewer) in seen_pairs:
                raise EvalError("Duplicate immutable human pairwise assessment")
            if not isinstance(record.get("preference"), str) or record["preference"] not in {"a", "b", "tie", "unknown"}:
                raise EvalError("Blind preference must be a, b, tie or unknown")
            _number(record.get("review_minutes"), "pairwise review_minutes", optional=True)
            if any(indexed[pair[name]]["status"] != "completed" or indexed[pair[name]].get("collection_error") for name in ("trial_a", "trial_b")):
                raise EvalError("Pair includes an unresolved trial")
            converted = "profile_" + record["preference"] if record["preference"] in {"a", "b"} else record["preference"]
            additions.append({"id": preference_id, **pair, "preference": converted, "reviewer": reviewer,
                              "notes": notes, "review_minutes": record.get("review_minutes"), "source": "explicit human import"})
            seen_ids.add(preference_id)
            seen_pairs.add((pair_id, reviewer))
        _write(target, existing + additions)
        return {"id": identifier, "added": len(additions), "total": len(existing) + len(additions)}


def prepare(vault, identifier, trial_id):
    from . import workflows
    with _locked(vault, identifier) as (path, manifest):
        _verify_environment(vault, manifest)
        trials = _load_trials(path, manifest)
        trial = next((t for t in trials if t["id"] == trial_id), None)
        cases = {c["id"]: c for c in manifest["cases"]}
        if trial is None or trial["status"] != "planned" or not cases[trial["case_id"]].get("workflow"):
            raise EvalError("Prepare requires a planned eligible host workflow trial")
        trial["status"] = "preparing"
        _write(path / "trials.json", trials)
        try:
            receipt = workflows.prepare(path, cases[trial["case_id"]], trial)
            case = cases[trial["case_id"]]
            receipt["case_prompt"] = _safe(path, case["prompt"], file=True).read_text(encoding="utf-8")
            receipt["max_words"] = case["max_words"]
            trial["workflow_preparation"] = receipt
            trial["preparation_recorded_at"] = _now()
            trial["status"] = "prepared"
            _write(path / "trials.json", trials)
            return {"id": identifier, "trial_id": trial_id, "requested_profile": next(p for p in manifest["profiles"] if p["id"] == trial["profile_id"]),
                    "workflow": receipt, "limitation": "Host-managed execution required; prepare starts no model or background agent"}
        except (ValueError, OSError) as error:
            trial["workflow_error"] = str(error)
            _write(path / "trials.json", trials)
            raise EvalError("Workflow preparation interrupted; reconcile existing workspace before proceeding: " + str(error)) from None


def _host_timing(observed_trace):
    if observed_trace is None:
        return {"execution_seconds": None, "queue_seconds": None, "timing_provenance": "unknown"}
    if not isinstance(observed_trace, dict) or observed_trace.get("source") != "host-observed" or not isinstance(observed_trace.get("events"), list):
        raise EvalError("Host trace requires explicit host-observed provenance and events array")
    start, finish = observed_trace.get("started_at"), observed_trace.get("finished_at")
    execution = None
    if start is not None or finish is not None:
        for stamp in (start, finish):
            if not isinstance(stamp, str):
                raise EvalError("Observed execution requires started_at and finished_at ISO timestamps")
            try:
                parsed = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError:
                raise EvalError("Invalid observed execution timestamp") from None
            if parsed.tzinfo is None:
                raise EvalError("Observed execution timestamps require timezone offsets")
        execution = _seconds(start, finish)
        if execution is None:
            raise EvalError("Observed execution timestamp order is invalid")
    queue = observed_trace.get("queue_seconds")
    _number(queue, "observed queue_seconds", optional=True)
    return {"execution_seconds": execution, "queue_seconds": queue,
            "timing_provenance": "host_observed_declared" if execution is not None or queue is not None else "unknown",
            "observed_started_at": start, "observed_finished_at": finish}


def finish(vault, identifier, trial_id, response=None, *, identity=None, observed_trace=None, allow_code_execution=False):
    from . import workflows
    with _locked(vault, identifier) as (path, manifest):
        _verify_environment(vault, manifest)
        trials = _load_trials(path, manifest)
        trial = next((t for t in trials if t["id"] == trial_id), None)
        if trial is None or trial["status"] != "prepared":
            raise EvalError("Finish requires a prepared host workflow trial")
        case = next(c for c in manifest["cases"] if c["id"] == trial["case_id"])
        if response is not None and (not isinstance(response, str) or not response.strip()):
            raise EvalError("Optional host response must be nonempty unmodified text")
        if identity is not None and not isinstance(identity, dict):
            raise EvalError("Observed host identity must be an object or null")
        timing = _host_timing(observed_trace)
        trial["status"] = "finishing"
        _write(path / "trials.json", trials)
        try:
            receipt = workflows.finish(path, case, trial, response, execution_source="host-managed", identity=identity,
                                       observed_trace=observed_trace, allow_code_execution=allow_code_execution)
            checks = receipt.get("final_state_checks")
            if not isinstance(checks, dict) or checks.get("status") not in {"pass", "fail", "unavailable"}:
                raise EvalError("Workflow finish returned no observable state validation")
            trial.update(host_result=True, workflow_result=receipt, final_state_checks=checks, artifacts=receipt.get("artifacts", []),
                         response=response, checks={"nonempty": bool(response and response.strip()),
                                                   "word_limit": isinstance(response, str) and len(response.split()) <= case["max_words"]},
                         status="unavailable" if checks["status"] == "unavailable" else "completed",
                         failure_kind="unavailable" if checks["status"] == "unavailable" else ("semantic" if checks["status"] == "fail" else None),
                         trajectory=receipt.get("trajectory", {"status": "unknown", "violations": []}),
                         model_reported=receipt.get("observed_identity", {}).get("model") if isinstance(receipt.get("observed_identity"), dict) else None)
            requested = next(p for p in manifest["profiles"] if p["id"] == trial["profile_id"])
            trial.update(timing, completion_recorded_at=_now())
            observed = receipt.get("observed_identity")
            if isinstance(observed, dict) and any(observed.get(k) is not None and observed[k] != requested[k]
                                                  for k in ("provider", "model", "effort")):
                trial.update(status="failed", failure_kind="infrastructure", error="Observed host configuration differs from frozen requested profile",
                             configuration_mismatch=True)
            _write(path / "trials.json", trials)
            return {"id": identifier, "trial_id": trial_id, "status": trial["status"], "workflow": receipt}
        except (ValueError, OSError) as error:
            trial["workflow_error"] = str(error)
            _write(path / "trials.json", trials)
            raise EvalError("Workflow finish interrupted; no automatic reset: " + str(error)) from None


def _number(value, label, *, optional=False, integer=False, maximum=None):
    if value is None and optional:
        return
    if type(value) not in ((int,) if integer else (int, float)) or value < 0:
        raise EvalError(f"Invalid {label}: nonnegative finite number required")
    if maximum is not None and value > maximum:
        raise EvalError(f"Invalid {label}: maximum is {maximum}")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise EvalError(f"Invalid {label}: finite number required")


def _strings(value, label, nonempty=False):
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value) or (nonempty and not value):
        raise EvalError(f"{label} must be a list of nonempty strings")


def legacy_grade_id(trial_id, evaluator):
    value = json.dumps([trial_id, evaluator], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "legacy-" + _digest(value)[:20]


def validate_assessments(records, kind, trials, existing=None, manifest=None, evidence_texts=None):
    if kind not in {"grade", "feedback", "trajectory"} or not isinstance(records, list):
        raise EvalError("Assessments must be an array of a known kind")
    indexed = {t["id"]: t for t in trials}
    blind_ids = {t["blind_id"]: t["id"] for t in trials}
    actor = "reviewer" if kind == "feedback" else "evaluator"
    seen = {(r["trial_id"], r[actor]) for r in (existing or [])}
    prior = {}
    active = {}
    for r in existing or []:
        key = r["trial_id"], r[actor]
        assessment_id = r.get("id") or legacy_grade_id(*key)
        prior[assessment_id] = r
        active[key] = assessment_id
    cleaned = []
    for record in records:
        if not isinstance(record, dict):
            raise EvalError("Each assessment must be an object")
        record = dict(record)
        trial_id = record.get("trial_id")
        blind_id = record.pop("blind_id", None)
        if blind_id is not None:
            mapped = blind_ids.get(blind_id)
            if mapped is None or trial_id not in (None, mapped):
                raise EvalError("Unknown or conflicting blind ID")
            trial_id = mapped
        if not isinstance(trial_id, str) or trial_id not in indexed or indexed[trial_id]["status"] != "completed" or indexed[trial_id].get("collection_error"):
            raise EvalError("Assessments require a known completed trial")
        record["trial_id"] = trial_id
        _text(record.get(actor), actor)
        _text(record.get("notes"), "assessment justification")
        key = trial_id, record[actor]
        supplied_id = record.get("id")
        assessment_id = supplied_id or legacy_grade_id(*key)
        if kind == "grade":
            slug(assessment_id, "assessment id")
            if assessment_id in prior:
                raise EvalError("Duplicate immutable assessment id")
            supersedes = record.get("supersedes")
            if key in seen:
                if supersedes != active.get(key):
                    raise EvalError("Correction must supersede the active record of the same trial/evaluator")
                previous = prior.get(supersedes)
                if not previous or (previous["trial_id"], previous[actor]) != key:
                    raise EvalError("A correction cannot change trial or evaluator identity")
                if previous.get("evaluator_config") != record.get("evaluator_config"):
                    raise EvalError("A correction cannot silently change evaluator configuration")
            elif supersedes is not None:
                raise EvalError("Superseded assessment is unknown or belongs to another evaluator")
            record["id"] = assessment_id
            if manifest and manifest.get("assessment_schema_version", 1) >= 2:
                if not isinstance(supplied_id, str) or not supplied_id.strip():
                    raise EvalError("New grades require an explicit assessment id")
                cases = {c["id"]: c for c in manifest["cases"]}
                case = cases[indexed[trial_id]["case_id"]]
                if record.get("rubric_version") != case.get("rubric_version"):
                    raise EvalError("Grade rubric_version must match frozen rubric hash")
                config = record.get("evaluator_config")
                if not isinstance(config, dict) or config.get("kind") not in {"human", "model"}:
                    raise EvalError("Grade requires explicit human/model evaluator configuration")
                if config["kind"] == "model":
                    validate_profiles([{"id": "judge", **{k: config.get(k) for k in ("provider", "model", "effort")}}])
                if type(record.get("conflict_of_authorship")) is not bool:
                    raise EvalError("Authorship conflict must be explicitly declared")
                criteria = record.get("criteria")
                expected_ids = {c["id"] for c in case.get("criteria_metadata", [])}
                if not isinstance(criteria, list) or len(criteria) != len(expected_ids):
                    raise EvalError("Grade requires every frozen criterion exactly once")
                observed_ids = set()
                for criterion in criteria:
                    if not isinstance(criterion, dict) or not isinstance(criterion.get("id"), str) or criterion["id"] not in expected_ids or criterion["id"] in observed_ids:
                        raise EvalError("Unknown or duplicate grade criterion")
                    observed_ids.add(criterion["id"])
                    if not isinstance(criterion.get("status"), str) or criterion["status"] not in {"pass", "partial", "fail", "unknown"}:
                        raise EvalError("Invalid criterion assessment status")
                    _strings(criterion.get("evidence"), "criterion literal evidence", nonempty=criterion["status"] != "unknown")
                    sources = (evidence_texts or {}).get(trial_id, [indexed[trial_id]["response"] or ""])
                    if any(not any(quote in source for source in sources) for quote in criterion["evidence"]):
                        raise EvalError("Criterion evidence must quote the unmodified response literally")
                failures = record.get("critical_failures")
                _strings(failures, "critical_failures")
                critical_ids = {c["id"] for c in case["criteria_metadata"] if c["critical"]}
                failed_ids = {c["id"] for c in criteria if c["status"] == "fail"}
                if len(failures) != len(set(failures)) or any(c not in critical_ids or c not in failed_ids for c in failures):
                    raise EvalError("Critical failures must identify frozen critical criteria assessed fail")
                _strings(record.get("evidence"), "literal grade evidence", nonempty=True)
                if any(not any(quote in source for source in sources) for quote in record["evidence"]):
                    raise EvalError("Grade evidence must quote original response/artifact literally")
            prior[assessment_id] = record
            active[key] = assessment_id
        elif key in seen:
            raise EvalError("Duplicate immutable trial/evaluator assessment")
        seen.add(key)
        if kind == "grade":
            _number(record.get("quality"), "quality", maximum=4,
                    integer=bool(manifest and manifest.get("assessment_schema_version", 1) >= 2))
            _strings(record.get("critical_failures"), "critical_failures")
            _strings(record.get("evidence"), "evidence", nonempty=True)
        elif kind == "feedback":
            if record.get("preference") not in {"use", "revise", "reject"}:
                raise EvalError("Invalid human preference")
            _number(record.get("review_minutes"), "review_minutes", optional=True)
            _number(record.get("corrections"), "corrections", optional=True, integer=True)
            for metric in ("preparation_minutes", "integration_minutes", "total_minutes", "accepted_delivery_minutes"):
                _number(record.get(metric), metric, optional=True)
            if record.get("acceptance", "unknown") not in {"accepted", "revise", "rejected", "unknown"}:
                raise EvalError("Invalid explicit human acceptance")
            if record.get("accepted_delivery_minutes") is not None and record.get("acceptance") != "accepted":
                raise EvalError("Accepted delivery duration requires explicit human acceptance")
        else:
            if record.get("status") not in {"pass", "fail"}:
                raise EvalError("Trajectory audit requires pass/fail")
            _strings(record.get("violations"), "violations")
            if record["status"] == "pass" and record["violations"]:
                raise EvalError("Passing trajectory cannot have violations")
        cleaned.append(record)
    return cleaned


def import_assessments(vault, identifier, kind, source):
    names = {"grade": "grades.json", "feedback": "feedback.json", "trajectory": "trajectory.json"}
    if kind not in names:
        raise EvalError("Unknown assessment kind")
    with _locked(vault, identifier) as (path, manifest):
        trials = _load_trials(path, manifest)
        target = _safe(path, names[kind], file=True)
        existing = read_json(target)
        texts = _evidence_texts(path, trials)
        existing = validate_assessments(existing, kind, trials, manifest=manifest, evidence_texts=texts)
        added = validate_assessments(read_json(source), kind, trials, existing, manifest, texts)
        _write(target, existing + added)
        return {"id": identifier, "kind": kind, "added": len(added), "total": len(existing) + len(added)}


def report(vault, identifier):
    from .report import build_report, render_markdown
    with _locked(vault, identifier) as (path, manifest):
        trials = _load_trials(path, manifest)
        if any(t.get("collection_error") for t in trials):
            raise EvalError("Unreconciled result collection errors; collect before reporting")
        inputs = {}
        texts = _evidence_texts(path, trials)
        for kind, name in (("grade", "grades"), ("feedback", "feedback"), ("trajectory", "trajectory")):
            values = read_json(_safe(path, name + ".json", file=True))
            inputs[name] = validate_assessments(values, kind, trials, manifest=manifest, evidence_texts=texts)
        pairwise_path = _safe(path, "pairwise-feedback.json")
        pairwise = read_json(pairwise_path) if pairwise_path.exists() else []
        observed_trials = [dict(trial, artifact_texts=artifact_texts(path, trial)) for trial in trials]
        result = build_report(manifest, observed_trials, inputs["grades"], inputs["feedback"], inputs["trajectory"], pairwise)
        scripts = Path(__file__).resolve().parents[1]
        current = {name: _digest(_safe(scripts, name, file=True).read_bytes())
                   for name in ("thinker_model_eval/core.py", "thinker_model_eval/report.py")}
        frozen = {name: manifest["environment"]["executor_hashes"].get(name) for name in current}
        result["report_generation"] = {"created_at": _now(), "source_hashes": current,
                                       "frozen_source_hashes": frozen, "source_changed": current != frozen}
        _write(path / "report.json", result)
        provenance = ("\nRelatório gerado em " + result["report_generation"]["created_at"] +
                      ". Motor ou renderizador diferem do ambiente congelado: " + ("sim" if current != frozen else "não") + ".\n")
        _write(path / "report.md", render_markdown(result) + provenance, text=True)
        return {"json": str(path / "report.json"), "markdown": str(path / "report.md")}
