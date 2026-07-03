Execute a operação INBOX para capturar: $ARGUMENTS

Siga o playbook `harness/operations/inbox.md`.

Deltas Claude Code:
- Se não houver argumentos, use o conteúdo mais recente compartilhado na conversa.
- Use o `inbox_dir` de `vault.config.json`; não assuma caminho fixo.
- Ao final, pergunte se o usuário quer processar agora ou deixar para depois.
