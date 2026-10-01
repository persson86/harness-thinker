# Inspirações e decisão de arquitetura

## Resumo

A oportunidade mais útil é tornar a continuidade e a supervisão propriedades do setup, reduzindo a reconstrução manual de contexto. A recomendação é preservar os hosts de agentes e o conhecimento curado e acrescentar uma camada pequena de tarefas, retomada e atenção. Esta é uma hipótese de produto a validar, não uma economia demonstrada.

## Ideias principais

- Tarefa, conversa, execução e conhecimento precisam de identidades e estados separados.
- A interface deve explicar o que exige ação e de onde veio essa informação.
- Retomar exige preservar correções e limites, não apenas recuperar o último texto.
- A implementação inicial deve continuar utilizável e reversível sem um serviço remoto.
- Medir preparação, supervisão e correções junto com o tempo de execução.

## Comparação por camada

| Camada | Referência | Ideia aproveitável | Decisão para o Thinker |
| --- | --- | --- | --- |
| Ambiente de trabalho | Synara | Conectar projeto, tarefa, sessão e revisão | Tarefa explícita e superfície de consulta; integração profunda depois |
| Execução persistente | Cloudroom core | Tratar ciclo de vida e recuperação como contratos próprios | Reutilizar supervisor existente e declarar estados desconhecidos |
| Atenção | cmux | Organização de sessões e notificações próximas do trabalho | Inbox com motivo, origem e leitura separada de resolução |
| Recuperação | QMD | Pesquisa local combinando diferentes mecanismos de busca | Experimento posterior, se houver falhas de recuperação medidas |
| Conhecimento | Harness e vault | Regras editoriais, proveniência e validação | Preservar a separação entre relato, proposta e conhecimento |

O [Synara](https://github.com/Emanuele-web04/synara) se apresenta como workspace local para agentes de programação: projetos, threads, sessões de provedores e ferramentas de execução/revisão. Sua documentação descreve worktrees gerenciados, handoffs e integrações com runtimes locais. A contribuição para esta spec é a separação de entidades e a proximidade entre tarefa e revisão. Não há evidência, nesta análise, de que sua instalação reduziria o esforço de manter uma wiki pessoal; copiar toda a aplicação ampliaria bastante a manutenção.

O [Cloudroom core](https://github.com/davidondrej/cloudroom-core) é um runtime Rust voltado a agentes em uma máquina Linux, com autenticação existente dos provedores e histórico em PostgreSQL externo. A aplicação desktop é uma peça separada. Isso resolve outra camada: execução e armazenamento de sessões. A inspiração relevante é explicitar ciclo de vida e recuperação. Adotar sua arquitetura inteira exigiria operação de infraestrutura que esta primeira hipótese de continuidade não necessita.

O [cmux](https://github.com/manaflow-ai/cmux) se concentra no terminal macOS, organização de trabalho paralelo e notificações de agentes. É uma referência de interface e distribuição de atenção, não evidência de correção semântica dos resultados. O [QMD](https://github.com/tobi/qmd) se apresenta como busca local para documentos e bases de conhecimento. Vale como experimento de recuperação separado; não substitui os contratos editoriais ou o controle de autorização.

As páginas acima foram verificadas em 2026-09-30. São descrições dos próprios projetos, não testes comparativos nem prova de adoção. A escolha de inspirar-se neles não exige instalar, migrar ou integrar qualquer um.

## Onde o setup já é forte

A baseline inspecionada, 7.22.1, já oferece contratos para o vault, verificação de integridade, delegação por propostas, estado privado, registros de origem, handoff e avaliação controlada de modelos. Isso é uma base operacional relevante. Criar outro executor ou trocar todos os agentes sacrificaria essa base antes de demonstrar uma necessidade.

A lacuna escolhida para o primeiro experimento fica entre essas peças: identidade estável da tarefa, correções que sobrevivem à troca de sessão e visão de pendências que não exija abrir cada histórico. Essa avaliação arquitetural precisa ser confrontada com o piloto. Se o handoff atual já resolver os casos com menos custo, a camada nova deve ser simplificada ou retirada.

## Sequência recomendada

1. Continuidade por tarefa com contexto determinístico e reversão exercitada.
2. Uso humano pareado, incluindo custo de registrar checkpoints e revisar respostas.
3. Se o valor for observado, integrar eventos reais dos hosts e do supervisor para reduzir registro manual.
4. Se a dificuldade persistente for encontrar evidências, testar busca híbrida com casos cegos.
5. Avaliar chat próprio, múltiplas raízes e execução remota somente após demonstrarem um problema que a camada atual não resolve.

O passo 3 tem potencial de reduzir mais atrito, mas também altera a fronteira de observação e controle. Exige testes próprios de reconexão, eventos repetidos, cancelamento e efeitos incertos. Não é apenas adicionar botões.

## O que faria esta recomendação mudar

Ganho humano ausente, manutenção frequente, duplicação do estado dos hosts, perda de correção, contexto excessivo ou alerta ruidoso são razões para reduzir o escopo. Uma preferência por interface integrada pode justificar experimentar Synara ou Cloudroom, mas ainda exigiria preservar conhecimento, autorização e possibilidade de saída. O critério decisivo é esforço até um resultado correto, não quantidade de recursos.
