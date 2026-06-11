Execute a operação INBOX para capturar a ideia: $ARGUMENTS

Se não houver argumentos, use o conteúdo mais recente compartilhado na conversa.

## Passos (executar em ordem)

1. **Criar arquivo** — crie `wiki/ideias-pensamentos/inbox/[slug].md` com:
   ```yaml
   ---
   title:
   summary:
   category: ideias-pensamentos
   type: inbox
   tags: []
   sources: []
   created: YYYY-MM-DD
   updated: YYYY-MM-DD
   ---
   ```
   Inclua o conteúdo da ideia, sem processar ou expandir ainda.

2. **Log + build** — inclua um `summary:` de uma linha (torna a captura encontrável) e rode `python3 .claude/scripts/build-index.py generate`; registre no topo de `wiki/log.md`:
   ```
   ## YYYY-MM-DD inbox | [título]
   - Arquivo: wiki/ideias-pensamentos/inbox/[slug].md
   ```

## Done when

- [ ] Arquivo criado em `inbox/` com frontmatter correto
- [ ] `wiki/log.md` atualizado
- [ ] `build-index.py generate` rodado

## Decisão ao final

Pergunte: "Quer processar agora (desenvolver em concept, insight ou source — ≤5min) ou deixar pendente?"
- **Processar agora** → execute o desenvolvimento inline e atualize o tipo da página
- **Deixar pendente** → encerre aqui; a ideia fica em `inbox/` para próximo `/feed`
