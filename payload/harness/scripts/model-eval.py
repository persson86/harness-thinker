#!/usr/bin/env python3
"""Personal model evaluation for text and workspace tasks. Planning and verification never call models."""
import argparse
import json
from pathlib import Path
import shlex
import sys

sys.dont_write_bytecode = True
from thinker_model_eval import core


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vault", default=str(Path(__file__).resolve().parents[2]))
    p.add_argument("--json", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="Freeze explicit cases/profiles without model calls")
    plan.add_argument("--suite", required=True)
    plan.add_argument("--profile", action="append", default=[], metavar="ID:EFFORT")
    plan.add_argument("--profiles-file")
    plan.add_argument("--all-profiles", action="store_true", help="Freeze dynamic configured inventory at high; retain excluded profiles")
    plan.add_argument("--doctor", action="store_true", help="Read-only CLI check through delegate; never proves model access")
    plan.add_argument("--policy-file", help="Optional frozen relevance margins, action weights and stopping policy")
    plan.add_argument("--case", action="append", required=True, dest="cases")
    plan.add_argument("--repeats", type=int, default=1)
    plan.add_argument("--max-calls", type=int, required=True)
    plan.add_argument("--timeout", type=int, default=180)
    plan.add_argument("--concurrency", type=int, default=2)
    plan.add_argument("--mode", choices=["screening", "candidate", "regression"], default="candidate")
    plan.add_argument("--session", help="Delegation session; generated if omitted, never activated by plan")
    plan.add_argument("--id", required=True)
    for name in ("inventory", "list"):
        command = sub.add_parser(name, help="List every configured alias plus explicit profiles")
        command.add_argument("--profiles-file")
        command.add_argument("--doctor", action="store_true")
    for name in ("run", "collect", "blind", "pairwise", "pairwise-feedback", "report", "verify", "grade", "feedback", "trajectory",
                 "prepare", "finish", "judge-packet", "calibrate", "reconcile"):
        command = sub.add_parser(name)
        command.add_argument("--id", required=True)
        if name in {"grade", "feedback", "trajectory", "pairwise-feedback", "judge-packet", "calibrate"}:
            command.add_argument("--file", required=True)
        if name in {"prepare", "finish", "reconcile"}:
            command.add_argument("--trial", required=True)
        if name == "finish":
            command.add_argument("--file", help="Original host response text, optional when artifact is the delivery")
            command.add_argument("--identity-file")
            command.add_argument("--trace-file")
            command.add_argument("--allow-code-execution", action="store_true", help="Explicitly permit trusted hidden tests in Docker only")
        if name == "reconcile":
            command.add_argument("--action", choices=["bind", "abandon"], required=True)
            command.add_argument("--reason", required=True)
            command.add_argument("--job", help="Existing full job UUID; never submits or retries a model")
    return p


def dispatch(args):
    if args.command in {"inventory", "list"}:
        profiles = core.read_json(args.profiles_file) if args.profiles_file else []
        if not isinstance(profiles, list):
            raise core.EvalError("Profiles file must contain an array")
        return core.inventory(args.vault, profiles, doctor=args.doctor)
    if args.command == "plan":
        profiles = core.read_json(args.profiles_file) if args.profiles_file else []
        if not isinstance(profiles, list):
            raise core.EvalError("Profiles file must contain an array")
        for item in args.profile:
            parts = item.rsplit(":", 1)
            if len(parts) != 2:
                raise core.EvalError("Profile must be ID:EFFORT")
            profiles.append({"id": parts[0], "effort": parts[1]})
        return core.plan(args.vault, args.suite, profiles, args.cases, identifier=args.id,
                         session=args.session, mode=args.mode, repeats=args.repeats, max_calls=args.max_calls,
                         timeout=args.timeout, concurrency=args.concurrency, all_profiles=args.all_profiles,
                         doctor=args.doctor, policy=core.read_json(args.policy_file) if args.policy_file else None)
    if args.command == "pairwise-feedback":
        return core.import_pairwise(args.vault, args.id, args.file)
    if args.command == "prepare":
        return core.prepare(args.vault, args.id, args.trial)
    if args.command == "reconcile":
        return core.reconcile(args.vault, args.id, args.trial, args.action, args.reason, job_id=args.job)
    if args.command == "finish":
        return core.finish(args.vault, args.id, args.trial,
                           Path(args.file).read_text(encoding="utf-8") if args.file else None,
                           identity=core.read_json(args.identity_file) if args.identity_file else None,
                           observed_trace=core.read_json(args.trace_file) if args.trace_file else None,
                           allow_code_execution=args.allow_code_execution)
    if args.command in {"judge-packet", "calibrate"}:
        from thinker_model_eval import judging
        return getattr(judging, "judge_packet" if args.command == "judge-packet" else "calibrate")(args.vault, args.id, args.file)
    if args.command in {"grade", "feedback", "trajectory"}:
        return core.import_assessments(args.vault, args.id, args.command, args.file)
    if args.command == "verify":
        manifest = core.verify(args.vault, args.id)
        return {"id": args.id, "verified": True, "frozen_files": len(manifest["hashes"])}
    return getattr(core, args.command)(args.vault, args.id)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
            if result.get("board_command"):
                print("Board: " + shlex.join(result["board_command"]))
                print("Next: " + shlex.join(result["next_command"]))
        return 0
    except (core.EvalError, OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
