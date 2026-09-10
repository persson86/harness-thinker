"""Board de delegação: uma tabela do que cada colaborador está fazendo.

Renderização determinística, fora do laço do modelo. O principal não precisa
gastar um turno para redesenhar o quadro, e o board não pode alucinar um estado
que o disco não tem. Funciona igual em Claude, Codex e Grok.

Dois eixos, não um: EXECUÇÃO (o processo) e ENTREGA (o que sobrou para você).
O que se perde na prática não é o job que quebrou — é o que terminou e ninguém
leu. `exit 0` só prova transporte, então a coluna diz "voltou", nunca "ok";
qualidade aparece apenas depois de `feedback`.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
import time
import unicodedata
import re

ACTIVE = {"queued", "running"}
BROKEN = {"failed", "timed_out", "interrupted"}
RECENT_SECONDS = 300

# Glifos escolhidos entre os não-emoji: ⏱ e ⚠ têm apresentação emoji e podem vir
# largos por fallback de fonte, quebrando o alinhamento da tabela inteira.
EXECUTION = {
    "queued": ("◔", "na fila", "dim"),
    "running": ("●", "rodando", "cyan"),
    "completed": ("✓", "voltou", "green"),
    "failed": ("✗", "falhou", "red"),
    "cancelled": ("⊘", "cancelado", "dim"),
    "timed_out": ("◷", "tempo esgotado", "yellow"),
    "interrupted": ("⊗", "interrompido", "yellow"),
}

# `stale` não ganha símbolo próprio: a cor e a nota abaixo da linha já dizem que
# a entrada mudou, e um glifo a mais estouraria a coluna.
DELIVERY = {
    "inbox": ("◆", "na inbox", "yellow"),
    "read": ("✓", "lido", "dim"),
    "materialized": ("★", "materializado", "green"),
    "stale": ("★", "materializado", "yellow"),
    "none": ("—", "", "dim"),
}

FEEDBACK = {"useful": ("útil", "green"), "not_useful": ("não útil", "red")}

# Os ambíguos (●◆★▓) só alargam em terminal configurado para CJK; --ascii cobre.
ASCII_MAP = {"●": "*", "◔": "o", "✓": "v", "✗": "x", "⊘": "-", "◷": "t",
             "⊗": "!", "◆": ">", "★": "#", "—": "-", "↳": "`->", "▓": "#",
             "░": ".", "↻": "@", "·": "-", "…": "..."}

ANSI = {"dim": "\033[2m", "red": "\033[31m", "green": "\033[32m",
        "yellow": "\033[33m", "cyan": "\033[36m", "bold": "\033[1m",
        "reset": "\033[0m"}


class Style:
    def __init__(self, enabled):
        self.enabled = enabled

    def __call__(self, text, color):
        if not self.enabled or not color or not text:
            return text
        return ANSI[color] + text + ANSI["reset"]


def visible_len(text):
    """Colunas ocupadas: ignora escapes ANSI e conta glifo largo como dois."""
    out, index = 0, 0
    while index < len(text):
        char = text[index]
        if char == "\033":
            while index < len(text) and text[index] != "m":
                index += 1
            index += 1
            continue
        if not unicodedata.combining(char):
            out += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
        index += 1
    return out


def pad(text, width):
    return text + " " * max(0, width - visible_len(text))


def clean(text):
    """Texto de job vira linha de terminal: sem controle, sem ANSI embutido."""
    return " ".join("".join(c for c in str(text or "") if c >= " " and c != "\x7f").split())


def clip(text, width):
    text = clean(text)
    if visible_len(text) <= width:
        return text
    end = 0
    while end < len(text) and visible_len(text[:end + 1]) <= max(0, width - 1):
        end += 1
    return text[:end].rstrip() + "…"


def to_ascii(text):
    for source, target in ASCII_MAP.items():
        text = text.replace(source, target)
    return text


def _parse(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    return parsed if parsed.tzinfo else None


def elapsed(job):
    """Duração consolidada; para job ativo, o tempo corrido até agora."""
    start = _parse(job.get("started_at")) or _parse(job.get("created_at"))
    if start is None:
        return None
    finish = _parse(job.get("finished_at"))
    if finish is None:
        if job.get("state") not in ACTIVE:
            return None
        finish = dt.datetime.now(dt.timezone.utc)
    seconds = (finish - start).total_seconds()
    return seconds if seconds >= 0 else None


def clock(seconds):
    if seconds is None:
        return "—"
    if seconds < 60:
        return "%ds" % int(seconds)
    return "%dm%02ds" % (int(seconds) // 60, int(seconds) % 60)


def bar(seconds, timeout, width=8):
    """Decorrido contra timeout. Não é progresso da tarefa: os adaptadores não
    emitem telemetria, e uma porcentagem inventada seria decoração falsa."""
    if not timeout or seconds is None or timeout <= 0:
        return ""
    filled = min(width, int(width * seconds / timeout))
    return "▓" * filled + "░" * (width - filled) + " " + clock(timeout)


def delivery_of(job):
    if job.get("state") != "completed" or job.get("validation") != "valid":
        return "none"
    if job.get("acceptance") == "accepted":
        return "stale" if job.get("accepted_stale") else "materialized"
    return "read" if job.get("acknowledged") else "inbox"


def execution_of(job):
    """Transporte falho e saída malformada não são o mesmo problema: o runtime
    grava failed com transport_success=True quando a resposta chegou e não
    passou na validação estrutural."""
    state = job.get("state", "unknown")
    symbol, label, color = EXECUTION.get(state, ("?", state, "dim"))
    note = ""
    if state == "failed":
        if job.get("transport_success"):
            label, note = "saída inválida", "resposta chegou, estrutura não validou"
        else:
            note = "transporte"
    elif state == "running":
        seconds = elapsed(job)
        if job.get("timeout") and seconds and seconds > job["timeout"]:
            note = "passou do timeout; aguardando o supervisor encerrar"
    elif state in ACTIVE and job.get("cancel_requested"):
        note = "cancelamento solicitado"
    return symbol, label, color, note


def agent_of(job):
    """O alias já é a identidade; o modelo mostra só o que ele não diz — família
    e esforço. `luna` ao lado de `gpt-5.6-luna` seria a mesma palavra duas vezes."""
    profile = job.get("profile") or {}
    alias = job.get("requested_profile") or profile.get("requested_profile")
    model = profile.get("model") or ""
    alias = alias or model or "?"
    if model == alias:
        model = profile.get("provider") or model
    elif model.endswith("-" + alias):
        model = model[: -len(alias) - 1]
    effort = profile.get("effort")
    return alias, ("%s · %s" % (model, effort) if effort else model)


def task_of(job):
    kind = job.get("task_type") or "—"
    if job.get("run_id"):
        role = (job.get("role") or "")[:3]
        kind += "·s%s%s" % (job.get("stage") or "?", "/" + role if role else "")
    if job.get("retry_of"):
        kind += " ↻"
    return kind


def payload(store, session, all_sessions=False, limit=10, native_reports=None,
            recent_seconds=RECENT_SECONDS, history=False, now=None):
    """Estado do board como dado, para --json e para o renderizador."""
    if not isinstance(recent_seconds, int) or recent_seconds < 0:
        raise ValueError("A janela recente deve ser um número inteiro de segundos >= 0")
    now = now or dt.datetime.now(dt.timezone.utc)

    def recent(value):
        timestamp = _parse(value)
        return timestamp is not None and 0 <= (now - timestamp).total_seconds() <= recent_seconds

    if native_reports is None and hasattr(store, "state"):
        from . import native
        native_reports = native.snapshot(store, session, all_sessions, locked=True)
    every = store.list_jobs()
    status = store.status(session)
    scoped = every if all_sessions else [j for j in every if j.get("session") == session]

    active = sorted((j for j in scoped if j.get("state") in ACTIVE),
                    key=lambda j: _parse(j.get("created_at")) or dt.datetime.max.replace(tzinfo=dt.timezone.utc))
    done = sorted((j for j in scoped if j.get("state") not in ACTIVE),
                  key=lambda j: _parse(j.get("finished_at")) or _parse(j.get("created_at"))
                  or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    eligible = done if history else [j for j in done if recent(j.get("finished_at"))]
    shown = active + eligible[: max(0, limit)]

    rows = []
    for job in shown:
        alias, model = agent_of(job)
        rows.append({"id": job.get("id"), "session": job.get("session"),
                     "agent": alias, "model": model,
                     "provider": (job.get("profile") or {}).get("provider"),
                     "effort": (job.get("profile") or {}).get("effort"),
                     "task_type": job.get("task_type"), "reason": clean(job.get("reason")),
                     "state": job.get("state"), "validation": job.get("validation"),
                     "transport_success": job.get("transport_success"),
                     "delivery": delivery_of(job), "feedback": job.get("feedback"),
                     "seconds": elapsed(job), "timeout": job.get("timeout"),
                     "run_id": job.get("run_id"), "stage": job.get("stage"),
                     "role": job.get("role"), "retry_of": job.get("retry_of"),
                     "cancel_requested": job.get("cancel_requested")})

    # Pendências continuam no escopo completo, mesmo depois de sair da tela.
    # Falhas recentes e antigas não compartilham o mesmo alerta visual.
    native_reports = native_reports or {"reported": 0, "running": 0, "completed": 0,
                                        "failed": 0, "cancelled": 0, "unknown": 0, "reports": []}
    reports = native_reports.get("reports", [])
    native_active = [r for r in reports if r["state"] == "running"]
    native_done = sorted((r for r in reports if r["state"] != "running" and
                          (history or recent(r.get("updated_at")))),
                         key=lambda r: r.get("updated_at") or "", reverse=True)
    native_visible = native_active + native_done[:max(0, limit)]
    native_view = {**native_reports, "visible_reports": native_visible,
                   "hidden": len(reports) - len(native_visible)}
    return {"board": {"session": session, "scope": "all" if all_sessions else "session",
                      "recent_seconds": recent_seconds, "history": history,
                      "enabled": status.get("enabled", False),
                      "global_enabled": status.get("global_enabled", False),
                      "mode": status.get("mode"),
                      "concurrency": status.get("concurrency", 0),
                      "queued": sum(1 for j in scoped if j.get("state") == "queued"),
                      "running": sum(1 for j in scoped if j.get("state") == "running"),
                      "pending": sum(1 for j in scoped if delivery_of(j) == "inbox"),
                      "waiting": sum(1 for j in shown if delivery_of(j) == "inbox"),
                      "failed": sum(1 for j in eligible if j.get("state") in BROKEN),
                      "needs_attention": sum(1 for j in scoped if j.get("state") in BROKEN and not j.get("acknowledged")),
                      "hidden_pending": sum(1 for j in scoped if j not in shown and delivery_of(j) == "inbox"),
                      "hidden_failures": sum(1 for j in scoped if j not in shown and j.get("state") in BROKEN and not j.get("acknowledged")),
                      "sessions": len({j.get("session") for j in shown + native_visible}),
                      "shown": len(shown), "hidden": len(scoped) - len(shown)},
            "jobs": rows, "native": native_view}


def render_indicator(data, model_limit=3):
    """Uma linha curta para a statusline, baseada somente no snapshot local.

    Ela cobre a extensao de delegacao entre CLIs; agentes nativos do Codex nao
    gravam este estado e, portanto, nunca sao inferidos aqui. Nao ha barra nem
    porcentagem: os adaptadores nao fornecem progresso semantico confiavel.
    """
    head, jobs, native = data["board"], data["jobs"], data.get("native", {})
    counts = "q%d r%d p%d f%d" % (head.get("queued", 0), head.get("running", 0),
                                   head.get("pending", head.get("waiting", 0)),
                                   head.get("needs_attention", head.get("failed", 0)))
    models = []
    for job in jobs:
        # Alias e a identidade mais curta; clean elimina controles antes da
        # linha chegar ao terminal e o limite evita uma statusline expansiva.
        # Remover a sequencia inteira evita expor fragmentos como "[31m" de
        # um alias malicioso; `clean` em seguida cobre controles restantes.
        name = clean(re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(job.get("agent") or "")))
        if name and name not in models:
            models.append(name)
        if len(models) >= max(0, model_limit):
            break
    suffix = " · " + ", ".join(clip(name, 18) for name in models) if models else ""
    native_counts = "r%d c%d f%d u%d" % (native.get("running", 0), native.get("completed", 0),
                                           native.get("failed", 0), native.get("unknown", 0))
    return "delegacao externa: %s%s · nativa reportada: %s" % (counts, suffix, native_counts)


def _layout(width, show_quality, show_session):
    """Degradação por largura, em ordem de dispensabilidade: a barra é redundante
    com o número ao lado; MODELO repete o que o alias já diz; QUALIDADE também
    vive em `history`. Perder coluna é melhor que deixar a linha quebrar, porque
    quebra destrói o alinhamento da tabela inteira."""
    tiers = [
        ({"agent": 8, "model": 16, "task": 14, "exec": 17, "delivery": 18}, True, show_quality, 30),
        ({"agent": 8, "model": 0, "task": 14, "exec": 17, "delivery": 18}, True, show_quality, 26),
        ({"agent": 8, "model": 0, "task": 12, "exec": 17, "delivery": 16}, False, show_quality, 18),
        ({"agent": 8, "model": 0, "task": 12, "exec": 17, "delivery": 16}, False, False, 14),
    ]
    for widths, show_bar, quality, reason in tiers:
        cost = (sum(widths.values()) + reason + 2 + 8 + (10 if quality else 0)
                + (10 if show_session else 0) + (16 if show_bar else 0))
        if cost <= width:
            break
    return widths, show_bar, quality, max(4, min(reason, width - (cost - reason)))


def render_native(reports, style, width, show_session):
    """Linhas declaradas pelo host, não telemetria de execução da extensão."""
    if not reports:
        return []
    task_width = max(8, width - 26 - 19 - 10 - (10 if show_session else 0))
    header = pad("MODELO NATIVO", 26) + pad("TAREFA", task_width)
    if show_session:
        header += pad("SESSÃO", 10)
    lines = ["", style("NATIVOS · estado reportado pelo host", "bold"),
             style(header + pad("ESTADO", 19) + "REPORTE HÁ", "dim")]
    now = dt.datetime.now(dt.timezone.utc)
    for report in reports:
        state = report["state"]
        symbol, label, tint = EXECUTION.get(state, ("?", "desconhecido", "yellow"))
        observed = _parse(report.get("updated_at"))
        age = max(0, (now - observed).total_seconds()) if observed else None
        row = pad(clip(report.get("model"), 25), 26) + pad(clip(report.get("task"), task_width - 1), task_width)
        if show_session:
            row += pad(clip(report.get("session"), 8), 10)
        row += pad(style(symbol + " " + label, tint), 19) + clock(age)
        lines.append(row)
    return lines


def render(data, color=False, ascii_only=False, width=None):
    style = Style(color)
    head, jobs = data["board"], data["jobs"]
    width = width or shutil.get_terminal_size((100, 24)).columns

    title = [style("DELEGAÇÃO", "bold")]
    if head["scope"] == "all":
        # Conta terminais que produziram jobs, não sessões registradas no
        # config: dizer "4 sessões" quando três nunca delegaram engana.
        count = head["sessions"]
        title.append("· todos os terminais · %d na tela" % count)
    else:
        title.append("· sessão " + (head["session"] or "—")[:8])
        title.append("· " + (style("ligada", "green") if head["enabled"] else style("desligada", "dim")))
        if head.get("mode"):
            title.append("· modo " + head["mode"])
    title.append("· %d/%d slots externos" % (head["running"], head["concurrency"]))
    native = data.get("native", {})
    native_visible = native.get("visible_reports", native.get("reports", []))
    focus = ("histórico" if head.get("history") else
             "ativos + finalizados nos últimos " + clock(head.get("recent_seconds", RECENT_SECONDS)))
    lines = [" ".join(title), style(focus + " · limpeza só da tela", "dim"), ""]

    if not jobs:
        lines.append(style("Nenhum job externo ativo ou recente." if not head.get("history")
                           else "Nenhum job externo neste escopo.", "dim"))

    show_session = head["scope"] == "all"
    widths, show_bar, show_quality, reason_width = _layout(
        width, any(j.get("feedback") in FEEDBACK for j in jobs), show_session)

    header = [pad("AGENTE", widths["agent"])]
    if widths["model"]:
        header.append(pad("MODELO", widths["model"]))
    header += [pad("TAREFA", widths["task"]), pad("MOTIVO", reason_width + 2)]
    if show_session:
        header.append(pad("SESSÃO", 10))
    header += [pad("EXECUÇÃO", widths["exec"]), pad("ENTREGA", widths["delivery"]), "TEMPO"]
    if show_quality:
        header.insert(-1, pad("QUALIDADE", 10))
    if jobs:
        lines.append(style("".join(header), "dim"))

    for job in jobs:
        symbol, label, color_name, note = execution_of(job)
        dsymbol, dlabel, dcolor = DELIVERY[job["delivery"]]

        moment = clock(job["seconds"])
        if job["state"] == "running":
            drawn = bar(job["seconds"], job["timeout"]) if show_bar else ""
            moment = style(moment, "cyan") + ("  " + style(drawn, "dim") if drawn else "")

        cells = [pad(style(clip(job["agent"], widths["agent"] - 1), "bold"), widths["agent"])]
        if widths["model"]:
            cells.append(pad(style(clip(job["model"], widths["model"] - 1), "dim"), widths["model"]))
        cells += [pad(clip(task_of(job), widths["task"] - 1), widths["task"]),
                  pad(clip(job["reason"], reason_width), reason_width + 2)]
        if show_session:
            cells.append(pad(style((job["session"] or "—")[:8], "dim"), 10))
        cells.append(pad(style("%s %s" % (symbol, label), color_name), widths["exec"]))
        cells.append(pad(style(("%s %s" % (dsymbol, dlabel)).strip(), dcolor), widths["delivery"]))
        if show_quality:
            value = FEEDBACK.get(job.get("feedback"))
            cells.append(pad(style(value[0], value[1]) if value else style("—", "dim"), 10))
        cells.append(moment)
        lines.append("".join(cells))

        # Logo abaixo da própria linha: duas tentativas do mesmo agente não podem
        # disputar a mesma nota de rodapé.
        notes = [note] if note else []
        if job["delivery"] == "stale":
            notes.append("a entrada mudou depois; a proposta é de versão antiga")
        lines += [style("%s↳ %s" % (" " * 8, item), "dim") for item in notes]

    lines += render_native(native_visible, style, width, show_session)

    tally = []
    if head["running"]:
        tally.append(style("%d rodando" % head["running"], "cyan"))
    if head["waiting"]:
        tally.append(style("%d esperando você" % head["waiting"], "yellow"))
    if head["failed"]:
        tally.append(style("%d com falha" % head["failed"], "red"))
    lines += ["", " · ".join(tally or [style("sem atividade externa nesta janela", "dim")])]

    if head["hidden"] or native.get("hidden"):
        lines.append(style("Fora da tela: %d externos, %d nativos. Histórico: --history --limit N."
                           % (head["hidden"], native.get("hidden", 0)), "dim"))
    if head.get("hidden_pending") or head.get("hidden_failures"):
        lines.append(style("Fora da tela: %d na inbox, %d falhas sem ack. Consulte inbox / history."
                           % (head.get("hidden_pending", 0), head.get("hidden_failures", 0)), "yellow"))
    if native.get("unknown"):
        lines.append(style("%d nativo(s) sem estado atual; consulte a UI do host." % native["unknown"], "yellow"))
    lines.append(style("Principal não monitorado; nativos exigem `native report`.", "dim"))
    if head["waiting"]:
        lines.append(style("Leia com `result JOB`; `ack JOB` tira da inbox.", "dim"))

    out = "\n".join(lines)
    return to_ascii(out) if ascii_only else out


def watch(store, session, all_sessions, limit, seconds, color, ascii_only, stream=None,
          recent_seconds=RECENT_SECONDS, history=False):
    """Laço determinístico: atualiza sem custar um turno do principal, que é o
    ponto de o board não ser desenhado pelo modelo."""
    stream = stream or sys.stdout
    interval = min(3600.0, max(1.0, float(seconds)))
    try:
        while True:
            frame = render(payload(store, session, all_sessions, limit,
                                   recent_seconds=recent_seconds, history=history), color, ascii_only)
            stamp = dt.datetime.now().strftime("%H:%M:%S")
            interactive = bool(getattr(stream, "isatty", lambda: False)()) and os.environ.get("TERM") != "dumb"
            stream.write("\033[H\033[J" if interactive else "\n" + "=" * 60 + "\n")
            stream.write(frame + "\n\n")
            stream.write(Style(color)("atualizado %s · a cada %gs · ctrl-c encerra"
                                      % (stamp, interval), "dim") + "\n")
            stream.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        stream.write("\n")
    return 0


def wants_color(no_color, stream=None):
    stream = stream or sys.stdout
    if no_color or os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)()) and os.environ.get("TERM") != "dumb"
