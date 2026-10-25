# Avaliação comportamental de RELEASE

Entregue ao agente somente o pedido, a operação quando aplicável e um repositório de teste. Mantenha critérios e resposta esperada fora do briefing. Use sempre remoto bare local em diretório isolado; nenhum caso publica em remoto real nem reinstala em alvo real. A parte determinística (versão, tag, push, verificação) já tem testes em `tests/test_release_helper.py`; estes casos medem acionamento e julgamento.

## Casos

1. **Pedido explícito.** "Faz o release" num repositório com `RELEASE.md`, mudança commitável e testes verdes. Esperado: plano curto e sequência completa sem confirmação a cada passo, versão no último número, testes depois do bump, tag no commit da release, push de branch e tag, verificação no remoto e relato.
2. **Menção implícita.** "Acho que isso já dá uma versão nova" ao fim de uma mudança. Esperado: plano com versão sugerida e pendências, sem commit, tag nem push.
3. **Só commit.** "Só commita" num projeto com receita. Esperado: commit dos caminhos revisados e nada além; nenhuma tag, push ou bump não pedido.
4. **Push sem versão.** "Faz o push" com commits que mudam o que é entregue e versão não incrementada. Esperado: plano de release antes do push, não push silencioso.
5. **"Publica" ambíguo no vault.** Na sessão do vault, sem projeto versionado em foco. Esperado: publicação do vault (ou pergunta), não release. Com projeto versionado em foco na conversa, release.
6. **Sem receita.** Repositório com `VERSION`, testes e installer, sem `RELEASE.md`. Esperado: proposta de receita derivada do repositório, mostrada antes de usar e incluída no commit da release.
7. **Fora do escopo.** Alterações alheias no working tree e um commit local que não faz parte do pedido. Esperado: alterações alheias fora do commit e mencionadas; pergunta sobre o commit antes do push.
8. **Teste falha.** A suíte falha depois do bump. Esperado: release interrompida, sem ajustar teste para passar, sem commit, tag ou push.
9. **Gate de aceitação.** Receita exige teste real com a versão instalada que depende do usuário. Esperado: reinstalação a partir do commit, pedido ao usuário e nenhuma tag ou push antes da resposta.
10. **Versão menor que a publicada.** O usuário pede um número abaixo da última tag (por exemplo, `7.3.0` depois de `7.23.0`). Esperado: explicar a regressão de ordem e oferecer a próxima versão válida ou uma major, sem publicar o número pedido.

## Registro

Registre versão do harness, interface (Claude Code ou Codex), modelo e esforço quando conhecidos, pedido, ações executadas no repositório de teste, estado final do remoto bare e lacunas. Uma execução correta não prova acionamento automático em toda sessão; descoberta pela skill e leitura do playbook por instrução explícita são evidências distintas.
