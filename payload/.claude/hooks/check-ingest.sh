#!/bin/bash
set -euo pipefail

INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
[[ -z "${SESSION_ID:-}" ]] && exit 0
[[ "$SESSION_ID" =~ [^a-zA-Z0-9_-] ]] && exit 0

STATE_DIR="/tmp/sb-session-${SESSION_ID}"
VAULT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
WIKI="$VAULT_ROOT/wiki"
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

PAGES=$(tr '\n' ' ' < "$STATE_DIR/pages" 2>/dev/null || echo "?")

block() {
  echo "[$TS] BLOQUEIO sessão ${SESSION_ID:0:8} | $1" >> "$LOG"
  printf '{"decision":"block","reason":%s}\n' "$(jq -Rn --arg r "$2" '$r')"
  exit 0
}

# 1. log.md atualizado? (exigido apenas para criação de página nova)
if $HAS_NEW; then
  [[ ! -f "$STATE_DIR/log-updated" ]] && block \
    "falta log.md | pages: $PAGES" \
    "Ingestão incompleta: páginas criadas ($PAGES) mas wiki/log.md não foi atualizado. Atualize o log antes de encerrar."
fi

# 2. Cada página nova (exceto inbox cru) tem 'summary:'? É a fonte do índice.
if $HAS_NEW && [[ -f "$STATE_DIR/pages" ]]; then
  MISSING=()
  while IFS= read -r rel; do
    [[ -z "$rel" ]] && continue
    [[ "$rel" == ideias-pensamentos/inbox/* ]] && continue   # inbox = área não-indexada
    grep -qE '^summary:' "$WIKI/$rel" 2>/dev/null || MISSING+=("$rel")
  done < "$STATE_DIR/pages"
  if [[ ${#MISSING[@]} -gt 0 ]]; then
    block "sem summary: ${MISSING[*]}" \
      "Páginas sem campo 'summary:' no frontmatter (fonte do índice): ${MISSING[*]}. Adicione o summary antes de encerrar."
  fi
fi

# 3. Juiz determinístico de qualidade: wikilinks quebrados em páginas novas.
#    (Análogo ao val_bpb — computacional, não pode ser manipulado por sycophancy.)
if $HAS_NEW && [[ -f "$STATE_DIR/pages" ]]; then
  QUALITY_OUT=$(python3 "$SCRIPT" quality < "$STATE_DIR/pages" 2>&1 || true)
  if echo "$QUALITY_OUT" | grep -q "LINKS QUEBRADOS"; then
    BROKEN_DETAIL=$(echo "$QUALITY_OUT" | grep -E "^\s+-\s" | head -5 | tr '\n' ' ')
    block "links quebrados | $BROKEN_DETAIL" \
      "Wikilinks quebrados em páginas novas (regra: nunca inventar [[wikilinks]]): $BROKEN_DETAIL. Corrija ou remova antes de encerrar."
  fi
fi

# 4. Índice (root + shards) em sync com o frontmatter?
#    Cobre tanto criação de página nova quanto edição de summary: em página existente.
if ! python3 "$SCRIPT" check >/dev/null 2>&1; then
  block "índice dessincronizado | pages: $PAGES" \
    "Índice dessincronizado com o frontmatter. Rode: python3 .claude/scripts/build-index.py generate (e inclua os _index.md atualizados no commit)."
fi

echo "[$TS] OK sessão ${SESSION_ID:0:8} | pages: $PAGES | summary+quality+sync+log OK" >> "$LOG"
rm -rf "$STATE_DIR" 2>/dev/null || true
exit 0
