"""Cota observada localmente: rollouts do Codex e stdin da statusLine do Claude.

Sem credenciais nem rede. O Claude entrega `rate_limits` à statusLine; o Codex
grava `rate_limits` nos rollouts.

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
import json
import math
import os
from pathlib import Path
import tempfile

EVIDENCE = "local_observation_not_attributed"
PROVIDER_LIMIT_EVIDENCE = "provider_limit_failure_not_attributed"
PROVIDER_LIMIT_SECONDS = 1800
CLAUDE_FILE = "quota-observation-claude.json"
CLAUDE_WINDOWS = (("five_hour", 300), ("seven_day", 10080))
CLAUDE_REFRESH_SECONDS = 300
SEVERITY = {"available": 0, "constrained": 1, "blocked": 2}
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


def strictest(*quotas):
    """A restrição mais forte entre sinais vigentes; empate mantém o primeiro."""
    best = None
    for quota in quotas:
        if quota and (best is None or SEVERITY[quota["availability"]] > SEVERITY[best["availability"]]):
            best = quota
    return best


def from_claude_statusline(data, now):
    """`rate_limits` do stdin da statusLine. O horário é o do recebimento, não o da medição."""
    limits = data.get("rate_limits") if isinstance(data, dict) else None
    if not isinstance(limits, dict):
        return None
    windows = []
    for key, minutes in CLAUDE_WINDOWS:
        value = limits.get(key)
        if not isinstance(value, dict):
            continue
        used, reset = value.get("used_percentage"), value.get("resets_at")
        if _number(used, 0, 1000) and _number(reset, 1, 10**12):
            windows.append({"minutes": minutes, "used_percent": float(used), "resets_at": float(reset)})
    if not windows:
        return None
    return {"provider": "claude", "source": "claude_statusline", "measured_at": now, "windows": windows}


def write_claude(state, data, now):
    """Escritor oportunista da statusLine: sem lock, rename atômico, só quando muda.

    Não cria a área de estado; sem ela não há delegação para informar. Qualquer
    falha é silenciosa, porque a statusLine nunca pode quebrar por causa disto.
    """
    observation = from_claude_statusline(data, now)
    state = Path(state)
    if observation is None or not state.is_dir():
        return False
    path = state / CLAUDE_FILE
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        current = None
    if (isinstance(current, dict) and current.get("windows") == observation["windows"]
            and _number(current.get("measured_at"), 1, 10**12)
            and 0 <= now - current["measured_at"] < CLAUDE_REFRESH_SECONDS):
        return False
    fd, temporary = tempfile.mkstemp(prefix=".quota-", dir=state)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(observation, stream, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def provider_limit_signal(jobs, provider, now):
    """Falha recente classificada como provider_limit vira constrained por 30 minutos.

    O classificador da CLI também casa "overloaded"/"capacity", que não esgotam a
    conta; por isso o sinal reserva o provedor sem bloqueá-lo.
    """
    latest = None
    for job in jobs:
        if (not isinstance(job, dict) or job.get("state") != "failed" or job.get("error_code") != "provider_limit"
                or (job.get("profile") or {}).get("provider") != provider):
            continue
        finished = _timestamp(job.get("finished_at"))
        if finished is not None and now - PROVIDER_LIMIT_SECONDS < finished <= now + 300:
            latest = finished if latest is None else max(latest, finished)
    if latest is None:
        return None
    return {"availability": "constrained", "expires_at": latest + PROVIDER_LIMIT_SECONDS,
            "evidence": PROVIDER_LIMIT_EVIDENCE}
