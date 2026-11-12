---
name: thinker-checkin
description: Rodada semanal em que o vault pergunta ao usuário sobre assuntos abertos (marco vencido, pendência parada, decisão sem desfecho) e transforma as respostas em relato e atualização das páginas vivas. Use quando o usuário pedir checkin, "o que está em aberto?", "me pergunta o que falta", ou quando `build-index.py checkin --due` indicar rodada vencida e ele aceitar a oferta.
---

# CHECKIN: assuntos abertos

Leia `harness/operations/checkin.md` no root do vault e siga a operação. Comece por `python3 .claude/scripts/build-index.py checkin --json`, reconcilie com as sources antes de perguntar e faça de 3 a 5 perguntas no total, organizadas por assunto e nunca por reunião da agenda. Resposta com fato novo vira source de relato e atualização das páginas; "desconsiderar" vira `checkin --dismiss`; feche com `checkin --record`.
