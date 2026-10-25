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

Pedido de agenda, calendario, disponibilidade ou planejamento de horario do usuario e operacao `agenda` (dados ao vivo nas duas fontes). O vault e complementar, nao substituto.

## Profundidade

- Superficial: root `wiki/index.md` + shard relevante.
- Profunda: root + shards relevantes + ate 5 paginas de conteudo.
- Recall amplo: `python3 .claude/scripts/build-index.py search "<termos>"`.

## Localizar paginas

Para achar paginas por pessoa, tema ou conceito, comece por `search` com 2 a 6 termos soltos: nomes proprios, conceito central e um sinonimo provavel (inclusive o termo em ingles ou portugues). Termos sem aspas rendem mais; use aspas so para frase exata e `--all` so para estreitar. A busca ranqueia por BM25 e ignora palavras funcionais soltas ("de", "que"). Use grep para string literal, para confirmar uma ocorrencia ou dentro de pagina ja escolhida. O ranking sugere candidatos; nao determina verdade nem vigencia.

## Execucao

1. Use o root como mapa das esferas e ponteiro para shards.
2. Abra apenas os shards que o topico toca; em esfera subsharded, siga so o sub-shard relevante (fontes por mes: so o(s) mes(es) do periodo).
3. Se profundo, leia as paginas mais relevantes na integra.
4. Incorpore conhecimento do vault com citacoes `[[wikilink]]`.
5. Se o vault nao cobre o tema, declare brevemente e siga com conhecimento externo separado.
