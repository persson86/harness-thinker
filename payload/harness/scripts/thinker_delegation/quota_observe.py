"""Cota observada nos rollouts locais do Codex; leitura explícita, sem credenciais nem rede.

O rollout é uma superfície não documentada: cada linha é dado opcional, formato
inesperado vira ausência de evidência e nunca zero. Os jobs da delegação rodam
`codex exec --ephemeral` e não deixam rollout, então só sessões interativas
renovam a leitura.

Dentro de uma janela o uso só cresce. Uma leitura antiga é, portanto, um limite
inferior: restrição observada vale até o reset da própria janela, mesmo velha;
folga observada só vale enquanto a leitura é recente.
"""
from __future__ import annotations

import datetime as dt
import math
import os
from pathlib import Path
import json

EVIDENCE = "local_observation_not_attributed"
CONSTRAINED_PERCENT = 90.0
BLOCKED_PERCENT = 100.0
FRESH_SECONDS = 1800
MAX_FILES = 20
MAX_WALK = 5000
TAIL_BYTES = 256 * 1024
MAX_LINE_BYTES = 128 * 1024


def codex_home():
    configured = os.environ.get("CODEX_HOME")
    return Path(configured).expanduser() if configured else Path.home() / ".codex"


def _number(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _window(value):
    if not isinstance(value, dict):
        return None
    used, minutes, reset = value.get("used_percent"), value.get("window_minutes"), value.get("resets_at")
    if not (_number(used, 0, 1000) and _number(minutes, 1, 10**6) and _number(reset, 1, 10**12)):
        return None
    return {"minutes": int(minutes), "used_percent": float(used), "resets_at": float(reset)}


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo else None


def _label(value):
    return value[:40] if isinstance(value, str) else None


def _parse(line):
    if len(line) > MAX_LINE_BYTES or b'"rate_limits"' not in line:
        return None
    try:
        record = json.loads(line)
    except ValueError:
        return None
    payload = record.get("payload") if isinstance(record, dict) else None
    if record.get("type") != "event_msg" or not isinstance(payload, dict) or payload.get("type") != "token_count":
        return None
    limits, measured = payload.get("rate_limits"), _timestamp(record.get("timestamp"))
    if not isinstance(limits, dict) or measured is None:
        return None
    windows = [w for w in (_window(limits.get("primary")), _window(limits.get("secondary"))) if w]
    if not windows:
        return None
    return {"provider": "codex", "source": "codex_rollout", "measured_at": measured, "windows": windows,
            "limit_id": _label(limits.get("limit_id")), "plan_type": _label(limits.get("plan_type"))}


def _tail(path):
    with path.open("rb") as stream:
        size = stream.seek(0, os.SEEK_END)
        stream.seek(max(0, size - TAIL_BYTES))
        data = stream.read(TAIL_BYTES)
    lines = data.split(b"\n")
    # Começando no meio do arquivo, a primeira linha está cortada.
    return lines[1:] if size > TAIL_BYTES else lines


def read_codex(home=None):
    """Última leitura válida entre os rollouts recentes, pelo horário do evento."""
    sessions = (Path(home) if home else codex_home()) / "sessions"
    if not sessions.is_dir():
        return None
    candidates = []
    for count, path in enumerate(sessions.rglob("rollout-*.jsonl")):
        if count >= MAX_WALK:
            break
        if path.is_file() and not path.is_symlink():
            candidates.append((path.stat().st_mtime, path))
    best = None
    # mtime só escolhe os candidatos; o horário do evento decide entre eles.
    for _, path in sorted(candidates, reverse=True)[:MAX_FILES]:
        try:
            lines = _tail(path)
        except OSError:
            continue
        for line in reversed(lines):
            found = _parse(line.strip())
            if found:
                if best is None or found["measured_at"] > best["measured_at"]:
                    best = found
                break
    return best


def classify(observation, now, fresh_seconds=FRESH_SECONDS, constrained=CONSTRAINED_PERCENT):
    """Disponibilidade derivada no instante `now`, ou None quando não há evidência válida."""
    if not isinstance(observation, dict) or not isinstance(observation.get("windows"), list):
        return None
    measured = observation.get("measured_at")
    if not _number(measured, 1, 10**12) or measured > now + 300:
        return None
    windows = [w for w in observation["windows"] if isinstance(w, dict)
               and _number(w.get("used_percent"), 0, 1000) and _number(w.get("resets_at"), 1, 10**12)
               and w["resets_at"] > now]
    for level, threshold in (("blocked", BLOCKED_PERCENT), ("constrained", constrained)):
        hit = [w["resets_at"] for w in windows if w["used_percent"] >= threshold]
        if hit:
            return {"availability": level, "expires_at": min(hit), "evidence": EVIDENCE}
    if windows and now - measured <= fresh_seconds:
        return {"availability": "available", "expires_at": measured + fresh_seconds, "evidence": EVIDENCE}
    return None


def pacing(observation, now):
    """Informativo: uso contra a fração decorrida de cada janela. Nunca entra no roteamento."""
    rows = []
    for w in (observation or {}).get("windows", []):
        if not isinstance(w, dict) or not _number(w.get("resets_at"), 1, 10**12) or w["resets_at"] <= now:
            continue
        length = w["minutes"] * 60
        elapsed = min(100.0, max(0.0, 100.0 * (1 - (w["resets_at"] - now) / length)))
        rows.append({"minutes": w["minutes"], "used_percent": w["used_percent"],
                     "elapsed_percent": round(elapsed, 1), "delta_points": round(w["used_percent"] - elapsed, 1)})
    return rows
