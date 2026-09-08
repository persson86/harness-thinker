---
name: thinker-model-eval
description: Avaliar rotas de modelos atuais ou candidatos no workload real de um vault Thinker, usando delegação controlada, casos cegos, checks determinísticos, board e relatório de Pareto. Use para benchmark local, calibração de rota e investigação de regressão ou nerf; não use para rankings públicos genéricos.
---

# Thinker Model Eval

Leia primeiro harness/operations/model-eval.md e, quando houver execução delegada, harness/operations/delegate.md.

Avalie o stack operacional observado: modelo solicitado, effort, CLI, instruções, permissões e transporte. Não converta uma rodada local em ranking universal, nem identidade solicitada em confirmação do modelo efetivamente servido.

Antes de consumir quota, apresente perfis, effort, casos, máximo de chamadas, limites, concorrência e regra de parada. Pedido explícito para executar o benchmark já autoriza essa matriz; pedido apenas de estratégia não autoriza chamadas.

Congele caso, gabarito e spec antes das respostas. Use python3 harness/scripts/model_eval_validate.py para a superfície determinística e preserve a avaliação semântica com o principal. Outcome, trajetória, eficiência e feedback humano são sinais separados.

Use o board para acompanhamento. Não force comparações independentes em um run linear, não some tokens entre provedores, não altere defaults nem publique resultados no vault sem autorização distinta.
