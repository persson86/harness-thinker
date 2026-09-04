# Operacao: transcript

Use para analisar ou ingerir transcricao de reuniao real do usuario quando o vault tiver uma esfera adequada para contexto profissional, projetos ou trabalho.

Objetivo duplo: preservar o contexto e as decisoes da reuniao e promover apenas conhecimento duravel sobre projetos, metodo, linguagem, jogadas e pontos cegos do usuario.

## Entrada

- Arquivo em `queue/` ou caminho fornecido.
- Texto de transcricao colado na conversa.

## Contrato de UX

A operacao tem duas fases. O verbo do pedido define o checkpoint:

- Se o usuario pedir apenas para **analisar**, concluir a Fase 1 sem escrever no vault e aguardar go-ahead.
- Se pedir explicitamente para **ingerir**, **analisar e ingerir** ou equivalente, executar as duas fases no mesmo turno; o pedido ja e o go-ahead para a ingestao.
- Ingestao nao autoriza commit nem push. Cada uma dessas acoes exige pedido explicito e segue seu proprio runbook.

## Fase 1 — Analise read-only

1. Ler a transcricao inteira antes de sintetizar. Se a leitura estiver incompleta, parar sem alterar vault, queue ou Git.
2. Identificar fonte, data, participantes, contexto e trechos com atribuicao incerta ou possivel erro de transcricao. Nao normalizar nomes ou falas por inferencia silenciosa.
3. Ler `vault.config.json`, paginas e sources relevantes para localizar entidades existentes, confirmacoes, contradicoes e extensoes.
4. Iniciar a devolutiva com um **Resumo** breve e 3-5 **Ideias principais** da reuniao.
5. Separar, quando material para decisao ou impacto:
   - fato observado;
   - relato atribuido;
   - inferencia;
   - hipotese ou opiniao;
   - plano;
   - decisao pendente ou confirmada;
   - producao observada;
   - aceite contratual;
   - resultado nao comprovado.
6. Montar um ledger compacto de deltas. Para cada delta, registrar:
   - **delta** — o que muda em relacao ao vault;
   - **destino** — source e eventual pagina viva;
   - **estado** — classificacao epistemica relevante;
   - **acao** — `promover`, `somente source` ou `descartar`;
   - **por que** — evidencia, contradicao, lacuna ou criterio de durabilidade.
7. Recomendar o escopo da ingestao. A source preserva o contexto da reuniao; paginas vivas recebem somente mudancas duraveis, sem duplicar a ata inteira.
8. Se o pedido nao autorizou ingestao, apresentar o ledger e aguardar go-ahead explicito.

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
5. Atualizar paginas de projeto ou contexto somente com os deltas marcados `promover`. Preservar atribuicao e limites epistemicos; uso ou atividade nao prova resultado.
   Se o delta corrigir uma interpretacao ou substituir um estado anterior, seguir `review.md` para conferir os resumos e dependencias candidatas pertinentes. Confirmacao de registro nao comprova claims causais nem todos os detalhes da source.
6. Refrescar pagina de perfil profissional se ela existir e houver evidencia comportamental nitida:
   - reconfirmar padroes existentes;
   - adicionar padrao novo sustentado por evidencia;
   - alimentar tensoes/pontos cegos, nao apenas forcas;
   - se em duvida, manter somente na source para futuro rebuild.
7. Garantir frontmatter e `summary:`.
8. Rodar `python3 .claude/scripts/build-index.py generate`.
9. Registrar em `wiki/log.md`:

```markdown
## YYYY-MM-DD transcript | titulo da reuniao
- Source criada: [[slug]]
- Deltas promovidos: [...]
- Paginas atualizadas: [...]
- Lacunas preservadas: [...]
```

10. Se a reuniao evidenciar que uma pagina do vault alimentou decisao ou entregavel real, propor uma linha `applied` com evidencia citada. Registrar apenas com confirmacao do usuario.
11. Validar indice, wikilinks, invariantes e `raw/`. Somente depois mover os arquivos de entrada para `queue/processed/[YYYY-MM-DD]/`; nunca deletar o bruto.
12. Encerrar com quatro pontos curtos: source preservada, deltas promovidos, lacunas ou itens nao promovidos e estado de validacao/Git.

## Rebuild Periodico

Quando solicitado ou apos lote suficiente de reunioes, recomputar o perfil a partir de todas as notas `source` da categoria apropriada. A sintese do perfil fica no agente-pai; sumarizacao de blocos pode ser paralelizada se a plataforma permitir.

## Erros Comuns

- Resumir a partir de leitura parcial.
- Entregar a analise sem resumo e ideias principais consultaveis.
- Escrever durante um pedido apenas de analise.
- Pedir um segundo go-ahead quando o usuario ja pediu explicitamente a ingestao.
- Promover relato, plano ou uso como decisao, aceite ou resultado comprovado.
- Copiar toda a ata para paginas vivas em vez de promover deltas.
- Fazer so relato factual e perder metodo/pontos cegos.
- Atualizar perfil so com qualidades.
- Mover a queue antes das validacoes ou deletar o bruto.
- Criar projeto duplicado.
- Inventar `applied` sem evidencia citavel.

## Done when

- A transcricao foi lida integralmente e incertezas de atribuicao foram preservadas.
- O ledger cobriu os deltas relevantes e distinguiu promocao, source-only e descarte.
- A Fase 1 parou sem escrita ou a Fase 2 tinha autorizacao explicita.
- Source e paginas vivas respeitam seus papeis distintos.
- Indice, links, log, `raw/` e queue foram validados.
- Estado de commit e push foi reportado sem ampliar a autorizacao.
