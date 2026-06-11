Execute a operação MEMORY — captura de aprendizados da sessão atual.

Reflita sobre o que aconteceu nesta sessão e capture até 3 aprendizados significativos.

## Perguntas para extrair aprendizados

- O que funcionou diferente do esperado nesta sessão?
- Algum wikilink foi tentado mas não existia? Qual?
- Algum passo de INGEST, INBOX, LINT ou QUERY foi pulado ou reordenado? Por quê?
- Alguma convenção do vault foi ambígua ou causou hesitação?
- Algum padrão novo identificado que deveria virar regra permanente?

## Destino

A memória viva deste vault no Claude Code: `~/.claude/projects/<este-vault>/memory/` (o Claude Code deriva o subdir do path do projeto).

Para cada aprendizado relevante: crie ou atualize o arquivo de memória adequado (tipo `feedback` para correções de comportamento, `project` para contexto do vault) e atualize o índice em `MEMORY.md`.

## Formato de memória (frontmatter obrigatório)

```markdown
---
name: [kebab-case-slug]
description: [uma linha — usada para decidir relevância em sessões futuras]
metadata:
  type: feedback | project | user | reference
---

[Regra ou fato principal]

**Why:** [razão — incidente, preferência, restrição]
**How to apply:** [quando e onde esta regra entra em jogo]
```

## Done when

- [ ] Até 3 aprendizados avaliados
- [ ] Memorias criadas/atualizadas no caminho correto
- [ ] `MEMORY.md` atualizado com ponteiro para cada memória nova
