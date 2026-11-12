---
description: Rodada semanal em que o vault pergunta ao usuário sobre assuntos abertos (marco vencido, pendência parada, decisão sem desfecho) e transforma as respostas em relato e atualização das páginas vivas. Use em pedidos de checkin, "o que está em aberto?" ou "me pergunta o que falta", e quando a rodada vencida for oferecida e aceita.
argument-hint: "[opcional: assunto ou categoria para restringir a rodada]"
---

Execute a operação CHECKIN para: $ARGUMENTS

Siga `harness/operations/checkin.md`. Comece por `python3 .claude/scripts/build-index.py checkin --json`, reconcilie com as sources antes de perguntar e faça de 3 a 5 perguntas no total, organizadas por assunto e nunca por reunião da agenda. Com argumento, restrinja a rodada a esse assunto ou categoria. Feche com `checkin --record`.
