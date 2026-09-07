#!/usr/bin/env python3
"""Thinker optional delegation: a small human/agent interface, no third-party deps."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

sys.dont_write_bytecode = True
from thinker_delegation import adapters
from thinker_delegation.runtime import DelegationStore, DelegationError, _atomic, _read
from thinker_delegation.git_publish import prepare_plan, execute_plan, PublicationError, _load_plan

LABELS = {"queued": "na fila", "running": "em andamento", "completed": "concluído",
          "failed": "falhou", "cancelled": "cancelado", "timed_out": "prazo encerrado",
          "interrupted": "interrompido"}


def parser():
    p = argparse.ArgumentParser(description="Delegação opcional do Thinker. Começa desligada.")
    p.add_argument("--vault", default=str(Path(__file__).resolve().parents[2]))
    p.add_argument("--state-dir", help="Área privada de estado; útil para laboratório isolado")
    p.add_argument("--session", default=os.environ.get("THINKER_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID"))
    p.add_argument("--json", action="store_true", help="Saída estruturada para o agente principal")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Estado, limites e sessão; não inicia agentes")
    on = sub.add_parser("on", help="Ativar explicitamente para esta sessão")
    on.add_argument("--mode", choices=["request", "auto"], default="request")
    on.add_argument("--model", choices=sorted(adapters.PROFILES), help="Preferência desta sessão")
    on.add_argument("--parallel", type=int, choices=range(1, 9), default=2)
    off = sub.add_parser("off", help="Desligar e solicitar cancelamento dos trabalhos próprios")
    off.add_argument("--all", action="store_true", help="Desligamento geral do vault")
    doctor = sub.add_parser("doctor", help="Verificar CLIs sem iniciar tarefas de modelo")
    doctor.add_argument("--model", choices=sorted(adapters.PROFILES))
    route = sub.add_parser("route", help="Explicar uma escolha sem executar nem mudar o padrão")
    submit = sub.add_parser("submit", help="Delegar uma contribuição delimitada em segundo plano")
    for command in (route, submit):
        command.add_argument("--task", choices=sorted(adapters.DEFAULT_ROUTES), default="review")
        command.add_argument("--model", help="Escolha explícita: tem prioridade sobre sessão e padrão")
        command.add_argument("--provider", choices=["codex", "claude", "grok"])
        command.add_argument("--effort", choices=sorted(adapters.EFFORTS))
    brief = submit.add_mutually_exclusive_group(required=True)
    brief.add_argument("--brief", help="MD/texto de instrução preparado pelo principal, dentro do vault")
    brief.add_argument("--prompt", help="Instrução curta; prefira --brief para textos longos")
    submit.add_argument("--file", action="append", default=[], help="Arquivo de contexto selecionado; repetível")
    submit.add_argument("--reason", required=True, help="Motivo curto da delegação")
    submit.add_argument("--timeout", type=float, default=300)
    for name, help_text in (("result", "Ler a contribuição"), ("accept", "Materializar um novo draft para coautoria"),
                            ("cancel", "Solicitar cancelamento"), ("retry", "Nova tentativa explícita"),
                            ("ack", "Marcar entrega como recebida")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("job")
    waiting = sub.add_parser("wait", help="Aguardar por até 60 segundos, mantendo resultado recuperável")
    waiting.add_argument("job")
    waiting.add_argument("--seconds", type=float, default=20)
    sub.add_parser("inbox", help="Entregas ainda não reconhecidas")
    history = sub.add_parser("history", help="Histórico de uso, escolhas e avaliações")
    history.add_argument("--export", action="store_true", help="Criar novo MD em drafts/delegation")
    feedback = sub.add_parser("feedback", help="Registrar avaliação explícita do usuário")
    feedback.add_argument("job")
    feedback.add_argument("--value", choices=["useful", "not_useful", "unknown"], required=True)
    feedback.add_argument("--note", default="")
    local = sub.add_parser("record", help="Registrar decisão de trabalhar no principal")
    local.add_argument("--task", choices=sorted(adapters.DEFAULT_ROUTES), default="review")
    local.add_argument("--reason", required=True)
    defaults = sub.add_parser("set-default", help="Alterar padrão durável apenas por pedido explícito")
    defaults.add_argument("--task", choices=sorted(adapters.DEFAULT_ROUTES), required=True)
    defaults.add_argument("--model", choices=sorted(adapters.PROFILES), required=True)
    defaults.add_argument("--reason", required=True)
    git = sub.add_parser("git", help="Publicação Git determinística, com autorização e escopo separados")
    commands = git.add_subparsers(dest="git_command", required=True)
    prepare = commands.add_parser("prepare", help="Preparar plano revisável, sem commit ou push")
    prepare.add_argument("--action", choices=["commit", "push", "commit-push"], required=True)
    prepare.add_argument("--authority-reference", required=True)
    prepare.add_argument("--authorize-commit", action="store_true")
    prepare.add_argument("--authorize-push", action="store_true")
    prepare.add_argument("--expected-branch", required=True)
    prepare.add_argument("--remote", default="origin")
    prepare.add_argument("--expected-remote", required=True)
    prepare.add_argument("--file", action="append", default=[])
    prepare.add_argument("--existing-commit", action="append", default=[])
    prepare.add_argument("--message")
    prepare.add_argument("--job", help="Contribuição Git do modelo efetivamente executado")
    execute = commands.add_parser("execute", help="Executar o plano já revisado pelo principal")
    execute.add_argument("plan", help="UUID do plano retornado por git prepare")
    return p


def session(args):
    if not args.session:
        raise DelegationError("Indique --session com o ID desta conversa. Não reutilize IDs entre terminais.")
    return args.session


def enabled(store, args):
    sid = session(args)
    if not store.status(sid).get("enabled"):
        raise DelegationError("Delegação desligada nesta sessão. Ative explicitamente com on.")
    return sid


def job_id(store, value, sid=None):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f][0-9a-f-]{0,35}", value):
        raise DelegationError("Indique um ID ou prefixo hexadecimal válido; consulte inbox/status.")
    found = [j for j in store.list_jobs(sid) if j["id"].startswith(value)]
    if len(found) != 1:
        raise DelegationError("Trabalho não encontrado ou ID ambíguo; consulte inbox/status.")
    return found[0]["id"]


def policy(store):
    value = _read(store.state / "policy.json", {"defaults": {}, "decisions": []})
    if not isinstance(value, dict) or not isinstance(value.get("defaults"), dict) or not isinstance(value.get("decisions"), list):
        raise DelegationError("Política de roteamento inválida; nenhuma rota será executada.")
    for task, name in value["defaults"].items():
        if task not in adapters.DEFAULT_ROUTES or name not in adapters.PROFILES:
            raise DelegationError("Política contém tarefa ou perfil desconhecido.")
    return value


def resolve(store, args):
    preference = store.status(args.session).get("profile") if args.session else None
    result = adapters.resolve_profile(args.task, explicit=args.model, effort=args.effort,
                                      provider=args.provider, session_profile=preference,
                                      defaults=policy(store)["defaults"])
    result["auth"] = "subscription"
    adapters.validate_profile(result)
    return result


def public_job(job):
    keys = ("id", "session", "state", "task_type", "reason", "created_at", "started_at", "finished_at",
            "transport_success", "validation", "acceptance", "accepted_path", "acceptance_action", "feedback", "feedback_note", "error", "error_code",
            "cancel_requested", "stale", "accepted_stale", "accepted_stale_sources", "model_source", "attempt_id", "retry_of")
    result = {key: job[key] for key in keys if key in job}
    result["profile"] = {key: job.get("profile", {}).get(key) for key in
                         ("provider", "model", "effort", "model_source", "cli_version", "isolation")}
    if job.get("result"):
        result["model_reported"] = job["result"].get("model_reported")
    return result


def new_history_draft(store, content):
    name = "historico-" + time.strftime("%Y-%m-%d") + "-" + uuid.uuid4().hex + ".md"
    destination = store.vault / "drafts" / "delegation" / name
    directory_fd = os.open(store.vault, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".historico-" + uuid.uuid4().hex
    try:
        for component in ("drafts", "delegation"):
            try:
                os.mkdir(component, dir_fd=directory_fd)
            except FileExistsError:
                pass
            try:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            except OSError:
                raise DelegationError("Destino do histórico deve ser diretório real, sem symlink.") from None
            os.close(directory_fd)
            directory_fd = next_fd
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd, follow_symlinks=False)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass
        os.close(directory_fd)
    return str(destination)


def git_history(store, sid):
    """Audit only this session's persisted plans, not inferred model activity."""
    plans = store.state / "git-plans"
    if not sid or not plans.exists():
        return ""
    entries = []
    for owner_path in sorted(plans.glob("*.owner.json")):
        owner = _read(owner_path, {})
        if owner.get("session") != sid or owner.get("vault") != str(store.vault):
            continue
        identifier = owner_path.name.removesuffix(".owner.json")
        try:
            if str(uuid.UUID(identifier)) != identifier:
                raise ValueError()
        except ValueError:
            continue
        try:
            plan = _load_plan(plans / (identifier + ".json"))
        except PublicationError:
            entries.append(f"### Plano {identifier}\n\nRegistro inválido; resultado não verificado.\n")
            continue
        spec, outcome = plan["spec"], plan["outcome"]
        if spec["repo"] != str(store.vault):
            continue
        metadata = spec.get("job_metadata", {})
        # All Git actions are deterministic. A model may have contributed an
        # earlier review; its completion never proves commit/push completion.
        entry = (f"### Plano {identifier}\n\n"
                 f"Ação: `{spec['action']}`. Resultado registrado: `{outcome['status']}`. "
                 "Execução Git determinística.\n\n")
        if metadata.get("job_id"):
            entry += (f"Contribuição vinculada: `{metadata['job_id']}`; "
                      f"{metadata.get('provider', 'não informado')} / {metadata.get('model', 'não informado')} "
                      f"({metadata.get('effort', 'esforço não informado')}).\n\n")
        else:
            entry += "Sem contribuição de modelo vinculada a esta publicação.\n\n"
        commit = outcome.get("commit_sha") or "não confirmado"
        remote = outcome.get("remote_sha") or ("não solicitado" if spec["action"] == "commit" else "não confirmado")
        parity = "confirmada" if outcome.get("parity") is True else "divergente" if outcome.get("parity") is False else "não verificada"
        entry += f"Commit: `{commit}`. SHA remoto: `{remote}`. Paridade: {parity}.\n"
        entries.append(entry)
    return ("\n## Publicações Git desta sessão\n\n" + "\n".join(entries)) if entries else ""


def dispatch(store, args):
    command = args.command
    if os.environ.get("THINKER_DELEGATION_CHILD") == "1" and command not in {"status", "route"}:
        raise DelegationError("Um colaborador não pode delegar, publicar ou alterar o controle do principal.")
    if command == "status":
        result = store.status(args.session)
        result["defaults"] = {**adapters.DEFAULT_ROUTES, **policy(store)["defaults"]}
        result["jobs"] = [public_job(j) for j in store.list_jobs(args.session)] if store.state.exists() else []
        return result
    if command == "on":
        sid = session(args)
        store.configure(enabled=True, concurrency=args.parallel)
        return store.set_session(sid, True, args.mode, profile=args.model)
    if command == "off":
        if args.all:
            result = store.configure(enabled=False)
        else:
            result = store.set_session(session(args), False)
        result["message"] = "Desligado. Novos trabalhos bloqueados; cancelamento solicitado aos trabalhos ativos."
        return result
    if command == "doctor":
        results = []
        for name in ([args.model] if args.model else ["luna", "sonnet", "grok"]):
            try:
                profile = adapters.resolve_profile(explicit=name)
                result = adapters.probe(profile, cwd=store.vault)
                result.update(profile=name, ready=True)
            except (adapters.AdapterError, OSError, ValueError) as error:
                result = {"profile": name, "ready": False, "error": str(error)}
            results.append(result)
        return {"providers": results, "note": "Verifica interface da CLI; acesso ao modelo e conclusão exigem teste real."}
    if command == "route":
        return resolve(store, args)
    if command == "submit":
        sid = enabled(store, args)
        profile = resolve(store, args)
        # Probe in a neutral existing directory: live vault integrations are not worker integrations.
        profile.update(adapters.probe(profile, cwd=str(Path(os.environ.get("TMPDIR", "/tmp")).resolve())))
        task = store._source(args.brief)["text"] if args.brief else args.prompt
        context_paths = [*args.file, *([args.brief] if args.brief else [])]
        return public_job(store.submit(sid, profile, task, context_paths=context_paths,
                                       timeout=args.timeout, model_source=profile["model_source"],
                                       reason=args.reason, task_type=args.task))
    if command == "set-default":
        with store._lock():
            value = policy(store)
            previous = value["defaults"].get(args.task, adapters.DEFAULT_ROUTES[args.task])
            value["defaults"][args.task] = args.model
            value["decisions"].append({"date": time.strftime("%Y-%m-%d"), "task": args.task,
                                       "previous": previous, "model": args.model,
                                       "reason": args.reason[:1000], "source": "explicit_user_request"})
            _atomic(store.state / "policy.json", value)
        return {"task": args.task, "default": args.model, "message": "Padrão atualizado por pedido explícito."}
    if command == "inbox":
        jobs = [public_job(j) for j in store.list_jobs(args.session)
                if j["state"] not in {"queued", "running"} and not j.get("acknowledged")]
        return {"jobs": jobs, "message": "Nenhuma entrega pendente." if not jobs else "Entregas disponíveis para revisão."}
    if command == "history":
        content = store.history(args.session) + git_history(store, args.session)
        decisions = policy(store)["decisions"]
        if decisions:
            content += "\n## Mudanças explícitas de padrão\n\n"
            for d in decisions:
                content += f"- {d['date']}: {d['task']} — {d['previous']} → {d['model']}.\n"
        if args.export:
            with store._lock():
                enabled(store, args)
                return {"history_path": new_history_draft(store, content)}
        return {"markdown": content}
    if command == "record":
        enabled(store, args)
        return store.record_local(args.session, reason=args.reason, task_type=args.task)
    if command == "git":
        sid = enabled(store, args)
        plans = store.state / "git-plans"
        if args.git_command == "prepare":
            plans.mkdir(mode=0o700, exist_ok=True)
            plan_name = str(uuid.uuid4())
            metadata = None
            if args.job:
                job = store.get(job_id(store, args.job, sid))
                if job["state"] != "completed" or job["validation"] != "valid" or job.get("task_type") != "git":
                    raise DelegationError("A contribuição Git precisa estar concluída e válida antes da publicação.")
                metadata = {"job_id": job["id"], **{k: job["profile"][k] for k in ("provider", "model", "effort")}}
            result = prepare_plan(repo=store.vault, plan_path=plans / (plan_name + ".json"),
                                  expected_branch=args.expected_branch, remote_name=args.remote,
                                  expected_remote_url=args.expected_remote, action=args.action,
                                  authority={"reference": args.authority_reference,
                                             "commit": args.authorize_commit, "push": args.authorize_push},
                                  files=args.file, message=args.message,
                                  authorized_existing_commits=args.existing_commit, job_metadata=metadata)
            # Owner binding is external to the plan's integrity digest.
            _atomic(plans / (plan_name + ".owner.json"), {"session": sid, "vault": str(store.vault)})
            return {"plan_id": plan_name, "plan": result, "message": "Plano preparado; ainda não foi executado."}
        try:
            identifier = str(uuid.UUID(args.plan))
        except ValueError:
            raise DelegationError("ID de plano inválido.") from None
        owner = _read(plans / (identifier + ".owner.json"), {})
        if owner.get("session") != sid or owner.get("vault") != str(store.vault):
            raise DelegationError("Plano não pertence a esta sessão e a este vault.")
        enabled(store, args)
        return execute_plan(plans / (identifier + ".json"), execution_guard=lambda: enabled(store, args))
    if command in {"accept", "retry", "cancel", "ack", "feedback"}:
        session(args)
    identifier = job_id(store, args.job, args.session)
    if command in {"accept", "retry"}:
        enabled(store, args)
    if command == "wait":
        if not 0 <= args.seconds <= 60:
            raise DelegationError("A espera deve ficar entre 0 e 60 segundos.")
        deadline = time.monotonic() + args.seconds
        while True:
            job = store.get(identifier)
            if job["state"] not in {"queued", "running"} or time.monotonic() >= deadline:
                return public_job(job)
            time.sleep(0.2)
    if command == "result":
        job = store.get(identifier)
        result = public_job(job)
        result["result"] = job.get("result")
        return result
    if command == "feedback":
        return public_job(store.feedback(identifier, args.value, args.note))
    method = {"accept": store.accept, "cancel": store.cancel, "retry": store.retry, "ack": store.acknowledge}[command]
    return public_job(method(identifier))


def render(value):
    if "markdown" in value:
        return value["markdown"]
    if value.get("result"):
        return value["result"]["text"]
    if "history_path" in value:
        return "Histórico pronto: " + value["history_path"]
    if "providers" in value:
        return "\n".join(f"{p['profile']}: " + (p.get("cli_version", "compatível") if p["ready"] else p["error"])
                         for p in value["providers"]) + "\n" + value["note"]
    if "enabled" in value:
        state = "ligada" if value["enabled"] else "desligada"
        return (f"Delegação {state}" + (f" nesta sessão ({value['session']})." if value.get("session") else ".")
                + "\n" + value.get("message", "Ative somente quando quiser usar a extensão." if not value["enabled"] else "Você pode continuar a conversa enquanto os colaboradores trabalham."))
    if "jobs" in value:
        return value.get("message", "") + "\n" + "\n".join(render(j) for j in value["jobs"])
    if "state" in value:
        model = value.get("profile", {}).get("model") or "modelo não informado"
        text = f"{value['id'][:8]} · {model} · {LABELS.get(value['state'], value['state'])}"
        if value.get("cancel_requested") and value["state"] in {"running", "queued"}:
            text += " · cancelamento solicitado"
        if value.get("accepted_path"):
            text += "\nRascunho: " + value["accepted_path"]
        if value.get("error"):
            text += "\nA execução não produziu uma entrega utilizável; consulte --json result JOB para diagnóstico."
        return text
    return json.dumps(value, ensure_ascii=False, indent=2)


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        store = DelegationStore(args.vault, args.state_dir)
        value = dispatch(store, args)
        print(json.dumps(value, ensure_ascii=False, indent=2) if args.json else render(value))
        return 0
    except (DelegationError, adapters.AdapterError, PublicationError, OSError, ValueError) as error:
        value = {"error": str(error), "code": getattr(error, "code", "delegation_refused")}
        print(json.dumps(value, ensure_ascii=False) if args.json else "Não executei: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
