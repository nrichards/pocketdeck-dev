#!/usr/bin/env bash
# push_all.sh — push every .py file in a directory (non-recursive by default,
# pass -r for recursive). Useful after git pull or structural edits.
# Usage: ./push_all.sh [-r] <directory>

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

recursive=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -r|--recursive) recursive=1; shift ;;
    -*) err "unknown flag: $1"; exit 1 ;;
    *) break ;;
  esac
done

if [[ $# -ne 1 ]]; then
  echo "usage: $0 [-r] <directory>" >&2
  exit 1
fi

dir="$1"
if [[ ! -d "$dir" ]]; then
  err "not a directory: $dir"
  exit 1
fi

if [[ $recursive -eq 1 ]]; then
  mapfile -t files < <(find "$dir" -type f -name '*.py')
else
  mapfile -t files < <(find "$dir" -maxdepth 1 -type f -name '*.py')
fi

if [[ ${#files[@]} -eq 0 ]]; then
  warn "no .py files found in $dir"
  exit 0
fi

log "pushing ${#files[@]} file(s)"
failed=0
for f in "${files[@]}"; do
  if ! push_file "$f"; then
    failed=$((failed + 1))
  fi
done

if [[ $failed -gt 0 ]]; then
  err "$failed file(s) failed"
  exit 1
fi
ok "all files pushed"
