#!/usr/bin/env bash
# run.sh — push a file and immediately `r <module>` it on the deck.
# Usage: ./run.sh path/to/my_app.py

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

push_file "$file"
mod="$(module_name_of "$file")"
run_remote "r $mod"
