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

Para um primeiro recorte pequeno, use `harness/evals/knowledge-mini-v1/`: oito casos sinteticos de revisao guiada, com controles corretos, caso cego, spec e rubrica separados. Copie-os para o diretorio da rodada e congele hashes antes das respostas. Envie apenas `case.md`; nao envie gabarito/spec nem reutilize como candidato um agente que os leu. O README da fixture descreve o procedimento sem introduzir servico ou chamadas automaticas. Screening nao valida ingestao end-to-end.

## Preparação

1. Leia wiki/index.md, vault.config.json, harness/contract.md, vault-heuristics.md quando existir e harness/operations/delegate.md.
2. Crie um ID de sessão exclusivo. Consulte status, doctor --all-profiles e board. Doctor comprova interface e login quando observáveis; não comprova acesso ao modelo nem identidade servida.
3. Descubra perfis dinamicamente. Para modelo não cadastrado, exija provider, ID e effort explícitos e confira route antes de submeter.
4. Defina se todos usam o mesmo effort — comparação com menos confusão — ou se cada rota usa seu default — teste da política de roteamento. Registre a escolha.
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

Primeiro aplique piso de qualidade e falhas críticas. Entre aprovados, identifique a fronteira de Pareto; preserve empate e resultado inconclusivo. Se todos empatarem, aumente a dificuldade antes do número de modelos. Se nenhum passar, revise caso, gabarito e transporte antes de culpar modelos.

## Encerramento

- todos os jobs pedidos estão terminais;
- inbox reconciliada;
- caso, gabarito, spec e relatório permitem reprodução;
- raw/ segue intocado;
- nenhuma alteração de default ou feedback foi inferida;
- a devolutiva começa com Resumo e Ideias principais, diz limites e propõe o teste mínimo que reduziria a incerteza restante.
