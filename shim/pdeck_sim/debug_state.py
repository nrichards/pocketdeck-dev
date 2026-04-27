"""debug_state.py — shared state read by the debug panel.

Producers (pdeck.led, audio.get_current_tick, pdeck.change_screen, the
runner's frame loop) write to a single DebugState instance. The
DebugPanel reads from it during render. This keeps the producers
decoupled from rendering — they don't know or care that a panel exists.

Thread-safety: writes happen from any thread (audio polls from the
worker, runner frame counter from the main thread). Reads happen only
from the main thread during render. Plain Python attribute assignment
on ints/floats is atomic enough for this — we don't need locks. The
panel might display a slightly stale value for a frame; that's fine.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List


# How recently must something have been touched to count as "active"?
# 1 second is short enough that briefly-paused activity reads as inactive,
# long enough that polling-based producers don't flicker.
ACTIVITY_WINDOW_S = 1.0


@dataclass
class DebugState:
    """Mutable diagnostic state surfaced by the debug panel.

    All fields are safe to read or write from any thread. None of them
    cross the boundary into pygame/SDL, which is what would actually
    require thread synchronization on macOS.
    """

    # Currently-displayed virtual screen (1-9). Updated by pdeck.change_screen.
    active_screen: int = 2

    # Per-LED brightness, indexed by LED number. Updated by pdeck.led(idx, b).
    # Sized for 8 LEDs which is what the deck physically has. Brightness is
    # an int 0-255 in the deck's API.
    led_brightness: List[int] = field(default_factory=lambda: [0] * 8)

    # Wall-clock timestamps of the last call to each producer. Used to
    # decide whether an indicator should display as "active" or "idle".
    # The panel's `is_active(field)` helper reads these.
    last_audio_tick: float = 0.0  # set by audio.get_current_tick

    # Frame counter and timing — populated by the runner's main loop.
    # The panel computes FPS from these on demand.
    frames_rendered: int = 0
    last_frame_time: float = field(default_factory=time.monotonic)
    fps_smoothed: float = 0.0

    def note_audio_tick(self) -> None:
        """Producer hook: called from audio.get_current_tick()."""
        self.last_audio_tick = time.monotonic()

    def note_frame(self) -> None:
        """Producer hook: called from the runner's main loop after each
        present(). Maintains a smoothed FPS using exponential moving average."""
        now = time.monotonic()
        delta = now - self.last_frame_time
        if 0.001 < delta < 1.0:
            instant_fps = 1.0 / delta
            # Smoothing factor 0.1 -> ~10-frame moving average feel
            self.fps_smoothed = self.fps_smoothed * 0.9 + instant_fps * 0.1
        self.last_frame_time = now
        self.frames_rendered += 1

    def is_audio_active(self) -> bool:
        return (time.monotonic() - self.last_audio_tick) < ACTIVITY_WINDOW_S


# Process-wide singleton — same pattern as the framebuffer.
_instance: "DebugState | None" = None


def get_debug_state() -> DebugState:
    global _instance
    if _instance is None:
        _instance = DebugState()
    return _instance


def reset_debug_state() -> None:
    """For test fixtures that need a clean state between runs."""
    global _instance
    _instance = DebugState()
