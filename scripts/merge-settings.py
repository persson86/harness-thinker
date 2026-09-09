#!/usr/bin/env python3
"""Merge only harness-owned hooks; preserve local settings and custom statusline."""
import argparse
import copy
import json
import shlex
from pathlib import Path


def merge(base, existing):
    if not isinstance(existing, dict):
        raise ValueError("settings.json must be an object")
    result = copy.deepcopy(existing)
    for key, value in base.items():
        if key not in {"hooks", "permissions"}:
            result.setdefault(key, value)
    permissions = result.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        raise ValueError("permissions must be an object")
    for key, value in base.get("permissions", {}).items():
        current = permissions.setdefault(key, [])
        if not isinstance(current, list):
            raise ValueError("permission rules must be lists")
        permissions[key] = list(dict.fromkeys(current + value))
    hooks = result.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("hooks must be an object")
    owned = {hook["command"] for groups in base.get("hooks", {}).values()
             for group in groups for hook in group.get("hooks", [])}
    for event in sorted(set(hooks) | set(base.get("hooks", {}))):
        groups = base.get("hooks", {}).get(event, [])
        current = hooks.get(event, [])
        if not isinstance(current, list):
            raise ValueError("hook event must be a list")
        retained = []
        for group in current:
            if not isinstance(group, dict) or not isinstance(group.get("hooks", []), list):
                raise ValueError("hook group must be an object with hooks")
            children = [h for h in group.get("hooks", []) if h.get("command") not in owned]
            if children:
                retained.append({**group, "hooks": children})
        hooks[event] = retained + groups
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.target.is_symlink() or args.target.parent.is_symlink():
        raise ValueError("settings target must not be a symlink")
    base = json.loads(args.base.read_text())
    # statusLine does not promise the hook-only CLAUDE_PROJECT_DIR variable.
    # Quote an absolute installed path, independent of the current shell cwd.
    base["statusLine"]["command"] = "python3 " + shlex.quote(str(
        args.target.parent.parent.resolve() / "harness/scripts/delegation-indicator.py")) + " --claude-statusline"
    existing = json.loads(args.target.read_text()) if args.target.exists() else {}
    merged = merge(base, existing)
    if not args.check:
        print(json.dumps(merged, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
