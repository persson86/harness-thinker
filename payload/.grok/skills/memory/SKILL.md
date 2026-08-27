---
name: memory
description: Recusa a operação MEMORY do Claude Code no Grok Build. Use when the user asks for /memory, MEMORY, persistir aprendizado de sessão, ou escrever em .claude/memory/.
---

# MEMORY — indisponível no Grok Build

Não execute a operação MEMORY. Grok Build não escreve na memória viva do Claude Code (`~/.claude/projects/*/memory/`) nem no snapshot `.claude/memory/`.

Se o usuário quiser persistir um aprendizado desta sessão:

1. Recuse o destino Claude.
2. Ofereça uma destas vias, e só execute com pedido explícito:
   - atualizar `harness/adapters/grok.md` ou `.grok/rules/thinker.md` (comportamento do Grok);
   - capturar como inbox/insight no vault via `harness/operations/inbox.md` ou `query.md`.

Não ressincronize `.claude/memory/` a partir desta sessão.
