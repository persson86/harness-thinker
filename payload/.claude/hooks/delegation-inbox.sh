#!/bin/bash
# Optional notifications; fail open, never alter the original workflow.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 -B "$HERE/delegation-inbox.py"
