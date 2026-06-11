#!/bin/bash
set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
VAULT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
VAULT_WIKI="$VAULT_ROOT/wiki"

[[ -z "${TOOL_NAME:-}" ]] && exit 0
[[ -z "${SESSION_ID:-}" ]] && exit 0

# Rejeitar session_id que não parece UUID/hex (proteção contra path traversal)
[[ "$SESSION_ID" =~ [^a-zA-Z0-9_-] ]] && exit 0

case "$TOOL_NAME" in
  Write|Edit|MultiEdit) ;;
  *) exit 0 ;;
esac

FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
[[ -z "${FILE:-}" ]] && exit 0

# Resolver path real — python3 preferido; fallback para realpath nativo
if command -v python3 &>/dev/null; then
  REAL=$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$FILE" 2>/dev/null || echo "$FILE")
else
  REAL=$(realpath "$FILE" 2>/dev/null || echo "$FILE")
fi

[[ "$REAL" != "$VAULT_WIKI/"* ]] && exit 0

STATE_DIR="/tmp/sb-session-${SESSION_ID}"
mkdir -p "$STATE_DIR"

if [[ "$REAL" == "$VAULT_WIKI/log.md" ]]; then
  touch "$STATE_DIR/log-updated"
elif [[ "$TOOL_NAME" == "Write" ]]; then
  # Só CRIAÇÃO de página nova arma o gate (Edit exige arquivo existente).
  # O índice é GERADO por build-index.py (root + */_index.md) via Bash, não pelo
  # Write tool — então esses arquivos nunca chegam aqui. Por garantia, ignora
  # explicitamente o root e qualquer shard, caso sejam tocados via Write.
  case "$REAL" in
    "$VAULT_WIKI/index.md"|*/_index.md|*/_index-*.md) ;;   # índice gerado (root, shard, sub-shard): não é página nova
    *)
      touch "$STATE_DIR/page-written"
      # Path relativo a wiki/ — evita colisão de basenames entre categorias
      echo "${REAL#$VAULT_WIKI/}" >> "$STATE_DIR/pages"
      ;;
  esac
elif [[ "$TOOL_NAME" == "Edit" || "$TOOL_NAME" == "MultiEdit" ]]; then
  # Edição de página existente: arma index-dirty para que o Stop gate verifique
  # sincronia do índice mesmo sem criação de página nova (cobre edição de summary:).
  case "$REAL" in
    "$VAULT_WIKI/log.md"|"$VAULT_WIKI/index.md"|*/_index.md|*/_index-*.md) ;;  # gerados: ignorar
    *) touch "$STATE_DIR/index-dirty" ;;
  esac
fi

exit 0
