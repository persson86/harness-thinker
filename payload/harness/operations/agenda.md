# Operacao: agenda

Use quando o usuario perguntar sobre agenda, calendario, proximo compromisso, reuniao do dia, disponibilidade, o que tem hoje/amanha/na semana, ou planejamento de horario.

Dados ao vivo, nao conhecimento do vault. O vault pode contextualizar uma reuniao conhecida; nao substitui as fontes.

## Fontes (obrigatorias, nunca alternativas)

1. **Gmail = pessoal** — Google Calendar MCP (`google_calendar__search` / `list_calendars`), quando a sessao expuser as tools. `time_min`/`time_max` em RFC3339 com offset do usuario.
2. **Calendar do Mac = profissional** — `bash harness/scripts/agenda.sh` (`icalBuddy` / EventKit). Inclui Exchange, Outlook/Teams e calendarios locais.

Gmail vazio nao implica dia livre. Nao responder com uma fonte so. Nao usar uma como fallback da outra.

## Passos

1. Determinar o intervalo. Default: de agora ate o fim de amanha. "hoje" = dia inteiro; "proxima" = a partir de agora; "semana" = hoje+7.
2. Consultar as duas fontes no mesmo intervalo, em paralelo:
   - MCP Gmail (pessoal);
   - `bash harness/scripts/agenda.sh upcoming 2` (ou `today` / `from START to END`).
3. Se o MCP Gmail nao estiver na sessao, declarar a lacuna explicitamente e ainda assim consultar o Mac.
4. Se `icalBuddy` falhar, declarar a lacuna e ainda assim consultar o Gmail.
5. Fundir as duas listas. Distinguir pessoal vs profissional. Marcar conflitos de horario.
6. Sintetizar: horario, titulo, pessoas-chave, conflitos. Nunca reexibir senha, link de reuniao, lista crua de participantes ou e-mails.

## Done when

- As duas fontes foram consultadas, ou a lacuna de uma delas foi declarada.
- A resposta distingue pessoal vs profissional.
- Nenhum segredo de convite foi reexibido.

## Nunca

- Tratar Gmail vazio como dia livre.
- Inventar eventos.
- Responder pedido de agenda so com o vault.
