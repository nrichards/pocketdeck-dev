"""vscreen_stream.py — stream-like wrapper around a Vscreen.

The deck's `main(vs, args)` receives a `vscreen_stream`. Apps use `vs.v` to
reach the underlying vscreen for graphics, and `vs.read(...)` / `print(...,
file=vs)` for stream-style I/O.

We implement enough of the stream protocol that the common app patterns work:
- `print("hello", file=vs)` — goes to stderr, clearly marked
- `vs.read(n, timeout_ms)` — blocks up to timeout_ms waiting for input
- `vs.write(data)` — echoes to stderr
- `vs.poll()` — checks for pending input
- `vs.ioctl(...)` — no-op but present

On the real deck, `vs.read(n, poll_ms)` polls the keyboard every `poll_ms`
until it either has `n` bytes or the user interrupts. In the shim we drive
the event pump on each poll so the window stays alive while an app blocks
waiting for a keystroke.
"""
from __future__ import annotations

import sys
import time
from typing import Optional

from .vscreen import Vscreen
from .framebuffer import get_framebuffer


class VscreenStream:
    """Stream-like facade. `.v` exposes the underlying Vscreen."""

    def __init__(self, v: Vscreen) -> None:
        self.v = v
        self._fb = get_framebuffer()

    # --- stream interface ---

    def write(self, data) -> int:
        if isinstance(data, (bytes, bytearray)):
            text = data.decode("utf-8", errors="replace")
        else:
            text = str(data)
        sys.stderr.write(text)
        sys.stderr.flush()
        return len(text)

    def read(self, n: int = 1, poll_ms: int = 50) -> bytes:
        """Block up to `poll_ms` at a time waiting for up to n bytes.

        On the real deck this loops until interrupted. In the shim we cap
        the total wait at 1 hour to avoid hanging a test run forever. Apps
        that truly want indefinite blocking will still feel the same.
        """
        deadline = time.time() + 3600
        poll_s = max(0.001, poll_ms / 1000.0)
        while time.time() < deadline:
            # Pump events so the window stays responsive and input arrives.
            self._fb.pump_events()
            if self._fb.flags.quit_requested:
                return b""
            got, data = self.v.read_nb(n)
            if got > 0:
                return data
            # Present frame and sleep one poll interval.
            self.v.fb.present()
            time.sleep(poll_s)
        return b""

    def async_read(self, n: int = 1) -> bytes:
        got, data = self.v.read_nb(n)
        return data if got > 0 else b""

    def poll(self) -> bool:
        return self.v.poll()

    def ioctl(self, *a, **kw) -> int:
        return 0

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def flush(self) -> None:
        sys.stderr.flush()

    def close(self) -> None:
        pass
