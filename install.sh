#!/usr/bin/env bash
#
# harness-thinker installer
#
# Materializa o harness no root de um vault: copia o conteúdo de payload/ 1:1
# para o target.
#
#   <target>/CLAUDE.md, <target>/AGENTS.md
#   <target>/harness/                       (contract + operations + adapters + scripts)
#   <target>/.claude/commands|hooks|scripts|settings.json
#   <target>/harness/.version + <target>/harness/.manifest  (drift check do verify.sh)
#
# O harness é a FONTE; no vault os arquivos instalados são descartáveis e
# regeneráveis. Edite sempre no repo harness-thinker e rode install.sh --update.
# Nunca toca wiki/, raw/, queue/, vault.config.json, .claude/memory/ nem
# .claude/settings.local.json.
#
# Dois modos:
#   ADOTAR (default)  instala o harness sobre um vault que já existe. Se não
#                     houver vault.config.json, deriva um a partir das pastas de wiki/.
#   CRIAR  (--init)   scaffolda um vault novo (wiki/ + categorias + config +
#                     .gitignore + README) e instala o harness por cima.
#
# Uso (local, a partir de um clone):
#   ./install.sh [TARGET_DIR] [--force|--update]      # adotar
#   ./install.sh --init <DIR_NOVO> [--force]          # criar do zero
#
# Uso (remoto, sem clonar):
#   curl -fsSL https://raw.githubusercontent.com/persson86/harness-thinker/main/install.sh | bash -s -- /path/do/vault --update
#
#   TARGET_DIR        diretório do vault (default: diretório atual)
#   --init            scaffolda um vault novo antes de instalar o harness
#   --force|--update  sobrescreve arquivos existentes sem abortar
#
set -euo pipefail

echo "harness-thinker installer starting..." >&2

REPO="persson86/harness-thinker"
REF="${UP_REF:-main}"
VERSION=""
TMP_ROOT=""

cleanup() { [ -n "$TMP_ROOT" ] && rm -rf "$TMP_ROOT" || true; }
trap cleanup EXIT

download_url() {
  local url="$1" label="$2" attempt=1 max_attempts=5 status=0
  while [ "$attempt" -le "$max_attempts" ]; do
    if curl -fsSL --connect-timeout 10 --max-time 60 "$url"; then
      return 0
    else
      status=$?
    fi
    if [ "$attempt" -lt "$max_attempts" ]; then
      echo "warning: falha ao baixar $label (tentativa $attempt/$max_attempts); retry..." >&2
      sleep 1
    fi
    attempt=$((attempt + 1))
  done
  echo "error: falha ao baixar $label de $url" >&2
  return "$status"
}

# SRC = diretório do script em modo local; vazio quando piped (curl | bash).
SRC=""
if [ -n "${BASH_SOURCE[0]:-}" ]; then
  SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || echo "")"
fi

if [ -n "$SRC" ] && [ -d "$SRC/payload" ]; then
  MODE="local"
  VERSION="$(cat "$SRC/VERSION" 2>/dev/null || echo "unknown")"
else
  command -v curl >/dev/null 2>&1 || { echo "error: curl é necessário no modo remoto." >&2; exit 1; }
  command -v tar  >/dev/null 2>&1 || { echo "error: tar é necessário no modo remoto." >&2; exit 1; }
  TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/harness-thinker-install.XXXXXX")"
  ARCHIVE="$TMP_ROOT/ht.tar.gz"
  ARCHIVE_URL="https://codeload.github.com/$REPO/tar.gz/$REF"
  echo "Baixando harness-thinker ($REF) do GitHub..." >&2
  download_url "$ARCHIVE_URL" "harness-thinker archive ($REF)" > "$ARCHIVE" || exit 1
  tar -xzf "$ARCHIVE" -C "$TMP_ROOT" || { echo "error: falha ao extrair o archive." >&2; exit 1; }
  PKG_DIRS=("$TMP_ROOT"/harness-thinker-*)
  [ -d "${PKG_DIRS[0]}" ] || { echo "error: archive não contém os arquivos do pacote." >&2; exit 1; }
  SRC="${PKG_DIRS[0]}"
  MODE="local"
  VERSION="$(cat "$SRC/VERSION" 2>/dev/null || echo "unknown")"
  echo "Archive extraído. Instalando..." >&2
fi
VERSION="${VERSION// /}"
PAYLOAD="$SRC/payload"

# hash portável (sha256sum no Linux, shasum -a 256 no macOS)
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | awk '{print $1}';
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

# --- argumentos --------------------------------------------------------
TARGET=""; FORCE=0; INIT=0
for arg in "$@"; do
  case "$arg" in
    --init)           INIT=1 ;;
    --force|--update) FORCE=1 ;;
    -*) echo "error: flag desconhecida: $arg" >&2; exit 2 ;;
    *)  TARGET="$arg" ;;
  esac
done
TARGET="${TARGET:-.}"

if [ "$INIT" -eq 1 ]; then
  # Criar do zero: o diretório pode não existir ainda.
  mkdir -p "$TARGET" || { echo "error: não consegui criar $TARGET" >&2; exit 1; }
fi
[ -d "$TARGET" ] || { echo "error: target não é um diretório: $TARGET" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"
[ "$TARGET" = "$SRC" ] && { echo "error: target é o próprio repo-fonte; instale em outro diretório." >&2; exit 1; }

# Guarda do --init: não scaffoldar por cima de um vault existente.
if [ "$INIT" -eq 1 ] && [ -d "$TARGET/wiki" ] && [ "$FORCE" -eq 0 ]; then
  echo "error: --init recusado: $TARGET já tem wiki/ (use o modo adotar, sem --init, ou --force)." >&2
  exit 1
fi

# --- modo CRIAR: scaffold do vault -------------------------------------
TEMPLATES="$SRC/templates/vault"
scaffold_vault() {
  [ -d "$TEMPLATES" ] || { echo "error: templates/vault ausente no pacote." >&2; exit 1; }
  # config primeiro (fonte das categorias). Não sobrescreve um já presente.
  [ -f "$TARGET/vault.config.json" ] || cp "$TEMPLATES/vault.config.json" "$TARGET/vault.config.json"
  # categorias + inbox_dir do config
  local cats inbox
  cats="$(python3 -c "import json;print(' '.join(c[0] for c in json.load(open('$TARGET/vault.config.json'))['categories']))")"
  inbox="$(python3 -c "import json;print(json.load(open('$TARGET/vault.config.json')).get('inbox_dir','ideas/inbox'))")"
  mkdir -p "$TARGET/wiki" "$TARGET/raw" "$TARGET/queue" "$TARGET/.claude/memory"
  local c
  for c in $cats; do mkdir -p "$TARGET/wiki/$c/sources"; done
  mkdir -p "$TARGET/wiki/$inbox"
  [ -f "$TARGET/wiki/log.md" ]            || cp "$TEMPLATES/wiki-log.md"      "$TARGET/wiki/log.md"
  [ -f "$TARGET/queue/README.md" ]        || cp "$TEMPLATES/queue-README.md"  "$TARGET/queue/README.md"
  [ -f "$TARGET/.gitignore" ]             || cp "$TEMPLATES/gitignore"        "$TARGET/.gitignore"
  [ -f "$TARGET/README.md" ]              || cp "$TEMPLATES/README.md"        "$TARGET/README.md"
  [ -f "$TARGET/.claude/memory/README.md" ] || cp "$TEMPLATES/memory-README.md" "$TARGET/.claude/memory/README.md"
  # template de personas na categoria que detém o inbox
  local ideas_cat="${inbox%%/*}"
  [ -f "$TARGET/wiki/$ideas_cat/vault-personas.md" ] || cp "$TEMPLATES/vault-personas.md" "$TARGET/wiki/$ideas_cat/vault-personas.md"
  echo "  + vault scaffoldado (categorias: $cats)" >&2
}
[ "$INIT" -eq 1 ] && scaffold_vault

[ -d "$TARGET/.git" ] || echo "warning: $TARGET não parece um repo git (sem .git) — vire um repo privado depois do install." >&2

# Lista de arquivos do payload (relpath a partir de payload/).
PAYLOAD_FILES=()
while IFS= read -r f; do PAYLOAD_FILES+=("$f"); done < <(cd "$PAYLOAD" && find . -type f | sed 's|^\./||' | sort)
[ "${#PAYLOAD_FILES[@]}" -gt 0 ] || { echo "error: payload/ vazio em $PAYLOAD." >&2; exit 1; }

# --- collision check (fresh install) -----------------------------------
if [ "$FORCE" -eq 0 ]; then
  collisions=()
  for rel in "${PAYLOAD_FILES[@]}"; do
    [ -e "$TARGET/$rel" ] && collisions+=("$rel")
  done
  if [ "${#collisions[@]}" -gt 0 ]; then
    echo "error: arquivos já existem no target (use --update para sobrescrever):" >&2
    printf '  %s\n' "${collisions[@]}" >&2
    exit 1
  fi
fi

# --- instalação --------------------------------------------------------
install_one() {
  local rel="$1" src="$PAYLOAD/$1" dest="$TARGET/$1"
  mkdir -p "$(dirname "$dest")"
  local tmp; tmp="$(mktemp "$dest.tmp.XXXXXX")"
  cat "$src" > "$tmp" || { rm -f "$tmp"; echo "error: falha ao instalar $rel" >&2; exit 1; }
  mv "$tmp" "$dest"
}

for rel in "${PAYLOAD_FILES[@]}"; do
  install_one "$rel"
done
echo "  + ${#PAYLOAD_FILES[@]} arquivos do harness em $TARGET" >&2

# hooks e verify.sh executáveis
chmod +x "$TARGET"/.claude/hooks/*.sh "$TARGET"/harness/scripts/verify.sh 2>/dev/null || true

# --- manifest + version (insumo do drift check em verify.sh) -----------
MANIFEST="$TARGET/harness/.manifest"
: > "$MANIFEST"
for rel in "${PAYLOAD_FILES[@]}"; do
  printf '%s  %s\n' "$(sha256_of "$TARGET/$rel")" "$rel" >> "$MANIFEST"
done
printf '%s\n' "$VERSION" > "$TARGET/harness/.version"
echo "  + harness/.version ($VERSION) + harness/.manifest (${#PAYLOAD_FILES[@]} entradas)" >&2

# --- modo ADOTAR: derivar config de um vault sem vault.config.json ------
# Conveniência para adotar um vault pré-existente: lê as pastas de wiki/ e gera
# um vault.config.json para o usuário revisar. Não sobrescreve um config presente.
if [ "$INIT" -eq 0 ] && [ ! -f "$TARGET/vault.config.json" ] && [ -d "$TARGET/wiki" ]; then
  python3 - "$TARGET" <<'PY'
import json, os, sys
target = sys.argv[1]
wiki = os.path.join(target, "wiki")
slugs = sorted(d for d in os.listdir(wiki)
               if os.path.isdir(os.path.join(wiki, d)) and not d.startswith('.'))
def titleize(s): return s.replace('-', ' ').replace('_', ' ').title()
cats = [[s, titleize(s), ""] for s in slugs]
inbox = next((f"{s}/inbox" for s in slugs
              if os.path.isdir(os.path.join(wiki, s, "inbox"))), "")
cfg = {"categories": cats, "subsharded": [], "fast_spheres": [],
       "inbox_dir": inbox or (slugs[-1] + "/inbox" if slugs else "ideas/inbox")}
with open(os.path.join(target, "vault.config.json"), "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
print(f"  + vault.config.json derivado de wiki/ ({len(cats)} categorias) — revise os escopos", file=sys.stderr)
PY
fi

# --- modo CRIAR: gerar o índice inicial --------------------------------
if [ "$INIT" -eq 1 ]; then
  ( cd "$TARGET" && CLAUDE_PROJECT_DIR="$TARGET" python3 .claude/scripts/build-index.py generate >/dev/null ) \
    && echo "  + índice inicial gerado (wiki/index.md + shards)" >&2
fi

echo >&2
echo "harness-thinker v$VERSION instalado em: $TARGET" >&2
echo "Valide com: bash harness/scripts/verify.sh" >&2
if [ "$INIT" -eq 1 ]; then
  echo >&2
  echo "Próximos passos:" >&2
  echo "  1. Edite vault.config.json com as suas categorias." >&2
  echo "  2. cd $TARGET && git init && git add -A && git commit -m 'init vault' (mantenha PRIVADO)." >&2
  echo "  3. Comece a ingerir: abra o Claude Code no vault e use /ingest, /inbox, /query." >&2
fi
