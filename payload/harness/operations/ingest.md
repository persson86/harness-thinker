# Operacao: ingest

Use para ingerir fonte externa: URL, texto colado, arquivo, referencia ou um topico/pergunta a pesquisar.

O ingest tem duas fases. Nunca criar arquivos na Fase 1.

Transcricoes de reuniao seguem `harness/operations/transcript.md`. O contrato de UX daquele playbook prevalece para decidir se o pedido ja autorizou a Fase 2; nao exigir um segundo go-ahead quando o usuario pediu explicitamente para ingerir a transcricao.

## Fase 1 — Analise

### Passo 0 — Classificar a fonte

Antes de analisar, decidir o que `$ARGUMENTS` (ou o material apontado) e:

- **Conteudo pronto** — URL, texto colado, arquivo, ou referencia com material acessivel. Seguir direto para "Analise" abaixo.
- **Topico ou pergunta sem conteudo** — apenas um tema, uma duvida ou um nome a investigar, sem material a ler. Executar antes o "Brief de pesquisa" abaixo para produzir o material; so entao seguir para "Analise".

### Brief de pesquisa (so quando a fonte e topico/pergunta)

Montar UM paragrafo autocontido no formato research-prompt e executa-lo:

1. Liderar com a pergunta unica + a decisao ou uso que ela informa (por que isso importa para o vault/usuario).
2. Numerar 3-6 sub-perguntas concretas que, respondidas, fecham a pergunta unica.
3. Declarar fontes preferidas: primarias e independentes; nomear o tipo esperado.
4. Exigir separacao fato vs. inferencia quando as fontes divergirem.
5. Executar via o recurso de busca/pesquisa disponivel na plataforma da sessao. Corroborar cada claim-chave com multiplas fontes primarias independentes; quando nao existirem, dizer explicitamente que o claim e nao-corroborado.
6. Consolidar os achados no formato fonte + claim especifico + por que importa. Esse consolidado passa a ser a "fonte" para a Analise.

### Analise (todos os casos)

1. Identificar a fonte, autor, contexto e credibilidade.
2. Iniciar a devolutiva com um **Resumo** breve e 3-5 **Ideias principais**. Em seguida, fazer analise critica: o que e solido, discutivel ou ruido. Separar fato de inferencia — marcar o que a fonte afirma como dado vs. o que ela infere ou opina; quando fontes conflitarem, registrar os lados, nao escolher em silencio.
3. Separar sinal de ruido: o que vale entrar no vault e o que deve ser descartado.
4. Ler paginas relevantes do vault para identificar confirmacoes, contradicoes e extensoes. Corroborar os claims-chave contra o que ja existe; quando a fonte for a unica base de um claim forte, marca-lo como nao-corroborado.
5. **Gap round (autocritica antes de recomendar):** revisar a propria analise em busca de lacunas — claim central sem corroboracao, sub-pergunta ainda aberta, contradicao nao resolvida, categoria ainda ambigua. Se uma lacuna material persistir e for pesquisavel, rodar mais UMA busca (recurso de pesquisa disponivel na plataforma) para fecha-la antes de prosseguir. Nao parar na primeira resposta plausivel.
6. Recomendar uma decisao:
   - ingerir completo;
   - ingerir parcialmente, especificando source/entity/concept;
   - descartar.
7. Aguardar go-ahead explicito do usuario.

## Fase 2 — Execucao

1. Ler `vault.config.json`; escolher categoria principal pelo escopo, perguntando se ambigua.
2. Criar pagina `source` em `wiki/[categoria]/sources/[slug].md`.
3. Criar ou atualizar entidades relevantes.
4. Criar ou atualizar conceitos relevantes.
5. Verificar cross-links para paginas existentes; nao criar link para pagina inexistente.
   Quando a fonte alterar uma premissa ou conclusao ja registrada, seguir `review.md` para revisar dependencias pertinentes dentro do escopo autorizado. Distinguir procedencia, contexto e contraditorio; repeticao da mesma origem nao e corroboracao independente.
6. Incluir **Fonte** quando houver arquivo em `raw/` e **Conexoes** quando houver relacoes reais.
7. Garantir frontmatter completo e `summary:` em paginas indexaveis.
8. Rodar `python3 .claude/scripts/build-index.py generate`.
9. Registrar em `wiki/log.md` no topo:

```markdown
## YYYY-MM-DD ingest | titulo da fonte
- Paginas criadas: [...]
- Paginas atualizadas: [...]
```

## Erros Comuns

- Criar arquivos sem go-ahead.
- Entregar a analise sem resumo e ideias principais consultaveis.
- Fazer sumario em vez de analise critica na Fase 1.
- Tratar um topico/pergunta como se ja fosse conteudo pronto e pular o brief de pesquisa.
- Recomendar decisao sem a gap round.
- Aceitar claim de fonte unica como fato corroborado.
- Ignorar o vault antes de recomendar.
- Inventar wikilink.
- Adivinhar categoria ambigua.
- Criar duplicata quando slug similar ja existe.
- Editar indice gerado a mao.

## Done when

- Quando a fonte era topico/pergunta, o brief de pesquisa foi executado.
- Gap round feita antes de recomendar.
- Fase 1 concluida e aprovada.
- Paginas criadas/atualizadas com frontmatter correto.
- Wikilinks verificados.
- Indice gerado e em sync.
- Log atualizado.
