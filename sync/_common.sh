#!/usr/bin/env bash
# _common.sh — sourced by the other scripts. Loads config and defines helpers.

set -euo pipefail

# Load user config
CONFIG_FILE="${POCKETDECK_CONFIG:-$HOME/.pocketdeck.env}"
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "error: config file not found at $CONFIG_FILE" >&2
  echo "See sync/README.md for setup." >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$CONFIG_FILE"

: "${POCKETDECK_HOST:?POCKETDECK_HOST not set in $CONFIG_FILE}"
: "${POCKETDECK_USER:?POCKETDECK_USER not set in $CONFIG_FILE}"
: "${POCKETDECK_PASSWORD:?POCKETDECK_PASSWORD not set in $CONFIG_FILE}"
: "${POCKETDECK_REMOTE_DIR:=/sd/py}"

# Require sshpass
if ! command -v sshpass >/dev/null 2>&1; then
  echo "error: sshpass not installed. brew install hudochenkov/sshpass/sshpass" >&2
  exit 1
fi

# --- small logging helpers ---
_ts() { date '+%H:%M:%S'; }
log()  { printf '[%s] %s\n' "$(_ts)" "$*"; }
warn() { printf '[%s] \033[33m%s\033[0m\n' "$(_ts)" "$*" >&2; }
err()  { printf '[%s] \033[31m%s\033[0m\n' "$(_ts)" "$*" >&2; }
ok()   { printf '[%s] \033[32m%s\033[0m\n' "$(_ts)" "$*"; }

# --- remote ops ---

# Push a single local file to $POCKETDECK_REMOTE_DIR on the deck.
# Preserves the basename.
push_file() {
  local local_path="$1"
  local base
  base="$(basename "$local_path")"
  local remote="${POCKETDECK_REMOTE_DIR}/${base}"

  log "scp $base -> $POCKETDECK_HOST:$remote"
  if sshpass -p "$POCKETDECK_PASSWORD" scp \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o LogLevel=ERROR \
      "$local_path" \
      "${POCKETDECK_USER}@${POCKETDECK_HOST}:${remote}"; then
    ok "pushed $base"
  else
    err "scp failed for $base"
    return 1
  fi
}

# Run a command on the deck's SSH shell. The deck's built-in shell accepts
# `r <module>` to reload + execute, or bare commands (ls, pwd, etc).
run_remote() {
  local cmd="$1"
  log "ssh: $cmd"
  if sshpass -p "$POCKETDECK_PASSWORD" ssh \
      -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null \
      -o LogLevel=ERROR \
      "${POCKETDECK_USER}@${POCKETDECK_HOST}" \
      "$cmd"; then
    ok "ran: $cmd"
  else
    err "ssh failed: $cmd"
    return 1
  fi
}

# Given a path like /foo/bar/my_app.py, return "my_app" (the MicroPython
# module name — no extension, no directory).
module_name_of() {
  local path="$1"
  local base
  base="$(basename "$path")"
  printf '%s' "${base%.py}"
}
