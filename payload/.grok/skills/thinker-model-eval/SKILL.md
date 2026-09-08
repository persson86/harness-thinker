---
name: thinker-model-eval
description: Avaliar modelos atuais ou candidatos no Thinker por delegação controlada, casos cegos, validação determinística, board e relatório de Pareto.
---

# Thinker Model Eval

Leia harness/operations/model-eval.md e harness/operations/delegate.md. O Grok permanece o interlocutor principal desta sessão; colaboradores devolvem propostas.

Descubra os perfis disponíveis e preserve nomes de outros provedores sem traduzi-los para modelos Grok. O teste mede modelo solicitado + effort + CLI + instruções + permissões, não um peso isolado.

Não faça chamadas quando o usuário pediu apenas o desenho. Com autorização de execução, congele caso, gabarito e spec antes das respostas, acompanhe pelo board e valide a estrutura com python3 harness/scripts/model_eval_validate.py.

Não some tokens entre provedores, não trate retorno como qualidade, não registre feedback humano por inferência e não mude defaults sem decisão explícita.
