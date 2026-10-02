---
name: thinker-model-eval
description: Avaliar modelos atuais ou candidatos no Thinker por delegação controlada, casos cegos, validação determinística, board e relatório de Pareto.
---

# Thinker Model Eval

Leia harness/operations/model-eval.md e harness/operations/delegate.md. O Grok permanece o interlocutor principal desta sessão; colaboradores devolvem propostas.

Descubra os perfis disponíveis e preserve nomes de outros provedores sem traduzi-los para modelos Grok. O teste mede modelo solicitado + effort + CLI + instruções + permissões, não um peso isolado.

Não faça chamadas quando o usuário pediu apenas o desenho. Com autorização de execução, congele caso, gabarito e spec antes das respostas, acompanhe pelo board e valide a estrutura com python3 harness/scripts/model_eval_validate.py.

Não some tokens entre provedores, não trate retorno como qualidade, não registre feedback humano por inferência e não mude defaults sem decisão explícita.

Para rodadas persistentes, use `python3 harness/scripts/model-eval.py`: plan congela sem chamadas; run/collect executam pela delegação; blind prepara revisão; grade, trajectory e feedback preservam sinais separados; report mostra cobertura e limites. A suíte workload-v1 contém doze casos sintéticos e não substitui avaliação de tarefas completas.

Novas rodadas e juízes exigem esforço solicitado mínimo high. Use inventory/--all-profiles e perfis explícitos para cobertura ampla; preserve indisponíveis sem substituição silenciosa. Para tarefas completas, prepare cria o workspace, o host executa com ferramentas e finish verifica o estado final. Isso não inicia um supervisor nem cria sandbox de segurança para o host. Código candidato exige o backend Docker isolado e explícito; sem runtime, registre indisponibilidade.

Use critérios com evidência literal, revisões via supersedes e julgamento calibrado. judge-packet e calibrate não chamam modelos. Pares cegos e feedback só registram observações humanas explícitas. Sucesso técnico não implica preferência pessoal, um número mínimo de casos não demonstra validade e nenhum relatório altera rotas automaticamente. Consulte workload-v2 para fixtures e referências; tarefas públicas não são confirmação privada.
