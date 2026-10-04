#!/bin/bash
# Lembrete após compactação automática ou manual; fail open, só injeta texto.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 -B "$HERE/post-compact.py"
