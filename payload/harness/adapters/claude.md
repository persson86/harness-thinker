# Adaptador Claude Code

Este adaptador registra o estado atual do Claude Code. Nesta fase, ele e preservado integralmente.

## Fonte operacional

- `CLAUDE.md`: constituicao do agente Claude.
- `.claude/commands/`: playbooks acionados por slash commands.
- `.claude/hooks/`: enforcement mecanico.
- `.claude/settings.json`: wiring de permissoes e hooks.
- `.claude/scripts/build-index.py`: gerador e verificador do indice.

## Regra desta fase

Nao alterar `CLAUDE.md`, `.claude/settings.json`, `.claude/commands/` ou `.claude/hooks/` para suportar Codex ou Grok. Esse suporte e aditivo e vive em `AGENTS.md` + `harness/`.

## Correspondencia com o contrato

- Protecao de `raw/`: `protect-raw.sh` em `PreToolUse`.
- Tracking de paginas novas: `track-ingest.sh` em `PostToolUse`.
- Gate de encerramento: `check-ingest.sh` em `Stop`.
- Indice gerado: `.claude/scripts/build-index.py generate`.
- Checagem de sincronia: `.claude/scripts/build-index.py check`.
- Memoria (MEMORY): skill `/memory` (`.claude/commands/memory.md`) escreve na memoria viva do projeto no Claude Code (`~/.claude/projects/<este-vault>/memory/`, subdir derivado do path do vault); um eventual `.claude/memory/` no repo de dados e so snapshot de backup. Capacidade especifica do Claude Code (ver `harness/contract.md` > Capacidades Claude-only).

## Calendario

Gmail (Google Calendar MCP) = pessoal. Calendar do Mac (`bash harness/scripts/agenda.sh`) = profissional. Sempre as duas, em qualquer mencao a agenda, calendario, reuniao do dia, disponibilidade ou planejamento de horario. Playbook: `harness/operations/agenda.md`. Gmail vazio nao implica dia livre. Nunca reexibir senha, link de reuniao ou lista crua de participantes. UserPromptSubmit injeta o lembrete; o Stop gate (`agenda-gate`) bloqueia virada de agenda sem as duas fontes.

## Observacao

O contrato agnostico em `harness/contract.md` descreve o comportamento comum. O Claude Code continua usando sua implementacao atual ate uma migracao explicita futura.
