# Operacao: inbox

Use para capturar ideia bruta, fragmento de pensamento, observacao ou nota ainda nao processada.

## Passos

1. Ler `vault.config.json` e usar `inbox_dir` como destino.
2. Criar pagina `[inbox_dir]/[slug].md` com `type: inbox`. `summary:` e opcional enquanto a ideia estiver crua, mas recomendado para tornar a captura encontravel.
3. Preservar o conteudo sem expandir demais; nao transformar captura em ensaio sem pedido.
4. Registrar no topo de `wiki/log.md`:

```markdown
## YYYY-MM-DD inbox | titulo
- Arquivo: wiki/[inbox_dir]/[slug].md
```

5. Rodar `python3 .claude/scripts/build-index.py generate` se o fluxo local exigir sync depois da escrita; o inbox continua nao indexado por localizacao.
6. Perguntar: "Quer processar agora ou deixar para depois?"

## Done when

- Ideia foi preservada sem superprocessar.
- Log foi atualizado.
- Nenhum wikilink inexistente foi criado.
