---
name: thinker-visual
description: Representar com diagramas processos, sequências de interação, estados, laços causais, estruturas de domínio e posicionamento. Use quando o usuário pedir diagrama, fluxo, desenho, mapa de sistema ou representação visual, e por iniciativa própria quando um mecanismo ficar difícil de seguir só em texto. Mermaid fica no texto; cena Excalidraw editável e PNG no tema do vault vão para output/ quando o material for mostrado ou enviado.
---

# VISUAL: diagramas e sistemas

Leia `harness/operations/visual.md` no root do vault e siga a operação. Escolha o tipo de diagrama pela pergunta que ele responde; um diagrama por ideia, sem enfeite.

Mermaid na página ou na resposta é a fonte. Para material que será mostrado ou enviado, gere cena e PNG com `bash harness/scripts/visual.sh render`, abra o PNG antes de entregar e diga o que ficou sem verificação. A primeira execução instala dependências fixadas num cache fora do vault; avise antes. No sandbox do Codex o render sai com código 3: rode o mesmo comando fora do sandbox pedindo aprovação (`sandbox_permissions: require_escalated`); com aprovação `never` ou negada, entregue o Mermaid e diga que cena e PNG ficaram pendentes.
