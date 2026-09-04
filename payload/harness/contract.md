# Harness Agnostico do Second-Brain

Contrato comum do second-brain independentemente de plataforma ou modelo. Adaptadores como Claude Code, Codex e Grok traduzem este contrato para suas ferramentas locais.

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

## Evidencia, interpretacao e autorizacao

- Tipo de pagina (`source`, `concept`, `insight`) nao e grau de certeza. Uma source tambem e uma elaboracao editorial; para conferir uma fala, voltar ao original quando disponivel.
- Separar o que foi observado ou relatado, o que o agente inferiu, o que continua hipotese e o que o usuario autorizou. Aprovar registro ou execucao nao valida todas as afirmacoes do texto.
- Uma sintese pode ir alem da fonte, desde que identifique essa passagem. Concordancia de modelos ou repeticao da mesma origem nao constitui evidencia independente.
- Afirmacoes materiais devem permitir recuperar origem, data e limite do que a evidencia sustenta. `sources:` e uma lista de procedencia, nao prova automatica de cada frase; referencias de contexto ou contraditorio devem ser explicadas no corpo/Conexoes. Nao contar ciclos entre paginas como corroboracao.
- Citacao literal exige trecho original localizavel; indicar traducao quando houver. Sem essa base, usar parafrase atribuida, sem aspas que sugiram literalidade.
- Resumos preservam os limites decisivos do corpo, inclusive data e natureza historica. Uma ressalva so no rodape nao corrige uma abertura categorica.

## Validade temporal e revisao

Campos opcionais para paginas em que a distincao temporal seja material; nao exigem migracao do acervo:

```yaml
knowledge_status: historical # current | historical | superseded
as_of: YYYY-MM-DD
superseded_by: slug-existente
```

`current` significa posicao vigente na data indicada, nao verdade comprovada; ausencia de status significa nao classificado. `historical` preserva um recorte passado; `superseded` marca uma conclusao substituida. `as_of` data o estado descrito, enquanto `updated` data a edicao. `superseded_by` aponta para a pagina que deve ser consultada sobre o estado posterior e deve existir. Indice e busca exibem a sinalizacao; nao escolhem automaticamente qual afirmacao e verdadeira.

Quando houver correcao do usuario, nova evidencia ou mudanca de decisao, seguir `harness/operations/review.md`: localizar registros e dependencias candidatas, revisar corpo e resumo sob a mesma autorizacao aplicavel a escrita e preservar a cronologia. Nao apagar fontes originais nem reescrever entradas antigas do log.

## Conversa e conhecimento duravel

Identificar pelo pedido se o momento e explorar, confrontar, decidir ou executar; nao exigir que o usuario escolha um modo a cada turno. Explorar admite hipoteses, humor e conexoes inesperadas. A critica acompanha a maturidade da ideia e o risco da decisao. Nao fabricar objecoes para parecer independente, nem tratar provocacao como insatisfacao sem fundamento.

A voz especifica do usuario vive em `vault-heuristics.md`. Requisitos de analise de material (Resumo/Ideias principais) nao obrigam toda troca conversacional a virar relatorio. Propor registro quando houver delta duravel e fizer sentido encerrar a exploracao, sem transformar cada resposta em pedido de publicacao. Escrita continua sujeita a autorizacao; autorizacao vigente para este resultado e escopo dispensa repeti-la, sem se estender a resultados futuros ou fora desse escopo.

## Limites da verificacao

Indice, grafo e manifest verificam propriedades estruturais. Nao certificam verdade, atribuicao, causalidade, validade temporal ou impacto do vault. Casos de avaliacao de comportamento vivem em `harness/evals/knowledge-review.md`; registrar resultado observado, falhas e limites separadamente dos testes deterministicos.

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

Operacoes comuns: `ingest`, `inbox`, `query`, `review`, `lint`, `update`, `feed`, `transcript`, `transcript-rebuild`, `dream`, `reverie`, `applied`.

`applied` registra proveniencia de valor quando uma pagina alimenta uma decisao ou entregavel real, a partir de evidencia citavel:

```markdown
## YYYY-MM-DD applied | [[origem]] -> entregavel/decisao real
```

`handoff` nao aparece na lista de operacoes comuns: e operacao de estado de sessao (compactacao de contexto para retomar uma tarefa depois), nao de conhecimento duravel. O resultado gerado nunca vira entrada em `wiki/log.md`, nunca vira pagina, nunca roda o indice, e nao e gerenciado pelo installer (os arquivos do playbook/command em si sao instalados normalmente, como o resto do payload). Um validador de `wiki/log.md` nao deve esperar entradas de handoff.

## Gates de Encerramento

Antes de concluir operacao que muda conhecimento duravel:

- `raw/` segue intocado.
- Paginas criadas tem frontmatter completo.
- Paginas indexaveis tem `summary:`.
- `wiki/log.md` foi atualizado quando aplicavel.
- O indice foi regenerado quando aplicavel.
- `build-index.py check` esta em sync.
- Wikilinks novos apontam para paginas existentes.

## Capacidades Locais do Ambiente

Ferramentas de sistema disponiveis a qualquer adaptador que rode Bash nesta maquina, independente de LLM:

- **Agenda**: duas fontes complementares, nunca alternativas. Sempre consultar as duas quando o usuario mencionar agenda, calendario, reuniao do dia, disponibilidade ou planejamento de horario. Gmail vazio nao implica dia livre. Playbook: `harness/operations/agenda.md`.
  - **Gmail = pessoal** — Google Calendar MCP, quando a sessao expuser as tools.
  - **Calendar do Mac = profissional** — `bash harness/scripts/agenda.sh` (`icalBuddy` / EventKit; inclui Exchange, Outlook/Teams e calendarios locais). Ja autorizado neste ambiente.
  A saida bruta pode incluir senhas, links de reuniao e listas de participantes — nunca reexibir cru; sintetizar horario, titulo, pessoas-chave e conflitos. Um hook (`agenda-gate`) impede encerrar a virada de agenda sem as duas fontes.

## Capacidades Adapter-Specific

MEMORY e Claude-only: escrita na memoria viva em `~/.claude/projects/.../memory/`. Codex e Grok nao tem memoria persistente equivalente. Camadas opcionais de revisao deliberativa podem existir fora do payload, via skills/plugins user-level.

Adaptadores: `harness/adapters/claude.md`, `harness/adapters/codex.md` e `harness/adapters/grok.md`. Grok Build entra por `.grok/rules/` e `.grok/hooks/`; nao altera `CLAUDE.md`, `AGENTS.md` nem `.claude/`.
