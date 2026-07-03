Execute a operação INGEST para a fonte: $ARGUMENTS

Siga o playbook `harness/operations/ingest.md`.

Deltas Claude Code:
- Se `$ARGUMENTS` for URL, leia o conteúdo antes de processar.
- Se for texto colado, use o conteúdo mais recente da conversa.
- Nunca crie arquivos na Fase 1; aguarde go-ahead explícito.
