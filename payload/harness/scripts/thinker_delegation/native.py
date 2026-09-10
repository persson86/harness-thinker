"""Metadados reportados de agentes nativos; nunca agenda nem observa processos.

O host informa explicitamente a existencia e o ultimo estado que conhece. Isso
nao prova transporte, qualidade ou que um processo ainda esta vivo.
"""
from __future__ import annotations

import datetime as dt
import re

from .runtime import DelegationError, _atomic, _identifier, _read

STATES = {"running", "completed", "failed", "cancelled"}
MAX_AGE_SECONDS = 15 * 60


def _text(value, label, limit):
    value = str(value or "")
    value = " ".join("".join(char for char in value if char >= " " and char != "\x7f").split())
    if not value or len(value) > limit:
        raise DelegationError("Native %s must contain 1 to %d safe characters" % (label, limit))
    return value


def _id(value):
    value = _text(value, "id", 128)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise DelegationError("Native id is invalid")
    return value


def _load(store):
    value = _read(store.state / "native.json", {"schema": 1, "reports": {}})
    if value.get("schema") != 1 or not isinstance(value.get("reports"), dict):
        raise DelegationError("Malformed native delegation state")
    return value


def report(store, session, identifier, model, state, task):
    """Registra um estado declarado pelo host; nenhum processo e tocado."""
    session, identifier = _identifier(session), _id(identifier)
    model, task = _text(model, "model", 128), _text(task, "task", 256)
    if state not in STATES:
        raise DelegationError("Native state must be running, completed, failed, or cancelled")
    with store._lock():
        value = _load(store)
        key = session + "\u0000" + identifier
        previous = value["reports"].get(key, {})
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        value["reports"][key] = {"id": identifier, "session": session, "model": model,
                                 "task": task, "state": state, "reported": True,
                                 "created_at": previous.get("created_at", now), "updated_at": now}
        _atomic(store.state / "native.json", value)
    return value["reports"][key]


def _when(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def snapshot(store, session=None, all_sessions=False, stale_after=MAX_AGE_SECONDS, locked=False):
    """Retorna somente o que foi reportado; running velho vira `unknown`."""
    if session is not None:
        _identifier(session)
    if type(stale_after) not in (int, float) or not 0 < stale_after <= 86400:
        raise DelegationError("Native stale threshold must be between 0 and 86400 seconds")

    def collect():
        value = _load(store)
        now = dt.datetime.now(dt.timezone.utc)
        reports = []
        for item in value["reports"].values():
            if not isinstance(item, dict):
                raise DelegationError("Malformed native delegation report")
            try:
                record = {key: item[key] for key in ("id", "session", "model", "task", "state", "reported", "updated_at")}
                _id(record["id"]); _identifier(record["session"])
                _text(record["model"], "model", 128); _text(record["task"], "task", 256)
            except (KeyError, DelegationError):
                raise DelegationError("Malformed native delegation report") from None
            if not isinstance(record["state"], str) or record["state"] not in STATES or record["reported"] is not True:
                raise DelegationError("Malformed native delegation report")
            if not all_sessions and record["session"] != session:
                continue
            observed = _when(record["updated_at"])
            record["state"] = ("unknown" if record["state"] == "running" and
                               (observed is None or (now - observed).total_seconds() > stale_after)
                               else record["state"])
            reports.append(record)
        reports.sort(key=lambda item: (item["session"], item["id"]))
        counts = {state: sum(item["state"] == state for item in reports)
                  for state in ("running", "completed", "failed", "cancelled", "unknown")}
        return {"scope": "all" if all_sessions else "session", "reported": len(reports),
                **counts, "reports": reports}

    if locked:
        return collect()
    with store._lock():
        return collect()
