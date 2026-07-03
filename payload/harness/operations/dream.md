# Operacao: dream

Rodada periodica em que o agente olha o vault sem ser perguntado: roda juizes deterministicos, examina poucos clusters candidatos e **propoe** melhorias num digest unico. Contrato: DREAM so propoe, nunca aplica.

## Passos

1. Rodar e resumir juizes deterministicos:
   - `python3 .claude/scripts/build-index.py check`
   - `python3 .claude/scripts/build-index.py graph`
   - `python3 .claude/scripts/build-index.py thresholds`
   - `python3 .claude/scripts/build-index.py stale`
   - `git status --porcelain`
2. Selecionar 2-3 clusters candidatos, nao tudo: orfas nao-inbox, entidades/conceitos stale com relevancia atual, paginas novas pouco conectadas, inbox com `summary:` aguardando promocao.
3. Ler ate ~8 paginas dos clusters e procurar contradicoes, conexoes reais nao registradas, refresh necessario e sinais de aplicacao real de conhecimento.
4. Escrever digest unico no `inbox_dir` configurado, com `type: inbox`, secoes:
   - **Saude** — resumo dos juizes em 3-5 linhas.
   - **Contradicoes** — pares de paginas em conflito, ou ausencia nos clusters examinados.
   - **Conexoes propostas** — pares `[[a]] <-> [[b]]` + 1 frase; so links existentes.
   - **Refresh sugerido** — paginas stale que valem atualizar e por que agora.
   - **Candidatas a promocao** — inbox pronto; recomendar promover, fundir ou descartar.
   - **Candidatas a aplicacao (`applied`)** — linhas propostas com evidencia citada; usuario ratifica.
5. Registrar no log: `## YYYY-MM-DD dream | digest`. Se ja existe digest do dia, atualizar o existente em vez de criar outro.

## Travas

- Nao aplicar cross-links, refresh, promocoes ou `applied` sem pedido/confirmacao do usuario.
- Sem inflar: se nao ha nada digno, diga isso em uma linha.
- Nunca inventar wikilinks.
- Agendamento e decisao do usuario; o agente nunca ativa sozinho.
