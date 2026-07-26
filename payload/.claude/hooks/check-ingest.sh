#!/bin/bash
set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
[[ -z "${SESSION_ID:-}" ]] && exit 0
[[ "$SESSION_ID" =~ [^a-zA-Z0-9_-] ]] && exit 0

STATE_DIR="/tmp/sb-session-${SESSION_ID}"
VAULT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
SCRIPT="$VAULT_ROOT/.claude/scripts/build-index.py"
LOG="$VAULT_ROOT/.claude/hooks/hook.log"
TS=$(date '+%Y-%m-%d %H:%M:%S')

HAS_NEW=false; [[ -f "$STATE_DIR/page-written" ]] && HAS_NEW=true
HAS_EDIT=false; [[ -f "$STATE_DIR/index-dirty" ]] && HAS_EDIT=true

# Gate só dispara quando uma página foi criada ou editada nesta sessão.
if ! $HAS_NEW && ! $HAS_EDIT; then
  rm -rf "$STATE_DIR" 2>/dev/null || true
  exit 0
fi

if [[ -f "$STATE_DIR/pages" ]]; then
  PAGES=$(tr '\n' ' ' < "$STATE_DIR/pages")
else
  PAGES="?"
fi

block() {
  echo "[$TS] BLOQUEIO sessão ${SESSION_ID:0:8} | $1" >> "$LOG"
  printf '{"decision":"block","reason":%s}\n' "$(jq -Rn --arg r "$2" '$r')"
  exit 0
}

# 1. Páginas novas registradas em wiki/log.md? (exigido só para criação de página)
#    Verifica o FATO (o slug aparece no log), não o canal (qual ferramenta escreveu).
#    O flag log-updated só é armado por Write/Edit/MultiEdit, então log escrito via
#    Bash (heredoc, cat >>, sed -i) era falso positivo. E o inverso: um `touch` no
#    log passava sem registrar nada. Ler o conteúdo resolve os dois lados.
if $HAS_NEW && [[ -f "$STATE_DIR/pages" ]]; then
  LOGFILE="$VAULT_ROOT/wiki/log.md"
  UNLOGGED=""
  while IFS= read -r REL; do
    [[ -z "$REL" ]] && continue
    SLUG="$(basename "$REL" .md)"
    if [[ ! -f "$LOGFILE" ]] || ! grep -Fq -- "$SLUG" "$LOGFILE"; then
      UNLOGGED="$UNLOGGED $SLUG"
    fi
  done < "$STATE_DIR/pages"

  [[ -n "${UNLOGGED// /}" ]] && block \
    "falta log.md | não registradas:$UNLOGGED" \
    "Ingestão incompleta: páginas criadas sem registro em wiki/log.md:$UNLOGGED. Adicione a entrada no topo do log (append-only) antes de encerrar."
fi

# 2-4. Gate determinístico em UMA chamada python (uma varredura do vault):
#    summary nas páginas novas + wikilinks quebrados em novas/editadas + índice em sync.
GATE_RC=0
GATE_OUT=$(cd "$VAULT_ROOT" && python3 "$SCRIPT" gate \
  --new "$STATE_DIR/pages" --edited "$STATE_DIR/pages-edited" 2>&1) || GATE_RC=$?

if [[ "$GATE_RC" -ne 0 ]]; then
  if echo "$GATE_OUT" | grep -q "SEM SUMMARY"; then
    MISSING=$(echo "$GATE_OUT" | grep "SEM SUMMARY" | head -1)
    block "sem summary | $MISSING" \
      "Páginas sem campo 'summary:' no frontmatter (fonte do índice): $MISSING. Adicione o summary antes de encerrar."
  elif echo "$GATE_OUT" | grep -q "LINKS QUEBRADOS"; then
    BROKEN_DETAIL=$(echo "$GATE_OUT" | grep -E "^\s+-\s" | head -5 | tr '\n' ' ')
    block "links quebrados | $BROKEN_DETAIL" \
      "Wikilinks quebrados em páginas novas/editadas (regra: nunca inventar [[wikilinks]]): $BROKEN_DETAIL. Corrija ou remova antes de encerrar."
  elif echo "$GATE_OUT" | grep -q "INDICE DESSINCRONIZADO"; then
    block "índice dessincronizado | pages: $PAGES" \
      "Índice dessincronizado com o frontmatter. Rode: python3 .claude/scripts/build-index.py generate (e inclua os _index.md atualizados no commit)."
  else
    DETAIL=$(echo "$GATE_OUT" | tail -3 | tr '\n' ' ')
    block "gate falhou | $DETAIL" \
      "Gate de encerramento falhou: $DETAIL"
  fi
fi

echo "[$TS] OK sessão ${SESSION_ID:0:8} | pages: $PAGES | summary+quality+sync+log OK" >> "$LOG"
rm -rf "$STATE_DIR" 2>/dev/null || true
exit 0
