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

HOOK=""
case "$EVENT_NORM" in
  pretooluse) HOOK="$VAULT_ROOT/.claude/hooks/protect-raw.sh" ;;
  posttooluse) HOOK="$VAULT_ROOT/.claude/hooks/track-ingest.sh" ;;
  stop) HOOK="$VAULT_ROOT/.claude/hooks/check-ingest.sh" ;;
  *) exit 0 ;;
esac

if [[ ! -f "$HOOK" ]]; then
  echo "shim Grok: hook ausente: $HOOK" >&2
  case "$EVENT_NORM" in
    pretooluse) exit 2 ;;
    *) exit 0 ;;
  esac
fi

set +e
printf '%s' "$NORMALIZED" | bash "$HOOK"
exit $?
