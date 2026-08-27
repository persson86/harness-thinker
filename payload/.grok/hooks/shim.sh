#!/usr/bin/env bash
#
# Traduz o JSON de hook do Grok Build para o formato Claude Code e despacha
# para os scripts já existentes em .claude/hooks/. Não modifica esses scripts.
#
set -euo pipefail

INPUT=$(cat)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ROOT="$(cd "$HERE/../.." && pwd)"
NORMALIZE="$HERE/normalize.py"

if ! command -v python3 >/dev/null 2>&1; then
  echo "shim Grok: python3 ausente — bloqueando por segurança" >&2
  exit 2
fi

NORMALIZED="$(printf '%s' "$INPUT" | python3 "$NORMALIZE" "$VAULT_ROOT")"

EVENT="$(printf '%s' "$NORMALIZED" | python3 -c "import json,sys; print(json.load(sys.stdin).get('_grok_event',''))" 2>/dev/null || true)"
WORKSPACE="$(printf '%s' "$NORMALIZED" | python3 -c "import json,sys; print(json.load(sys.stdin).get('_grok_workspace',''))" 2>/dev/null || true)"
EVENT_NORM="$(printf '%s' "$EVENT" | tr '[:upper:]' '[:lower:]' | tr -d '_')"
export CLAUDE_PROJECT_DIR="${WORKSPACE:-$VAULT_ROOT}"

blocked() {
  printf '%s' "$1" | grep -q '"decision"[[:space:]]*:[[:space:]]*"block"'
}

case "$EVENT_NORM" in
  pretooluse)
    HOOK="$VAULT_ROOT/.claude/hooks/protect-raw.sh"
    if [[ ! -f "$HOOK" ]]; then
      echo "shim Grok: hook ausente: $HOOK" >&2
      exit 2
    fi
    set +e
    printf '%s' "$NORMALIZED" | bash "$HOOK"
    exit $?
    ;;
  posttooluse)
    HOOK="$VAULT_ROOT/.claude/hooks/track-ingest.sh"
    [[ -f "$HOOK" ]] || exit 0
    set +e
    printf '%s' "$NORMALIZED" | bash "$HOOK"
    exit $?
    ;;
  stop)
    INGEST="$VAULT_ROOT/.claude/hooks/check-ingest.sh"
    AGENDA="$VAULT_ROOT/.claude/hooks/agenda-gate.sh"
    ingest_out=""; agenda_out=""
    set +e
    if [[ -f "$INGEST" ]]; then
      ingest_out="$(printf '%s' "$NORMALIZED" | bash "$INGEST")"
    fi
    if [[ -f "$AGENDA" ]]; then
      # JSON cru do Grok: agenda-gate aceita sessionId/promptId camelCase.
      agenda_out="$(printf '%s' "$INPUT" | bash "$AGENDA")"
    fi
    set -e
    if blocked "$ingest_out"; then
      printf '%s\n' "$ingest_out"
      exit 0
    fi
    if blocked "$agenda_out"; then
      printf '%s\n' "$agenda_out"
      exit 0
    fi
    [ -n "$ingest_out" ] && printf '%s\n' "$ingest_out"
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
