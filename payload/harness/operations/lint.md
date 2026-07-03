# Operacao: lint

Use para health-check completo do vault.

## Passos

1. Rodar `python3 .claude/scripts/build-index.py graph`: orfas, sub-conectadas e links quebrados. Links quebrados sao P1; orfas/sub-conectadas sao P2 salvo decisao consciente.
2. Dos links quebrados, separar typo de conceito que merece pagina.
3. Procurar contradicoes relevantes: datas conflitantes, afirmacoes opostas, entidades duplicadas.
4. Sugerir gaps de conhecimento e areas sub-representadas em relacao ao escopo das categorias.
5. Verificar saude do harness:
   - arquivos criticos existem;
   - hooks existem e sao executaveis;
   - `python3 .claude/scripts/build-index.py check`;
   - `python3 .claude/scripts/build-index.py thresholds`;
   - `bash harness/scripts/verify.sh`;
   - `queue/` tem pendencias?;
   - `git status --porcelain` mostra conhecimento nao commitado?
6. Reportar por prioridade:
   - P1: quebrado/bloqueante;
   - P2: importante;
   - P3: melhoria.

## Done when

- Links quebrados e gaps foram reportados.
- Contradicoes foram identificadas ou declaradas ausentes.
- Saude do harness foi reportada.
- Acoes recomendadas estao priorizadas.
