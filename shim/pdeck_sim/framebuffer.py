"""framebuffer.py — 1-bit-per-pixel framebuffer, pygame-rendered.

The deck has a 400x240 monochrome LCD with two buffers (0 = displayed,
1 = scratch). We mirror that here. Each buffer is a pygame.Surface with only
two logical colors. Pygame handles the window, blitting, and scaling.

Drawing primitives on the vscreen object poke pixels into whichever buffer is
currently active (via `switch_buffer`). The callback loop periodically flips
buffer 0 to the window.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pygame

# Deck hardware
SCREEN_W = 400
SCREEN_H = 240
NUM_BUFFERS = 2

# Desktop presentation
DEFAULT_SCALE = 2
FPS = 60

# Monochrome palette. We render as black-on-white to match the default deck
# look (LCD is reflective, pixels are dark on pale background).
COLOR_BG = (230, 230, 220)  # off-white, suggests LCD reflection
COLOR_FG = (20, 20, 20)     # soft black, easier on eyes than pure black


@dataclass
class RuntimeFlags:
    invert: bool = False
    scale: int = DEFAULT_SCALE
    quit_requested: bool = False
    detach_requested: bool = False  # C-S-D equivalent


class Framebuffer:
    """Owns the pygame window + two 1bpp buffers.

    One instance per process, held by the active module. The active vscreen
    draws into `buffers[active_buffer]`. Presentation reads from `buffers[0]`.
    """

    _instance: "Framebuffer | None" = None

    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Pocket Deck Simulator")
        self.flags = RuntimeFlags()
        self._window = pygame.display.set_mode(
            (SCREEN_W * self.flags.scale, SCREEN_H * self.flags.scale)
        )
        # Two monochrome buffers. Using 8-bit surfaces so per-pixel ops are
        # cheap. Values are 0 (background) or 1 (foreground); we translate at
        # blit time.
        self.buffers = [
            pygame.Surface((SCREEN_W, SCREEN_H), depth=8)
            for _ in range(NUM_BUFFERS)
        ]
        for b in self.buffers:
            b.set_palette([COLOR_BG, COLOR_FG] + [(0, 0, 0)] * 254)
            b.fill(0)
        self.active_buffer = 0
        self.clock = pygame.time.Clock()

        # Key/input state shared with vscreen
        self.key_state: dict[int, bool] = {}       # HID usage-ish -> pressed
        self.input_queue: bytearray = bytearray()   # bytes waiting for read_nb

        # Lock protects buffers during the brief moment we blit to window.
        self._blit_lock = threading.Lock()

    @classmethod
    def get(cls) -> "Framebuffer":
        if cls._instance is None:
            cls._instance = Framebuffer()
        return cls._instance

    def reset_for_testing(self) -> None:
        """Reset all mutable state to defaults. For use by test fixtures —
        the framebuffer is a process-wide singleton, so without an explicit
        reset, state from one test leaks into the next.

        Does not recreate the pygame window (that would require re-entering
        pygame.init and breaks on macOS when called off-main-thread). Only
        resets data we can touch safely.
        """
        for b in self.buffers:
            b.fill(0)
        self.active_buffer = 0
        self.key_state.clear()
        self.input_queue.clear()
        self.flags.invert = False
        self.flags.quit_requested = False
        self.flags.detach_requested = False

    # --- presentation ---

    def present(self) -> None:
        """Blit buffer 0 to the window, respecting invert and scale."""
        with self._blit_lock:
            buf = self.buffers[0].copy()
        if self.flags.invert:
            # Swap palette entries
            buf.set_palette([COLOR_FG, COLOR_BG] + [(0, 0, 0)] * 254)
        scaled = pygame.transform.scale(
            buf, (SCREEN_W * self.flags.scale, SCREEN_H * self.flags.scale)
        )
        self._window.blit(scaled, (0, 0))
        pygame.display.flip()

    def resize_window(self, scale: int) -> None:
        self.flags.scale = max(1, min(4, scale))
        self._window = pygame.display.set_mode(
            (SCREEN_W * self.flags.scale, SCREEN_H * self.flags.scale)
        )

    # --- event pump ---

    def pump_events(self) -> None:
        """Drain pygame events, update key state and input queue.

        Called from the main thread. Must run every frame or the OS thinks
        the app hung.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.flags.quit_requested = True
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event)
            elif event.type == pygame.KEYUP:
                self.key_state[event.key] = False

    def _handle_keydown(self, event: pygame.event.Event) -> None:
        self.key_state[event.key] = True
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL)
        shift = bool(mods & pygame.KMOD_SHIFT)

        # Runtime shortcuts (handled here, not forwarded to app)
        if event.key == pygame.K_ESCAPE:
            self.flags.quit_requested = True
            return
        if event.key == pygame.K_F5:
            # Reload handled by runner; expose via a flag
            self.flags.reload_requested = True  # type: ignore[attr-defined]
            return
        if event.key == pygame.K_F6:
            self.flags.invert = not self.flags.invert
            return
        if event.key == pygame.K_F11:
            self.resize_window(1 if self.flags.scale == 2 else 2)
            return
        if ctrl and shift and event.key == pygame.K_d:
            self.flags.detach_requested = True
            return

        # Forward to app input queue
        if event.unicode:
            self.input_queue.extend(event.unicode.encode("utf-8"))
            return
        # Arrow keys as ANSI escapes (matches what the deck sends)
        escape_map = {
            pygame.K_UP: b"\x1b[A",
            pygame.K_DOWN: b"\x1b[B",
            pygame.K_RIGHT: b"\x1b[C",
            pygame.K_LEFT: b"\x1b[D",
        }
        if event.key in escape_map:
            self.input_queue.extend(escape_map[event.key])


def get_framebuffer() -> Framebuffer:
    return Framebuffer.get()
