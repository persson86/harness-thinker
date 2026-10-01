# Estratégia de implementação

## Sequência e responsabilidade

Construir incrementos que possam ser avaliados e revertidos separadamente. O principal integra mudanças e evidencia os gates; colaboradores recebem caminhos exclusivos. O laboratório não instala nada no vault de trabalho real.

| Etapa | Entrega | Dependência | Evidência de conclusão |
| --- | --- | --- | --- |
| M0 | Baseline, manifesto de isolamento, fixtures e rubrica congelados | Spec revisada | Hashes, paths validados, ausência de contas no laboratório determinístico |
| M1 | Registro de tarefa, checkpoint, vínculos e CLI | M0 | R1, R3, R5 e testes de persistência verdes |
| M2 | Compilador de retomada e exportação de handoff | M1 | R2 e casos de corte, correção, fonte alterada e reset verdes |
| M3 | Projeção de atenção e UI local de consulta | M1, M2 | R4, R6, avaliação visual e cenários de indisponibilidade verdes |
| M4 | Release candidata e rollback completo | M1 a M3 | Suíte completa, install/update/downgrade no laboratório, tag candidata |
| M5 | Ensaios com agentes e uso humano no laboratório | M4 | Resultados brutos, adjudicação e relatório de valor sem lacunas ocultas |
| M6 | Decidir manter, simplificar ou promover | M5 | Gate de qualidade e valor aplicado; reinstalação autorizada é separada de promoção estável |

M1 e M2 devem ser utilizáveis pela CLI mesmo sem UI. Não abrir frentes de busca híbrida ou chat próprio antes de chegar a M4. Revisar o escopo se M1 a M3 exigirem duplicar o supervisor.

## Estrutura implementada

```text
payload/harness/scripts/task.py                 interface CLI
payload/harness/scripts/thinker_tasks/          store, contexto, projeções
payload/harness/operations/task.md              operação compartilhada
payload/harness/task-surface/                   HTML, CSS e JS locais
tests/test_tasks_*.py                           regressões determinísticas
tests/fixtures/tasks/                          documentos sintéticos
scripts/setup-lab.py                            criação e inspeção do laboratório
specs/setup-optimization/                       contratos e protocolo público
```

O runner não contém paths pessoais fixos. Relatórios privados, autenticação e resultados de modelos não entram no repositório público. Não adicionar dados pessoais a fixtures ou screenshots.

## M0 antes de código de produto

1. Fixar SHA e tag da baseline, versão dos provedores e versões da spec/rubrica.
2. Definir `LAB_ROOT`, raiz protegida, targets baseline/candidato e estados separados. Recusar sobreposição por ancestralidade e identidade física dos caminhos, inclusive aliases de caixa e Unicode.
3. Criar `HOME`, `XDG_STATE_HOME` e diretórios de configuração descartáveis para os testes determinísticos. Não copiar credenciais.
4. Instalar baseline e candidato apenas em targets sintéticos distintos.
5. Criar fixture equivalente para cada braço. Congelar fontes, perguntas e rubrica antes das chamadas de modelos.
6. Conferir prevenção de escrita e registrar hashes da raiz protegida em arquivo externo a ela. Hashes são evidência de alteração, não mecanismo preventivo.

O smoke atual `tests/live_delegation.py` não basta para demonstrar isolamento: ele pode herdar HOME e configurações dos provedores. Não o chamar de sandbox completa. Determinístico e live são pipelines distintos.

## Contratos de implementação

O módulo de tarefas deve depender de interfaces pequenas: leitura de arquivo selecionado, persistência atômica e projeção de job. Não importar a implementação interna inteira do supervisor como API estável. Onde for necessário, extrair uma função de projeção documentada e testar paridade com o board antes de consumi-la.

Não acrescentar `task_id` obrigatório aos jobs antigos. O vínculo pode viver no envelope de tarefa e validar workspace e ID de origem. Não materializar cópias de resultados, acceptance ou feedback que possam divergir.

CLI da candidata, sempre com `--workspace PATH --state-dir PATH`:

```text
task create
task checkpoint --expected-revision
task link
task resume --budget-bytes
task attention
task seen --expected-revision
task reset --expected-revision
task export
task pause/close/reopen --expected-revision
task-surface.py --snapshot FILE
```

Comandos de retomada e superfície não iniciam modelos. Erros estruturados distinguem conflito, fonte alterada, fonte ausente, schema incompatível, estado indisponível e limite excedido. Não tratar todos como lista vazia.

## Experiência da superfície

Apresentar tarefas pelo objetivo, não por UUID. IDs completos ficam copiáveis nos detalhes. Tela inicial: tarefas retomáveis e itens que precisam de atenção. Cada referência a artefato mostra vínculo e origem declarada; não prova entrega, revisão ou utilidade. Mostrar quando a projeção foi gerada; a primeira UI não promete atualização em tempo real.

Na primeira versão, criar checkpoint e reconhecer atenção são comandos CLI. Copiar o pacote e navegar pelos detalhes são ações da UI. A restrição de consulta permite validar organização e compreensão antes de acrescentar controle de execução.

Após o piloto, controles de tarefa na UI só entram se o custo da CLI aparecer como fricção relevante. O eventual chat nativo exige uma spec adicional com matriz de capacidades por host, sessões retomáveis, eventos, perguntas, permissões e custo observado.

## Trabalho paralelo

Um colaborador pode implementar store/CLI; outro, fixtures e testes independentes; outro, UI sobre um contrato congelado. Não permitir edições concorrentes no mesmo arquivo. Integração, mudanças semânticas, revisão de diff, versão e tag ficam com o principal. Identidade e esforço solicitados/reportados são registrados quando observáveis; ausência permanece desconhecida.

Revisão independente deve tentar quebrar os critérios, não apenas confirmar o design. Uma segunda opinião sem inspeção do código não conta como code review.

## Incrementos seguintes condicionais

**Recuperação híbrida:** comparar busca atual com uma implementação substituível, usando perguntas com vocabulário divergente e estados históricos. Medir recall de evidência útil, qualidade final e latência total. Um ranking melhor sem resposta melhor não justifica incorporação.

**Pesquisadores com ferramentas:** somente após demonstrar que preparar pacotes é gargalo. Restrição real de leitura ao laboratório, fontes recuperáveis e principal integrador. Não ampliar a permissão dos colaboradores atuais silenciosamente.

**Chat e eventos nativos:** somente após demonstrar que a interface de consulta deixa fricção material. Cada provedor declara capacidades; não prometer uma sessão nativa única entre provedores.

**Remoto:** somente diante de tarefa concreta que necessite continuar sem o host local. Não faz parte da release candidata.
