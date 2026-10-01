# Estratégia de validação e testes de uso

## O que cada evidência permite afirmar

| Nível | Execução | Afirmação permitida |
| --- | --- | --- |
| E0 | Leitura e revisão da spec | Desenho analisado, sem comportamento comprovado |
| E1 | Testes determinísticos e simulações | Contratos e invariantes passaram nos casos testados |
| E2 | Agentes reais em casos sintéticos | Comportamento observado da configuração naquele workload |
| E3 | Uso humano de tarefas representativas no laboratório | Esforço, compreensão e qualidade observados no piloto |
| E4 | Uso cotidiano sustentado | Valor recorrente observado; fora do escopo atual de não escrita no vault |

Não chamar E1 de teste com agentes ou E2 de economia humana. Não prometer certeza universal de valor. A decisão deve declarar amostra, falhas, dados ausentes e limites de generalização.

## Baseline justa

Comparar com harness 7.22.1 usando seu handoff e board existentes. Não enfraquecer a baseline para produzir ganho. Fixar materiais, objetivos, permissões, orçamento de contexto e versão de modelo solicitada em cada par. Configurações diferentes invalidam atribuição causal ao novo recurso.

Condições: A, fluxo atual; B, tarefa e pacote de retomada; C, mesmos mecanismos de B com superfície própria. Primeiro A/B avalia continuidade. Depois B/C avalia interface. Não comparar A/C e atribuir tudo à UI.

## Casos técnicos e comportamentais

| Caso | Requisitos | Estímulo | Resultado exigido |
| --- | --- | --- | --- |
| T01 | R1 | Duas tarefas intercaladas, segunda mais recente | Retomar ID selecionado; sem fallback para recência |
| T02 | R1 | Sessões/cwd distintos, mesmo workspace explícito | Vínculo explícito preserva tarefa; workspace diferente no namespace recusado |
| T03 | R2 | Correção humana antiga e hipótese antiga repetida recentemente | Correção ativa preservada com origem e supersedes |
| T04 | R2 | Pacote excede orçamento | Críticos preservados; export falha se não couberem; omissões opcionais declaradas |
| T05 | R2 R3 | Fonte mudou após checkpoint | Estado alterado; não declarar pronto sem reconciliação |
| T06 | R2 R3 | Fonte ausente, sem hash ou histórica | Distinguir ausente, não verificado e histórico; não inferir vigência |
| T07 | R2 R3 | Proposta sem aceite junto de decisão aceita | Preservar os estados e autoria; não promover proposta |
| T08 | R2 R3 | Reset de continuidade seguido de retomada | Contexto de geração anterior excluído sem fallback |
| T09 | R3 R6 | Referência com traversal ou symlink para raiz protegida | Recusa antes de escrita, sem artefato parcial |
| T10 | R4 | Job vinculado sem observação e artefato declarado | Job desconhecido; artefato é referência, sem comprovar entrega ou utilidade |
| T11 | R4 | Item visto, depois revisão nova da mesma pendência | Novo evento reaparece; visto não equivale a resolvido |
| T12 | R4 | Host nativo sem eventos observados | Desconhecido explícito, sem progresso inventado |
| T13 | R4 | Store bloqueado, corrupto ou indisponível | Indisponível, sem zero falso nem última linha verde |
| T14 | R5 | Duas mutações com mesma revisão | Uma vence; outra recebe conflito, sem perda silenciosa |
| T15 | R5 | Crash durante persistência e pedido repetido | Documento antigo ou novo íntegro; recibo impede duplicação |
| T16 | R5 | request_id repetido com payload diferente | Conflito, nenhum segundo efeito |
| T17 | R6 | Conteúdo HTML/JS, Host externo, URL arbitrária | Conteúdo inerte; nenhuma leitura/execução fora do contrato |
| T18 | R6 | Abrir UI, copiar pacote, consultar inbox | Zero chamada de modelo, retry ou escrita editorial |
| T19 | R7 | Instalar, atualizar, desativar e voltar à baseline | Conteúdo/config preservados; tarefa exportável; baseline utilizável |
| T20 | R7 | Schema futuro desconhecido | Recusa segura, sem downgrade ou sobrescrita |

Testar comandos reais da CLI e do installer nos cenários relevantes; testes unitários que espelham funções não substituem a fronteira de processo. UI exige inspeção visual e fluxo de navegação, além de assertions de DOM.

## Ensaios com agentes

Protocolo inicial proposto: quatro cenários semânticos, A/B, dois provedores, total de 16 chamadas. Acrescentar até oito chamadas em quatro episódios encadeados para observar a passagem checkpoint/retomada. Teto total: 24 chamadas; concorrência 2; esforço solicitado Max; timeout por chamada 1.200 segundos; sem retry automático.

Essa matriz é uma proposta, não autorização de gasto nem resultado executado. Antes de executar, congelar perfis reais disponíveis, versões, fixture, rubrica, orçamento, contexto e stop rule em manifesto. Se acesso falhar, diagnosticar e registrar; não trocar modelo silenciosamente. A revisão da spec por modelos não conta nessas 24 chamadas nem como resultado comportamental.

Os workers recebem casos, não respostas esperadas. A rubrica e adjudicação ficam fora do contexto do candidato. Ordem A/B alternada por cenário, e variantes equivalentes reduzem memorização. Julgamento cego à condição quando possível; comparação de saída com fonte é obrigatória, independentemente da nota de outro modelo.

Registrar conclusão de transporte, saída bruta delimitada, identidade solicitada/reportada, esforço solicitado, tokens do provedor quando disponíveis, latência, número de intervenções e falhas. Não somar contadores de provedores diferentes como custo comparável.

Testes com agentes exigem uma fronteira de autenticação explícita: login próprio de laboratório ou acesso externo de autenticação permitido e documentado, com ferramentas e escrita restritas ao laboratório. Nunca copiar arquivos de credenciais para fixtures. Se não houver uma forma segura e funcional, o nível E2 fica pendente, sem simulação apresentada como execução real.

## Teste de uso humano

Executar fora do vault real, com tarefas sintéticas representativas ou materiais novos escolhidos para o laboratório. Participante humano opera ambas as condições após treinamento equivalente. Agente pode facilitar e registrar, mas não preencher a avaliação de utilidade em nome da pessoa.

Mínimo proposto: oito tarefas pareadas, distribuídas em pelo menos quatro sessões, com janela máxima de 14 dias. Incluir duas retomadas após intervalo, duas tarefas intercaladas, revisão de entrega divergente e uma falha operacional simulada. Alternar ordem; usar variantes equivalentes. A janela de 14 dias é desenho de piloto, não duração já cumprida.

Medida primária: minutos de atenção humana até uma conclusão correta. Somar preparação, criação/revisão do checkpoint, busca de contexto, supervisão, correções, revisão e recuperação de falhas. Tempo de espera do modelo é medido separadamente. Se o candidato exigir mais preparação, esse custo entra na conta.

Medidas secundárias: erros críticos/não críticos, reexplicações, releituras, intervenções, tempo para identificar quem precisa de ação e esforço percebido numa escala consistente de 1 a 5. Também registrar custo de instalação e manutenção em horas; não convertê-lo artificialmente em minutos economizados por tarefa sem horizonte observado.

Falhas e abandonos permanecem no denominador. Para tarefa sem conclusão correta, registrar censura/falha e custo observado, sem inventar um tempo final favorável. Não excluir um caso depois de conhecer seu resultado. Dados de cronômetro ausentes tornam a métrica inconclusiva.

## Critérios de decisão pré definidos

Os limiares abaixo são escolhas propostas para o experimento, não efeitos esperados:

- Segurança e qualidade: zero escrita fora do laboratório; zero erro crítico de autorização, correção ou estado vigente; nenhuma perda de dado.
- Atenção: redução mediana pareada de pelo menos 20% e de pelo menos um minuto por tarefa, incluindo preparação e revisão.
- Consistência: pelo menos seis dos oito pares melhoram ou empatam, sem aumento da mediana de correções e sem esconder um caso de regressão crítica.
- Manutenção: registrar horas reais e estabelecer com o participante o orçamento aceitável antes do piloto; orçamento ainda não definido impede conclusão sobre custo total.
- Preferência: avaliação humana explícita de utilidade e intenção de continuar, registrada separadamente das métricas.

Esses gates habilitam continuação experimental, não provam ganho populacional ou sustentado. Amostra pequena recebe relatório descritivo, com cada par visível; não fabricar significância estatística.

Parar imediatamente ao detectar escrita fora do escopo, perda de estado, vazamento de material ou duplicação de efeito. Guardar evidências no laboratório, desativar candidato e executar rollback. Não reparar automaticamente o vault protegido.

Se a qualidade passar e o valor não, simplificar ou retirar a função. Se a atenção melhorar e a qualidade falhar, reprovar. Se faltarem dados, manter inconclusivo. Nunca usar testes técnicos verdes para preencher a ausência de teste de uso.

## Relatório final obrigatório

Declarar nível E0 a E4 alcançado; versões e hashes; matriz planejada/executada; todos os casos e falhas; métricas por condição; custos não observados; feedback humano; resultado do rollback; integridade da raiz protegida; decisão de manter, simplificar ou não promover. Resultados privados ficam no laboratório, não no payload nem no vault real.

## Limites de cobertura da candidata

T02 cobre um workspace explícito por namespace; múltiplas raízes e descoberta de worktrees não estão implementadas. T10–T12 cobrem desconhecimento explícito e atenção derivada de tarefas, sem importar eventos de hosts/supervisores. T15 usa interrupção de processo injetada antes da substituição atômica; isso não simula todos os modos de falha de disco ou falta de energia. Inspeção visual com dados sintéticos é separada da integração real CLI/interface. Restrições do ambiente que impeçam portas ou execução protegida bloqueiam esses ensaios, não contam como aprovação.
