Execute a operação DREAM — rodada proativa de manutenção e síntese do vault.

Siga o playbook `harness/operations/dream.md`. Contrato inegociável: **só propor, nunca aplicar** — todo output vai para um digest único em `wiki/ideias-pensamentos/inbox/digest-YYYY-MM-DD.md` que o usuário revisa e promove.

## Resumo do protocolo

1. **Juízes determinísticos**: `build-index.py check`, `graph`, `thresholds`, `stale` + `git status --porcelain` (durabilidade).
2. **2–3 clusters candidatos**: órfãs não-inbox, entidades stale relevantes, páginas novas pouco conectadas, inbox com `summary:` aguardando promoção.
3. **Ler as páginas** dos clusters (máx ~8) procurando contradições, conexões não registradas e refresh necessário.
4. **Digest** com seções: Saúde / Contradições / Conexões propostas / Refresh sugerido / Candidatas a promoção. Cada proposta com 1 frase de justificativa; só `[[wikilinks]]` existentes; sem inflar — se não há nada digno, dizer em uma linha.
5. **Log**: `## YYYY-MM-DD dream | digest`. Digest do dia já existe → atualizar, não duplicar.

## Done when

- [ ] Juízes rodados e resumidos
- [ ] Digest único criado/atualizado em `inbox/` (não indexado)
- [ ] Nenhuma página de conhecimento alterada
- [ ] Log atualizado
