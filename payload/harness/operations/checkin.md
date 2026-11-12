# Operação CHECKIN

O vault pergunta ao usuário sobre assuntos abertos que ele não consegue fechar sozinho: marco vencido, pendência parada, decisão sem desfecho registrado. Tudo o que acontece fora de gravação (evento presencial, corredor, conversa no carro) só chega à wiki assim. A rodada é semanal, curta e por assunto; a resposta vira relato e atualização das páginas vivas.

## Acionamento

- Pedido explícito: `/thinker-checkin` no Claude Code, `$thinker-checkin` no Codex, ou "o que está em aberto?", "faz o checkin", "me pergunta o que falta".
- Cadência: semanal. No início de sessão no vault, rode `python3 .claude/scripts/build-index.py checkin --due` (só lê `checkin.json`). Exit 0 = vencida: no fim da **primeira resposta substantiva**, ofereça a rodada em uma linha. Exit 1 = em dia: silêncio. Nunca abra a sessão com perguntas, nunca interrompa outra tarefa e ofereça no máximo uma vez por sessão.
- Recusa da semana ("agora não", "pula") → `checkin --record` para adiar até a próxima semana. "Depois" sem recusa → não registre; a próxima sessão oferece de novo.
- Se `vault-heuristics.md` tiver preferência sobre cadência, número de perguntas ou tom, ela prevalece.

## Passos

1. **Candidatos.** `python3 .claude/scripts/build-index.py checkin --json`. O script lista só entidades vivas (fora do inbox, sem status histórico ou superado) e dois sinais: `open` (linhas em seções de pendência, próximos passos, riscos ou lacunas, ou com marcador de futuro seguido de data, cuja data mais recente já passou) e `reconcile` (estado vigente datado antes do `as_of` da página). É evidência localizada, não conclusão.
2. **Reconciliar antes de perguntar.** Para cada candidato, confira nas sources mais recentes do assunto (`build-index.py review <slug>`, `search`, shard de fontes do mês) se o desfecho já está registrado. Se estiver, atualize a página a partir da source, seguindo o "Como manter" dela, e não pergunte. Os itens de `reconcile` quase sempre se resolvem assim.
3. **Agrupar por assunto.** A unidade é a pessoa, a conta, o projeto ou a decisão, nunca a reunião ou o evento da agenda. Não pergunte "a reunião X aconteceu?"; pergunte o estado do assunto ("a decisão de manter Fulano foi comunicada ao time?"). A agenda não entra na rodada, salvo pedido do usuário; se entrar, siga `agenda.md` (as duas fontes).
4. **Escolher de 3 a 5 perguntas no total.** Ordem: decisão material em aberto > compromisso com terceiro > marco vencido > curiosidade. Prefira assunto com mais links de entrada e data vencida recente. Linha antiga sem peso atual vira proposta de limpeza no fim da rodada, não pergunta.
5. **Perguntar.** Numeradas, cada uma autocontida em uma ou duas linhas: o que o vault sabe, com a data, e o que falta. Diga que uma frase basta e que "nada relevante", "não aconteceu", "desconsiderar" e "ignorar" fecham o item.
6. **Tratar as respostas.**
   - **Fato novo:** uma source de relato por rodada, `wiki/<categoria>/sources/AAAA-MM-DD-relato-checkin-<assunto-principal>.md`, `type: source`, tag `autorrelato`, abrindo com "Relato escrito do usuário em DATA, sem gravação". Frases do usuário entre aspas, literais; o que for leitura do agente fica marcado como tal; o que não foi dito vai em Lacunas. Depois, atualize as páginas vivas afetadas (estado vigente, movimento recente, `as_of`, `sources:`), como num `ingest`. Se a resposta mudar posição ou síntese, e não só registro, mostre o plano antes de gravar (`ingest.md`, fase 1).
   - **"Nada relevante", "não aconteceu":** tire a linha da seção aberta e registre o fechamento em "Movimento recente" (ou seção histórica equivalente), com a data da resposta. Se a linha precisar ficar onde está, escreva nela o fechamento com "encerrado", "sem novidade", "nada relevante" ou "não aconteceu": o detector ignora linhas com esses marcadores. Assim o sinal fecha sem estado escondido. Source só se a ausência importar.
   - **"Adiado para DATA":** troque a data vencida pela nova; a linha volta só se a nova data também passar.
   - **"Desconsiderar", "ignorar":** `checkin --dismiss <chave>` com as chaves das linhas (`slug:hash8`, impressas pelo script). Nada muda na wiki.
   - **Sem resposta:** o item volta na próxima rodada.
7. **Fechar.** `checkin --record`; entrada `ingest` em `wiki/log.md` quando houve escrita, citando a rodada; `build-index.py generate`, `check` e `bash harness/scripts/verify.sh`.

## Estado

`checkin.json` no root do vault guarda só a data da última rodada e as chaves descartadas. É conteúdo do usuário: o installer não o cria nem sobrescreve, e ele não guarda conhecimento. O que foi respondido mora na wiki.

## Nunca

- Perguntar por agenda, reunião ou evento sem gravação como unidade.
- Perguntar o que as sources já registram.
- Passar de 5 perguntas por rodada ou repetir item descartado.
- Registrar mais do que o usuário disse, inferir sentimento ou completar lacuna por plausibilidade.
- Encerrar sem `--record` quando a rodada aconteceu ou foi recusada.

## Done when

- Candidatos reconciliados com as sources antes das perguntas.
- Cada resposta virou source de relato e atualização de página, correção da linha de origem ou descarte registrado.
- `checkin --record` executado; log, índice e `verify.sh` em ordem quando houve escrita.
