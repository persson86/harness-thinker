#!/usr/bin/env python3
"""Passive inbox: no worker launch, source content, blocking decision or OFF writes."""
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness/scripts"))


def main():
    if os.environ.get("THINKER_DELEGATION_CHILD") == "1":
        return
    try:
        data = json.loads(sys.stdin.read(65536))
        event = data.get("hook_event_name") or data.get("hookEventName")
        session = os.environ.get("THINKER_SESSION_ID") or data.get("session_id") or data.get("sessionId")
        if event not in {"UserPromptSubmit", "PostToolUse"} or not session:
            return
        from thinker_delegation.runtime import DelegationStore, TERMINAL
        store = DelegationStore(ROOT, os.environ.get("THINKER_DELEGATION_STATE_DIR"))
        if not store.status(session).get("enabled"):
            return
        jobs = [job for job in store.list_jobs(session)
                if job["state"] in TERMINAL and not job["acknowledged"]]
        if not jobs:
            return
        listing = "; ".join(f"{j['id'][:8]}: {j['state']}" for j in jobs[:5])
        context = (f"Thinker: {len(jobs)} retorno(s) pendente(s) nesta sessão. {listing}. "
                   "Consulte a inbox por harness/scripts/delegate.py, revise resultado e fontes atuais, "
                   "e use ack depois de comunicar o retorno. Conclusão de execução não significa aprovação. "
                   "Siga harness/operations/delegate.md; não incorpore automaticamente.")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                          "additionalContext": context}}, ensure_ascii=False))
    except Exception:
        # A broken optional extension must never block the existing conversation.
        return


if __name__ == "__main__":
    main()
