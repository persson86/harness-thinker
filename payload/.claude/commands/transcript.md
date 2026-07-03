Execute a operação TRANSCRIPT para: $ARGUMENTS

Siga o playbook `harness/operations/transcript.md`.

Deltas Claude Code:
- Se houver arquivo em queue ou caminho nos argumentos, processe cada transcrição em sequência.
- Leia a transcrição inteira antes de sintetizar.
- Proponha `applied` somente com evidência citável; registre apenas com confirmação do usuário.
