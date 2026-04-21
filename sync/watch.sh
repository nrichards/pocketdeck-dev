#!/usr/bin/env bash
# watch.sh — watch a directory for .py changes, push + run on save.
# Usage: ./watch.sh [--no-run] <directory>
#
# By default, every save pushes the file AND runs `r <module>` on the deck.
# Pass --no-run to only push (useful for sub-modules you don't want to launch).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/_common.sh"

if ! command -v fswatch >/dev/null 2>&1; then
  err "fswatch not installed. brew install fswatch"
  exit 1
fi

no_run=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-run) no_run=1; shift ;;
    -h|--help)
      sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    -*) err "unknown flag: $1"; exit 1 ;;
    *) break ;;
  esac
done

if [[ $# -ne 1 ]]; then
  echo "usage: $0 [--no-run] <directory>" >&2
  exit 1
fi

WATCH_DIR="$1"
if [[ ! -d "$WATCH_DIR" ]]; then
  err "not a directory: $WATCH_DIR"
  exit 1
fi
WATCH_DIR="$(cd "$WATCH_DIR" && pwd)"

log "watching $WATCH_DIR"
log "target:   $POCKETDECK_USER@$POCKETDECK_HOST:$POCKETDECK_REMOTE_DIR"
log "mode:     $([ $no_run -eq 1 ] && echo 'push only' || echo 'push + run')"
log "ctrl-c to stop"

# Debounce: editors often write-rename-close, which fires fswatch multiple
# times in tens of milliseconds. Track last-processed timestamp per file.
declare -A last_seen

should_ignore() {
  local path="$1"
  local base
  base="$(basename "$path")"
  case "$base" in
    .*) return 0 ;;                # dotfiles
    *~|*.swp|*.swo|*.swx) return 0 ;;  # vim/emacs swap files
    \#*\#) return 0 ;;             # emacs autosave
    4913|.goutputstream-*) return 0 ;; # vim/gedit probes
  esac
  [[ "$path" != *.py ]]
}

handle_change() {
  local path="$1"
  [[ -f "$path" ]] || return 0
  should_ignore "$path" && return 0

  # Debounce within 300ms window
  local now
  now=$(date +%s%3N 2>/dev/null || python3 -c 'import time; print(int(time.time()*1000))')
  local prev="${last_seen[$path]:-0}"
  if (( now - prev < 300 )); then
    return 0
  fi
  last_seen[$path]=$now

  if ! push_file "$path"; then
    return 0  # stay alive on transient failures
  fi

  if [[ $no_run -eq 0 ]]; then
    local mod
    mod="$(module_name_of "$path")"
    run_remote "r $mod" || true
  fi

  echo  # blank line between events, easier to read
}

# fswatch in line mode, one path per line. --latency bundles bursts.
# --event Updated+Created covers save-replaces and new files.
fswatch \
  --recursive \
  --latency 0.1 \
  --event Updated --event Created --event Renamed \
  "$WATCH_DIR" \
| while IFS= read -r changed; do
    handle_change "$changed"
  done
