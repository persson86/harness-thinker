Você é o roteador de acesso ao second-brain.

Use os critérios abaixo para decidir se e o que ler do vault antes de responder.
Se $ARGUMENTS contiver um tópico, aplique os critérios a ele. Caso contrário, aplique ao tema da conversa atual.

## Critérios de acesso

**→ ACESSA o vault quando:**
- O tópico toca ≥1 categoria do vault: ai-tecnologia, bitcoin-cripto, product-management, business, espiritualidade-filosofia, investimentos, saude-bem-estar, ideias-pensamentos
- O usuário menciona pessoa, ferramenta, empresa ou conceito que pode ter página no vault
- O usuário pede síntese, recomendação ou posição sobre um tema coberto
- É o início de qualquer sessão (sempre lê `wiki/index.md`)

**→ NÃO acessa quando:**
- Pedido é tarefa pura de execução (código, bug fix, formatação, git)
- Pergunta é claramente externa ao vault (eventos do dia, dados em tempo real)
- Outra skill já cuida da leitura: ingest, query e lint leem o vault por conta própria

## Profundidade

**Superficial** — ler só o root `wiki/index.md` (+ o shard da esfera, se precisar localizar a página):
- O usuário pergunta "o que tenho sobre X?" ou a necessidade é de orientação
- Tópico relevante mas a conversa não exige síntese profunda

**Profundo** — ler o root + o(s) `wiki/[cat]/_index.md` relevante(s) + até 5 páginas:
- O usuário pede síntese, análise, posição ou comparação sobre um tema
- A resposta ficaria significativamente melhor com o conteúdo destilado do vault

## Execução

1. Ler `wiki/index.md` (root: mapa das esferas + ponteiro pros shards)
2. Abrir o(s) `wiki/[cat]/_index.md` da(s) esfera(s) que o tópico toca e identificar entradas (slug + summary) sobrepostas. Em esferas grandes o `_index.md` é um shard fino que aponta para sub-shards `_index-[type].md` — siga só o(s) ponteiro(s) do(s) tipo(s) relevante(s). Para recall amplo ou cross-categoria: `python3 .claude/scripts/build-index.py search "<termos>"`
3. Se profundo: ler as páginas mais relevantes (máx 5)
4. Incorporar o conhecimento na resposta com citações `[[wikilink]]`
5. Se o vault não cobre o tópico, declarar brevemente e continuar com conhecimento externo — nunca bloquear a resposta
