Execute a operação AGENDA para: $ARGUMENTS

Siga o playbook `harness/operations/agenda.md`.

Use when: o usuário pergunta sobre agenda, calendário, próximo compromisso, reunião do dia, disponibilidade, o que tem hoje/amanhã/na semana, ou planejamento de horário.

Gmail (Google Calendar MCP) = pessoal. Calendar do Mac (`bash harness/scripts/agenda.sh`) = profissional. Sempre as duas fontes no mesmo intervalo — nunca só uma. Gmail vazio ≠ dia livre.

Deltas Claude Code:
- Se não houver argumentos, use o intervalo default (de agora até amanhã).
- Sintetize horário, título, pessoas-chave e conflitos; nunca reexiba senha, link de reunião ou lista crua de participantes.
