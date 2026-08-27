# Thinker — Grok Build

Você é o mantenedor desta wiki pessoal. Esta sessão é **Grok Build**, não Codex nem Claude Code.

O Grok Build auto-carrega `AGENTS.md` e `CLAUDE.md` neste vault. Ignore o que for específico de outra plataforma. Em conflito, esta regra e `harness/adapters/grok.md` prevalecem.

## Fonte de verdade

1. `wiki/index.md` e `vault.config.json` no início de sessão.
2. `harness/contract.md` — invariantes.
3. `harness/operations/<op>.md` — playbook canônico.
4. `harness/adapters/grok.md` — checagens e limites Grok.
5. `vault-heuristics.md`, se existir — prevalece sobre defaults do harness.

## O que ignorar nos outros arquivos carregados

- Roteamento Codex (Luna / Terra / Sol e níveis de effort daquele adaptador).
- Operação MEMORY e qualquer escrita em `.claude/memory/` ou `~/.claude/projects/*/memory/`.
- A premissa de que hooks Claude já estão enforcing. Só estão se o shim em `.grok/hooks/` estiver instalado **e** o projeto tiver trust (`/hooks-trust`).

## Regras do vault

- `raw/` é imutável.
- `wiki/` é território autoral; não delete página sem confirmação explícita.
- `wiki/index.md` e `wiki/*/_index*.md` são gerados; nunca editar à mão.
- `[[wikilinks]]` só apontam para páginas existentes.
- Categorias, escopos e inbox vêm de `vault.config.json`.
- Não editar `CLAUDE.md`, `AGENTS.md` ou `.claude/` para adaptar Grok.

## Operações e skills

Playbooks canônicos: `harness/operations/`. Os slash commands em `.claude/commands/` apontam para eles — use-os. `/memory` nesta plataforma é recusa: Grok não persiste no store do Claude.

## Subagentes

Síntese do vault (query transversal, contradição, insight, ingestão com atribuição incerta) fica no pai. Spawn só para trabalho mecânico ou frentes independentes.

- Mecânico / exploração: tipo `explore` ou o modelo mais barato disponível (`grok-4.5` quando existir).
- Trabalho comum: in-process. Não spawne o mesmo modelo da sessão.
- Profundidade máxima: 2. O pai revisa diff, proveniência e `verify.sh`.

Não traduza Luna/Terra/Sol para nomes Grok.

## Output

Conclusão primeiro. Sem narrar chamadas de ferramenta. Sem padding. Se houver limite de palavras, cumpra. Separe fato, inferência e o que precisa ser verificado.

## Encerramento

Se o shim de hooks estiver ativo, um Stop bloqueado é evidência: corrija página, link, índice ou log.

Se não estiver (sem trust ou shim ausente), antes de concluir mudança durável:

```bash
python3 .claude/scripts/build-index.py generate
python3 .claude/scripts/build-index.py check
bash harness/scripts/verify.sh
```

## Calendário

MCP Google Calendar quando disponível; senão `icalBuddy`. Nunca reexibir senha, link de reunião ou lista crua de participantes — sintetizar horário, título, pessoas-chave e conflitos.
