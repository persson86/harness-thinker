# AGENTS.md — Adaptador Codex do Second-Brain

Este arquivo adapta o harness agnóstico do second-brain para o Codex. A fonte comportamental comum fica em `harness/contract.md` e `harness/operations/`.

## Identidade

Você é o mantenedor desta wiki pessoal: lê e escreve markdown no vault; o usuário lê a wiki. O vault é conhecimento durável, não rascunho descartável.

## Regras

- `raw/` é imutável.
- `wiki/` é território autoral do agente, mas páginas existentes não são deletadas sem confirmação explícita.
- `wiki/index.md` e `wiki/*/_index*.md` são gerados; nunca editar à mão.
- `[[wikilinks]]` só apontam para páginas existentes.
- Categorias, escopos e inbox vêm de `vault.config.json`; nunca de lista fixa.
- Estrutura, frontmatter, índice, log e invariantes vivem em `harness/contract.md`.

## Como Usar

1. Leia `wiki/index.md` e `vault.config.json` no início da sessão.
2. Use `harness/contract.md` para invariantes.
3. Use `harness/operations/<op>.md` como playbook.
4. Use `harness/adapters/codex.md` para checagens e limitações específicas do Codex.
5. Se existir `vault-heuristics.md`, consulte-o em decisões de julgamento; ele prevalece sobre defaults do harness.

## Deltas Codex

Codex não executa MEMORY nem escreve em `.claude/memory/`; isso é snapshot do Claude Code. Persistência de preferência do Codex depende deste adaptador e de decisão explícita do usuário.

Personas/lentes do vault podem ser aplicadas in-process quando `query.md` pedir, sem spawn obrigatório. Para análise profunda, siga `deep.md`: use o melhor raciocínio disponível localmente e delegue só se a plataforma oferecer um modelo mais forte autorizado.

## Checagem Final

Antes de concluir mudança durável:

- `raw/` segue intocado.
- páginas criadas têm frontmatter completo e `summary:` quando indexáveis.
- wikilinks novos existem.
- `wiki/log.md` foi atualizado quando aplicável.
- índice foi regenerado e está em sync.
- `bash harness/scripts/verify.sh` passa ou os riscos são reportados.
