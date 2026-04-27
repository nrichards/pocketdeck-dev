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

Sandbox enforcement (two layers):
    1. Logical-escape check, always on. Deck paths with `..` segments
       that climb out of the deck filesystem root are rejected. Catches
       app-controlled path construction tricks like
       `/sd/../../../etc/passwd`.
    2. Symlink-escape check, OFF by default. When enabled (via
       POCKETDECK_ALLOW_SYMLINK_ESCAPE=0), resolved paths that land
       outside the deck root are rejected. This layer interferes with
       developer setups that symlink parts of the deck root to real
       source directories, so it's opt-in.

The default posture trusts developer disk layout and distrusts app code
— appropriate for a dev tool where you control the root but not
necessarily every app you run.
"""
from __future__ import annotations

import os
from pathlib import Path


# Paths that are considered deck-absolute and need rewriting.
# Order matters: longer prefixes first to avoid /s matching before /sd.
_DECK_PREFIXES = ("/sd/", "/config/", "/int/")


class SandboxEscapeError(Exception):
    """Raised when a translated path would resolve outside the deck root.

    The shim emulates a sandboxed filesystem. This exception is the
    guardrail that prevents apps — whether buggy or malicious — from
    reaching host files outside the emulated root via `..` traversal,
    planted symlinks, or similar tricks.
    """


def get_root() -> Path:
    """Return the configured host root directory, creating if needed."""
    root_env = os.environ.get("POCKETDECK_ROOT")
    if root_env:
        root = Path(root_env).expanduser()
    else:
        root = Path.home() / ".pocketdeck-root"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_deck_library_paths() -> list:
    """Return host filesystem paths that mirror MicroPython's search order
    on the deck.

    On device, MicroPython looks in /sd/py first (user apps), then /sd/lib
    (system library). The shim mirrors that priority by translating both
    to host paths and returning them in order.

    Only returns paths that actually exist on the host filesystem — this
    is what tells the rest of the shim whether to fall back to its own
    stubs or trust the real deck source. If the user hasn't pointed
    POCKETDECK_ROOT at a populated tree, this returns [].
    """
    root = get_root()
    candidates = [root / "sd" / "py", root / "sd" / "lib"]
    return [str(p.resolve()) for p in candidates if p.is_dir()]


def _is_inside(resolved: Path, root_resolved: Path) -> bool:
    """True if `resolved` is `root_resolved` itself or a descendant.

    Uses resolved (absolute, symlink-followed) paths on both sides, so
    the comparison isn't fooled by `..` segments or by symlinks pointing
    outside the tree.
    """
    try:
        resolved.relative_to(root_resolved)
        return True
    except ValueError:
        return False


def _symlink_strict_mode() -> bool:
    """Return True if the strict symlink-containment check is enabled.

    Default is permissive: the shim assumes developers configure their
    deck root with symlinks pointing at source-of-truth locations (real
    deck repos, shared asset directories, etc). The check that blocks
    those setups is therefore off by default.

    Set POCKETDECK_ALLOW_SYMLINK_ESCAPE=0 to opt into strict mode, in
    which any resolved path landing outside the root raises.

    Note: `..` traversal is blocked regardless of this setting — it's a
    separate defense layer in _logical_escape_check.
    """
    val = os.environ.get("POCKETDECK_ALLOW_SYMLINK_ESCAPE", "1").strip().lower()
    return val in ("0", "false", "no", "")


def _logical_escape_check(deck_path: str) -> None:
    """Reject deck paths whose LOGICAL form escapes the deck filesystem.

    "Logical" means we collapse `..` segments against the input path
    itself, without touching the host filesystem. The deck filesystem
    root is the deck's `/` — so `/sd/../../etc/passwd` logically climbs
    out of the deck tree before we even get to host translation.

    This is a pure string operation. It catches app-generated traversal
    tricks without being confused by host-filesystem symlink layouts.
    """
    # Collapse .. segments logically. os.path.normpath does this without
    # touching the filesystem.
    normalized = os.path.normpath(deck_path)
    # After normalization, a path like "/sd/../../etc" becomes "/etc" —
    # the .. segments pulled us out of anything rooted under a deck
    # prefix. Check that what's left still lives under one of the
    # deck prefixes.
    if not normalized.startswith("/"):
        # Shouldn't happen for deck-absolute paths, but guard anyway
        raise SandboxEscapeError(
            f"Deck path normalized to non-absolute form: "
            f"{deck_path!r} -> {normalized!r}"
        )
    # Does it still start with a legitimate deck prefix?
    # Allow bare /sd, /config, /int as well as /sd/..., /config/..., /int/...
    for prefix in _DECK_PREFIXES:
        bare = prefix.rstrip("/")  # "/sd/" -> "/sd"
        if normalized == bare or normalized.startswith(prefix):
            return
    raise SandboxEscapeError(
        f"Deck path escapes via .. traversal: "
        f"{deck_path!r} normalizes to {normalized!r}, "
        f"which is outside the deck filesystem root"
    )


def _symlink_escape_check(host_path: str) -> None:
    """In strict mode, reject translated host paths that resolve outside
    the deck root via symlinks.

    Off by default because developer setups often symlink parts of the
    deck root to source-of-truth directories elsewhere on disk.
    """
    if not _symlink_strict_mode():
        return
    root_resolved = get_root().resolve()
    candidate_resolved = Path(host_path).resolve()
    if not _is_inside(candidate_resolved, root_resolved):
        raise SandboxEscapeError(
            f"Path escapes deck root via symlink: {host_path!r} resolves to "
            f"{candidate_resolved!r}, which is outside {root_resolved!r}. "
            f"Set POCKETDECK_ALLOW_SYMLINK_ESCAPE=1 to permit this."
        )


def translate(path) -> str:
    """Rewrite a deck path to a host path. Safe to call with any path.

    Returns a string (not a Path) so callers can pass the result to any
    file API that accepts str-or-path.

    Two sandbox layers apply to translated paths (those starting with a
    deck prefix):
      1. Logical-escape check (always on): rejects `..` traversal that
         would leave the deck filesystem. Defends against app-controlled
         path construction tricks.
      2. Symlink-escape check (off by default): rejects resolved paths
         that land outside the deck root. Defends against planted
         symlinks. Off because developers commonly symlink parts of the
         deck root to real source directories.

    Non-translated paths (bare host paths, relative paths) pass through
    unchanged — the shim doesn't sandbox what it doesn't translate.
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
            # Layer 1: logical-escape check on the deck-form path.
            # Runs on the INPUT (deck path), before translation, so it
            # catches attacks against the deck filesystem root regardless
            # of how the host root is configured.
            _logical_escape_check(s)

            # Translate to host path
            if prefix == "/int/":
                # /int/ is the internal flash root, maps to POCKETDECK_ROOT itself
                relative = s[len("/int/"):]
                host = str(root / relative)
            else:
                # /sd/ and /config/ map to subdirs of the root
                host = str(root / s[1:])

            # Layer 2: symlink-escape check on the translated host path.
            # Off by default; enabled via POCKETDECK_ALLOW_SYMLINK_ESCAPE=0.
            _symlink_escape_check(host)
            return host

    # Bare `/` or other absolute host paths — leave alone
    return s


# ---------------------------------------------------------------------------
# Path-translation patches for builtins.open and os file APIs
#
# Deck library code (xbmreader, pdeck_utils, pem, etc.) calls open(),
# os.stat(), os.listdir() with deck-absolute paths like "/sd/lib/data/x.xbm".
# On the deck those paths are real filesystem locations; on a Mac they're
# not. Path-based module lookup gets us the real source code, but the
# real source code still wants to see deck paths work natively.
#
# We patch the builtins / os functions to translate deck paths before
# calling the original implementation. Non-deck paths pass through
# unchanged. This makes path translation transparent — deck library
# code Just Works without modification.
#
# Sandbox enforcement still applies because translate() does the
# ..-traversal and symlink-escape checks. So patching open() doesn't
# weaken security — if anything it makes it stronger by catching every
# file access, not just the ones that explicitly route through translate().
# ---------------------------------------------------------------------------


_DECK_PATH_PREFIXES = ("/sd/", "/config/", "/int/")
_path_patches_installed = False


def _looks_like_deck_path(path) -> bool:
    """True if the argument is a string-like deck path that needs translation.

    Accepts str and pathlib.Path. Other types (file descriptors, bytes,
    BytesIO) pass through unchanged — open() and os.stat() accept all of
    those, but only str/Path can carry a deck prefix that we'd want to
    translate.
    """
    if isinstance(path, (str, Path)):
        s = str(path)
        return s.startswith(_DECK_PATH_PREFIXES)
    return False


def install_path_translation_in_builtins() -> None:
    """Wrap builtins.open and selected os functions to translate deck paths.

    Idempotent: re-running install_all() doesn't double-wrap. We track
    installation state in a module-level flag and check it on entry.

    Functions wrapped:
      - builtins.open: the big one — file reads/writes go through this
      - os.stat: apps use this to check file existence and size
      - os.listdir: file managers and ls walk deck directories

    Functions NOT wrapped (deferred until an example needs them):
      - os.unlink, os.remove, os.mkdir, os.makedirs, os.rename
      - os.path.exists, os.path.isfile, os.path.isdir
        (these delegate to os.stat internally, so they pick up the
        translation for free)
    """
    global _path_patches_installed
    if _path_patches_installed:
        return

    import builtins
    import os as _os

    # --- builtins.open ---
    _real_open = builtins.open

    def _translating_open(file, *args, **kwargs):
        if _looks_like_deck_path(file):
            file = translate(str(file))
        return _real_open(file, *args, **kwargs)

    # Preserve identity / introspection where reasonable
    _translating_open.__wrapped__ = _real_open  # type: ignore[attr-defined]
    builtins.open = _translating_open

    # --- os.stat ---
    _real_stat = _os.stat

    def _translating_stat(path, *args, **kwargs):
        if _looks_like_deck_path(path):
            path = translate(str(path))
        return _real_stat(path, *args, **kwargs)

    _translating_stat.__wrapped__ = _real_stat  # type: ignore[attr-defined]
    _os.stat = _translating_stat

    # --- os.listdir ---
    _real_listdir = _os.listdir

    def _translating_listdir(path="."):
        if _looks_like_deck_path(path):
            path = translate(str(path))
        return _real_listdir(path)

    _translating_listdir.__wrapped__ = _real_listdir  # type: ignore[attr-defined]
    _os.listdir = _translating_listdir

    _path_patches_installed = True