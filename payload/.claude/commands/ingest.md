Execute a operação INGEST para a fonte: $ARGUMENTS

Se $ARGUMENTS for uma URL, leia o conteúdo da página antes de processar. Se for texto colado na conversa, use o conteúdo mais recente compartilhado.

O INGEST tem duas fases separadas por decisão do usuário. **Nunca criar arquivos na Fase 1.**

## Fase 1 — Análise (sem tocar em arquivos)

1. **Identificar** — o que é? Quem é a fonte? Qual o contexto e credibilidade do autor?

2. **Ideias centrais** — 3-5 pontos com análise crítica (não sumário):
   - O que é sólido e bem fundamentado?
   - O que é discutível ou exige ceticismo?
   - O que é ruído, genérico ou promocional?

3. **Filtro sinal/ruído** — o que tem valor real para o vault vs. o que pode ser descartado?

4. **Conexões com o vault** — leia as páginas relevantes antes de responder; o conteúdo confirma, contradiz ou estende o que já existe?

5. **Recomendação** — uma das três:
   - Ingerir completo (justificar por quê vale espaço)
   - Ingerir parcialmente (especificar o quê: source / entity / concept)
   - Descartar (justificar)

6. **Aguardar go-ahead** — não criar nenhum arquivo até o usuário confirmar.

## Fase 2 — Execução (só após go-ahead)

7. **Source** — crie `wiki/[categoria]/sources/[slug].md` com frontmatter:
   ```yaml
   ---
   title:
   summary:
   category:
   type: source
   tags: []
   sources: []
   created: YYYY-MM-DD
   updated: YYYY-MM-DD
   ---
   ```
   Inclua seção **Fonte** e seção **Conexões** no final.

8. **Entidades** — identifique pessoas, empresas, ferramentas. Para cada uma: verificar se já existe `wiki/[categoria]/[slug].md`; se sim, atualizar; se não, criar com `type: entity`.

9. **Conceitos** — identifique ideias, frameworks, metodologias. Para cada um: verificar existência; criar ou atualizar com `type: concept`.

10. **Cross-links** — verifique quais páginas já existentes devem referenciar as novas. Adicione `[[slug]]` + frase de relação na seção Conexões delas.

11. **Index + Log** — o índice é **gerado**: nunca edite `wiki/index.md` nem os `_index.md` à mão. Garanta `summary:` no frontmatter de cada página criada e rode `python3 .claude/scripts/build-index.py generate` (reescreve root + shards). Registre em `wiki/log.md` (append no topo):
    ```
    ## YYYY-MM-DD ingest | [título da fonte]
    - Páginas criadas: [lista]
    - Páginas atualizadas: [lista]
    ```

## Done when

- [ ] Fase 1 concluída com recomendação explícita
- [ ] Go-ahead recebido do usuário
- [ ] Página source criada com frontmatter correto (se aplicável)
- [ ] Entidades e conceitos criados/atualizados (se aplicável)
- [ ] Cross-links verificados e adicionados
- [ ] `summary:` no frontmatter de cada página criada
- [ ] `build-index.py generate` rodado (root + shards)
- [ ] `wiki/log.md` atualizado

## Erros comuns

- **Criar arquivos sem go-ahead** → bloqueado; sempre aguardar Fase 1 completa
- **Sumário em vez de análise** → Fase 1 exige opinião crítica, não bullet points de conteúdo
- **Ignorar o vault na Fase 1** → sempre ler páginas relevantes antes de recomendar
- **Wikilink inexistente** → não criar o link; anotar o gap como "conceito sem página" ao reportar
- **Categoria ambígua** → perguntar antes de criar; nunca adivinhar
- **Fonte sem autor** → usar o domínio como referência (ex: `substack.com`)
- **Slug similar ao existente** → atualizar a página existente, não criar duplicata
- **Frontmatter incompleto** → bloquear a criação; preencher todos os campos obrigatórios
- **Editar `index.md`/`_index.md` à mão** → são gerados; rode `build-index.py generate` (o Stop gate bloqueia se o índice ficar dessincronizado)
