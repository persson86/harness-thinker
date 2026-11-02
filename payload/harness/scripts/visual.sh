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
# No sandbox do Codex (CODEX_SANDBOX definido), render sai com código 3 e pede
# execução fora do sandbox com aprovação; check só relata.
#
# Uso: bash harness/scripts/visual.sh render <entrada> --out <base> [opções]
#      bash harness/scripts/visual.sh check
#      bash harness/scripts/visual.sh --help
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/visual"
VAULT="$(cd "$HERE/../.." && pwd)"

usage() { sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

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

sandbox="${CODEX_SANDBOX:-}"
# Sem CODEX_SANDBOX, a rede desligada pelo Codex também indica sandbox (Linux).
[ -z "$sandbox" ] && [ "${CODEX_SANDBOX_NETWORK_DISABLED:-}" = "1" ] && sandbox="network-disabled"

# check não prepara nada: sem cache, só relata (funciona dentro do sandbox).
if [ "$1" = "check" ] && ! cache_ok "$run"; then
  RUN="$run" SANDBOX="${sandbox:-nenhum}" node -e 'console.log(JSON.stringify({ node: process.versions.node,
    cache: `ausente em ${process.env.RUN}; o primeiro render prepara (usa a rede uma vez)`, sandbox: process.env.SANDBOX }, null, 2))'
  exit 0
fi

# O sandbox do Codex (seatbelt no macOS) impede o Chrome headless de abrir e a
# escrita do cache fora do vault. Falhar cedo, com a saída que o agente precisa.
if [ "$1" = "render" ] && [ -n "$sandbox" ] && [ "${THINKER_VISUAL_ALLOW_SANDBOX:-0}" != "1" ]; then
  {
    echo "visual: o sandbox do Codex ($sandbox) bloqueia o Chrome headless e a escrita do cache fora do vault."
    echo "visual: rode o mesmo comando fora do sandbox, com aprovação do usuário (no Codex: sandbox_permissions=require_escalated; justificativa: abrir o Chrome headless e usar o cache de dependências fixadas, que na primeira vez baixa do npm)."
    echo "visual: com aprovação 'never' (codex exec, colaboradores), não peça: entregue o Mermaid e diga que a cena e o PNG ficaram pendentes."
  } >&2
  exit 3
fi

if ! cache_ok "$run"; then
  mkdir -p "$home" 2>/dev/null && [ -w "$home" ] \
    || { echo "visual: sem permissão de escrita no cache $home (defina THINKER_VISUAL_HOME para outro diretório)." >&2; exit 1; }
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
