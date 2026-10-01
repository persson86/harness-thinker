# Evolução do setup Thinker

Esta especificação define uma evolução do Thinker centrada em tarefas: retomar o trabalho correto, preservar decisões e correções e identificar o que depende de atenção humana. O conhecimento continua no vault e os agentes continuam nos seus hosts. O resultado esperado é menos reconstrução de contexto e supervisão, com qualidade preservada.

**Estado:** candidata implementada em laboratório, em validação; benefícios humanos ainda não demonstrados. Versão documental: `1.0.0`. Base técnica inspecionada: harness `7.22.1`. Versão de runtime candidata: `7.23.0-rc.1`, exclusivamente em laboratório. A atribuição de uma versão não substitui os gates para criar a tag de release.

| Documento | Finalidade |
| --- | --- |
| [RESEARCH.md](RESEARCH.md) | Comparação das referências e decisão de arquitetura |
| [QUICKSTART.md](QUICKSTART.md) | Operação manual da candidata e do piloto em laboratório |
| [SPEC.md](SPEC.md) | Produto, arquitetura, contratos e critérios de aceite |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | Sequência executável de entregas e dependências |
| [VALIDATION.md](VALIDATION.md) | Testes técnicos, comportamentais e de uso, com critérios de valor |
| [RELEASE.md](RELEASE.md) | Versionamento, isolamento, promoção e rollback |
| [experiment.json](experiment.json) | Critérios de avaliação legíveis por máquina, ainda sem resultados |

## Limites desta mudança

Durante implementação e testes, o vault de trabalho real é protegido integralmente contra escrita. Isso inclui conteúdo, arquivos ocultos, configuração, índices, memória extraída, drafts, estado Git e harness instalado. Não executar comandos de startup que sincronizem conversas naquele diretório. O laboratório usa conteúdo sintético e estado independente; a fase inicial não autorizou instalação real. O pedido posterior de reinstalação permite atualizar somente os arquivos gerenciados do harness, após validação.

A reinstalação solicitada não autoriza editar conhecimento, índices, logs editoriais ou memória do vault. Concluir testes ou criar uma tag também não autoriza publicação remota.

## Decisão de produto

Implementar primeiro continuidade por tarefa e uma superfície própria de atenção. O supervisor existente permanece responsável por execução. A primeira interface registra vínculos com jobs, sem importar eventos ou criar outro motor de agentes. Busca híbrida, chat multiprovedor completo e execução remota ficam condicionados a falhas e ganhos observados, com contratos de extensão previstos, sem implementação especulativa.

A medição separa funcionamento técnico, qualidade das respostas e valor para a pessoa. Testes sintéticos podem habilitar um piloto, mas não demonstram redução de esforço humano. Um resultado sem dados suficientes continua inconclusivo.

## Referências consultadas

Documentação e código consultados em 2026-09-30; capacidades de projetos externos não foram validadas neste ambiente. As referências inspiram decisões específicas, não demonstram superioridade ou adoção.

- [Synara Agent Gateway](https://www.trysynara.com/docs/workflows/agent-gateway): vínculos entre principal, tarefas e capacidades.
- [Cloudroom lifecycle](https://github.com/davidondrej/cloudroom-core/blob/main/docs/session-lifecycle.md): recuperação e efeitos incertos.
- [cmux notifications](https://github.com/manaflow-ai/cmux/blob/main/docs/notifications.md): atenção persistente, origem e leitura separada de execução.
- [Codex App Server](https://developers.openai.com/codex/app-server) e [Claude programático](https://code.claude.com/docs/en/headless): capacidades nativas para uma integração posterior.
- [QMD](https://github.com/tobi/qmd): recuperação híbrida local como experimento separado.
- [Graphiti](https://github.com/getzep/graphiti): inspiração temporal; o Thinker já suporta `knowledge_status`, `as_of` e `superseded_by`.
