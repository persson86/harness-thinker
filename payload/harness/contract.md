# Harness Agnostico do Second-Brain

Este contrato descreve o comportamento comum do second-brain independentemente de plataforma ou modelo. Adaptadores como Claude Code e Codex traduzem este contrato para suas ferramentas locais.

## Papel

O agente e o mantenedor da wiki pessoal. O usuario le a wiki; o agente escreve, organiza e mantem o conhecimento duravel em Markdown.

## Invariantes

- `raw/` e imutavel: nunca escrever, editar, mover ou deletar fontes originais.
- `wiki/` e o territorio autoral do agente.
- Nunca deletar paginas existentes sem confirmacao explicita do usuario.
- Nunca criar `[[wikilinks]]` para paginas inexistentes.
- Quando a categoria for ambigua, perguntar antes de criar pagina.
- Preservar linguagem em portugues, mantendo termos tecnicos em ingles quando a traducao reduzir precisao.
- Toda pagina deve terminar com uma secao **Conexoes** quando houver relacoes relevantes.
- Paginas derivadas de fonte em `raw/` devem incluir secao **Fonte**.

## Categorias

| Categoria | Pasta | Escopo |
|---|---|---|
| AI & Tecnologia | `ai-tecnologia/` | LLMs, agentes, automacao, tools, infraestrutura, tendencias tech |
| Bitcoin & Cripto | `bitcoin-cripto/` | Bitcoin, hard money, escola austriaca, filosofia monetaria |
| Investimentos & Mercados | `investimentos/` | FIIs, renda fixa, macro, analise tecnica, portfolio |
| Product Management | `product-management/` | Frameworks, discovery, delivery, metodologias de produto |
| Business & Empreendedorismo | `business/` | Estrategia, posicionamento, vendas, modelos de negocio |
| Saude & Bem-estar | `saude-bem-estar/` | Neurodivergencia, protocolos, sono, longevidade |
| Espiritualidade & Filosofia | `espiritualidade-filosofia/` | Jung, estoicismo, sistemas, consciencia, sentido |
| Vida Profissional | `vida-profissional/` | Projetos, reunioes, perfil profissional e contexto real de trabalho |
| Lingua Inglesa | `lingua-inglesa/` | Aulas, erros diagnosticados, vocabulario e evolucao no ingles |
| Ideias & Pensamentos | `ideias-pensamentos/` | Inbox de ideias, insights e analises gerados pelo vault |

Se uma fonte tocar multiplas categorias, criar a pagina na categoria principal e adicionar cross-links nas secundarias somente quando as paginas existirem.

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

`summary:` e obrigatorio para paginas indexaveis. Ele e a fonte do indice gerado. Paginas em `ideias-pensamentos/inbox/` nunca sao indexadas — exclusao por localizacao, independente de terem `summary:`; so entram no indice ao serem promovidas para fora do inbox.

## Tipos e localizacao

- `source`: `wiki/[categoria]/sources/[slug].md`
- `entity`: `wiki/[categoria]/[slug].md`
- `concept`: `wiki/[categoria]/[slug].md`
- `insight`: `wiki/ideias-pensamentos/[slug].md`
- `inbox`: `wiki/ideias-pensamentos/inbox/[slug].md`

Slugs devem ser descritivos e em `kebab-case`.

## Indice

O indice e gerado, nao editado a mao.

- Root: `wiki/index.md`
- Shards: `wiki/[categoria]/_index.md`
- Sub-shards por tipo em esferas grandes: `wiki/[categoria]/_index-[type].md` (o `_index.md` vira shard fino com ponteiros; categorias no conjunto `SUBSHARDED` do script)
- Implementacao atual: `.claude/scripts/build-index.py`

Para refletir paginas novas, removidas ou alteracoes de `summary:`, rode:

```bash
python3 .claude/scripts/build-index.py generate
```

Para validar sincronia:

```bash
python3 .claude/scripts/build-index.py check
```

## Log

`wiki/log.md` e append-only. Adicione entradas novas no topo, sem editar historico antigo.

Formato:

```markdown
## YYYY-MM-DD operacao | titulo
- Paginas criadas: [...]
- Paginas atualizadas: [...]
```

Operacoes comuns: `ingest`, `inbox`, `query`, `lint`, `update`, `feed`, `transcript`, `transcript-rebuild`, `dream`.

## Gates de encerramento

Antes de concluir uma operacao que muda conhecimento duravel:

- `raw/` segue intocado.
- Paginas criadas tem frontmatter completo.
- Paginas indexaveis tem `summary:`.
- `wiki/log.md` foi atualizado quando aplicavel.
- O indice foi regenerado quando aplicavel.
- `build-index.py check` esta em sync.
- Wikilinks novos apontam para paginas existentes.

## Memoria

Captura de memoria viva (operacao MEMORY) e **adapter-specific**, nao uma invariante do vault. O conhecimento duravel do vault vive em `wiki/`; memoria de comportamento/preferencia do agente e responsabilidade de cada plataforma e seu destino depende do adaptador. Ver `harness/adapters/*.md`.

## Capacidades Claude-only (sem equivalente Codex)

Algumas capacidades existem apenas no adaptador Claude Code e nao fazem parte do contrato agnostico:

- **MEMORY** — escrita na memoria viva em `~/.claude/projects/.../memory/`. Codex nao tem memoria persistente equivalente.

Camadas opcionais de revisao deliberativa (peer-review cruzado entre modelos) podem ser plugadas via skills user-level do Claude Code, mas nao sao embarcadas pelo harness — dependem de agents e plugins fora do payload.

Essas capacidades sao documentadas em `harness/adapters/claude.md` e nao devem ser listadas nos playbooks de `harness/operations/` como operacoes universais.

## Adaptadores

- Claude Code: ver `harness/adapters/claude.md`.
- Codex: ver `harness/adapters/codex.md`.
