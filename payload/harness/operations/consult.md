# Advisor, Reviewer e autonomia

O **Orquestrador** é o principal da sessão escolhido pelo usuário. Ele conserva escopo, autorização, integração e verificação. **Advisor** aconselha antes ou durante uma dificuldade, em modelo nativo do mesmo harness/provedor. **Reviewer** contesta uma proposta ou entrega, em modelo de fronteira de outro harness/provedor; se o outro provedor estiver indisponível, um agente novo do mesmo harness assume como fallback declarado (ver `reviewer.md`). Os dois papéis são opcionais e podem ser acionados separadamente.

## Escolha e iniciativa

Escolha modelo e esforço pelo assunto, dificuldade, consequência do erro, contexto necessário, disponibilidade, uso e latência. Opus, Sol, Fable, Astra e outros perfis elegíveis podem ocupar esses papéis conforme o contexto. Não há exigência de Advisor superior nem escada fixa. Consulte as capacidades reais do host; ausência de modelo explicitamente solicitado não autoriza substituição silenciosa.

Autonomia vem ligada por padrão, mas disponibilidade não obriga convocação. Acione **Advisor** quando uma dúvida delimitada, alternativas incompatíveis ou dificuldade persistente puderem mudar a abordagem. Acione **Reviewer** para aposta material, irreversibilidade, evidência frágil ou travamento, conforme os gatilhos de `delegate.md`. Profundidade e complexidade precisam de uma pergunta concreta; a sensação de confiança do principal não é critério suficiente. Pergunta rápida, reflexão aberta e trabalho mecânico com checagem determinística ficam no principal quando não houver consequência material.

Anuncie em uma linha o motivo, papel e modelo antes de convocar. Uma consulta só é `explicit` quando o usuário pediu aquela consulta ou revisão, dentro do seu escopo. Autorizar a tarefa principal não transforma suas consultas automáticas em explícitas. Colaboradores entregam pareceres; não convocam outros colaboradores e não alteram controles.

## Controle pela conversa

O agente opera a CLI; o usuário não precisa escrever comandos:

| Pedido | Comando |
|---|---|
| Mostrar a autonomia e consultas desta sessão | `python3 harness/scripts/delegate.py autonomy status` |
| Desligar / ligar a autonomia nesta sessão | `python3 harness/scripts/delegate.py autonomy off` / `autonomy on` |
| Deixar desligado / ligado por padrão nas próximas sessões | `python3 harness/scripts/delegate.py autonomy off --default` / `autonomy on --default` |
| Desligar / ligar em todas as sessões e no padrão | `python3 harness/scripts/delegate.py autonomy off --all` / `autonomy on --all` |
| Desligar e solicitar cancelamento das automáticas nesta sessão | `python3 harness/scripts/delegate.py autonomy off --cancel` |

Use sempre o ID real da sessão, conforme `delegate.md`. O escopo padrão é esta sessão. Uma sessão é conhecida após admissão, job ou configuração explícita; leitura de status é somente leitura e não registra a sessão. O default é fixado para uma sessão na sua primeira admissão; mudar apenas o default não altera escolhas de sessões já registradas. `--all` invalida escolhas anteriores no escopo e muda o default. Uma escolha explícita posterior para uma sessão pode abrir uma exceção, que deve ser informada. Reinício, atualização e pedido explícito avulso não religam a autonomia.

**Autonomia desligada:** bloqueia novas consultas automáticas nativas e externas pelo protocolo, inclusive as ainda não iniciadas. Vale para toda iniciativa automática da extensão: uma submissão sem papel de consulta também é automática e fica bloqueada até haver pedido explícito. Pedidos explícitos continuam possíveis e não mudam o toggle. Trabalhos já iniciados continuam por padrão; seus retornos podem ser integrados sem abrir novas consultas automáticas. Informe os ativos. Com `--cancel`, solicita-se cancelamento das consultas automáticas ativas; consultas explicitamente pedidas não são canceladas por esse toggle. Distinga cancelamento solicitado de confirmado; agentes nativos exigem o controle real do host para parar. Nunca afirmar que um processo parou a partir de metadados.

**Delegação desligada** (`off` / `off --all`, sem `autonomy`) é outro controle: bloqueia inclusive submissões explícitas da extensão e solicita cancelamento. Ele prevalece sobre a autonomia; não o religue para contornar uma recusa. Para nativos, consulte esse estado antes da admissão e use o host para cancelamento. Preserve também o modo legado `request`: ele não autoriza convocações automáticas.

## Admissão e execução

Leia `delegate.md` para transporte, contexto, quotas e inbox. Antes de cada consulta, consulte os controles. Identifique uma **entrega** estável em `--delivery`: todas as tentativas e papéis do mesmo resultado usam esse ID. Não trocar o ID, sessão, papel ou provedor para recuperar orçamento.

Nativo, no mesmo provedor, com a pergunta e o benefício em `--reason`:

```bash
python3 harness/scripts/delegate.py --json consult admit --consult-role advisor --delivery arquitetura-v1 --initiation auto --provider codex --model astra --reason "Comparar as alternativas de persistência antes de escolher"
python3 harness/scripts/delegate.py --json consult start ID
```

Só depois do `start` autorizado use o spawn do host, com brief mínimo e paths exclusivos quando houver escrita autorizada. Não há spawn pela CLI. Assim que o spawn devolver o ID do agente (no Claude Code, o `agentId`; no Codex, o ID ou apelido do agente), registre `consult link ID --agent-id AGENTE`, para que painéis mostrem o papel no próprio agente; se o ID só chegar no retorno, passe `--agent-id` no `finish`. Ao evento real de retorno, registre `consult finish ID --state completed|failed|cancelled`, além dos metadados `native report` quando pertinentes. Se o spawn falhar, finalize como falha; não abandone uma admissão em execução nem registre conclusão antes do retorno. Uma consulta nativa sem `finish` por mais de duas horas aparece como `stale` e deixa de ocupar vaga de concorrência; isso é registro, não prova de que o host parou o agente. Uma reserva invalidada pelo desligamento não pode iniciar ao religar.

Externo, no outro provedor, use o supervisor existente:

```bash
python3 harness/scripts/delegate.py --json submit --task review --model opus --consult-role reviewer --delivery arquitetura-v1 --initiation auto --critical-review --benefit "Contestar premissas e limites da proposta" --reason "gatilho: mudança de invariante" --prompt "Examine os requisitos e o artefato anexado; devolva objeções verificáveis." --file drafts/proposta.md
```

Reviewer de fallback, no mesmo provedor, quando o outro está indisponível, usa a admissão nativa com o motivo observado:

```bash
python3 harness/scripts/delegate.py --json consult admit --consult-role reviewer --fallback "quota do codex blocked" --delivery arquitetura-v1 --initiation auto --provider claude --model fable --reason "Contestar premissas e limites da proposta"
```

O fallback ocupa a vaga de Reviewer da entrega. Sem tentativa externa (indisponibilidade vista na quota ou no `doctor`), ocupa a vaga diretamente; depois de uma tentativa externa, só a reaproveita se ela falhou por limite, infraestrutura ou timeout, não por saída inválida ou cancelamento. No máximo um fallback automático por entrega.

`--consult-role` não é o `--role` dos runs. Submissões legadas sem classificação continuam compatíveis, mas omitir `--initiation` significa `auto` e não contorna autonomia OFF ou modo `request`; omitir o papel não oferece garantia técnica de orçamento por papel, portanto o Orquestrador deve classificar toda consulta. Em uma rodada adicional explicitamente solicitada de um job existente, `retry JOB --initiation explicit --reason "Pedido e diagnóstico"` preserva a entrega e o papel. Em pedido explícito, use `--initiation explicit` sem alterar a autonomia; preserve a referência ao pedido no motivo. Registro de iniciativa é declaração do Orquestrador, não prova automática de autorização humana. Não omita os campos de consulta nem use submissão legada, outro transporte ou delegação genérica para contornar os controles.

## Orçamento e verificação

O orçamento automático inicial é uma admissão de Advisor e uma de Reviewer por entrega, dentro dos limites agregados de sessão/provedor e concorrência. Falhas, cancelamentos e troca de modelo não devolvem orçamento. Novas rodadas exigem questão ainda aberta e autorização explícita quando o orçamento automático acabou; não há escalada recursiva. Os limites não são quota real nem teto monetário. Uso desconhecido continua desconhecido; não somar tokens de provedores como se fossem uma quota única.

Consulte a política de admissão para nativos e os metadados de consulta dos jobs externos ao informar o estado. Motivo, iniciativa, papel e modelo devem ser recuperáveis. Prefira um Advisor sobre as alternativas e o Reviewer único sobre o artefato real antes da adoção/publicação; se já gastou a revisão na proposta, não presuma outra gratuita para o diff. O Orquestrador confere o resultado real, registra o efeito da consulta sem inferir aprovação humana e preserva divergências materiais. Não resolve por votação ou prestígio do modelo. Fato pede fonte ou teste; prioridade e tolerância a risco podem exigir decisão do usuário. Nenhuma consulta autoriza escrever, publicar ou executar além do pedido.

## Limite do controle nativo

A CLI controla admissões e subprocessos externos; não intercepta as ferramentas de spawn de todos os hosts. No Codex e nos demais hosts sem gate técnico integrado, o Orquestrador deve obrigatoriamente executar `consult admit/start` antes de convocar um consultor nativo. É um protocolo cooperativo, não um bloqueio técnico universal. A janela entre a checagem e o spawn e sessões que não seguem o protocolo não estão cobertas como processos pelo controle. Informe essa limitação quando ela afetar um desligamento; não prometa economia ou cancelamento que não foram observados.
