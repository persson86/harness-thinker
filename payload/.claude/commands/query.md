Execute a operação QUERY para responder: $ARGUMENTS

## Passos (executar em ordem)

1. **Mapear** — leia `wiki/index.md` (root) e abra o(s) `wiki/[cat]/_index.md` da(s) esfera(s) relevante(s); identifique as páginas mais relevantes (máximo 5). Para recall amplo/cross-categoria use `python3 .claude/scripts/build-index.py search "<termos>"` (candidatos rankeados com summary inline). Se não houver, declare: "O vault não tem cobertura sobre X."

2. **Ler** — leia cada página identificada.

2b. **Personas** — quando o domínio justificar (estratégia, produto, negócio, decisão, investimento, filosofia, posicionamento), consulte [[vault-personas]] para selecionar as lentes e o formato de resposta por nº de personas (ver seção QUERY do `CLAUDE.md`). Páginas de persona são lidas além do teto de 5 páginas de conteúdo. Pule em perguntas factuais simples ou execução técnica pura.

3. **Sintetizar** — responda com citações explícitas às páginas consultadas. Formato: "segundo [[slug]]..." ou "de acordo com [[slug]] e [[slug2]]...". Separe claramente: fato do vault vs. perspectiva externa trazida por você.

4. **Encerrar com pergunta** — pergunte: "Vale salvar esta síntese como um insight em `ideias-pensamentos/`?"

## Done when

- [ ] Páginas consultadas listadas explicitamente
- [ ] Resposta com citações reais (não inventadas)
- [ ] Pergunta sobre salvar como insight feita

## Nunca

- Inventar `[[wikilink]]` que não existe no vault
- Responder sem consultar `wiki/index.md` primeiro
- Omitir quando o vault não tem cobertura: declarar ausência explicitamente
