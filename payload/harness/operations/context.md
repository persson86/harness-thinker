# Operacao: context

Use esta operacao para decidir quanto do vault ler antes de responder.

## Sempre

Leia `wiki/index.md` no inicio de uma sessao neste diretorio. Ele e o root fino do vault e aponta para os shards de cada categoria.

## Acessar o vault quando

- O topico toca uma categoria do vault.
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

## Resposta

Quando usar conhecimento do vault, cite paginas reais com `[[slug]]`. Se o vault nao cobrir o tema, diga isso brevemente e continue com conhecimento externo separado.
