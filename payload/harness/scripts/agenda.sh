#!/usr/bin/env bash
#
# Calendar do Mac (profissional / Exchange via EventKit).
# Gmail pessoal NÃO entra aqui — o agente consulta Google Calendar MCP no mesmo intervalo.
#
# Uso:
#   bash harness/scripts/agenda.sh              # daqui até +2 dias (só eventos futuros)
#   bash harness/scripts/agenda.sh today        # hoje inteiro
#   bash harness/scripts/agenda.sh upcoming [N] # daqui até +N dias (default 2)
#   bash harness/scripts/agenda.sh from START to END
#
# START/END: linguagem natural ("tomorrow at 18:00") ou "YYYY-MM-DD HH:MM:SS +HHMM".
set -euo pipefail

ICALBUDDY="${ICALBUDDY:-icalBuddy}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

usage() {
  printf 'uso: %s [today | upcoming [N] | from START to END]\n' "$(basename "$0")" >&2
  exit 2
}

if ! command -v "$ICALBUDDY" >/dev/null 2>&1; then
  printf 'error: icalBuddy ausente (%s). Instale: brew install ical-buddy\n' "$ICALBUDDY" >&2
  printf 'Calendar do Mac é a fonte profissional; sem ele a agenda está incompleta.\n' >&2
  exit 1
fi

FROM_NOW=0
CMD=()
case "${1:-upcoming}" in
  today)
    CMD=(eventsToday)
    ;;
  upcoming)
    N="${2:-2}"
    [[ "$N" =~ ^[0-9]+$ ]] || usage
    CMD=("eventsToday+${N}")
    FROM_NOW=1
    ;;
  from)
    [ "${3:-}" = "to" ] && [ -n "${2:-}" ] && [ -n "${4:-}" ] || usage
    CMD=("eventsFrom:${2}" "to:${4}")
    FROM_NOW=1
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage
    ;;
esac

OPTS=(-sc -nrd -npn -iep "datetime,title,location,attendees" -po "datetime,title,location,attendees" -ps "| : |" -b "• ")
if [ "$FROM_NOW" -eq 1 ]; then
  OPTS+=(-n)
fi

RAW="$("$ICALBUDDY" "${OPTS[@]}" "${CMD[@]}" 2>&1)" || {
  printf 'error: icalBuddy falhou\n%s\n' "$RAW" >&2
  exit 1
}

python3 - "$RAW" <<'PY'
import re, sys

raw = sys.argv[1] if len(sys.argv) > 1 else ""
text = raw
text = re.sub(r'https?://\S+', '', text, flags=re.I)
text = re.sub(r'\b[\w.+-]+@[\w.-]+\.\w+\b', '', text)
text = re.sub(r'(?i)\b(password|senha|pwd|passcode|código de acesso|codigo de acesso)\b\s*[:=]?\s*\S+', '', text)
text = re.sub(r'[ \t]{2,}', ' ', text)
text = re.sub(r' : \s*(?=:|$)', '', text)
text = re.sub(r'\n{3,}', '\n\n', text).strip()

print("# Calendar do Mac — profissional (Exchange / trabalho / locais)")
print("# Gmail pessoal NÃO está nesta lista. Consulte Google Calendar MCP no mesmo intervalo.")
print("# Gmail vazio ≠ dia livre. Não reexibir senha, link ou lista crua de participantes.")
print()
print(text if text else "(nenhum evento neste intervalo no Calendar do Mac)")
PY
