#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

failures=0

check() {
  local name="$1"
  shift
  printf '[verify] %s\n' "$name"
  if "$@"; then
    printf '  => ok\n'
  else
    printf '  => FAIL\n' >&2
    failures=$((failures + 1))
  fi
}

diagnose() {
  local name="$1"
  shift
  printf '[verify] %s\n' "$name"
  if "$@"; then
    printf '  => ok\n'
  else
    printf '  => WARN (diagnostic reported issues)\n' >&2
  fi
}

exists() {
  local path="$1"
  [[ -e "$path" ]]
}

executable() {
  local path="$1"
  [[ -x "$path" ]]
}

no_missing_summary() {
  local missing
  missing="$(
    find wiki -type f -name '*.md' \
      ! -name 'index.md' \
      ! -name '_index.md' \
      ! -name '_index-*.md' \
      ! -name 'log.md' \
      ! -path 'wiki/ideias-pensamentos/inbox/*' \
      -print0 |
    while IFS= read -r -d '' file; do
      if ! grep -q '^summary:' "$file"; then
        printf '%s\n' "$file"
      fi
    done
  )"
  if [[ -n "$missing" ]]; then
    printf '%s\n' "$missing" >&2
    return 1
  fi
}

raw_has_no_tracked_changes() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    [[ -z "$(git status --short -- raw 2>/dev/null)" ]]
  else
    return 0
  fi
}

# Hash portável: sha256sum (Linux) ou shasum -a 256 (macOS).
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# Drift check: compara os arquivos instalados contra harness/.manifest, gravado
# pelo install.sh (fonte: github.com/persson86/harness-thinker). Cada linha do
# manifest é "<sha256>  <relpath>". Drift = arquivo instalado editado in-place no
# vault em vez de na fonte. WARN (não FAIL): um hotfix legítimo não deve brickar
# o verify; o objetivo é tornar o drift visível no LINT/health-check.
installed_matches_manifest() {
  local manifest="harness/.manifest"
  [[ -f "$manifest" ]] || { printf '  (sem .manifest — harness não instalado via install.sh; pulando)\n'; return 0; }
  local drift=0 rel want got
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    want="${line%% *}"
    rel="${line#* }"; rel="${rel# }"
    if [[ ! -f "$rel" ]]; then
      printf '  AUSENTE: %s\n' "$rel" >&2
      drift=$((drift + 1)); continue
    fi
    got="$(sha256_of "$rel")"
    if [[ "$want" != "$got" ]]; then
      printf '  DRIFT: %s (editado in-place; edite na fonte e rode install.sh --update)\n' "$rel" >&2
      drift=$((drift + 1))
    fi
  done < "$manifest"
  [[ "$drift" -eq 0 ]]
}

check "critical files exist" exists "CLAUDE.md"
check "AGENTS.md exists" exists "AGENTS.md"
check "harness contract exists" exists "harness/contract.md"
check "codex adapter exists" exists "harness/adapters/codex.md"
check "claude adapter exists" exists "harness/adapters/claude.md"
check "build-index.py exists" exists ".claude/scripts/build-index.py"
check "wiki index exists" exists "wiki/index.md"
check "wiki log exists" exists "wiki/log.md"

check "claude protect hook executable" executable ".claude/hooks/protect-raw.sh"
check "claude track hook executable" executable ".claude/hooks/track-ingest.sh"
check "claude stop hook executable" executable ".claude/hooks/check-ingest.sh"

check "index sync" python3 ".claude/scripts/build-index.py" check
diagnose "graph health command" python3 ".claude/scripts/build-index.py" graph
check "indexable pages have summary" no_missing_summary
check "raw has no tracked changes" raw_has_no_tracked_changes
diagnose "installed files match manifest" installed_matches_manifest

if (( failures > 0 )); then
  printf '[verify] %d failure(s)\n' "$failures" >&2
  exit 1
fi

printf '[verify] all checks passed\n'
