#!/usr/bin/env bash
#
# visual.sh — diagramas Mermaid → cena .excalidraw editável + PNG, no tema do vault.
# Operação: harness/operations/visual.md.
#
# Na primeira execução (e quando o código ou o lockfile mudam), instala as
# dependências fixadas do package-lock.json num cache FORA do vault:
#   ${THINKER_VISUAL_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/thinker-visual}/<hash>/
# com `npm ci --ignore-scripts`, e gera o bundle do navegador. Nada é instalado
# globalmente; nenhuma chave de API é usada.
#
# Uso: bash harness/scripts/visual.sh render <entrada> --out <base> [opções]
#      bash harness/scripts/visual.sh check
#      bash harness/scripts/visual.sh --help
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/visual"
VAULT="$(cd "$HERE/../.." && pwd)"

usage() { sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

case "${1:-}" in
  ""|-h|--help|help) usage; exit 0 ;;
  render|check) ;;
  *) echo "visual: comando desconhecido: $1 (use render ou check)" >&2; exit 2 ;;
esac

command -v node >/dev/null 2>&1 || { echo "visual: Node.js 22+ é necessário (node não encontrado)." >&2; exit 2; }
command -v npm  >/dev/null 2>&1 || { echo "visual: npm não encontrado." >&2; exit 2; }
major="$(node -p 'process.versions.node.split(".")[0]')"
[ "$major" -ge 22 ] || { echo "visual: Node.js 22+ é necessário (encontrado $(node -v))." >&2; exit 2; }

if command -v sha256sum >/dev/null 2>&1; then hasher=(sha256sum); else hasher=(shasum -a 256); fi
key="$(cd "$SRC" && cat package.json package-lock.json theme.mjs browser.js visual.mjs | "${hasher[@]}" | cut -c1-16)"
home="${THINKER_VISUAL_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/thinker-visual}"
run="$home/$key"

# Cache utilizável: marcador e os arquivos que a execução carrega.
cache_ok() {
  [ -f "$1/.ready" ] && [ -f "$1/visual.mjs" ] && [ -f "$1/bundle.js" ] \
    && [ -f "$1/node_modules/@excalidraw/cli/package.json" ] && [ -f "$1/node_modules/playwright-core/package.json" ]
}

if ! cache_ok "$run"; then
  mkdir -p "$home"
  # Exclusão mútua por mkdir (atômico): uma preparação por versão de cada vez.
  # Trava com mais de 15 min é tratada como abandonada.
  lock="$home/.lock-$key"
  waited=0
  until mkdir "$lock" 2>/dev/null; do
    if [ -n "$(find "$lock" -maxdepth 0 -mmin +15 2>/dev/null)" ]; then rm -rf "$lock"; continue; fi
    [ "$waited" -eq 0 ] && echo "visual: outra execução está preparando o cache; aguardando..." >&2
    waited=$((waited + 1))
    [ "$waited" -le 900 ] || { echo "visual: tempo esgotado esperando a trava $lock" >&2; exit 1; }
    sleep 1
  done
  tmp=""
  trap 'rm -rf "$lock" ${tmp:+"$tmp"}' EXIT
  if ! cache_ok "$run"; then
    tmp="$(mktemp -d "$home/.build.XXXXXX")"
    echo "visual: preparando dependências fixadas em $run (uma vez por versão)..." >&2
    cp "$SRC"/package.json "$SRC"/package-lock.json "$SRC"/theme.mjs "$SRC"/browser.js "$SRC"/visual.mjs "$tmp/"
    ( cd "$tmp" && npm ci --ignore-scripts --no-audit --no-fund --loglevel=error >&2 )
    ( cd "$tmp" && ./node_modules/.bin/esbuild browser.js --bundle --format=iife --minify \
        --outfile=bundle.js --loader:.css=empty --loader:.woff2=empty --loader:.ttf=empty \
        --define:process.env.NODE_ENV='"production"' --log-level=error >&2 )
    touch "$tmp/.ready"
    # Só um cache inválido é removido, e só sob a trava; um válido nunca é trocado.
    rm -rf "$run"
    mv "$tmp" "$run"
    tmp=""
  fi
  rm -rf "$lock"
  trap - EXIT
fi

export THINKER_VAULT="${THINKER_VAULT:-$VAULT}"
exec node "$run/visual.mjs" "$@"
