#!/bin/bash
set -euo pipefail

# Fail-closed: se dependências ausentes, bloquear por segurança
command -v jq     >/dev/null 2>&1 || { echo "jq ausente — bloqueando por segurança" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "python3 ausente — bloqueando por segurança" >&2; exit 2; }

INPUT=$(cat)

# JSON inválido → fail-closed
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null) || {
  echo "JSON inválido — bloqueando por segurança" >&2
  exit 2
}

# Raiz do vault: $CLAUDE_PROJECT_DIR quando o Claude Code define; senão,
# o diretório dois níveis acima deste script (.claude/hooks/ → raiz do vault).
VAULT_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
# Canonicaliza para casar com o realpath dos paths comparados (defesa de symlink).
VAULT_ROOT="$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$VAULT_ROOT" 2>/dev/null || echo "$VAULT_ROOT")"
VAULT_RAW="$VAULT_ROOT/raw"

canonicalize() {
  python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$1" 2>/dev/null || echo "$1"
}

deny() {
  printf '{"hookSpecificOutput":{"permissionDecision":"deny"}}\n'
  echo "BLOQUEADO: raw/ é imutável. Fontes originais não são editáveis." >&2
  exit 2
}

case "$TOOL_NAME" in
  Write|Edit|MultiEdit)
    # Write/Edit cobertos pela deny rule no settings.json para paths literais.
    # O hook cobre o vetor de symlink: resolve o path real antes de comparar.
    FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
    [[ -z "$FILE" ]] && exit 0
    REAL=$(canonicalize "$FILE")
    [[ "$REAL" == "$VAULT_RAW/"* ]] && deny
    ;;
  Bash)
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null) || {
      echo "JSON inválido no command — bloqueando" >&2
      exit 2
    }
    # Proteção via Bash é best-effort: regex não captura semântica de shell completa.
    # A deny rule + Write/Edit no hook são a defesa primária; Bash é segunda camada.
    RAW_RE="(${VAULT_RAW}/|[[:space:]]raw/|^raw/)"
    WRITE_RE="(rm[[:space:]]|unlink[[:space:]]|rmdir[[:space:]]|shred[[:space:]]|[[:space:]]?>|[[:space:]]?>>|tee[[:space:]]|cp[[:space:]]|mv[[:space:]]|sed[[:space:]]+-i|touch[[:space:]]|mkdir[[:space:]]|rsync[[:space:]]|dd[[:space:]].*of=|curl[[:space:]].*(\ -o|--output)|python3?[[:space:]]+-c)"
    if echo "$CMD" | grep -qE "$RAW_RE" && echo "$CMD" | grep -qE "$WRITE_RE"; then
      deny
    fi
    # Bloqueia cd para raw/ — cobre o bypass "cd raw && rm ..."
    if echo "$CMD" | grep -qE "cd[[:space:]]+(${VAULT_ROOT}/)?raw(/|[[:space:]]|$)"; then
      deny
    fi
    ;;
esac

exit 0
