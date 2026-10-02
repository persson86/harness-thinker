# Operação: model-eval

Use para comparar rotas atuais ou qualificar um modelo novo no workload do Thinker. A unidade é o stack observado — modelo solicitado, effort, provider CLI, instruções, permissões e transporte — e não um ranking universal do modelo-base.

## Autorização e escopo

Se o usuário pedir somente estratégia, apresente o experimento e pare antes das chamadas. Antes de consumir quota, deixe explícitos perfis, effort, casos, máximo de chamadas, contexto e saída, concorrência, timeout, retry e regra de parada. Um pedido direto para executar autoriza a matriz já delimitada.

Fixtures e relatórios ficam em drafts/model-eval/ID/. Não escrever em raw/ nem promover resultados para wiki/ sem pedido separado.

## Modos

- screening: uma chamada por perfil no mesmo caso; encontra falhas óbvias e candidatos de Pareto;
- candidate: modelo novo contra o baseline econômico plausível e o baseline confiável;
- regression: mesmo caso, snapshot e condições repetidos; requer ao menos duas repetições adicionais antes de declarar regressão, nerf ou melhoria.

Prefira candidate a repetir todos os perfis. Use screening completo somente quando solicitado ou quando cobertura ampla for o objetivo.

## Avaliador persistente

`python3 harness/scripts/model-eval.py` organiza rodadas privadas em `drafts/model-eval/ID/`. O agente opera a CLI a partir de linguagem natural: não exige que a pessoa prepare arquivos JSON. Antes de executar, transforma o pedido em matriz, critérios e orçamento revisáveis. Instalação, inventário incluindo doctor, planejamento, exportação, calibração e relatório não chamam modelos.

### Cobertura e esforço

Use `inventory` para descobrir os perfis configurados e `inventory --doctor` para conferir a interface das CLIs. `plan --all-profiles --doctor` seleciona o inventário configurado e congela a checagem atual de interface; sem `--doctor`, a disponibilidade continua desconhecida e precisa ser conferida antes de executar; `--profiles-file` acrescenta modelos exatos e observações explícitas de disponibilidade. Consulte `--help` para os argumentos atuais. Modelos expostos apenas no host precisam de configuração e transporte compatíveis; não invente que uma CLI os oferece. Atualize o inventário ao congelar cada rodada.

Novas rodadas e juízes-modelo exigem esforço solicitado mínimo `high`. Níveis superiores são configurações distintas. Não reduza esforço, substitua modelo ou repita chamada silenciosamente. Interface pronta não confirma acesso ao modelo, identidade servida nem esforço aplicado. Indisponíveis permanecem no relatório com motivo e fora das chamadas elegíveis, sem nota zero de capacidade.

### Texto e tarefas completas

`plan` congela entradas, rubricas, perfis, política e ambiente. `run` executa casos textuais pela delegação existente, preenche os slots autorizados e retorna; `collect` recupera resultados. Não há serviço ou retry automático. Falha operacional interrompe novas submissões; trabalhos conhecidos continuam recuperáveis. Submissão interrompida sem ID exige reconciliação. Use `reconcile --id ID --trial TRIAL --action bind --job JOB --reason MOTIVO` somente para vincular um job conferido contra sessão, perfil e tarefa. `--action abandon` encerra uma tentativa interrompida, preserva artefatos e motivo e não chama o modelo. Não remova estados de erro para repetir silenciosamente. Mudança do executor não autoriza finalizar uma tarefa antiga sob condições diferentes; preserve a evidência e crie uma rodada reconciliada nova.

Para casos com workflow, use `prepare --id ID --trial TRIAL`. O retorno entrega uma cópia limpa dos arquivos de trabalho em diretório temporário externo ao vault e ao experimento, com limites de escrita. Execute a tarefa com um agente do host no workspace retornado, usando somente o pacote candidato, sem rubricas, testes ou respostas de referência. O host continua responsável pelo orçamento e por observar as ferramentas. Essa cópia delimita escopo, mas não é sandbox de segurança contra um agente com acesso ao disco inteiro.

Depois, `finish --id ID --trial TRIAL` verifica arquivos efetivamente produzidos e captura os artefatos. Use as opções de arquivo de resposta, identidade e trajetória observada quando disponíveis; não preencha identidade ou trajetória com auto-relato do candidato. `run` não converte workflows em propostas textuais nem lança um segundo supervisor. Ausência de identidade ou auditoria permanece desconhecida.

Nunca execute código candidato no host para fazer o teste passar. A opção de execução de código requer Docker isolado, sem rede e com limites. Ausência de runtime ou imagem é indisponibilidade do verificador. Instalação do harness não instala Docker, não baixa imagens e não inicia candidatos.

`workload-v1` contém doze casos textuais para regressão e triagem. `workload-v2` acrescenta tarefas com estado final, controles em que agir é correto e referências de calibração. São fixtures públicas de desenvolvimento; nomes de reserva não as tornam um conjunto secreto de confirmação. Crie novos casos privados antes de qualificação. Pesquisa com fontes congeladas não demonstra busca web; checagem de Markdown/HTML não demonstra qualidade visual renderizada.

### Julgamento e calibração

Fluxo textual: `plan` → `verify` → `run`/`collect` → `blind` → `grade` e `trajectory` → `report`. Fluxo de workspace troca run/collect por prepare, execução pelo host e finish. `feedback` importa somente manifestação humana explícita. O pacote cego oferece rubrica ao avaliador, nunca ao candidato; o cegamento é processual.

Novas avaliações registram ID, avaliador, configuração, versão da rubrica, conflito de autoria, nota ordinal e cada critério com estado e evidência literal. Escala: 0 inutilizável; 1 erro central; 2 correção substancial; 3 revisão leve; 4 sem correção material identificada. Não é escala de inteligência. Se todos os avaliadores ativos tiverem conflito ou forem potenciais autoavaliadores, exija revisão independente. Uma revisão usa `supersedes` para apontar a avaliação ativa do mesmo avaliador e tentativa; histórico é preservado, sem simular outro juiz. Divergência entre juízes fica visível e não vira automaticamente uma falha factual confirmada.

`judge-packet --id ID --file PERFIL` exporta respostas originais e rubricas para um juiz explicitamente configurado em high ou acima. O agente prepara PERFIL com id, provider, model, effort e declaração booleana conflict_of_authorship. O comando não chama o juiz: delegue todos os pacotes retornados sob orçamento separado, leia o retorno e importe as avaliações. A exportação divide o conteúdo em pacotes de até 64 KiB por padrão, configuráveis entre 8 e 128 KiB; um item maior que o limite é recusado inteiro, sem truncar a evidência. Não retire avisos ou acrescente texto à resposta avaliada. Ferramentas e artifacts exigem auditoria própria além da leitura textual.

`calibrate --id ID --file OBSERVACOES` compara avaliações com um conjunto de referências atribuídas. Registre evaluator, reference_set (id, provenance synthetic ou human, reviewer, items com criteria e critical_failures) e assessments com reference_id. Referência humana exige evidência explícita; autoria declarada não é autenticada pelo software. A concordância informa cobertura, diferenças e falhas críticas; não aprova automaticamente um juiz nem inventa preferência pessoal. As referências de workload-v2 ajudam a construir esse material; os rótulos esperados ficam fora do pacote usado pelo juiz.

Use `pairwise --id ID` para pares cegos com as duas ordens; `pairwise-feedback --id ID --file ARQUIVO` registra a escolha expressa pela pessoa, justificativa e tempo observado. Ordens invertidas não são observações independentes. O agente prepara os arquivos, preservando desconhecidos. O resultado de uma comparação não deve ser transformado em autorização para mudar rotas.

### Relatório e decisão

Preserve denominadores, indisponibilidade, erros operacionais, notas por critério, ações observadas e feedback humano separadamente. Um timeout pode violar um prazo congelado, mas não prova baixa capacidade semântica. Gravidade de formato depende do caso. Falha crítica confirmada exige revisão; discordância de juiz exige adjudicação.

Compare subconjuntos com casos e condições equivalentes, mantendo exclusões explícitas. Nenhum melhor observado é apresentado como melhor entre os ausentes. Diferenças pareadas por caso, variabilidade e margens práticas declaradas devem acompanhar comparações; poucos segundos em uma tentativa não sustentam superioridade. Três casos ou IDs diferentes não demonstram validade por si mesmos.

Sucesso técnico observado é diferente de recomendação pessoal. Preferência, revisão, integração e tempo até entrega aceita exigem observações humanas. Sem elas, mantenha a recomendação pessoal inconclusiva. Pesos de ações são explicitamente definidos, não inferidos de frequência de arquivos. Não some tokens entre provedores nem trate estimativa de custo como fatura. Nunca promova resultados a defaults ou wiki por inferência.

### Exemplo de rodada delimitada

O agente opera a CLI a partir de pedidos naturais, como "avalie este modelo" ou "retome a rodada ID". O exemplo abaixo não autoriza chamadas por si só. Antes de executá-lo, declare a matriz e confira `delegate.py --session eval-example status` e `doctor --all-profiles`.

```bash
python3 harness/scripts/model-eval.py plan --id example --session eval-example \
  --suite harness/evals/workload-v1/suite.json \
  --profile luna:high --profile sol:high --profile sonnet:high \
  --case retrieval-current-decision --case analysis-intervention-result \
  --max-calls 6 --timeout 180 --concurrency 2
python3 harness/scripts/model-eval.py run --id example
python3 harness/scripts/model-eval.py collect --id example
python3 harness/scripts/delegate.py --session eval-example board --watch 5
```

`run` agenda somente slots disponíveis e retorna. O operador alterna coleta e execução até todos os trabalhos estarem terminais ou a rodada indicar bloqueio. `collect` nunca submete. Não executar laço infinito nem ignorar `blocked`. Encerrado o trabalho:

```bash
python3 harness/scripts/model-eval.py blind --id example
python3 harness/scripts/model-eval.py grade --id example --file drafts/review-grades.json
python3 harness/scripts/model-eval.py report --id example
```

O arquivo de notas é uma lista JSON. Cada item usa `blind_id` do pacote cego (ou `trial_id` em revisão declaradamente não cega), `evaluator`, `quality` de 0 a 4, `critical_failures` como lista, `notes` e `evidence` como lista não vazia de trechos/justificativas verificáveis. Importações são aditivas, sem sobrescrever a avaliação da mesma pessoa/agente. Uma segunda leitura usa outro identificador e não se passa por manifestação humana. Para trajetória, `trajectory --file` recebe itens com `trial_id`, `evaluator`, `status` pass/fail, `violations` e `notes`. Se não houver evidência suficiente, não importe aprovação.

`feedback --file` recebe itens com `trial_id`, `reviewer`, `preference` use/revise/reject, `review_minutes` e `corrections` (podem ser null) e `notes`. Só registrar essas preferências após manifestação do usuário. O relatório registra desconhecido até então. Resultados incompletos continuam consultáveis e não alteram rotas.

Para um primeiro recorte pequeno, use `harness/evals/knowledge-mini-v1/`: oito casos sinteticos de revisao guiada, com controles corretos, caso cego, spec e rubrica separados. Copie-os para o diretorio da rodada e congele hashes antes das respostas. Envie apenas `case.md`; nao envie gabarito/spec nem reutilize como candidato um agente que os leu. O README da fixture descreve o procedimento sem introduzir servico ou chamadas automaticas. Screening nao valida ingestao end-to-end.

## Preparação

1. Leia wiki/index.md, vault.config.json, harness/contract.md, vault-heuristics.md quando existir e harness/operations/delegate.md.
2. Crie um ID de sessão exclusivo. Consulte status, doctor --all-profiles e board. Doctor comprova interface e login quando observáveis; não comprova acesso ao modelo nem identidade servida.
3. Descubra perfis dinamicamente. Para modelo não cadastrado, exija provider, ID e effort explícitos e confira route antes de submeter.
4. Defina se todos usam high ou se serão comparadas configurações explícitas com esforço superior. Registre a escolha; defaults inferiores a high não entram em novas rodadas.
5. Fixe antes dos jobs:
   - objetivo e decisão que o teste pode informar;
   - hashes ou snapshot das entradas;
   - perfis, providers, modelos e efforts solicitados;
   - casos, gabaritos e falhas críticas;
   - máximo de chamadas, timeout, concorrência e retry;
   - métricas de outcome, trajetória e eficiência;
   - regra de parada e autorização observada.
6. Prepare um brief compacto, material cego, gabarito não enviado e spec JSON.

## Resposta estruturada

Prefira JSON estrito com findings. Cada finding contém:

- id;
- defect;
- evidence como lista não vazia de IDs;
- epistemic_state;
- claim_action;
- corrected_evidence_action.

Separe claim_action, sobre a afirmação original, de corrected_evidence_action, destino da formulação corrigida ou da evidência. Não informe a quantidade de defeitos quando a descoberta fizer parte do teste.

`expected_ids`, `allowed_evidence_ids` e os dois campos de ação são obrigatórios e não vazios. Spec mínimo:

    {
      "expected_ids": ["S1", "S2"],
      "allowed_evidence_ids": ["E1", "E2"],
      "max_words": 450,
      "action_fields": {
        "claim_action": ["promover", "somente source", "descartar"],
        "corrected_evidence_action": ["promover", "somente source", "descartar"]
      },
      "expected_actions": {
        "S1": {
          "claim_action": "descartar",
          "corrected_evidence_action": "promover"
        }
      }
    }

## Execução

Ative a delegação somente quando autorizado. Comparações cegas usam jobs independentes com o mesmo caso e ID no reason. O harness atual não oferece run paralelo de comparação; não force jobs independentes em chain ou principal-eval.

Use concorrência limitada. Entregue ao usuário o comando exato:

    python3 harness/scripts/delegate.py --session ID board --watch 5

O board é a fonte do estado operacional. Tempo exibido não é percentual de progresso. Voltou comprova transporte e validação estrutural, não qualidade.

Recupere e reconheça cada resultado. Valide com:

    python3 harness/scripts/delegate.py --session ID --json result JOB |
      python3 harness/scripts/model_eval_validate.py --spec drafts/model-eval/ID/spec.json --result-json -

Não faça retry automático. Falha de transporte, limite, autenticação, saída vazia ou spec defeituosa pede diagnóstico antes de nova chamada.

## Avaliação

Reporte separadamente:

- outcome: detecção, precisão, estado epistemológico, ações, aderência da evidência, concisão e formato;
- trajetória: perfil solicitado, modelo reportado, transporte, retries, timeout, fronteiras de escrita, board e alterações;
- eficiência: execução separada da fila, palavras visíveis, correções do principal, uso por job/provedor e custo somente quando rotulado como estimativa;
- feedback humano: unknown até manifestação explícita.

Não misture outcome e trajetória num score único. Não some ou normalize silenciosamente tokens entre provedores. Se model_reported vier vazio, diga que o perfil foi solicitado, mas a identidade efetivamente servida não foi confirmada.

Primeiro confira qualidade, falhas críticas e divergências de julgamento. Compare candidatos observados em condições equivalentes, com margens práticas congeladas; preserve empate e resultado inconclusivo. Se todos empatarem, aumente a dificuldade antes do número de modelos. Se nenhum passar, revise caso, gabarito e transporte antes de culpar modelos.

## Encerramento

- todos os jobs pedidos estão terminais;
- inbox reconciliada;
- caso, gabarito, spec e relatório permitem reprodução;
- raw/ segue intocado;
- nenhuma alteração de default ou feedback foi inferida;
- a devolutiva começa com Resumo e Ideias principais, diz limites e propõe o teste mínimo que reduziria a incerteza restante.

## Exemplo de tarefa completa

Este exemplo prepara uma tarefa, sem chamar um modelo. O agente escolhe explicitamente quem executará o workspace e registra a configuração realmente solicitada. A instrução do caso e o workspace vêm no retorno de prepare.

```bash
python3 harness/scripts/model-eval.py plan --id workflow-example \
  --suite harness/evals/workload-v2/suite.json --profile sol:high \
  --case retrieval-pilot-decision-v2 --max-calls 1
python3 harness/scripts/model-eval.py prepare --id workflow-example --trial t0001
# O agente do host executa o caso no workspace retornado.
python3 harness/scripts/model-eval.py finish --id workflow-example --trial t0001
python3 harness/scripts/model-eval.py blind --id workflow-example
python3 harness/scripts/model-eval.py report --id workflow-example
```

O relatório continua inconclusivo para recomendação pessoal até receber julgamento, auditoria e observações de uso suficientes. `finish` não executa a tarefa pelo agente nem confirma a identidade por conta própria.

A proteção de histórico é aplicada pela CLI e pela validação de registros. Não é autenticação criptográfica contra quem pode reescrever todo o disco. Pare o agente candidato antes de finish: a captura compara e preserva arquivos, mas não é um snapshot atômico do sistema de arquivos.
