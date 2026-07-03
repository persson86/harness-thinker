# Operacao: ingest

Use para ingerir fonte externa: URL, texto colado, arquivo ou referencia.

O ingest tem duas fases. Nunca criar arquivos na Fase 1.

## Fase 1 — Analise

1. Identificar a fonte, autor, contexto e credibilidade.
2. Extrair 3-5 ideias centrais com analise critica, nao apenas resumo: o que e solido, discutivel ou ruido.
3. Separar sinal de ruido: o que vale entrar no vault e o que deve ser descartado.
4. Ler paginas relevantes do vault para identificar confirmacoes, contradicoes e extensoes.
5. Recomendar uma decisao:
   - ingerir completo;
   - ingerir parcialmente, especificando source/entity/concept;
   - descartar.
6. Aguardar go-ahead explicito do usuario.

## Fase 2 — Execucao

1. Ler `vault.config.json`; escolher categoria principal pelo escopo, perguntando se ambigua.
2. Criar pagina `source` em `wiki/[categoria]/sources/[slug].md`.
3. Criar ou atualizar entidades relevantes.
4. Criar ou atualizar conceitos relevantes.
5. Verificar cross-links para paginas existentes; nao criar link para pagina inexistente.
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
- Fazer sumario em vez de analise critica na Fase 1.
- Ignorar o vault antes de recomendar.
- Inventar wikilink.
- Adivinhar categoria ambigua.
- Criar duplicata quando slug similar ja existe.
- Editar indice gerado a mao.

## Done when

- Fase 1 concluida e aprovada.
- Paginas criadas/atualizadas com frontmatter correto.
- Wikilinks verificados.
- Indice gerado e em sync.
- Log atualizado.
