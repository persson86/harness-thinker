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
4. Selecionar ate 8 paginas pertinentes e ler na integra.
5. Incluir perfil do usuario quando disponivel na plataforma/memoria ativa.
6. Produzir analise com:
   - maximo rigor;
   - ceticismo saudavel;
   - separacao entre fato, inferencia e opiniao;
   - tensoes e contra-argumentos;
   - ausencia de bajulacao.
7. Se a plataforma permitir e a politica ativa autorizar, delegar a um subagente/modelo forte. Caso contrario, executar localmente.
8. Perguntar ao final: "Vale salvar como insight no vault?"

## Done when

- Paginas consultadas foram consideradas explicitamente.
- Conclusoes e incertezas estao separadas.
- O usuario recebeu uma sintese acionavel, nao apenas um resumo.
