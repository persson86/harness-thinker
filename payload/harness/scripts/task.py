#!/usr/bin/env python3
"""Explicit task metadata and continuity; JSON output, no provider execution."""
from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True
from thinker_tasks.core import DEFAULT_BUDGET, TaskError, TaskStore, read_checkpoint_file


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise TaskError("invalid_input", message)


def parser():
    root = Parser(description="Task continuity in an explicit private state directory.")
    root.add_argument("--workspace", required=True)
    root.add_argument("--state-dir", required=True)
    commands = root.add_subparsers(dest="command", required=True, parser_class=Parser)
    create = commands.add_parser("create")
    create.add_argument("--title", required=True)
    create.add_argument("--objective", required=True)
    create.add_argument("--request-id")
    for name in ("checkpoint", "link", "seen", "reset", "close", "reopen", "pause"):
        command = commands.add_parser(name)
        command.add_argument("task")
        command.add_argument("--expected-revision", required=True, type=int)
        command.add_argument("--request-id", required=True)
        if name == "checkpoint":
            command.add_argument("--file", required=True)
        elif name == "link":
            command.add_argument("--kind", required=True, choices=("session", "run", "job", "artifact"))
            command.add_argument("--external-id", required=True)
            command.add_argument("--provider", required=True)
        elif name == "seen":
            command.add_argument("--key", required=True)
    for name in ("resume", "export"):
        command = commands.add_parser(name)
        command.add_argument("task")
        command.add_argument("--budget-bytes", type=int, default=DEFAULT_BUDGET)
        if name == "export":
            command.add_argument("--name", required=True)
    commands.add_parser("snapshot")
    commands.add_parser("attention")
    return root


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        store = TaskStore(args.workspace, args.state_dir)
        command = args.command
        if command == "create":
            result = store.create(args.title, args.objective, args.request_id)
        elif command == "checkpoint":
            result = store.checkpoint(args.task, args.expected_revision, args.request_id, read_checkpoint_file(args.file))
        elif command == "link":
            result = store.link(args.task, args.expected_revision, args.request_id, args.kind, args.external_id, args.provider)
        elif command == "seen":
            result = store.seen(args.task, args.expected_revision, args.request_id, args.key)
        elif command == "reset":
            result = store.reset(args.task, args.expected_revision, args.request_id)
        elif command in {"close", "reopen", "pause"}:
            result = store.transition(args.task, args.expected_revision, args.request_id,
                                      {"close": "closed", "reopen": "open", "pause": "paused"}[command])
        elif command == "resume":
            result = store.resume(args.task, args.budget_bytes)
        elif command == "export":
            result = store.export(args.task, args.name, args.budget_bytes)
        else:
            result = store.snapshot()
            if command == "attention":
                result = {key: result[key] for key in ("schema", "generated_at", "attention")}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except TaskError as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False), file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        error = TaskError("state_unavailable", "Selected input or state is unavailable or malformed; no execution was started.")
        print(json.dumps(error.as_dict()), file=sys.stderr)
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
