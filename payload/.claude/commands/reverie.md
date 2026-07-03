Execute a operação REVERIE — associação livre entre páginas do vault.

Siga o playbook `harness/operations/reverie.md`. Contrato inegociável: **produz material bruto, nunca propõe ações** — o output fica no inbox configurado em `vault.config.json` até revisão do usuário.

## Resumo do protocolo

1. **Leitura do índice completo**: `wiki/index.md` + todos os shards `wiki/[cat]/_index.md`. Não buscar — deixar que algo puxe.
2. **Seleção sem agenda**: 4–7 páginas de pelo menos 3 categorias distintas, sem wikilinks mútuos entre si, sem tema explícito comum. Não rodar logo após INGEST recente.
3. **Leitura sem tarefa**: ler as páginas completas, sem buscar contradições, conexões, ou utilidade.
4. **Escrita livre**: criar o arquivo no inbox com frontmatter mínimo + lista de páginas escolhidas (e o que "puxou") + corpo livre. Sem formato, sem seções obrigatórias, sem conclusão.
5. **Log**: `## YYYY-MM-DD reverie | [título livre que emergiu]`

## Done when

- [ ] Índice + shards lidos
- [ ] 4–7 páginas selecionadas de 3+ categorias sem wikilinks mútuos
- [ ] Arquivo de inbox criado com frontmatter correto
- [ ] Nenhuma página de conhecimento alterada
- [ ] Log atualizado
