"""shim_log.py — centralized logging helpers for pdeck_sim.

All shim diagnostic output goes through these functions so the message
format stays consistent and so we can change it (add timestamps, colors,
log levels) in one place.

Format: `[pdeck_sim:<producer>] <message>`

The producer tag identifies which subsystem emitted the message —
`runner`, `paths`, `audio`, `pie`, `xbmreader`, etc. This is useful
when the runner is producing a flood of output and you want to filter:

    python3 -m pdeck_sim.runner my_app.py 2>&1 | grep ':paths]'

User-visible app output (`print(..., file=vs)`) does NOT go through
this — those messages come from the user's app, not from the shim.
The prefix is reserved for shim-emitted diagnostics.
"""
from __future__ import annotations

import sys
import warnings


_PREFIX = "[pdeck_sim"


def log(producer: str, message: str) -> None:
    """Print an informational shim message, prefixed with the producer tag.

    Goes to stderr to keep stdout clean for app I/O.
    """
    sys.stderr.write(f"{_PREFIX}:{producer}] {message}\n")
    sys.stderr.flush()


def warn(producer: str, message: str, stacklevel: int = 2) -> None:
    """Emit a Python warning prefixed with the producer tag.

    Used for advisory issues — missing assets, stubbed-call advisories,
    etc. The warning system gives users control over filtering via
    `warnings.filterwarnings`.
    """
    warnings.warn(f"{_PREFIX}:{producer}] {message}", stacklevel=stacklevel + 1)


def error(producer: str, message: str) -> None:
    """Print an error message. Currently identical to log() in formatting,
    but separated so future-you can add color or a level prefix without
    sweeping callers.
    """
    sys.stderr.write(f"{_PREFIX}:{producer}] ERROR: {message}\n")
    sys.stderr.flush()
