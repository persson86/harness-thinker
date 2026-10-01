# Especificação de tarefas e continuidade do Thinker

## Resultado pretendido

Ao retomar uma tarefa em outra sessão, a pessoa encontra o estado relevante, as correções que prevalecem, as fontes que precisam ser conferidas e as entregas pendentes. Ao supervisionar vários agentes, identifica o que exige uma ação sem reconstruir o histórico de cada janela.

Hipóteses a testar: a identidade de tarefa reduz retomadas incorretas; um pacote de contexto explícito reduz omissões; uma inbox orientada a ações reduz atenção de supervisão. Nenhuma dessas hipóteses é um ganho já observado.

## Base e problemas

O harness 7.22.1 possui delegação por propostas, estado privado, snapshots com hashes, diagnóstico, cancelamento, recuperação de supervisor interrompido, board, handoff manual e metadados temporais de conhecimento. O novo código deve reutilizar esses contratos.

Há uma diferença entre tarefa, conversa, execução e conhecimento. Uma tarefa pode atravessar sessões e provedores. Uma execução pode terminar sem a entrega ter sido revisada. Um relato de conclusão não comprova efeito. Uma conversa recente pode pertencer a outra tarefa. Uma fonte inalterada pode continuar semanticamente desatualizada.

O coletor de conversas do setup motivador seleciona por caminho e recência. Ele não pertence ao payload genérico atual. Esta versão não deve modificar o coletor instalado ou depender dele para identificar tarefas.

## Escopo da primeira versão

P0, obrigatório para `7.23.0-rc.1`:

1. Envelope de tarefa durável fora do vault, com ID explícito e seleção independente do diretório corrente. O namespace permanece vinculado a um workspace explícito.
2. Checkpoint ligado ao handoff existente, com proveniência, correções e pendências explícitas.
3. Pacote de retomada determinístico, inspecionável e com orçamento explícito.
4. Inbox derivada de tarefas e referências a jobs. Na candidata, jobs vinculados ficam explicitamente desconhecidos; importar observações do supervisor é um incremento posterior.
5. Superfície local de consulta com Retomar, Precisa de mim e Entregas; CLI para criar e atualizar tarefas. Controles de mutação na UI entram em um incremento posterior.
6. Laboratório reproduzível, migração aditiva e rollback ensaiado.
7. Instrumentos de teste de uso, sem atribuir feedback humano automaticamente.

Ficam fora do primeiro runtime: chat próprio com loop de ferramentas, escrita autônoma no conhecimento, novo scheduler, execução remota, leitura indiscriminada de sessões privadas, sincronização de credenciais, busca vetorial obrigatória e seleção automática de modelos. Não alterar os defaults de esforço ou rota do usuário.

## Fluxos

**Iniciar:** fornecer um workspace explícito e criar tarefa com título, objetivo e escopo. A interface abre vazia quando não há tarefas. Dados de demonstração só aparecem em modo de demonstração explícito.

**Registrar progresso:** principal fornece checkpoint conciso. O sistema registra autoria declarada e evidências; não transforma texto em fato verificado. Decisões aceitas, propostas e perguntas abertas permanecem distinguíveis. Atualização exige a revisão esperada da tarefa.

**Retomar:** escolher tarefa pelo ID explícito. A candidata não resolve a sessão atual automaticamente nem seleciona a tarefa mais recente. A resolução por vínculo de sessão é uma extensão futura. Exibir fontes alteradas, ausentes ou não verificáveis antes da exportação do pacote.

**Supervisionar:** inbox ordena bloqueios e perguntas, entregas pendentes e estados incertos. Uma tarefa em andamento sem ação humana pendente não gera alerta repetitivo. Abrir uma linha mostra origem, instante observado e próxima ação suportada.

**Revisar:** ler uma entrega, reconhecer a notificação, incorporar uma proposta e declarar utilidade são ações diferentes. A interface não marca entrega útil ao abrir, copiar ou reconhecer uma notificação.

**Esquecer:** reset explícito incrementa a geração de continuidade. Pacotes e checkpoints da geração anterior deixam de ser elegíveis por padrão. O artefato original não vira conhecimento e não é reintroduzido por fallback automático. A retenção de auditoria fica separada da elegibilidade para contexto.

## Fronteiras de arquitetura

| Componente | Responsabilidade | Não deve fazer |
| --- | --- | --- |
| Registro de workspace | Uma raiz explícita por namespace; aliases futuros | Descobrir worktrees por varredura de diretórios pessoais |
| Store de tarefas | Metadados, revisões, checkpoints e reconhecimento de atenção | Duplicar o estado autoritativo dos jobs |
| Compilador de retomada | Selecionar e apresentar contexto com justificativa | Resumir semanticamente por chamada oculta de modelo |
| Adaptador de delegação (futuro) | Projetar estado do supervisor existente; candidata registra apenas vínculos | Iniciar, recuperar ou cancelar processos por conta própria |
| Superfície local | Navegação e consulta; mutações somente pela CLI | Executar shell arbitrário ou escrever no vault |
| Host nativo | Ferramentas, sessão e eventos disponíveis | Ser apresentado como observado quando só há relato |
| Wiki | Conhecimento canônico | Receber estado descartável de tarefa automaticamente |

Na primeira versão, vínculos de jobs são metadados inspecionáveis. Os comandos existentes de delegação continuam separados. Cancelamento remoto, perguntas do host e steering só virão após contratos e ensaios próprios. Ações indisponíveis não recebem botões que aparentem funcionar.

## Estado e concorrência

Usar um JSON por tarefa em namespace privado versionado, lock e substituição atômica, aproveitando os padrões do runtime atual. Estado, histórico de revisão e recibos de `request_id` ficam no mesmo documento para evitar transação entre journal e snapshot. Repetição do mesmo pedido e payload retorna o mesmo resultado; reutilização com payload diferente falha. Isso vale para metadados, não promete efeitos externos exatamente uma vez. Não introduzir banco ou barramento no primeiro incremento. Impor tamanho máximo ao documento e recusar expansão além dele, com exportação/arquivamento explícitos; nunca descartar correções ou recibos silenciosamente.

Campos mínimos:

| Registro | Campos |
| --- | --- |
| Workspace | `workspace_id`, uma raiz explícita; geração de continuidade por tarefa |
| Tarefa | `task_id`, workspace, título, objetivo, estado, revisão, geração, timestamps |
| Checkpoint | ID, tarefa, revisão-base, autor/origem, estado declarado, decisões, correções com `supersedes`, pendências, evidências |
| Referência de evidência | caminho relativo ao workspace explícito, hash quando disponível, instante de verificação, escopo da verificação |
| Vínculo | tarefa, tipo `session/run/job/artifact`, provedor, ID externo, capacidades declaradas |
| Atenção | chave estável derivada, motivo, revisão/evento de origem, reconhecido em |
| Medição | tarefa, condição experimental, evento e valor observado; autoria humana ou instrumentação |

Timestamps são UTC com timezone. O estado da tarefa é `open`, `paused` ou `closed`; execução e aceitação ficam nos registros de origem. Fechar a tarefa não encerra agentes. Pausar tarefa não cancela processos.

O store recusa revisão inesperada com conflito explícito; duas sessões não sobrescrevem silenciosamente o mesmo checkpoint. Nenhuma operação lê PID de disco para enviar sinais. Não migrar o store de delegação na primeira versão.

## Compilação do contexto

A ordem do pacote é: identidade e objetivo; limites registrados; correções ativas; decisões; estado verificado e lacunas; próxima ação; ponteiros de evidência; referências explicitamente vinculadas, sem leitura automática de conversas.

Cada item selecionado mantém origem e indicação de ser relato, proposta ou verificação. Escopo autorizado é referência a uma decisão humana; sua presença no pacote não amplia autorização nem torna texto externo uma instrução confiável.

O pacote preserva todas as correções e limites marcados como críticos. Se não couberem no orçamento, recusa a exportação e informa o excesso. Não truncar silenciosamente um item crítico. Itens opcionais omitidos aparecem em um manifesto de exclusão com motivo e ponteiro. Nunca estimar tokens como se a contagem fosse do provedor; usar bytes/caracteres medidos ou tokenizer identificado.

Fontes alteradas exigem reconciliação antes de um pacote marcado pronto. Ausência de hash significa não verificado. Hash igual prova identidade de bytes, não atualidade ou verdade. O papel da evidência é declarado no checkpoint. A candidata preserva valores escalares simples de `knowledge_status`, `as_of` e `superseded_by` no frontmatter, sem interpretá-los como verdade, autorização ou vigência. Não é um parser YAML geral nem um recuperador semântico; conteúdo integral da fonte não entra automaticamente no pacote.

Uma referência movida pode ser substituída explicitamente com `replaces` e `replacement_reason`: o alvo deve estar ativo, o novo arquivo deve ser verificável e a criticidade anterior é preservada. A auditoria guarda a referência anterior. Correções podem substituir decisões, correções e restrições, sempre críticas e declaradas; só uma decisão humana real altera autorização.

O arquivo exportado é um handoff fora do vault. A UI permite inspecionar e copiar o pacote. A primeira versão não o injeta numa sessão nativa sem ação explícita.

## Inbox confiável

A inbox é projeção, não supervisor. O board existente pode atualizar estado privado ao detectar supervisor órfão; a documentação não deve chamá-lo de leitura pura. Integridade de fontes continua sendo conferida na operação de leitura/aceitação apropriada, não inferida do board.

Origens do contrato: `supervisor_observed`, `host_event`, `principal_reported`, `local_verification`, `unknown`. A candidata aceita checkpoints apenas com `principal_reported` ou `unknown`; `local_verification` é produzido internamente. `host_event` e `supervisor_observed` ficam reservados para adaptadores futuros, não são aceitos como alegação manual. Mostrar tempo da observação e validade. Principal e agentes nativos sem eventos disponíveis aparecem como não observados, nunca como saudáveis por ausência de erro.

Reconhecimento aplica-se a uma chave de evento/revisão. `seen` não significa `resolved`: resolução exige reconciliação explícita ou desaparecimento comprovado da condição. Um evento posterior pode reabrir atenção. A deduplicação não deve esconder uma falha nova. A fonte indisponível produz um estado indisponível, sem reutilizar silenciosamente a última linha verde.

## Isolamento e superfície local

Todo estado, exportação, log e cache ficam em uma raiz de laboratório explicitamente registrada, externa ao vault protegido. Não aceitar caminhos de saída arbitrários, travessias ou symlinks para fora da raiz. O runner recusa uma raiz de laboratório que contenha ou esteja contida no vault protegido.

O servidor escuta somente loopback, sem recursos de terceiros. A primeira UI é de consulta: não possui endpoints de mutação e consome projeção previamente produzida pela CLI, sem consultar diretamente operações de recuperação do supervisor. Validar Host e origem, limitar acesso aos dados da sessão local e escapar conteúdo HTML. Não expor endpoint de execução de shell, leitura arbitrária de arquivo ou navegação fora das raízes registradas. Uma futura UI com mutações exigirá token de sessão, método apropriado, limite de tamanho, revisão esperada e testes de repetição e origem; não está implicitamente autorizada por esta primeira versão.

Instalação não inicia servidor, observador ou modelo. Só o comando explícito abre a superfície. O laboratório deve combinar prevenção de escrita no vault protegido com verificação de integridade; comparar hashes depois não é uma sandbox.

## Aceite do produto

Os requisitos são rastreados como `R1` identidade e seleção; `R2` contexto e correções; `R3` integridade e escopo; `R4` inbox e estados; `R5` concorrência e recuperação; `R6` isolamento e segurança local; `R7` rollback; `R8` evidência de valor. Os cenários correspondentes estão em [VALIDATION.md](VALIDATION.md).

Uma release candidata pode estar tecnicamente apta e ainda não ter valor demonstrado. A promoção funcional exige os testes de uso. A instalação real exige pedido explícito e gates técnicos. O pedido posterior de reinstalação permite atualizar o harness, preservando conteúdo, configuração local e memória do vault.
