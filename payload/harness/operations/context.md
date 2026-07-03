# Operacao: context

Use para decidir quanto do vault ler antes de responder.

## Sempre

Leia `wiki/index.md` no inicio de uma sessao neste diretorio. Leia tambem `vault.config.json`: as esferas vivem ali, nao em listas fixas do payload.

## Acessar o vault quando

- O topico toca uma ou mais esferas do vault.
- O usuario menciona pessoa, ferramenta, empresa, projeto ou conceito que pode ter pagina.
- O usuario pede sintese, recomendacao, posicao ou analise sobre tema coberto.
- A resposta depende de conhecimento ja processado pelo second-brain.

## Nao expandir leitura quando

- A tarefa e execucao tecnica pura.
- A pergunta e claramente externa ao vault ou depende de dados em tempo real.
- Outra operacao ja define seu proprio protocolo de leitura.

## Profundidade

- Superficial: root `wiki/index.md` + shard relevante.
- Profunda: root + shards relevantes + ate 5 paginas de conteudo.
- Recall amplo: `python3 .claude/scripts/build-index.py search "<termos>"`.

## Execucao

1. Use o root como mapa das esferas e ponteiro para shards.
2. Abra apenas os shards que o topico toca; em esfera subsharded, siga so o sub-shard relevante.
3. Se profundo, leia as paginas mais relevantes na integra.
4. Incorpore conhecimento do vault com citacoes `[[wikilink]]`.
5. Se o vault nao cobre o tema, declare brevemente e siga com conhecimento externo separado.
