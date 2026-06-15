#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

REPO="${HT_REPO:-persson86/harness-thinker}"
REF="${HT_REF:-main}"

if [[ -n "${HT_INSTALLER:-}" ]]; then
  echo "Updating harness-thinker using local installer: $HT_INSTALLER" >&2
  bash "$HT_INSTALLER" "$ROOT" --update
else
  command -v curl >/dev/null 2>&1 || { echo "error: curl is required." >&2; exit 1; }
  URL="https://raw.githubusercontent.com/$REPO/$REF/install.sh"
  echo "Updating harness-thinker from $URL" >&2
  curl -fsSL "$URL" | bash -s -- "$ROOT" --update
fi

bash harness/scripts/verify.sh
