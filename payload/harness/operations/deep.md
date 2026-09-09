# Operacao: deep

Use para analise de alta intensidade.

## Quando acionar

Quando o usuario pedir explicitamente:

- melhor modelo;
- maior esforco;
- analise profunda;
- geracao de hipoteses;
- reflexao rigorosa;
- subagente, se a plataforma permitir.

## Protocolo

1. Ler `wiki/index.md`.
2. Abrir shards relevantes.
3. Usar `python3 .claude/scripts/build-index.py search "<termos>"` para recall amplo quando util.
4. Selecionar ate 8 paginas pertinentes. Em paginas grandes, partir do estado vigente e das secoes pertinentes; ler integralmente quando necessario para reconciliar a evidencia. Nunca tratar trecho como leitura completa.
5. Incluir perfil do usuario quando disponivel na plataforma/memoria ativa.
6. Produzir analise com:
   - maximo rigor;
   - ceticismo saudavel;
   - separacao entre fato, inferencia e opiniao;
   - tensoes e contra-argumentos;
   - ausencia de bajulacao.
7. Comparar com execucao no principal atual antes de delegar. Se houver ganho por trabalho independente ou revisao critica, escolher a rota suficiente (inclusive outro provedor para diversidade), sem exigir modelo mais forte nem repetir a mesma analise por default. Declarar beneficio, contexto e custo de integracao; seguir `delegate.md`.
8. Preservar a diferenca entre exploracao, conclusao sustentada e decisao. Propor registro quando houver delta duravel e fizer sentido encerrar; nao forcar esse fechamento durante uma exploracao. Autorizacao vigente para este resultado e escopo dispensa repeti-la.
9. Quando houver correcao de conhecimento registrado, seguir `review.md` no escopo autorizado.

## Done when

- Paginas consultadas foram consideradas explicitamente.
- Conclusoes e incertezas estao separadas.
- O usuario recebeu uma sintese acionavel, nao apenas um resumo.
