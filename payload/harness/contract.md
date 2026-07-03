# Harness Agnostico do Second-Brain

Contrato comum do second-brain independentemente de plataforma ou modelo. Adaptadores como Claude Code e Codex traduzem este contrato para suas ferramentas locais.

## Papel

O agente e o mantenedor da wiki pessoal. O usuario le a wiki; o agente escreve, organiza e mantem conhecimento duravel em Markdown.

## Invariantes

- `raw/` e imutavel: nunca escrever, editar, mover ou deletar fontes originais.
- `wiki/` e o territorio autoral do agente.
- Nunca deletar paginas existentes sem confirmacao explicita do usuario.
- Nunca criar `[[wikilinks]]` para paginas inexistentes.
- Quando a categoria for ambigua, perguntar antes de criar pagina.
- Preservar portugues, mantendo termos tecnicos em ingles quando a traducao reduzir precisao.
- Paginas com relacoes relevantes terminam com **Conexoes**.
- Paginas derivadas de fonte em `raw/` incluem **Fonte**.

## Configuracao do Vault

Categorias sao configuracao do vault, nao do harness: vivem em `vault.config.json` (`categories` como lista `[slug, display, escopo]`, mais `subsharded`, `fast_spheres`, `inbox_dir`). Leia o config no inicio de sessao.

`vault-heuristics.md` e opcional no root do vault. Conteudo do usuario, nunca sobrescrito pelo installer. Quando existir, orienta decisoes de julgamento (priorizacao, recomendacao, arquitetura de pagina, trade-offs) e prevalece sobre defaults do harness.

Se uma fonte tocar multiplas categorias: pagina na principal, cross-links nas secundarias somente quando as paginas existirem.

## Frontmatter

Toda pagina indexavel deve abrir com:

```yaml
---
title:
summary:
category:
type: source | entity | concept | insight | inbox
tags: []
sources: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

`summary:` e obrigatorio para paginas indexaveis e e a fonte do indice gerado. Paginas no `inbox_dir` configurado nunca sao indexadas por localizacao, mesmo com `summary:`; so entram no indice ao serem promovidas para fora do inbox.

## Tipos e Localizacao

- `source`: `wiki/[categoria]/sources/[slug].md`
- `entity`: `wiki/[categoria]/[slug].md`
- `concept`: `wiki/[categoria]/[slug].md`
- `insight`: categoria cujo escopo em `vault.config.json` cobre sinteses geradas pelo vault
- `inbox`: caminho configurado em `vault.config.json` como `inbox_dir`

Slugs devem ser descritivos e em `kebab-case`.

## Indice

O indice e gerado, nao editado a mao.

- Root: `wiki/index.md`
- Shards: `wiki/[categoria]/_index.md`
- Sub-shards por tipo em esferas grandes: `wiki/[categoria]/_index-[type].md`
- Implementacao: `.claude/scripts/build-index.py`

Para refletir paginas novas, removidas ou alteracoes de `summary:`, rode `python3 .claude/scripts/build-index.py generate`. Para validar sincronia, rode `python3 .claude/scripts/build-index.py check`.

## Log

`wiki/log.md` e append-only. Adicione entradas novas no topo, sem editar historico antigo.

```markdown
## YYYY-MM-DD operacao | titulo
- Paginas criadas: [...]
- Paginas atualizadas: [...]
```

Operacoes comuns: `ingest`, `inbox`, `query`, `lint`, `update`, `feed`, `transcript`, `transcript-rebuild`, `dream`, `reverie`, `applied`.

`applied` registra proveniencia de valor quando uma pagina alimenta uma decisao ou entregavel real, a partir de evidencia citavel:

```markdown
## YYYY-MM-DD applied | [[origem]] -> entregavel/decisao real
```

## Gates de Encerramento

Antes de concluir operacao que muda conhecimento duravel:

- `raw/` segue intocado.
- Paginas criadas tem frontmatter completo.
- Paginas indexaveis tem `summary:`.
- `wiki/log.md` foi atualizado quando aplicavel.
- O indice foi regenerado quando aplicavel.
- `build-index.py check` esta em sync.
- Wikilinks novos apontam para paginas existentes.

## Capacidades Adapter-Specific

MEMORY e Claude-only: escrita na memoria viva em `~/.claude/projects/.../memory/`. Codex nao tem memoria persistente equivalente. Camadas opcionais de revisao deliberativa podem existir fora do payload, via skills/plugins user-level.

Adaptadores: `harness/adapters/claude.md` e `harness/adapters/codex.md`.
