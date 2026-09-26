"""Metadados reportados de agentes nativos; nunca agenda nem observa processos.

O host informa explicitamente a existencia e o ultimo estado que conhece. Isso
nao prova transporte, qualidade ou que um processo ainda esta vivo.
"""
from __future__ import annotations

import datetime as dt
import re

from .runtime import DelegationError, _atomic, _identifier, _read

STATES = {"running", "completed", "failed", "cancelled"}
# Esforço declarado pelo host; `unknown` quando ele não informa. É declaração,
# não confirmação de que o provedor aplicou esse esforço.
EFFORTS = {"low", "medium", "high", "xhigh", "max", "ultra", "unknown"}
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


def report(store, session, identifier, model, state, task, effort=None):
    """Registra um estado declarado pelo host; nenhum processo e tocado."""
    session, identifier = _identifier(session), _id(identifier)
    model, task = _text(model, "model", 128), _text(task, "task", 256)
    if state not in STATES:
        raise DelegationError("Native state must be running, completed, failed, or cancelled")
    effort = "unknown" if effort is None else effort
    if effort not in EFFORTS:
        raise DelegationError("Native effort must be one of: " + ", ".join(sorted(EFFORTS)))
    with store._lock():
        value = _load(store)
        key = session + "\u0000" + identifier
        previous = value["reports"].get(key, {})
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        created, updated = previous.get("created_at", now), now
        if previous.get("state") in STATES - {"running"}:
            if state == "running":
                # Mesmo ID de novo em execução depois de terminal: reabre o
                # registro no lugar. A chave é sessão+id; um registro novo
                # exigiria outro schema do native.json.
                created = now
            elif state == previous.get("state"):
                # Terminal repetido não reescreve quando terminou.
                updated = previous.get("updated_at", now)
        value["reports"][key] = {"id": identifier, "session": session, "model": model,
                                 "task": task, "state": state, "effort": effort, "reported": True,
                                 "created_at": created, "updated_at": updated}
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
            # Campos opcionais: registros anteriores à 7.22.0 não os têm.
            record["effort"] = item.get("effort", "unknown")
            if record["effort"] not in EFFORTS:
                raise DelegationError("Malformed native delegation report")
            record["created_at"] = item.get("created_at") if _when(item.get("created_at")) else None
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
