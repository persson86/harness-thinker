# Adaptador Claude Code

Este adaptador registra o estado atual do Claude Code. Nesta fase, ele e preservado integralmente.

## Fonte operacional

- `CLAUDE.md`: constituicao do agente Claude.
- `.claude/commands/`: playbooks acionados por slash commands.
- `/thinker-advisor` e `/thinker-reviewer`, ou necessidade concreta reconhecida pelo Orquestrador: `harness/operations/advisor.md`, `reviewer.md` e política comum `consult.md`. Autonomia vem ligada e respeita toggle e orçamento; pedidos explícitos não a religam. Antes de cada consulta nativa use `consult admit/start`, depois do retorno `consult finish`. A CLI não intercepta a ferramenta Agent do host; controle nativo cooperativo, sem promessa de bloqueio técnico universal. Use o host para cancelamento e reporte apenas o que foi confirmado. Reviewer de fallback (Codex indisponível): ferramenta Agent com subagente novo e `model` explícito (Fable, Opus ou outro); nunca `subagent_type: fork`, que herda a conversa, nem `SendMessage` a agente existente.
- `/thinker-rea` e pedidos naturais para entender repositórios, sistemas ou funcionalidades: `harness/operations/rea.md`, compartilhado com a skill Codex `thinker-rea`. Consultas simples admitem resposta direta; profundidade e evidência seguem a pergunta.
- `/thinker-release` e pedidos de release ou nova versão de qualquer projeto: `harness/operations/release.md`, compartilhado com a skill Codex `thinker-release`. Pedido explícito autoriza a sequência completa; menção implícita só mostra o plano.
- `.claude/hooks/`: enforcement mecanico.
- `.claude/settings.json`: wiring de permissoes e hooks.
- `.claude/scripts/build-index.py`: gerador e verificador do indice.

## Regra desta fase

Nao alterar `CLAUDE.md`, `.claude/settings.json`, `.claude/commands/` ou `.claude/hooks/` para suportar Codex ou Grok. Esse suporte e aditivo e vive em `AGENTS.md` + `harness/`.

## Correspondencia com o contrato

- Protecao de `raw/`: `protect-raw.sh` em `PreToolUse`.
- Tracking de paginas novas: `track-ingest.sh` em `PostToolUse`.
- Gate de encerramento: `check-ingest.sh` em `Stop`.
- Compactação: `autoCompactWindow` (300 mil tokens) em `.claude/settings.json`; sem ele, modelos de 1M nativo só compactam perto de 967 mil. Valor local prevalece no update; `--autocompact` ou `CLAUDE_CODE_AUTO_COMPACT_WINDOW` sobrescrevem por sessão.
- Pós-compactação: `post-compact.sh` em `SessionStart` (matcher `compact`) lembra que o resumo é memória, não fonte nem autorização ampliada. Não lê transcript nem aciona nada.
- Indice gerado: `.claude/scripts/build-index.py generate`.
- Checagem de sincronia: `.claude/scripts/build-index.py check`.
- Memoria (MEMORY): skill `/memory` (`.claude/commands/memory.md`) escreve na memoria viva do projeto no Claude Code (`~/.claude/projects/<este-vault>/memory/`, subdir derivado do path do vault); um eventual `.claude/memory/` no repo de dados e so snapshot de backup. Capacidade especifica do Claude Code (ver `harness/contract.md` > Capacidades Claude-only).

## Calendario

Gmail (Google Calendar MCP) = pessoal. Calendar do Mac (`bash harness/scripts/agenda.sh`) = profissional. Sempre as duas, em qualquer mencao a agenda, calendario, reuniao do dia, disponibilidade ou planejamento de horario. Playbook: `harness/operations/agenda.md`. Gmail vazio nao implica dia livre. Nunca reexibir senha, link de reuniao ou lista crua de participantes. UserPromptSubmit injeta o lembrete; o Stop gate (`agenda-gate`) bloqueia virada de agenda sem as duas fontes.

## Observacao

O contrato agnostico em `harness/contract.md` descreve o comportamento comum. O Claude Code continua usando sua implementacao atual ate uma migracao explicita futura.
