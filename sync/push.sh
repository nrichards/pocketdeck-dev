#!/usr/bin/env bash
# push.sh — push a single .py file to the deck without running it.
# Usage: ./push.sh path/to/file.py

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <path-to-.py-file>" >&2
  exit 1
fi

file="$1"
if [[ ! -f "$file" ]]; then
  err "not a file: $file"
  exit 1
fi
if [[ "$file" != *.py ]]; then
  warn "file doesn't end in .py — pushing anyway"
fi

push_file "$file"
