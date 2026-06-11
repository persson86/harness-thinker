Execute a operação TRANSCRIPT — ingestão de transcrição de reunião na esfera `vida-profissional`.

A fonte é: $ARGUMENTS

Esta operação é distinta do `/ingest` (que analisa fontes externas e credibilidade de autor). Aqui a fonte é uma reunião real do usuário. O objetivo é duplo: **(1) capturar conhecimento de projeto/cliente** (memória de trabalho viva) e **(2) destilar quem o usuário é profissionalmente** — método, tom, linguagem, jogadas e pontos cegos — alimentando [[perfil-profissional]].

## Modos de entrada

- **Arquivo:** se houver arquivos em `queue/transcricoes/` (ou um caminho em `$ARGUMENTS`), processe cada um em sequência.
- **Colado:** se `$ARGUMENTS` ou o conteúdo mais recente da conversa for uma transcrição, processe direto (não há arquivo a mover).

## Passos (executar em ordem, por transcrição)

1. **Ler a transcrição inteira** antes de qualquer síntese. Nunca resumir a partir de leitura parcial.

2. **Identificar o engajamento** → mapear para uma página de projeto existente na esfera profissional (ex.: `wiki/vida-profissional/`, conforme o slug em `vault.config.json`). Se for um engajamento novo, criar página `type: entity` para ele.

3. **Criar a nota `source`** em `wiki/vida-profissional/sources/[YYYY-MM-DD]-[projeto]-[topico].md` com frontmatter obrigatório (`type: source`, `category: vida-profissional`) e as seções:
   - **O que rolou** — narrativa enxuta dos blocos da reunião.
   - **Decisões** — o que ficou decidido / próximos passos com responsável e data quando houver.
   - **Jogadas de método observadas** — o que a reunião revela sobre como o usuário trabalha (com link para [[perfil-profissional]]).
   - **Conexões** — link para a página de projeto, o perfil e conceitos existentes do vault (nunca inventar wikilink).

4. **Aplicar deltas na página de projeto** — decisões, estado atual, pessoas, conhecimento de domínio novo.

5. **Refrescar [[perfil-profissional]]** — **toque leve, não recálculo global.** No fluxo de 1 transcrição você NÃO recomputa o perfil inteiro (isso é o rebuild periódico, abaixo). Apenas:
   - Padrão já listado e reconfirmado → incrementar a marca ✕N.
   - Padrão novo e nítido → adicionar (forças *ou* tensões/pontos cegos).
   - **Sempre alimentar a seção Tensões/pontos cegos**, não só as forças — e vigiar a razão forças:tensões; um perfil que só cresce em qualidades virou marketing, não autoconhecimento.
   - **✕N é contagem qualitativa, não medição** — trate como "apareceu em N reuniões observadas", nunca como métrica precisa.
   - Se em dúvida sobre deduplicar/realocar um padrão, **deixe anotado para o rebuild** em vez de forçar — o toque incremental não tem o quadro inteiro.

6. **Índice + Log** — garanta `summary:` no frontmatter das páginas criadas e rode `python3 .claude/scripts/build-index.py generate` (índice gerado; não editar à mão). Registre em **`wiki/log.md`** (append no topo):
   ```
   ## YYYY-MM-DD transcript | [título da reunião]
   - Source criada: [[slug]]
   - Projeto atualizado: [[slug]]
   - Perfil refrescado: [padrões tocados]
   ```

7. **Se veio de arquivo:** mover o bruto para `queue/processed/[YYYY-MM-DD]/`. **Não deletar.** Reportar a nota gerada e pedir que o usuário **revise antes de deletar** — a nota da wiki passa a ser a única fonte de verdade.

## Done when

- [ ] Transcrição lida integralmente
- [ ] Nota `source` criada com frontmatter correto
- [ ] Página de projeto criada/atualizada
- [ ] `perfil-profissional` refrescado (forças e/ou tensões, com ✕N)
- [ ] `build-index.py generate` rodado; `log.md` atualizado
- [ ] Arquivo movido para `queue/processed/[data]/` (se veio da queue) e usuário avisado para revisar/deletar

## Erros comuns

- **Sumário em vez de extração de método** → o valor está em *como* o usuário conduz, não no relato dos fatos
- **Perfil só com forças** → sempre registrar também tensões/pontos cegos
- **Deletar o bruto sem revisão** → o agente nunca deleta; só move para processed/ e avisa
- **Criar projeto duplicado** → se o engajamento já existe, atualizar a página, não criar outra
- **Wikilink inexistente** → não criar o link; anotar o gap ao reportar
- **Discrição** → conteúdo sensível (ex.: zona regulatória) entra com nota de discrição no topo da página

## Rebuild periódico do perfil (modo lote — a cada ~10 reuniões ou sob demanda)

O `perfil-profissional` degrada se mantido só por toques incrementais: o ✕N deriva, padrões duplicam e a razão forças:tensões desbalanceia. Por isso, **periodicamente (a cada ~10 novas reuniões, ou quando o usuário pedir), recompute o perfil do zero a partir de todas as notas `source`** — não dos toques acumulados.

Acionado por: `/transcript rebuild` (ou pedido explícito do usuário).

1. Ler **todas** as notas em `wiki/vida-profissional/sources/` (a sumarização por bloco pode ser paralelizada em subagentes Sonnet; **a síntese do perfil fica no agente-pai** — exige segurar o quadro inteiro).
2. Recontar cada padrão de método (✕N) sobre o conjunto completo; deduplicar e realocar forças/tensões.
3. Reescrever `perfil-profissional` preservando: rótulo de que ✕N é qualitativo, seção Tensões com o mesmo rigor das forças, e a leitura transversal.
4. Registrar em `wiki/log.md`: `## YYYY-MM-DD transcript-rebuild | perfil recomputado sobre N reuniões`.

**Regra de divisão:** páginas de projeto crescem por *append* (robusto no incremental); o perfil exige *recálculo global* (só confiável no rebuild). Não tente fazer o trabalho do rebuild no fluxo de 1 transcrição.
