# Operacao: transcript

Use para analisar ou ingerir transcricao de reuniao real do usuario quando o vault tiver uma esfera adequada para contexto profissional, projetos ou trabalho.

Objetivo duplo: preservar o contexto e as decisoes da reuniao e promover apenas conhecimento duravel sobre projetos, metodo, linguagem, jogadas e pontos cegos do usuario.

## Entrada

- Arquivo em `queue/` ou caminho fornecido.
- Texto de transcricao colado na conversa.
- Companions opcionais de mesmo basename: `.jsonl` (turnos) e `.analysis.jsonl`
  (trilha `mic|system` por turno, `quality_flags`, blocos `type:"chunk"` com
  diagnostico). Quando existir `.analysis.jsonl`, le-lo faz parte da Fase 1.

## Contrato de UX

A operacao tem duas fases. O verbo do pedido define o checkpoint:

- Se o usuario pedir apenas para **analisar**, concluir a Fase 1 sem escrever no vault e aguardar go-ahead.
- Se pedir explicitamente para **ingerir**, **analisar e ingerir** ou equivalente, executar as duas fases no mesmo turno; o pedido ja e o go-ahead para a ingestao.
- Ingestao nao autoriza commit nem push. Cada uma dessas acoes exige pedido explicito e segue seu proprio runbook.

## Fase 1 — Analise read-only

1. Ler a transcricao inteira antes de sintetizar. Se a leitura estiver incompleta, parar sem alterar vault, queue ou Git.
2. Identificar fonte, data, participantes, contexto e trechos com atribuicao incerta ou possivel erro de transcricao. Para cada nome de pessoa, rodar `python3 .claude/scripts/build-index.py resolve <nome>`: `unico` aponta a unica entrada cadastrada, que ainda se confere com a sala (pessoa fora do cadastro pode ter o mesmo nome); `ambiguo` so se resolve pela regra de desambiguacao impressa e pelo contexto da sala, e sem regra que decida vira lacuna ou pergunta; `nao encontrado` e nome novo ou grafia de transcricao. Nao normalizar nomes ou falas por inferencia silenciosa.
3. Se existir `[basename].analysis.jsonl`, ler antes de sintetizar. Preferir o
   `track` (mic|system) e os `quality_flags` por turno de la; `remote_unclustered`
   so sinaliza turno remoto sem separacao de falantes e nao serve de triagem
   sozinha. Cruzar isso com blocos `type:"chunk"` e localizar trechos que mudariam
   uma decisao ou fato duravel (polaridade/negacao, numero, entidade inesperada,
   autoria de fala remota). Listar esses trechos na devolutiva com `mm:ss` +
   trilha; se `vault.config.json` tiver `transcript.review_tool_dir`, incluir o
   comando exato (`python3 <dir>/review_turns.py <arquivo.jsonl> --at mm:ss
   --track mic|system`, ou `--chunks` para diagnostico por bloco). Sem essa
   chave, listar so `mm:ss` + trilha. Nao pedir para ouvir a reuniao inteira —
   so os trechos que mudam conclusao.
4. Ler `vault.config.json`, paginas e sources relevantes para localizar entidades existentes, confirmacoes, contradicoes e extensoes.
5. Iniciar a devolutiva com um **Resumo** breve e 3-5 **Ideias principais** da reuniao.
6. Separar, quando material para decisao ou impacto:
   - fato observado;
   - relato atribuido;
   - inferencia;
   - hipotese ou opiniao;
   - plano;
   - decisao pendente ou confirmada;
   - producao observada;
   - aceite contratual;
   - resultado nao comprovado.
7. Montar um ledger compacto de deltas. Para cada delta, registrar:
   - **delta** — o que muda em relacao ao vault;
   - **destino** — source e eventual pagina viva;
   - **estado** — classificacao epistemica relevante;
   - **acao** — `promover`, `somente source` ou `descartar`;
   - **por que** — evidencia, contradicao, lacuna ou criterio de durabilidade;
   - trechos sinalizados no passo 3 entram como lacuna/
     contradicao a resolver, nao como fato ja corrigido.
8. Recomendar o escopo da ingestao. A source preserva o contexto da reuniao; paginas vivas recebem somente mudancas duraveis, sem duplicar a ata inteira.
9. Se o pedido nao autorizou ingestao, apresentar o ledger e aguardar go-ahead explicito.

## Fase 2 — Execucao

1. Escolher a categoria cujo escopo em `vault.config.json` cobre a reuniao. Se nao existir ou houver ambiguidade material, pedir confirmacao antes de criar pagina.
2. Identificar o engajamento e mapear para pagina existente; se for novo, criar `entity` somente quando o ledger justificar.
3. Criar nota `source` em `wiki/[categoria]/sources/[YYYY-MM-DD]-[projeto]-[topico].md`.
4. Incluir, quando houver evidencia:
   - **O que rolou**
   - **Decisoes e estados**
   - **Deltas promovidos**
   - **Itens mantidos somente na source**
   - **Jogadas de metodo observadas**
   - **Lacunas e contradicoes**
   - **Conexoes**
5. **Conferencia de fidelidade, antes de promover.** Com a source escrita e ao menos um delta `promover` no ledger, um leitor independente confere a source contra o bruto. Sem delta a promover, registrar no fechamento "conferencia dispensada: nada promovido".
   - **Por que:** `build-index.py quotes` so confere se as aspas existem no bruto; nao pega inversao de sentido, atribuicao trocada nem relato promovido a fato.
   - **Quem:** no Claude Code, ferramenta Agent com `subagent_type: thinker-blind-reader` e `model` Sonnet; no Codex, `spawn_agent` novo sem historico da conversa, com a lista de leitura de `reviewer.md` e a limitacao de isolamento declarada. A funcao declarada e a conferencia de fidelidade; nao e consulta de Advisor ou Reviewer e nao consome esse orcamento. Em lote, um leitor por transcricao, em paralelo. Com a delegacao desligada nesta sessao (`delegate.py status`) ou host sem subagente, o principal faz a passada sozinho contra o bruto e declara no fechamento "conferencia sem leitor independente".
   - **Lista de leitura:** so a source nova e os arquivos de entrada em `queue/` (transcricao e, se houver, `.jsonl` e `.analysis.jsonl`), por caminho absoluto. O brief cola os deltas `promover` do ledger. Nada de paginas vivas, perfil ou outras sources.
   - **O que o brief pede**, para cada delta `promover` e cada citacao ou numero da source:
     - polaridade ou negacao invertida;
     - relato atribuido escrito como fato, plano como decisao, uso como resultado;
     - fala atribuida a pessoa errada, ou trilha `mic|system` incompativel com a autoria;
     - citacao fora de contexto;
     - numero: unidade, denominador e conta (recalcular percentuais e somas ditos ou mostrados; divergencia entre slide e fala).
     Cada alerta volta com a afirmacao da source, o trecho do bruto com `mm:ss` ou linha e o tipo. "Sem problema" e resposta valida.
   - **Integracao:** o principal confere cada alerta no bruto antes de agir. Alerta confirmado corrige a redacao da source e o ledger (e erro de sintese, nao de transcricao); ambiguidade vira lacuna e o delta nao e promovido como fato; alerta que depende de ouvir o audio segue a regra de trecho sinalizado. Nenhum delta com alerta aberto segue para o passo 6.
   - **Limite:** o leitor compara com a transcricao, nao com a gravacao.
6. Atualizar paginas de projeto ou contexto somente com os deltas marcados `promover`. Preservar atribuicao e limites epistemicos; uso ou atividade nao prova resultado.
   Antes de encerrar, reconciliar pendencias e estado vigente ja escritos: nao deixar "aguardar aprovacao" ativo quando a mesma evidencia registra recusa. Preservar o passo antigo na cronologia, com seu desfecho e fonte. "Somente source" significa nao reproduzir o conteudo substantivo nas paginas vivas; um ponteiro neutro para a source e suficiente.
   Se o delta corrigir uma interpretacao ou substituir um estado anterior, seguir `review.md` para conferir os resumos e dependencias candidatas pertinentes. Confirmacao de registro nao comprova claims causais nem todos os detalhes da source.
   Em pagina-hub (ver `contract.md`, "Paginas-hub"), seguir a regra de forma de `ingest.md` (passo 7): atualizar a linha correspondente do estado vigente ou da tabela; acrescentar uma linha datada, com ponteiro para a source, em "Movimento recente"; deixar o detalhe na source; nunca abrir secao datada nova no topo da pagina. O delta que nao altera decisao, restricao ou interpretacao atual fica so na source.
   O texto do trecho na source continua valendo como registrado — nao reescrever a source por causa de um trecho sinalizado. Uma correcao de trecho sinalizado (Fase 1, passo 3) so entra na pagina wiki quando o usuario efetivamente ouviu o trecho, com nota `(conferido no audio mm:ss)`. Trecho sinalizado e nao ouvido fica marcado como divergencia nao resolvida, nunca promovido como fato corrigido.
7. Refrescar pagina de perfil profissional se ela existir e houver evidencia comportamental nitida:
   - reconfirmar padroes existentes;
   - adicionar padrao novo sustentado por evidencia;
   - alimentar tensoes/pontos cegos, nao apenas forcas;
   - se em duvida, manter somente na source para futuro rebuild.
8. Garantir frontmatter e `summary:`. Quando o usuario confirmar uma identidade nova ou corrigir uma atribuicao, registrar no cadastro (ver `contract.md`, "Cadastro de pessoas"): `aliases:` na pagina da pessoa ou a linha `Desambiguacao:` na entrada da secao de pessoas.
   Conferir as citacoes da source nova com `python3 .claude/scripts/build-index.py quotes <slug>`; citacao `AUSENTE` volta ao bruto antes do log ou vira parafrase atribuida, sem aspas.
9. Rodar `python3 .claude/scripts/build-index.py generate`.
10. Registrar em `wiki/log.md`:

```markdown
## YYYY-MM-DD transcript | titulo da reuniao
- Source criada: [[slug]]
- Deltas promovidos: [...]
- Paginas atualizadas: [...]
- Lacunas preservadas: [...]
- Conferencia de fidelidade: [N alertas, N confirmados | dispensada | sem leitor independente]
```

11. Se a reuniao evidenciar que uma pagina do vault alimentou decisao ou entregavel real, propor uma linha `applied` com evidencia citada. Registrar apenas com confirmacao do usuario.
12. Validar indice, wikilinks, invariantes e `raw/`. Somente depois mover os arquivos de entrada para `queue/processed/[YYYY-MM-DD]/`; nunca deletar o bruto.
13. Encerrar com quatro pontos curtos: source preservada, deltas promovidos, lacunas ou itens nao promovidos e estado de validacao (conferencia de fidelidade incluida)/Git.

## Rebuild Periodico

Quando solicitado ou apos lote suficiente de reunioes, recomputar o perfil a partir de todas as notas `source` da categoria apropriada. A sintese do perfil fica no agente-pai; sumarizacao de blocos pode ser paralelizada se a plataforma permitir.

## Erros Comuns

- Resumir a partir de leitura parcial.
- Entregar a analise sem resumo e ideias principais consultaveis.
- Escrever durante um pedido apenas de analise.
- Pedir um segundo go-ahead quando o usuario ja pediu explicitamente a ingestao.
- Promover relato, plano ou uso como decisao, aceite ou resultado comprovado.
- Promover delta antes da conferencia de fidelidade ou com alerta dela em aberto.
- Copiar toda a ata para paginas vivas em vez de promover deltas.
- Fazer so relato factual e perder metodo/pontos cegos.
- Atualizar perfil so com qualidades.
- Mover a queue antes das validacoes ou deletar o bruto.
- Criar projeto duplicado.
- Inventar `applied` sem evidencia citavel.
- Mandar ouvir a reuniao inteira em vez de listar so os trechos que mudam conclusao.
- Promover correcao de trecho sinalizado sem o usuario ter ouvido o audio.
- Usar `remote_unclustered` sozinho como criterio de triagem de trecho suspeito.

## Done when

- A transcricao foi lida integralmente e incertezas de atribuicao foram preservadas.
- O ledger cobriu os deltas relevantes e distinguiu promocao, source-only e descarte.
- A conferencia de fidelidade rodou antes da promocao, ou o fechamento declarou por que foi dispensada ou feita sem leitor independente.
- A Fase 1 parou sem escrita ou a Fase 2 tinha autorizacao explicita.
- Source e paginas vivas respeitam seus papeis distintos.
- Indice, links, log, `raw/` e queue foram validados.
- Estado de commit e push foi reportado sem ampliar a autorizacao.
