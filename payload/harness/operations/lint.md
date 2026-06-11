# Operacao: lint

Use para health-check do vault.

## Passos

1. Rodar `python3 .claude/scripts/build-index.py graph`.
2. Identificar links quebrados, paginas orfas e paginas sub-conectadas.
3. Diferenciar links quebrados que sao typo de conceitos que merecem pagina.
4. Procurar contradicoes relevantes: datas conflitantes, afirmacoes opostas, entidades duplicadas.
5. Sugerir gaps de conhecimento e areas sub-representadas.
6. Verificar saude do harness:
   - arquivos criticos existem;
   - hooks Claude existem e sao executaveis;
   - `python3 .claude/scripts/build-index.py check`;
   - `python3 .claude/scripts/build-index.py thresholds`;
   - `bash harness/scripts/verify.sh`.
7. Reportar por prioridade:
   - P1: quebrado/bloqueante;
   - P2: importante;
   - P3: melhoria.

## Done when

- Links quebrados e gaps foram reportados.
- Contradicoes foram identificadas ou declaradas ausentes.
- Saude do harness foi reportada.
- Acoes recomendadas estao priorizadas.
