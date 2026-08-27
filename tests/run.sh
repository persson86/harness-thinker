#!/usr/bin/env bash
#
# Smoke tests do harness-thinker: installer (init/adopt), build-index.py
# (check/gate/health), hooks (protect-raw, check-ingest) com JSON sintético.
# Roda tudo em diretórios mktemp; não toca vault real. Uso: bash tests/run.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/ht-tests.XXXXXX")"
trap 'rm -rf "$TMP" /tmp/sb-session-httest01 /tmp/sb-session-httestgrok01 /tmp/sb-agenda-httestagenda01' EXIT

PASS=0; FAIL=0
OUT=""; RC=0

run() { # captura stdout+stderr e o exit code do comando
  OUT="$("$@" 2>&1)"; RC=$?
}

ok()   { echo "ok   $1"; PASS=$((PASS + 1)); }
bad()  { echo "FAIL $1"; [ -n "${2:-}" ] && printf '%s\n' "$2" | sed 's/^/     | /'; FAIL=$((FAIL + 1)); }

assert_rc() { # nome, rc esperado
  [ "$RC" -eq "$2" ] && ok "$1" || bad "$1 (rc=$RC, esperado $2)" "$OUT"
}
assert_out() { # nome, padrão esperado na saída
  echo "$OUT" | grep -q "$2" && ok "$1" || bad "$1 (padrão '$2' ausente)" "$OUT"
}

page() { # cria página: path, summary (vazio = sem frontmatter), corpo opcional
  mkdir -p "$(dirname "$1")"
  if [ -n "$2" ]; then
    printf -- '---\ntitle: t\nsummary: "%s"\ntype: concept\ncreated: 2026-01-01\nupdated: 2026-01-01\n---\n\n%s\n' "$2" "${3:-corpo}" > "$1"
  else
    printf -- '%s\n' "${3:-corpo sem frontmatter}" > "$1"
  fi
}

# ---------------------------------------------------------------- init
V1="$TMP/v1"
run "$REPO/install.sh" --init "$V1"
assert_rc "install --init" 0
run test -f "$V1/wiki/index.md"
assert_rc "init gera wiki/index.md" 0
run test -f "$V1/.grok/rules/thinker.md"
assert_rc "init instala .grok/rules/thinker.md" 0
run test -x "$V1/.grok/hooks/shim.sh"
assert_rc "init deixa shim Grok executável" 0
run test -f "$V1/.grok/skills/memory/SKILL.md"
assert_rc "init instala skill memory Grok" 0
run bash -c "cd '$V1' && CLAUDE_PROJECT_DIR='$V1' bash harness/scripts/verify.sh"
assert_rc "verify.sh verde no vault novo" 0

# ---------------------------------------------------------------- adopt
V2="$TMP/v2"
page "$V2/wiki/alpha/pagina-um.md" "primeira página"
run "$REPO/install.sh" "$V2"
assert_rc "install adopt" 0
run grep -q '"alpha"' "$V2/vault.config.json"
assert_rc "adopt deriva categoria de wiki/" 0

# ------------------------------------------------- build-index: categoria fora do config
BI() { (cd "$V1" && CLAUDE_PROJECT_DIR="$V1" python3 .claude/scripts/build-index.py "$@"); }
page "$V1/wiki/naoexiste/perdida.md" "página em categoria fora do config"
run BI check
assert_rc "check falha com categoria fora do config" 1
assert_out "check aponta a categoria" "categoria fora do config"
run BI health
assert_rc "health falha com categoria fora do config" 1
rm -rf "$V1/wiki/naoexiste"

# ------------------------------------------------- build-index: gate
page "$V1/wiki/reference/pagina-ok.md" "página válida"
run BI generate
assert_rc "generate após página nova" 0
S="$TMP/state"; mkdir -p "$S"

echo "reference/pagina-ok.md" > "$S/pages"
run BI gate --new "$S/pages"
assert_rc "gate limpo passa" 0

page "$V1/wiki/reference/sem-summary.md" ""
echo "reference/sem-summary.md" > "$S/pages"
run BI gate --new "$S/pages"
assert_rc "gate bloqueia página sem summary" 1
assert_out "gate marca SEM SUMMARY" "SEM SUMMARY"
rm "$V1/wiki/reference/sem-summary.md"

page "$V1/wiki/reference/link-quebrado.md" "página com link ruim" "aponta para [[alvo-inexistente]]"
run BI generate
echo "reference/link-quebrado.md" > "$S/pages"
run BI gate --new "$S/pages"
assert_rc "gate bloqueia wikilink quebrado" 1
assert_out "gate marca LINKS QUEBRADOS" "LINKS QUEBRADOS"
rm "$V1/wiki/reference/link-quebrado.md"
run BI generate

page "$V1/wiki/reference/fora-do-indice.md" "página não indexada ainda"
echo "reference/fora-do-indice.md" > "$S/pages"
run BI gate --new "$S/pages"
assert_rc "gate bloqueia índice dessincronizado" 1
assert_out "gate marca INDICE DESSINCRONIZADO" "INDICE DESSINCRONIZADO"
rm "$V1/wiki/reference/fora-do-indice.md"
run BI generate

# ------------------------------------------------- hook: protect-raw
PR="$V1/.claude/hooks/protect-raw.sh"
hook() { echo "$1" | CLAUDE_PROJECT_DIR="$V1" bash "$2"; }
run hook "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$V1/raw/fonte.md\"}}" "$PR"
assert_rc "protect-raw bloqueia Write em raw/" 2
run hook "{\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$V1/wiki/reference/livre.md\"}}" "$PR"
assert_rc "protect-raw libera Write em wiki/" 0
run hook "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":\"rm raw/fonte.md\"}}" "$PR"
assert_rc "protect-raw bloqueia rm em raw/ via Bash" 2

# ------------------------------------------------- hook: check-ingest (Stop gate)
CI="$V1/.claude/hooks/check-ingest.sh"
SID="httest01"; SD="/tmp/sb-session-$SID"
arm() { mkdir -p "$SD"; echo "reference/pagina-ok.md" > "$SD/pages"; touch "$SD/page-written"; }

arm
run hook "{\"session_id\":\"$SID\"}" "$CI"
assert_out "check-ingest bloqueia página nova ausente do log" '"decision":"block"'
assert_out "bloqueio nomeia o slug não registrado" "pagina-ok"

# flag log-updated armado (Write/Edit no log) mas sem registrar a página:
# o gate verifica o conteúdo, não o canal — tem que continuar bloqueando.
arm; touch "$SD/log-updated"
run hook "{\"session_id\":\"$SID\"}" "$CI"
assert_out "check-ingest bloqueia log tocado sem registrar a página" '"decision":"block"'

# log escrito via Bash (sem passar por Write/Edit, logo sem o flag): tem que passar.
rm -f "$SD/log-updated"
printf '\n## 2026-01-01 ingest | teste\n- Página criada: [[pagina-ok]]\n' >> "$V1/wiki/log.md"
arm
run hook "{\"session_id\":\"$SID\"}" "$CI"
assert_rc "check-ingest passa com página registrada no log (escrito via Bash)" 0
run test ! -d "$SD"
assert_rc "check-ingest limpa o state dir ao passar" 0

# ------------------------------------------------- grok shim: JSON Grok → hooks Claude
GS="$V1/.grok/hooks/shim.sh"
grok_hook() { echo "$1" | bash "$GS"; }
GROK_SID="httestgrok01"

run grok_hook "{\"hookEventName\":\"pre_tool_use\",\"sessionId\":\"$GROK_SID\",\"cwd\":\"$V1\",\"workspaceRoot\":\"$V1\",\"toolName\":\"write\",\"toolInput\":{\"file_path\":\"$V1/raw/fonte.md\",\"content\":\"x\"}}"
assert_rc "shim Grok bloqueia write em raw/" 2

run grok_hook "{\"hookEventName\":\"pre_tool_use\",\"sessionId\":\"$GROK_SID\",\"cwd\":\"$V1\",\"workspaceRoot\":\"$V1\",\"toolName\":\"write\",\"toolInput\":{\"file_path\":\"$V1/wiki/reference/livre.md\",\"content\":\"x\"}}"
assert_rc "shim Grok libera write em wiki/" 0

run grok_hook "{\"hookEventName\":\"pre_tool_use\",\"sessionId\":\"$GROK_SID\",\"cwd\":\"$V1\",\"workspaceRoot\":\"$V1\",\"toolName\":\"run_terminal_command\",\"toolInput\":{\"command\":\"rm raw/fonte.md\"}}"
assert_rc "shim Grok bloqueia rm em raw/ via run_terminal_command" 2

run grok_hook "{\"hookEventName\":\"PreToolUse\",\"session_id\":\"$GROK_SID\",\"cwd\":\"$V1\",\"workspaceRoot\":\"$V1\",\"tool_name\":\"Write\",\"tool_input\":{\"file_path\":\"$V1/raw/fonte.md\"}}"
assert_rc "shim Grok aceita JSON já no formato Claude" 2

page "$V1/wiki/reference/grok-nova.md" "página criada via Grok"
run grok_hook "{\"hookEventName\":\"post_tool_use\",\"sessionId\":\"$GROK_SID\",\"cwd\":\"$V1\",\"workspaceRoot\":\"$V1\",\"toolName\":\"write\",\"toolInput\":{\"file_path\":\"$V1/wiki/reference/grok-nova.md\",\"content\":\"x\"}}"
assert_rc "shim Grok track-ingest em write de wiki" 0
run grok_hook "{\"hookEventName\":\"stop\",\"sessionId\":\"$GROK_SID\",\"cwd\":\"$V1\",\"workspaceRoot\":\"$V1\"}"
assert_out "shim Grok Stop bloqueia página nova ausente do log" '"decision":"block"'
assert_out "shim Grok Stop nomeia o slug não registrado" "grok-nova"
rm -rf "/tmp/sb-session-$GROK_SID"

run bash -c "printf '%s' '{\"hookEventName\":\"pre_tool_use\",\"sessionId\":\"s\",\"toolName\":\"search_replace\",\"toolInput\":{\"file_path\":\"$V1/wiki/reference/pagina-ok.md\"}}' | python3 '$V1/.grok/hooks/normalize.py' '$V1'"
assert_rc "normalize.py roda" 0
assert_out "search_replace em arquivo existente vira Edit" '"tool_name": "Edit"'

# ------------------------------------------------- agenda.sh sanitiza convite
run test -x "$V1/harness/scripts/agenda.sh"
assert_rc "agenda.sh instalado e executável" 0
run test -f "$V1/harness/operations/agenda.md"
assert_rc "operação agenda instalada" 0
run test -f "$V1/.claude/commands/agenda.md"
assert_rc "command /agenda instalado" 0

FAKE="$TMP/fake-icalBuddy"
cat > "$FAKE" <<'EOS'
#!/bin/bash
echo "• 09:00 - 09:30 : Secret Call : https://teams.microsoft.com/l/meetup-join/abc : attendees: ana@trinca.com, Maria"
echo "password: hunter2 join https://meet.google.com/xxx"
EOS
chmod +x "$FAKE"
run bash -c "ICALBUDDY='$FAKE' bash '$V1/harness/scripts/agenda.sh' today"
assert_rc "agenda.sh aceita icalBuddy fake" 0
assert_out "agenda.sh nomeia fonte profissional" "profissional"
assert_out "agenda.sh lembra Gmail pessoal" "Gmail"
echo "$OUT" | grep -q 'https://' && bad "agenda.sh remove URLs" "$OUT" || ok "agenda.sh remove URLs"
echo "$OUT" | grep -qi 'hunter2' && bad "agenda.sh remove senha" "$OUT" || ok "agenda.sh remove senha"
echo "$OUT" | grep -q 'ana@trinca.com' && bad "agenda.sh remove e-mail" "$OUT" || ok "agenda.sh remove e-mail"

run bash -c "ICALBUDDY=/nao-existe bash '$V1/harness/scripts/agenda.sh' today"
assert_rc "agenda.sh falha sem icalBuddy" 1

# ------------------------------------------------- agenda-gate: duas fontes
AG="$V1/.claude/hooks/agenda-gate.sh"
SID="httestagenda01"
rm -rf "/tmp/sb-agenda-$SID"
gate() { echo "$1" | bash "$AG"; }

run gate "{\"hookEventName\":\"UserPromptSubmit\",\"sessionId\":\"$SID\",\"promptId\":\"p1\",\"prompt\":\"o que e product lead\"}"
assert_rc "agenda-gate ignora prompt que não é agenda" 0
run gate "{\"hookEventName\":\"Stop\",\"sessionId\":\"$SID\",\"promptId\":\"p1\"}"
assert_rc "agenda-gate não bloqueia virada comum" 0
echo "$OUT" | grep -q '"decision"' && bad "agenda-gate não bloqueia virada comum (sem block)" "$OUT" || ok "agenda-gate não bloqueia virada comum (sem block)"

rm -rf "/tmp/sb-agenda-$SID"
run gate "{\"hookEventName\":\"UserPromptSubmit\",\"sessionId\":\"$SID\",\"promptId\":\"p2\",\"prompt\":\"qual minha próxima agenda?\"}"
assert_rc "agenda-gate marca prompt de agenda" 0
assert_out "agenda-gate injeta contexto no Claude" "Calendar do Mac"

run gate "{\"hookEventName\":\"Stop\",\"sessionId\":\"$SID\",\"promptId\":\"p2\"}"
assert_out "agenda-gate bloqueia sem Calendar do Mac" '"decision": "block"'
assert_out "bloqueio pede icalBuddy/agenda.sh" "Calendar do Mac"

run gate "{\"hookEventName\":\"PreToolUse\",\"sessionId\":\"$SID\",\"promptId\":\"p2\",\"toolName\":\"Bash\",\"toolInput\":{\"command\":\"bash harness/scripts/agenda.sh upcoming 2\"}}"
assert_rc "agenda-gate registra Mac" 0
run gate "{\"hookEventName\":\"Stop\",\"sessionId\":\"$SID\",\"promptId\":\"p2\"}"
assert_out "agenda-gate bloqueia sem Gmail depois do Mac" "Gmail"

run gate "{\"hookEventName\":\"PreToolUse\",\"sessionId\":\"$SID\",\"promptId\":\"p2\",\"toolName\":\"use_tool\",\"toolInput\":{\"tool_name\":\"google_calendar__search\"}}"
assert_rc "agenda-gate registra Gmail" 0
run gate "{\"hookEventName\":\"Stop\",\"sessionId\":\"$SID\",\"promptId\":\"p2\"}"
echo "$OUT" | grep -q '"decision"' && bad "agenda-gate libera com as duas fontes" "$OUT" || ok "agenda-gate libera com as duas fontes"

# shim Stop combina check-ingest + agenda-gate
rm -rf "/tmp/sb-agenda-$SID"
run gate "{\"hookEventName\":\"UserPromptSubmit\",\"sessionId\":\"$SID\",\"promptId\":\"p3\",\"prompt\":\"o que tenho hoje\"}"
run grok_hook "{\"hookEventName\":\"stop\",\"sessionId\":\"$SID\",\"promptId\":\"p3\",\"reason\":\"end_turn\"}"
assert_out "shim Stop bloqueia agenda incompleta" '"decision": "block"'
assert_out "shim Stop pede Calendar do Mac" "Calendar do Mac"

# ----------------------------------------------------------------
echo
echo "resultado: $PASS ok, $FAIL falha(s)"
[ "$FAIL" -eq 0 ]
