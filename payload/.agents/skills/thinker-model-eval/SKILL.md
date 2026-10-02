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

Para rodadas persistentes, use `python3 harness/scripts/model-eval.py`: plan congela sem chamadas; run/collect executam pela delegação; blind prepara revisão; grade, trajectory e feedback preservam sinais separados; report mostra cobertura e limites. A suíte workload-v1 contém doze casos sintéticos e não substitui avaliação de tarefas completas.

Novas rodadas e juízes exigem esforço solicitado mínimo high. Use inventory/--all-profiles e perfis explícitos para cobertura ampla; preserve indisponíveis sem substituição silenciosa. Para tarefas completas, prepare cria o workspace, o host executa com ferramentas e finish verifica o estado final. Isso não inicia um supervisor nem cria sandbox de segurança para o host. Código candidato exige o backend Docker isolado e explícito; sem runtime, registre indisponibilidade.

Use critérios com evidência literal, revisões via supersedes e julgamento calibrado. judge-packet e calibrate não chamam modelos. Pares cegos e feedback só registram observações humanas explícitas. Sucesso técnico não implica preferência pessoal, um número mínimo de casos não demonstra validade e nenhum relatório altera rotas automaticamente. Consulte workload-v2 para fixtures e referências; tarefas públicas não são confirmação privada.
