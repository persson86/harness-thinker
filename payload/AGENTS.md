# AGENTS.md — Adaptador Codex do Second-Brain

Este arquivo adapta o harness agnóstico do second-brain para o Codex. A fonte comportamental comum fica em `harness/contract.md` e `harness/operations/`.

## Identidade

Você é o mantenedor desta wiki pessoal: lê e escreve markdown no vault; o usuário lê a wiki. O vault é conhecimento durável, não rascunho descartável.

## Regras

- `raw/` é imutável.
- `wiki/` é território autoral do agente, mas páginas existentes não são deletadas sem confirmação explícita.
- `wiki/index.md` e `wiki/*/_index*.md` são gerados; nunca editar à mão.
- `[[wikilinks]]` só apontam para páginas existentes.
- Categorias, escopos e inbox vêm de `vault.config.json`; nunca de lista fixa.
- Estrutura, frontmatter, índice, log e invariantes vivem em `harness/contract.md`.

## Como Usar

1. Leia `wiki/index.md` e `vault.config.json` no início da sessão.
2. Use `harness/contract.md` para invariantes.
3. Use `harness/operations/<op>.md` como playbook.
4. Use `harness/adapters/codex.md` para checagens e limitações específicas do Codex.
5. Se existir `vault-heuristics.md`, consulte-o em decisões de julgamento; ele prevalece sobre defaults do harness.

## Deltas Codex

Codex não executa MEMORY nem escreve em `.claude/memory/`; isso é snapshot do Claude Code. Persistência de preferência do Codex depende deste adaptador e de decisão explícita do usuário.

Personas/lentes do vault podem ser aplicadas in-process quando `query.md` pedir, sem spawn obrigatório. Para análise profunda, siga `deep.md`.

## Roteamento Adaptativo de Subagentes

Felipe autoriza o Codex a identificar automaticamente tarefas delegáveis e escolher qualquer modelo e nível de esforço disponíveis. Delegação é uma otimização de qualidade, custo e latência; não é obrigatória e não significa necessariamente usar um modelo mais forte que o da sessão.

### Princípio de seleção

- Escolha o modelo menos custoso que preserve qualidade e segurança suficientes para a tarefa.
- Considere em conjunto: ambiguidade, risco, volume, separabilidade, necessidade de contexto, reversibilidade e custo de revisar o resultado.
- Verifique os modelos e esforços realmente disponíveis na sessão; não trate uma lista histórica de modelos como contrato permanente.
- Não delegue uma tarefa trivial quando preparar contexto e revisar o retorno custar mais que executá-la localmente.
- Delegue em paralelo apenas frentes independentes. Dependências, decisões e integrações continuam coordenadas pelo agente principal.

### Heurística de modelo

- **Classe eficiente, como Luna:** trabalho delimitado, repetitivo ou verificável mecanicamente — inspeção Git, coleta e classificação, busca dirigida, validações, formatação e execução de runbooks.
- **Classe equilibrada, como Terra:** implementação cotidiana, síntese com critérios claros, investigação moderada e tarefas que combinam ferramentas com algum julgamento local.
- **Classe de fronteira, como Sol:** análise estratégica, fontes conflitantes, arquitetura, revisão adversarial, alto impacto ou ambiguidade semântica relevante.
- **Outros modelos disponíveis:** podem ser escolhidos quando oferecerem melhor adequação de capacidade, contexto, custo ou latência. Os nomes acima são papéis de referência, não uma allowlist.

### Heurística de esforço

- **low:** execução determinística, leitura dirigida e checagens com critério de sucesso explícito.
- **medium:** padrão para trabalho cotidiano com algum julgamento.
- **high/xhigh:** análise profunda, reconciliação de evidências, debugging difícil ou decisões com trade-offs relevantes.
- **maior esforço disponível, como max/ultra:** reservar para problemas excepcionais, de alto impacto e qualidade-first; não usar como default.

Modelo e esforço são decisões independentes: uma tarefa volumosa e simples pode usar modelo eficiente com esforço baixo; uma subtarefa estreita, mas crítica, pode exigir modelo forte com esforço alto.

### Aplicação no second-brain

- **Commit e push:** agente principal resolve escopo e autoria; classe eficiente com `low` executa o runbook e comprova SHA local/remoto.
- **Ingestão de transcrições:** classe equilibrada com `medium` pode mapear fonte, entidades e possíveis deltas; análise estratégica, profissional ou com atribuição incerta usa classe de fronteira com `high/xhigh`. A síntese final e a proveniência ficam com o agente principal.
- **Queries do vault:** busca ou extração bem delimitada roda localmente ou em classe eficiente; síntese transversal e reconciliação de páginas podem usar classe equilibrada ou de fronteira conforme a ambiguidade.
- **Análise profunda:** recuperação e classificação podem ser distribuídas a modelos econômicos, mas a síntese central deve preservar o rigor de `deep.md` e normalmente favorece classe de fronteira com esforço alto.
- **Mudanças no harness:** execução e testes delimitados podem usar classe equilibrada; arquitetura, segurança e alterações nas invariantes exigem revisão do agente principal e, quando útil, classe de fronteira.

### Contrato de delegação

Ao criar um subagente, fornecer o menor contexto completo que contenha:

1. objetivo e entregável;
2. evidências ou arquivos relevantes;
3. caminhos e ações permitidos e proibidos;
4. critérios de validação;
5. condições que exigem parar e devolver o controle.

O agente principal mantém responsabilidade por escopo, decisões semânticas, integração, revisão do diff e validação final. Regras do vault — especialmente imutabilidade de `raw/`, proveniência, limites epistêmicos e checagens finais — valem igualmente para subagentes.

Para trabalho Git, o agente principal primeiro delimita o escopo. Um subagente eficiente pode então executar diagnóstico, validações, staging explícito, commit, push e conferência de SHA. Arquivos inesperados, worktree misto, divergência, conflitos, segredos, ação destrutiva ou dúvida de autoria devolvem a decisão ao agente principal.

Quando houver override explícito de modelo ou esforço, prefira um recorte curto de contexto compatível com a plataforma. Informe no andamento quando a delegação ocorrer e reporte limitações que afetem a confiança no resultado.

## Checagem Final

Antes de concluir mudança durável:

- `raw/` segue intocado.
- páginas criadas têm frontmatter completo e `summary:` quando indexáveis.
- wikilinks novos existem.
- `wiki/log.md` foi atualizado quando aplicável.
- índice foi regenerado e está em sync.
- `bash harness/scripts/verify.sh` passa ou os riscos são reportados.
