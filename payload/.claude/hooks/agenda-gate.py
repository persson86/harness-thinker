#!/usr/bin/env python3
"""Enforcement da operação AGENDA: Gmail (pessoal) + Calendar do Mac (profissional).

Eventos:
- UserPromptSubmit: se o prompt pede agenda, marca a virada e (no Claude) injeta contexto.
- PreToolUse / PostToolUse: registra icalBuddy/agenda.sh e Google Calendar MCP.
- Stop: bloqueia se a virada era de agenda e faltou alguma fonte.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

AGENDA_CONTEXT = (
    "AGENDA — duas fontes obrigatórias, nunca alternativas. "
    "Gmail (Google Calendar MCP) = pessoal. "
    "Calendar do Mac (`bash harness/scripts/agenda.sh`, icalBuddy/EventKit, Exchange) = profissional. "
    "Consulte as duas no mesmo intervalo antes de responder. "
    "Gmail vazio ≠ dia livre. Siga harness/operations/agenda.md. "
    "Nunca reexibir senha, link de reunião ou lista crua de participantes."
)

# Pedidos de agenda do usuário — não dispara em "agenda de produto" / "agenda Salesforce",
# nem em "agenda com Fulano" no sentido de reunião/transcrição já ocorrida.
#
# `proxim[ao]s?\s+(reuniao|call|evento)` sozinho casava com qualquer menção futura
# ("teste refutável na próxima reunião"), não só com pedido de agenda. Trocado por
# formas de pergunta/pedido explícitas (qual/quando/que horas, "tenho próxima",
# "minha próxima reunião").
#
# `\bcalendar\b` (inglês, sem acento) foi removido: "Calendar" aparece descrevendo
# o app/feature em discussões técnicas do próprio harness ("Calendar do Mac",
# "botão do Calendar do app"), sem ser pedido de agenda. `\bcalendario\b` (PT,
# raramente usado fora do sentido de agenda) e `meu\s+calend` seguem cobrindo o
# pedido pessoal legítimo. `disponibilidade` isolado também casava com uso técnico
# ("disponibilidade do servidor"); restrito a formas pessoais/temporais.
AGENDA_RE = re.compile(
    r"""
    /agenda\b
    | proximo\s+compromisso
    | meus?\s+compromissos
    | minhas?\s+proxim[ao]s?\s+agendas?\b
    | meu\s+calend
    | \bmy\s+(calendar|schedule)\b
    | \bnext\s+meeting\b
    | \bcalendario\b
    | o\s+que\s+(eu\s+)?tenho\s+(hoje|amanha|essa\s+semana|esta\s+semana|na\s+semana)
    | o\s+que\s+tem\s+(hoje|na\s+minha|na\s+agenda)
    | reunioes?\s+(de\s+)?hoje
    | reuniao\s+do\s+dia
    | minha\s+disponibilidade
    | tenho\s+disponibilidade
    | disponibilidade\s+(hoje|amanha|essa\s+semana|esta\s+semana|de\s+horario)
    | horario\s+livre
    | planejamento\s+(do\s+dia|da\s+semana|de\s+horario)
    | (qual|quando|que\s+horas?)\s+(e\s+)?(a\s+)?(minha\s+)?proxim[ao]s?\s+(reuniao|call|evento)
    | tenho\s+(alguma\s+)?proxim[ao]
    | minha\s+proxim[ao]\s+(reuniao|call|evento)
    | compromissos?\s+(hoje|amanha)
    | estou\s+livre
    | fica\s+livre
    | icalbuddy
    """,
    re.I | re.X,
)

# Molduras de mensagens de outro agente/subagente chegando ao UserPromptSubmit
# como se fossem prompt do usuário (relatório de subagente, hand-back, notificação
# de tarefa assíncrona). Não são pedido de agenda do usuário — e não devem alterar
# o estado do turno: nem marcar `required` (falso positivo), nem resetar uma
# exigência de agenda real que já esteja em aberto no mesmo turno (o reset ocorreria
# entre a pergunta do usuário e as fontes ainda sendo consultadas, apagando a
# exigência antes do Stop poder cobrá-la).
AGENT_MESSAGE_RE = re.compile(
    r"<agent-message\b|\[Subagent hand-back\]|<task-notification>",
    re.I,
)


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def event_name(data: dict) -> str:
    raw = (
        data.get("hookEventName")
        or data.get("hook_event_name")
        or os.environ.get("GROK_HOOK_EVENT")
        or ""
    )
    return re.sub(r"[^a-z]", "", str(raw).lower())


def session_id(data: dict) -> str:
    sid = (
        data.get("sessionId")
        or data.get("session_id")
        or os.environ.get("GROK_SESSION_ID")
        or ""
    )
    sid = str(sid)
    if not sid or re.search(r"[^a-zA-Z0-9_-]", sid):
        return ""
    return sid


def prompt_id(data: dict) -> str:
    pid = data.get("promptId") or data.get("prompt_id") or "latest"
    pid = str(pid)
    if not pid or re.search(r"[^a-zA-Z0-9._-]", pid):
        return "latest"
    return pid


def prompt_text(data: dict) -> str:
    for key in ("prompt", "user_prompt", "userPrompt", "text", "content"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return ""


def tool_blob(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False).lower()


def state_dir(sid: str, pid: str) -> str:
    path = os.path.join("/tmp", f"sb-agenda-{sid}", pid)
    os.makedirs(path, exist_ok=True)
    return path


def mark(path: str, name: str) -> None:
    with open(os.path.join(path, name), "w", encoding="utf-8") as fh:
        fh.write("1\n")


def flagged(path: str, name: str) -> bool:
    return os.path.isfile(os.path.join(path, name))


def reset(path: str) -> None:
    for name in ("required", "mac", "gmail"):
        try:
            os.remove(os.path.join(path, name))
        except FileNotFoundError:
            pass


def is_agenda_prompt(text: str) -> bool:
    return bool(AGENDA_RE.search(fold(text)))


def looks_mac(blob: str) -> bool:
    return "icalbuddy" in blob or "harness/scripts/agenda.sh" in blob or "harness/scripts/agenda " in blob


def looks_gmail(blob: str) -> bool:
    return "google_calendar" in blob or "google-calendar" in blob


def emit(obj: dict) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def block(reason: str) -> None:
    emit({"decision": "block", "reason": reason})


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(data, dict):
        return 0

    sid = session_id(data)
    if not sid:
        return 0

    ev = event_name(data)
    pid = prompt_id(data)
    here = state_dir(sid, pid)
    latest = state_dir(sid, "latest")

    if ev in {"userpromptsubmit", "beforesubmitprompt"}:
        text = prompt_text(data)
        if AGENT_MESSAGE_RE.search(text):
            # Não é prompt do usuário: nem marca `required` nem reseta o estado
            # do turno (ver comentário em AGENT_MESSAGE_RE). Ignora e sai.
            return 0
        # Cada novo prompt começa do zero — não deixa a exigência de uma
        # pergunta de agenda antiga bloquear turnos seguintes sem relação.
        reset(latest)
        if is_agenda_prompt(text):
            mark(here, "required")
            mark(latest, "required")
            emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": AGENDA_CONTEXT,
                    }
                }
            )
        return 0

    if ev in {"pretooluse", "posttooluse", "posttoolusefailure"}:
        blob = tool_blob(data)
        if looks_mac(blob):
            mark(here, "mac")
            mark(latest, "mac")
        if looks_gmail(blob):
            mark(here, "gmail")
            mark(latest, "gmail")
        return 0

    if ev != "stop":
        return 0

    reason = str(data.get("reason") or "")
    if reason in {"channel_closed", "shutdown"}:
        return 0

    required = flagged(here, "required") or flagged(latest, "required")
    if not required:
        return 0

    mac = flagged(here, "mac") or flagged(latest, "mac")
    gmail = flagged(here, "gmail") or flagged(latest, "gmail")
    stop_active = bool(data.get("stopHookActive") or data.get("stop_hook_active"))

    if not mac:
        block(
            "Agenda incompleta: falta o Calendar do Mac (profissional). "
            "Rode `bash harness/scripts/agenda.sh` (icalBuddy / Exchange) no mesmo intervalo. "
            "Gmail sozinho não basta. Playbook: harness/operations/agenda.md."
        )
        return 0

    if not gmail and not stop_active:
        block(
            "Agenda incompleta: falta o Gmail (pessoal). "
            "Consulte Google Calendar MCP (`google_calendar__search`) no mesmo intervalo. "
            "Se o MCP não estiver nesta sessão, declare a lacuna e consulte o Mac mesmo assim. "
            "Calendar do Mac sozinho não basta quando o MCP está disponível."
        )
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
