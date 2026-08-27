#!/bin/bash
# Wrapper para agenda-gate.py (precisa funcionar via `bash script`, como os outros hooks).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$HERE/../.." && pwd)}"
if ! command -v python3 >/dev/null 2>&1; then
  echo "agenda-gate: python3 ausente" >&2
  exit 0
fi
exec python3 "$HERE/agenda-gate.py"
