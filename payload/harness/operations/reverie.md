# REVERIE — associacao livre entre paginas do vault

Rodada de leitura sem agenda: o agente percorre o indice, deixa que paginas "puxem" por atração intuitiva, le-as sem tarefa, e escreve livremente o que emerge. Contrato inegociavel: **o REVERIE produz material bruto, nunca propoe acoes** — o output e ruido candidato a insight, nao um plano de acao.

Diferenca critica em relacao ao DREAM: sem juizes deterministicos, sem template de output, sem busca por contradicoes ou conexoes. A instrucao e o oposto: nao organize, nao conclua, nao seja util.

## Passos

1. **Leitura do indice completo** — ler `wiki/index.md` e todos os shards `wiki/[cat]/_index.md` (incluindo sub-shards de categorias subsharded). O objetivo nao e buscar; e deixar que algo chame atencao.

2. **Selecao sem agenda** — escolher 4-7 paginas de pelo menos 3 categorias distintas. Criterios:
   - Algo "puxou" — sem saber articular por que essas paginas juntas
   - Categorias diferentes (nao agrupar por tema obvio)
   - Sem `[[wikilinks]]` mutuos entre si (verificar nas paginas escolhidas)
   - Nao rodar logo apos um INGEST recente: a fonte fresca dominaria a selecao

3. **Leitura sem tarefa** — ler as paginas completas. Sem buscar contradicoes, conexoes, ou o que e "util". Nao ha checklist nessa fase.

4. **Escrita livre** — criar o arquivo no inbox configurado em `vault.config.json` com:
   - Frontmatter minimo: `type: inbox`, `summary: reverie livre de YYYY-MM-DD`, `created:`, `updated:`
   - Primeiro bloco: lista das paginas escolhidas e a atracao que gerou a escolha (1 linha por pagina) — nao e analise, e observacao do proprio processo de selecao
   - Corpo: escrita livre. Pode ser prosa, fragmentos, perguntas, imagens mentais, tensoes, silencio. Nao organizar. Nao concluir. Permitir inconsistencia e incompletude.

5. **Registrar no log**: `## YYYY-MM-DD reverie | [titulo livre que emergiu do texto]`

## Travas

- Nunca propor acoes, cross-links ou promocoes — isso pertence ao DREAM ou ao usuario.
- Output pode ser ruido: isso e esperado, nao uma falha.
- Nao indexar: o arquivo fica em `inbox/` ate revisao explicita do usuario.
- Nao inventar `[[wikilinks]]` no corpo do texto.
- Se nao emergiu nada de interessante, o arquivo registra isso em uma linha — sem inflar.
- Agendamento e decisao do usuario (manual ou `/loop`) — nunca ativacao automatica.
