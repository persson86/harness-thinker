Execute a operação CONTEXT para: $ARGUMENTS

Siga o playbook `harness/operations/context.md`.

Deltas Claude Code:
- Se não houver argumentos, aplique ao tema atual da conversa.
- Use `wiki/index.md` como root fino e `vault.config.json` como fonte das esferas.
- Cite páginas reais com `[[wikilink]]`; se o vault não cobrir o tema, declare brevemente e siga com conhecimento externo separado.
