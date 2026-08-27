#!/usr/bin/env python3
"""Traduz JSON de hook do Grok Build para o formato esperado por .claude/hooks/*.sh."""
import json
import os
import sys


def normalize(data, vault):
    if not isinstance(data, dict):
        data = {}

    tool = data.get("toolName") or data.get("tool_name") or ""
    session = data.get("sessionId") or data.get("session_id") or ""
    event = data.get("hookEventName") or data.get("hook_event_name") or ""
    tool_input = data.get("toolInput") or data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    workspace = data.get("workspaceRoot") or data.get("cwd") or vault
    path = tool_input.get("file_path") or tool_input.get("target_file") or ""

    if tool in ("write", "Write"):
        name = "Write"
    elif tool in ("search_replace",):
        name = "Edit" if path and os.path.lexists(path) else "Write"
    elif tool in ("Edit", "MultiEdit"):
        name = tool
    elif tool in ("run_terminal_command", "Bash", "Shell"):
        name = "Bash"
    else:
        name = tool

    out_input = dict(tool_input)
    if "file_path" not in out_input and path:
        out_input["file_path"] = path

    return {
        "tool_name": name,
        "session_id": session,
        "tool_input": out_input,
        "cwd": workspace,
        "_grok_event": event,
        "_grok_workspace": workspace,
    }


def main():
    vault = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("shim Grok: JSON inválido — bloqueando por segurança", file=sys.stderr)
        sys.exit(2)
    json.dump(normalize(data, vault), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
