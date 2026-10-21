#!/usr/bin/env bash
# Conta as palavras da One Page antes de "## Fontes", sem sintaxe de tabela, checkbox nem diagrama em bloco de código.
# Uso: bash harness/scripts/one-page-count.sh <arquivo.md>
set -euo pipefail
sed '/^## Fontes/,$d' "$1" | sed '/^```/,/^```/d' | grep -v -E '^[[:space:]]*\|?[[:space:]]*:?-{3}' | tr '|' ' ' | sed 's/- \[[ x]\]//' | wc -w | tr -d ' '
