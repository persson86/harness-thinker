Execute a operação INGEST para a fonte: $ARGUMENTS

Siga o playbook `harness/operations/ingest.md`.

Deltas Claude Code:
- Se `$ARGUMENTS` for URL, leia o conteúdo (WebFetch) antes de processar.
- Se for texto colado, use o conteúdo mais recente da conversa.
- Se `$ARGUMENTS` for um tópico ou pergunta sem conteúdo pronto, monte o brief de pesquisa da Fase 1 e execute-o via WebSearch/WebFetch ou a skill `deep-research`; só depois siga para a análise.
- Nunca crie arquivos na Fase 1; aguarde go-ahead explícito.
