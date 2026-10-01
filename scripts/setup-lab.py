#!/usr/bin/env python3
"""Create an isolated synthetic lab; never install into a protected workspace."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab_paths import canonical, load_lab, overlap, protected_paths

SOURCE = Path(__file__).resolve().parents[1]
MARKER = "thinker-lab.json"


def environment(root):
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "USER", "LOGNAME", "LANG", "LC_ALL"}}
    for key, part in {"HOME": "home", "XDG_STATE_HOME": "xdg", "CODEX_HOME": "codex", "CLAUDE_CONFIG_DIR": "claude", "GROK_HOME": "grok", "TMPDIR": "tmp"}.items():
        directory = canonical(root / part)
        directory.mkdir(exist_ok=True, mode=0o700)
        env[key] = str(directory)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def inventory(path):
    result = {}
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in list(dirs):
            item = Path(base) / name
            if item.is_symlink():
                result[str(item.relative_to(path))] = "symlink:" + os.readlink(item)
                dirs.remove(name)
        for name in files:
            item = Path(base) / name
            result[str(item.relative_to(path))] = ("symlink:" + os.readlink(item) if item.is_symlink()
                                                  else hashlib.sha256(item.read_bytes()).hexdigest())
    return result


def load(root):
    return load_lab(root, MARKER)


def execute(root, command, *, authenticated=False, capture=True):
    root, config = load(root)
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").exists():
        raise ValueError("Guarded execution requires validated macOS sandbox-exec")
    env = environment(root)
    if authenticated:
        # Explicit boundary: use existing provider login; never copy credentials.
        for key in ("HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
            if key in os.environ:
                env[key] = os.environ[key]
            else:
                env.pop(key, None)
        env["THINKER_LAB_AUTH_BOUNDARY"] = "existing_login_no_credential_copy"
    profile = "(version 1)\n(allow default)\n"
    for protected in config["protected_roots"] + [str(root / "sentinel")]:
        profile += "(deny file-write* (subpath " + json.dumps(protected) + "))\n"
    # Rebuild the policy from validated marker, never trust an edited policy file.
    policy = root / "protection.sb"
    if policy.is_symlink():
        raise ValueError("Invalid policy path")
    policy.write_text(profile)
    return subprocess.run(["/usr/bin/sandbox-exec", "-f", str(policy), *command],
                          cwd=SOURCE, env=env, capture_output=capture, text=True)


def prepare(root, protected_roots, baseline):
    root = canonical(root)
    protected = protected_paths(protected_roots)
    if not protected or any(overlap(root, p) for p in protected) or root == SOURCE:
        raise ValueError("Explicit disjoint protected roots are required")
    if root.exists():
        raise ValueError("Lab root must be new")
    sha = subprocess.check_output(["git", "rev-parse", "--verify", baseline + "^{commit}"], cwd=SOURCE, text=True).strip()
    archive = subprocess.check_output(["git", "archive", "--format=tar", sha], cwd=SOURCE)
    root.mkdir(parents=True, mode=0o700)
    (root / "sentinel").mkdir()
    config = {"schema": 1, "root": str(root), "source": str(SOURCE), "baseline_tag": baseline,
              "baseline_sha": sha, "protected_roots": list(map(str, protected)),
              "authentication": "deterministic_no_accounts", "candidate_version": (SOURCE / "VERSION").read_text().strip()}
    (root / MARKER).write_text(json.dumps(config, indent=2) + "\n")
    baseline_source = root / "baseline-source"
    baseline_source.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            dest = baseline_source / member.name
            if not (member.isfile() or member.isdir()) or not dest.resolve().is_relative_to(baseline_source):
                raise ValueError("Unsafe baseline archive")
        for member in tar.getmembers():
            dest = baseline_source / member.name
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as incoming:
                    dest.write_bytes(incoming.read())
                dest.chmod(member.mode & 0o755)
    before = {str(p): inventory(p) for p in protected}
    (root / "protected-before.json").write_text(json.dumps(before, sort_keys=True))
    positive = root / "guard-positive-control"
    control = execute(root, ["/usr/bin/touch", str(positive)])
    if control.returncode != 0 or not positive.is_file():
        raise ValueError("Guarded process could not write inside laboratory; isolation proof inconclusive")
    positive.unlink()
    proof = execute(root, ["/usr/bin/touch", str(root / "sentinel" / "denied")])
    if proof.returncode == 0 or (root / "sentinel" / "denied").exists():
        raise ValueError("Write protection sentinel failed")
    for name, source in (("baseline", baseline_source), ("candidate", SOURCE)):
        result = execute(root, ["bash", str(source / "install.sh"), "--init", str(root / name)])
        (root / (name + "-install.log")).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise ValueError(name + " installation failed; inspect lab log")
    return {"lab": str(root), "baseline_sha": sha, "sentinel_write_denied": True,
            "targets": [str(root / "baseline"), str(root / "candidate")]}


def audit(root):
    root, config = load(root)
    before = json.loads((root / "protected-before.json").read_text())
    delta = {}
    for name in config["protected_roots"]:
        current = inventory(Path(name))
        delta[name] = sorted(p for p in set(before[name]) | set(current) if before[name].get(p) != current.get(p))
    report = {"protected_unchanged": not any(delta.values()), "changes": delta,
              "audit_scope": "regular-file bytes and symlink targets; directory metadata not captured"}
    (root / "protected-audit.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--protected-root", action="append", required=True)
    prep.add_argument("--baseline", default="v7.22.1")
    run = commands.add_parser("run")
    run.add_argument("--authenticated", action="store_true", help="Use existing login; caller must independently restrict provider tools")
    run.add_argument("argv", nargs=argparse.REMAINDER)
    commands.add_parser("audit")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            output = prepare(args.root, args.protected_root, args.baseline)
        elif args.command == "audit":
            output = audit(args.root)
        else:
            command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            if not command:
                raise ValueError("Command required")
            result = execute(Path(args.root), command, authenticated=args.authenticated, capture=False)
            return result.returncode
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if output.get("protected_unchanged", True) else 1
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
