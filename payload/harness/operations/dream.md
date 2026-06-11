# DREAM — rodada proativa de manutencao e sintese

Rodada periodica em que o agente olha o vault sem ser perguntado: roda os juizes deterministicos, examina 2-3 clusters candidatos e **propoe** melhorias num digest unico. Contrato inegociavel: **o DREAM so propoe, nunca aplica** — nenhum cross-link, refresh ou promocao acontece sem revisao do usuario.

## Passos

1. **Juizes deterministicos** — rodar e resumir:
   - `python3 .claude/scripts/build-index.py check` (sincronia do indice)
   - `python3 .claude/scripts/build-index.py graph` (orfas, sub-conectadas, links quebrados)
   - `python3 .claude/scripts/build-index.py thresholds` (gatilhos de escala)
   - `python3 .claude/scripts/build-index.py stale` (entity/concept antigos em esferas rapidas)
   - `git status --porcelain` (mudancas nao commitadas = conhecimento sem protecao)
2. **Selecionar 2-3 clusters candidatos** (nao tudo): orfas nao-inbox, entidades stale com relevancia atual, paginas novas pouco conectadas, inbox com `summary:` aguardando promocao.
3. **Ler as paginas dos clusters** (maximo ~8 paginas) e procurar: contradicoes entre paginas, conexoes reais nao registradas, refresh necessario.
4. **Escrever o digest** em `wiki/ideias-pensamentos/inbox/digest-YYYY-MM-DD.md` (`type: inbox` — nunca indexado), secoes:
   - **Saude** — resumo dos juizes em 3-5 linhas
   - **Contradicoes** — pares de paginas em conflito, com citacao do trecho (ou "nenhuma detectada nos clusters examinados")
   - **Conexoes propostas** — cada proposta: par `[[a]] ↔ [[b]]` + 1 frase de justificativa; so wikilinks existentes
   - **Refresh sugerido** — paginas stale que valem atualizar (e por que agora)
   - **Candidatas a promocao** — inbox com summary pronto; recomendar promover, fundir ou descartar
5. **Registrar no log**: `## YYYY-MM-DD dream | digest`. Se ja existe digest do dia, atualizar o existente em vez de criar outro.

## Travas

- So propoe — aplicar qualquer item exige pedido explicito do usuario depois da revisao.
- Sem bajulacao e sem inflar: se nao ha nada digno de proposta, o digest diz isso em uma linha.
- Nunca inventar `[[wikilinks]]`; cada conexao proposta aponta paginas que existem.
- Agendamento e opcional e decisao do usuario (manual, `/loop` ou `/schedule` semanal) — o agente nunca ativa sozinho.
