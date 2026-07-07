Execute a operação HANDOFF para: $ARGUMENTS

Compacta o estado da tarefa em andamento nesta sessão num bloco copiável para retomada. Siga o playbook `harness/operations/handoff.md`.

Deltas Claude Code:
- Invocação manual apenas; nunca dispare handoff automaticamente.
- Use o contexto da conversa atual como fonte do estado — não peça ao usuário para redigitar o que já foi feito.
- Se `$ARGUMENTS` nomear a tarefa/foco, use como título do handoff; se vazio, derive o título do trabalho em andamento na sessão.
- Não confundir com `memory`: handoff é estado descartável de UMA tarefa; memory é aprendizado durável. Não escreva na memória viva aqui.
- Exiba o bloco completo no chat (transporte primário) além de gravar o arquivo de backup.
