"""paths.py — translate deck absolute paths to host filesystem paths.

Deck apps reference files with paths like `/sd/lib/data/ghost1.xbm` — these
are absolute within the deck's filesystem but meaningless on a Mac. This
module rewrites those paths to live under a configurable root directory
on the host, letting apps run unmodified.

Configuration: set POCKETDECK_ROOT environment variable to the host
directory that mirrors the deck's root. A typical layout:

    $POCKETDECK_ROOT/
        sd/
            lib/data/ghost1.xbm
            py/my_app.py
            Documents/
        config/
            apps.json

If POCKETDECK_ROOT is unset, the shim falls back to
`~/.pocketdeck-root/`, creating it on first access.

Path rewriting rules:
    - Absolute paths beginning with `/sd/`, `/config/`, or `/int/` are
      rewritten under the root.
    - `/int/` (internal flash, mounted in command shells) maps to the
      root itself — equivalent to the deck's `/`.
    - Other absolute paths (like `/tmp/foo`) pass through unchanged; they
      refer to the host filesystem as normal.
    - Relative paths pass through unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path


# Paths that are considered deck-absolute and need rewriting.
# Order matters: longer prefixes first to avoid /s matching before /sd.
_DECK_PREFIXES = ("/sd/", "/config/", "/int/")


def get_root() -> Path:
    """Return the configured host root directory, creating if needed."""
    root_env = os.environ.get("POCKETDECK_ROOT")
    if root_env:
        root = Path(root_env).expanduser()
    else:
        root = Path.home() / ".pocketdeck-root"
    root.mkdir(parents=True, exist_ok=True)
    return root


def translate(path) -> str:
    """Rewrite a deck path to a host path. Safe to call with any path.

    Returns a string (not a Path) so callers can pass the result to any
    file API that accepts str-or-path.
    """
    if path is None:
        return path
    s = str(path)

    # Relative or host paths pass through unchanged
    if not s.startswith("/"):
        return s

    root = get_root()
    for prefix in _DECK_PREFIXES:
        if s.startswith(prefix):
            # strip the leading slash so pathlib joins cleanly
            if prefix == "/int/":
                # /int/ is the internal flash root, maps to POCKETDECK_ROOT itself
                relative = s[len("/int/"):]
                return str(root / relative)
            else:
                # /sd/ and /config/ map to subdirs of the root
                return str(root / s[1:])

    # Bare `/` or other absolute host paths — leave alone
    return s
