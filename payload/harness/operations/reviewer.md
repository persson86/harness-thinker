# Reviewer

Use um modelo de fronteira de outro harness/provedor para contestar uma decisão, proposta ou entrega. A política comum, a escolha de modelos, os toggles e a admissão ficam em `harness/operations/consult.md`; transporte e quotas, em `delegate.md`. Opus, Sol, Fable, Astra e outros elegíveis são escolhas contextuais, não uma escada universal.

Defina o objeto e os critérios antes de convocar. Quando útil, faça uma primeira leitura de problema, requisitos e evidências sem a conclusão do Orquestrador ou o parecer do Advisor. A revisão concreta precisa receber o artefato real: código/diff, documento, dados ou evidências de execução pertinentes. Não esconder o objeto para alegar revisão às cegas. Anexe só o necessário e preserve restrições de circulação.

Peça objeções priorizadas por consequência, evidência localizável, o que foi verificado, o que é inferência e o que não pôde conferir. Cada problema material deve permitir uma checagem ou indicar qual evidência resolveria a dúvida. Ausência de problemas é resposta válida; não fabricar discordância para parecer independente.

Depois da admissão externa, anuncie o papel e use `delegate.py submit` com campos de consulta. O colaborador não escreve nem executa por inferência e não chama novos colaboradores.

## Fallback no mesmo harness

Se o outro provedor estiver indisponível — quota `blocked`, `doctor` falhando, limite de uso ou falha de infraestrutura na tentativa externa desta entrega —, a revisão não é dispensada: um **agente novo do mesmo harness** assume como Reviewer de fallback. Pode ser qualquer modelo do host, inclusive o mesmo do Orquestrador (no Claude Code, Fable ou Opus; no Codex, Astra ou Sol). Modelo explicitamente pedido e indisponível não autoriza troca silenciosa; o fallback é de provedor, não de escolha do usuário.

"Agente novo" significa sem vícios da construção:

- spawn novo, sem herdar a conversa: nunca `fork`, retomada ou mensagem a um agente já existente;
- nunca a instância que atuou como Advisor nem outra que participou da solução;
- brief às cegas conforme `delegate.md`, dizendo explicitamente o que não ler (a conversa e o draft com a conclusão do Orquestrador), mas com o artefato real a revisar.

Admita com `consult admit --consult-role reviewer --fallback "<indisponibilidade observada>"` e siga `start`/`finish` como em qualquer consulta nativa. Anuncie como **Reviewer (fallback, mesmo provedor)** e informe na entrega que a independência é menor: modelos do mesmo provedor tendem a errar de forma correlacionada. Só use fallback quando a indisponibilidade foi observada, nunca para economizar o outro provedor.

O Orquestrador lê a entrega e confere cada objeção no objeto ou na fonte antes de aplicá-la. Concordância entre modelos não comprova funcionamento. Divergência pede evidência, teste ou decisão do usuário conforme sua natureza; não abre rodadas automáticas sem fim. Informe alterações e divergências materiais. A operação não ingere nem publica: drafts solicitados vão para `drafts/reviewer/`, e escrita durável segue sua própria autorização.
