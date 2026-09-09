#!/usr/bin/env python3
"""Statusline da delegacao externa do Thinker.

Le somente o estado local da extensao; nao le prompts, nao consulta modelos e
nao tenta representar agentes nativos de nenhuma CLI.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path


def arguments():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--state-dir")
    parser.add_argument("--session", default=os.environ.get("THINKER_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID"))
    parser.add_argument("--claude-statusline", action="store_true", help="Ler somente identidade de sessão do stdin do host")
    parser.add_argument("--all-sessions", action="store_true")
    parser.add_argument("--watch", type=int, metavar="SEG",
                        help="Reemite por no maximo SEG segundos (1-60)")
    parser.add_argument("--help", action="help")
    return parser.parse_args()


def main():
    args = arguments()
    if args.claude_statusline:
        raw = sys.stdin.read(65536)
        try:
            # Claude may invoke a statusLine without context on the first draw.
            # Vazio significa identidade desconhecida e usa o fallback de todos
            # os jobs existentes; JSON malformado continua sendo desconhecido.
            if raw.strip():
                data = json.loads(raw)
                args.session = data.get("session_id") or args.session
        except (ValueError, AttributeError):
            print("delegacao: estado desconhecido")
            return 0
    if args.watch is not None and not 1 <= args.watch <= 60:
        print("delegacao externa: estado desconhecido")
        return 0
    sys.dont_write_bytecode = True
    scripts = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    try:
        from thinker_delegation import board
        from thinker_delegation.runtime import DelegationStore

        # Sem sessao, o unico fallback honesto para uma statusline instalada
        # globalmente e observar os jobs ja existentes deste vault.
        all_sessions = args.all_sessions or not args.session
        store = DelegationStore(args.vault, args.state_dir)
        deadline = time.monotonic() + (args.watch or 0)
        while True:
            data = snapshot(store, args.session, all_sessions)
            print(board.render_indicator(data))
            if args.watch is None or time.monotonic() >= deadline:
                break
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    except (OSError, ValueError, ImportError):
        # Statuslines devem permanecer nao bloqueantes. "desconhecido" e
        # distinto de quatro zeros quando o estado nao pode ser lido.
        print("delegacao externa: estado desconhecido")
    return 0


def snapshot(store, session, all_sessions):
    """Leitura consistente, compartilhada e nao bloqueante do estado privado.

    `DelegationStore.list_jobs()` recupera jobs e pode adquirir lock exclusivo;
    isto e correto para a CLI de controle, mas errado numa statusline. Aqui o
    lock compartilhado bloqueia escritores enquanto o snapshot e montado e a
    contencao vira estado desconhecido, nunca espera nem zero fabricado.
    """
    # `main` importa localmente para manter o entrypoint leve, mas `snapshot`
    # tambem e chamado por testes e pelo watcher; mantenha todas as referencias
    # que ele usa no seu proprio escopo.
    from thinker_delegation import board, native
    from thinker_delegation.runtime import DelegationError
    if not store.state.exists():
        class EmptyStore:
            def list_jobs(self):
                return []
            def status(self, ignored):
                return store.status(ignored)
        return board.payload(EmptyStore(), session, all_sessions, limit=24,
                             native_reports=native.snapshot(store, session, all_sessions, locked=True))

    lock_path = store.state / ".lock"
    try:
        fd = os.open(lock_path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        raise DelegationError("Delegation state is incomplete") from None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DelegationError("Delegation state is busy") from None
        jobs = [store._get_locked(path.parent.name) for path in store._paths()]
        # _get_locked validates ownership, identifier and file safety, but does
        # not recover/mutate active jobs or dereference their prompt snapshots.
        class SnapshotStore:
            def list_jobs(self):
                return jobs
            def status(self, ignored):
                return store.status(ignored)
        return board.payload(SnapshotStore(), session, all_sessions, limit=24,
                             native_reports=native.snapshot(store, session, all_sessions, locked=True))
    finally:
        os.close(fd)


if __name__ == "__main__":
    raise SystemExit(main())
