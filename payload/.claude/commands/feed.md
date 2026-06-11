Você é o roteador automático do segundo cérebro.

A fonte é: $ARGUMENTS

Se $ARGUMENTS for uma URL, leia o conteúdo antes de classificar. Se não houver argumentos, use o conteúdo mais recente compartilhado na conversa.

## Passo 0 — Verificar queue/

Antes de classificar, verifique se há arquivos pendentes em `queue/` (excluindo `queue/processed/` e `queue/README.md`). Se houver, liste-os e processe cada um em sequência antes de continuar.

Formato esperado dos arquivos:
- `[ts]-audio-[slug].txt` → INBOX com transcrição de áudio
- `[ts]-url-[slug].md` → classificar normalmente (INGEST ou INBOX)
- `[ts]-nota-[slug].md` → INBOX
- `[ts]-meeting-[slug].md` → TRANSCRIPT (transcrição de reunião; companion `.jsonl` de mesmo basename — mover junto para `processed/`)

Após processar, mova para `queue/processed/[YYYY-MM-DD]/[arquivo]`.

## Classificação

Analise o conteúdo e determine a operação correta:

**→ INGEST** se TODOS forem verdadeiros:
- Tem autor(es) identificável(is) com credibilidade no domínio
- Tem profundidade para criar 2+ páginas wiki significativas (source + concept ou entity)
- Os conceitos são transferíveis além do contexto específico da fonte

**→ INBOX** se QUALQUER for verdadeiro:
- Conteúdo raso (threads curtas, listas de ponteiros, snippets)
- Ideia embrionária que precisa de mais pesquisa para ser processada
- Qualidade mista — parte real, parte ruído sem separação limpa possível

**→ ANÁLISE + CONFIRMAÇÃO** (não executar automaticamente) se:
- Viés comercial significativo distorce partes do conteúdo
- Conteúdo cruza categorias incompatíveis
- Dúvida real sobre se o conceito já existe no vault

## Execução

1. Abra com 2 linhas: decisão tomada + razão
2. Execute imediatamente:
   - **INGEST** → siga os 7 passos do `/ingest`
   - **INBOX** → siga os 3 passos do `/inbox`
   - **TRANSCRIPT** → siga o `/transcript`
   - **ANÁLISE** → apresente análise e aguarde confirmação antes de executar

## Done when

- [ ] `queue/` verificada (sem pendências ou todas processadas)
- [ ] Fonte classificada como INGEST, INBOX ou ANÁLISE
- [ ] Operação executada com seus próprios critérios "Done when" satisfeitos
- [ ] Arquivo movido para `queue/processed/[YYYY-MM-DD]/` (se veio da queue)
