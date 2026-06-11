Execute a operação LINT — health-check completo do vault.

## Passos (executar em ordem)

1. **Grafo (determinístico)** — rode `python3 .claude/scripts/build-index.py graph`: reporta órfãs (0 inbound), sub-conectadas (<2 links) e links quebrados (alvo inexistente), já excluindo `index.md`/`log.md`/`_index.md` e ignorando `[[...]]` dentro de código. Links quebrados = **P1** (corrigir ou remover). Órfãs/sub-conectadas = **P2** (cross-link ou aceitar conscientemente).

2. **Conceitos sem página** — dos links quebrados do passo 1, quais merecem virar página (gap de conhecimento real) vs. apenas corrigir o link? Liste os gaps.

3. **Contradições** — detecte conflitos: datas inconsistentes, afirmações opostas sobre o mesmo conceito, entidades com atributos conflitantes entre páginas.

4. **Gaps de conhecimento** — sugira tópicos que aparecem com frequência nos textos mas não têm página; áreas sub-representadas em relação ao escopo do vault.

5. **Ações recomendadas** — reporte resumo estruturado com prioridade: P1 (bloqueante), P2 (importante), P3 (nice-to-have).

6. **Saúde do harness** — verifique:
   - Hooks existem e são executáveis: `.claude/hooks/protect-raw.sh`, `.claude/hooks/track-ingest.sh` e `.claude/hooks/check-ingest.sh`
   - Quantas operações em `wiki/log.md` no último mês (contar entradas `## YYYY-MM`)
   - `MEMORY.md` tem entradas recentes (< 30 dias)?
   - `queue/` tem arquivos pendentes (fora de `queue/processed/`)?
   - **Índice gerado em sync:** rode `python3 .claude/scripts/build-index.py check`. DRIFT → P1 (rode `generate` e commite os shards). O índice (root + `[cat]/_index.md` + sub-shards `_index-[type].md` nas esferas grandes) é gerado do frontmatter; nunca editar à mão.
   - **Completude de `summary:`:** páginas sem `summary:` no frontmatter (exceto `inbox/` cru) não entram no índice → P2 com a lista (o `generate` as imprime como "puladas").
   - **Reconciliar `hook.log`:** arquivos mencionados no log sem entrada nos shards `[cat]/_index*.md` → P1 (indica INGEST sem `build-index.py generate`).
   - **Gatilhos adiados (Fase 3):** rode `python3 .claude/scripts/build-index.py thresholds`. Se disparar (shard > 150 linhas → adicionar a `SUBSHARDED` no `build-index.py`; > 800 páginas → FTS5), reportar **P3** e referenciar [[reestruturacao-index-spec]].
   - **Durabilidade git:** rode `git status --porcelain` — mudanças não commitadas em `wiki/` → P2 informacional (todo o rollback do vault é git; conhecimento fora de commit não tem proteção). Sugerir commit, nunca commitar sozinho.

## Done when

- [ ] Lista de órfãs gerada
- [ ] Gaps de wikilinks listados
- [ ] Contradições identificadas (ou "nenhuma encontrada")
- [ ] Saúde do harness reportada
- [ ] Relatório com P1/P2/P3 entregue
