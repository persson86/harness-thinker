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

raw_has_no_tracked_changes() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    [[ -z "$(git status --short -- raw 2>/dev/null)" ]]
  else
    return 0
  fi
}

# Drift check: compara os arquivos instalados contra harness/.manifest, gravado
# pelo install.sh (fonte: github.com/persson86/harness-thinker). Cada linha do
# manifest é "<sha256>  <relpath>" — o formato nativo de `sha256sum -c`, então a
# verificação roda em UM processo em vez de um hash por arquivo. Drift = arquivo
# instalado editado in-place no vault em vez de na fonte. WARN (não FAIL): um
# hotfix legítimo não deve brickar o verify; o objetivo é tornar o drift visível.
installed_matches_manifest() {
  local manifest="harness/.manifest"
  [[ -f "$manifest" ]] || { printf '  (sem .manifest — harness não instalado via install.sh; pulando)\n'; return 0; }
  local out rc=0
  if command -v sha256sum >/dev/null 2>&1; then
    out="$(sha256sum -c "$manifest" 2>&1)" || rc=1
  else
    out="$(shasum -a 256 -c "$manifest" 2>&1)" || rc=1
  fi
  if [[ "$rc" -ne 0 ]]; then
    printf '%s\n' "$out" | grep -v ': OK$' | sed 's/^/  DRIFT: /' >&2
    printf '  (editado in-place ou ausente; edite na fonte e rode install.sh --update)\n' >&2
    return 1
  fi
}

manifest_covers_installed() {
  local manifest="harness/.manifest"
  [[ -f "$manifest" ]] || { printf '  (sem .manifest — harness não instalado via install.sh; pulando)\n'; return 0; }

  local expected actual extras
  expected="$(mktemp)"
  actual="$(mktemp)"

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local rel="${line#* }"
    rel="${rel# }"
    printf '%s\n' "$rel"
  done < "$manifest" | sort -u > "$expected"

  {
    [[ -f CLAUDE.md ]] && printf 'CLAUDE.md\n'
    [[ -f AGENTS.md ]] && printf 'AGENTS.md\n'
    [[ -f .claude/settings.json ]] && printf '.claude/settings.json\n'
    [[ -d harness ]] && find harness -type f ! -path 'harness/.version' ! -path 'harness/.manifest' -print
    [[ -d .claude/commands ]] && find .claude/commands -type f -print
    [[ -d .claude/hooks ]] && find .claude/hooks -type f ! -path '.claude/hooks/hook.log' -print
    [[ -d .claude/scripts ]] && find .claude/scripts -type f -print
    [[ -d .grok ]] && find .grok -type f -print
  } | sed 's|^\./||' | sort -u > "$actual"

  extras="$(comm -13 "$expected" "$actual")"
  if [[ -n "$extras" ]]; then
    while IFS= read -r rel; do
      [[ -z "$rel" ]] && continue
      printf '  EXTRA (fora do manifest): %s — upstream para o repo-fonte ou remova\n' "$rel" >&2
    done <<< "$extras"
    rm -f "$expected" "$actual"
    return 1
  fi
  rm -f "$expected" "$actual"
}

check "critical files exist" exists "CLAUDE.md"
check "AGENTS.md exists" exists "AGENTS.md"
check "harness contract exists" exists "harness/contract.md"
check "codex adapter exists" exists "harness/adapters/codex.md"
check "claude adapter exists" exists "harness/adapters/claude.md"
check "grok adapter exists" exists "harness/adapters/grok.md"
check "grok rules exist" exists ".grok/rules/thinker.md"
check "build-index.py exists" exists ".claude/scripts/build-index.py"
check "wiki index exists" exists "wiki/index.md"
check "wiki log exists" exists "wiki/log.md"

check "claude protect hook executable" executable ".claude/hooks/protect-raw.sh"
check "claude track hook executable" executable ".claude/hooks/track-ingest.sh"
check "claude stop hook executable" executable ".claude/hooks/check-ingest.sh"
check "grok hook shim executable" executable ".grok/hooks/shim.sh"

# health = check + summaries + categorias fora do config + grafo em UMA varredura
# (substitui as antigas chamadas separadas de check/graph/no_missing_summary)
check "vault health (sync + summaries + grafo)" python3 ".claude/scripts/build-index.py" health
check "raw has no tracked changes" raw_has_no_tracked_changes
diagnose "installed files match manifest" installed_matches_manifest
diagnose "manifest covers installed files" manifest_covers_installed

if (( failures > 0 )); then
  printf '[verify] %d failure(s)\n' "$failures" >&2
  exit 1
fi

printf '[verify] all checks passed\n'
