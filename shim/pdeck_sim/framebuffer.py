"""framebuffer.py — 1-bit-per-pixel framebuffer, pygame-rendered.

The deck has a 400x240 monochrome LCD with two buffers (0 = displayed,
1 = scratch). We mirror that here. Each buffer is a pygame.Surface with only
two logical colors. Pygame handles the window, blitting, and scaling.

Drawing primitives on the vscreen object poke pixels into whichever buffer is
currently active (via `switch_buffer`). The callback loop periodically flips
buffer 0 to the window.

Optional debug side panel (right of the LCD) shows runtime state — active
screen number, LED brightness, audio activity, FPS. Enabled by default;
disable via POCKETDECK_DEBUG_PANEL=0 to render only the device-accurate
LCD area.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

import pygame

# Deck hardware
SCREEN_W = 400
SCREEN_H = 240
NUM_BUFFERS = 2

# Debug panel geometry — mirrors the constants in debug_panel.py.
# Defined here too so we can compute window dimensions without importing
# debug_panel (which imports pygame.font, has heavier startup cost).
DEBUG_PANEL_W = 199
DIVIDER_W = 1
COLOR_DIVIDER = (140, 140, 140)

# Desktop presentation
DEFAULT_SCALE = 2
FPS = 60

# Monochrome palette. We render as black-on-white to match the default deck
# look (LCD is reflective, pixels are dark on pale background).
COLOR_BG = (230, 230, 220)  # off-white, suggests LCD reflection
COLOR_FG = (20, 20, 20)     # soft black, easier on eyes than pure black


def _debug_panel_enabled() -> bool:
    """Read POCKETDECK_DEBUG_PANEL env var. Default: enabled.

    Set to 0/false/no/empty to disable, leaving only the LCD-accurate
    area visible. Useful when taking screenshots of just the device
    output, or for tests that want to assert on window dimensions.
    """
    raw = os.environ.get("POCKETDECK_DEBUG_PANEL", "1").strip().lower()
    return raw not in ("0", "false", "no", "")


@dataclass
class RuntimeFlags:
    invert: bool = False
    scale: int = DEFAULT_SCALE
    quit_requested: bool = False
    detach_requested: bool = False  # C-S-D equivalent
    # Set when something outside the drawing pipeline has changed
    # what the window should show (invert toggle, scale change, reload).
    # The runner consumes and clears this after presenting.
    needs_repaint: bool = False


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

        # Panel is checked once at construction. Toggling it at runtime
        # would require reopening the window — not supported. If a user
        # really wants to flip it, they relaunch the runner.
        self.panel_enabled = _debug_panel_enabled()
        self._window = pygame.display.set_mode(
            (self.window_width(), SCREEN_H * self.flags.scale)
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

        # Debug panel surface is created lazily on first use to avoid
        # paying its font-loading cost when disabled or in headless tests.
        self._panel = None  # type: ignore[assignment]
        self._panel_surface = None  # type: ignore[assignment]

    def window_width(self) -> int:
        """Total window pixel width including optional debug panel.

        At scale=2: 800px LCD-only, or 1200px with panel (400+199+1 = 600
        logical pixels, doubled).
        """
        logical_w = SCREEN_W
        if self.panel_enabled:
            logical_w += DIVIDER_W + DEBUG_PANEL_W
        return logical_w * self.flags.scale

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
        self.flags.needs_repaint = False
        # Reset debug state too so tests inspecting LED state, screen
        # number, etc. see clean values.
        from .debug_state import reset_debug_state
        reset_debug_state()

    # --- presentation ---

    def present(self) -> None:
        """Blit buffer 0 to the window, plus optional debug panel.

        Order: LCD on the left, single-pixel divider, panel on the right.
        Everything is scaled by the runtime scale factor at blit time.
        """
        with self._blit_lock:
            buf = self.buffers[0].copy()
        if self.flags.invert:
            # Swap palette entries
            buf.set_palette([COLOR_FG, COLOR_BG] + [(0, 0, 0)] * 254)

        scale = self.flags.scale

        # --- LCD (left side) ---
        scaled = pygame.transform.scale(
            buf, (SCREEN_W * scale, SCREEN_H * scale)
        )
        self._window.blit(scaled, (0, 0))

        # --- Divider + panel (right side, if enabled) ---
        if self.panel_enabled:
            self._render_panel(scale)

        pygame.display.flip()

    def _render_panel(self, scale: int) -> None:
        """Draw the divider line and the debug panel into the window."""
        # Lazy panel construction — defers font init cost
        if self._panel is None:
            from .debug_panel import DebugPanel, PANEL_W, PANEL_H
            self._panel = DebugPanel()
            self._panel_surface = pygame.Surface((PANEL_W, PANEL_H))

        from .debug_state import get_debug_state
        from .debug_panel import PANEL_W, PANEL_H
        state = get_debug_state()

        # Render at logical resolution, then upscale once for the blit.
        # Drawing at native resolution and scaling up gives crisper text
        # than rendering at scale-multiplied resolution would.
        self._panel.render_to(self._panel_surface, state)

        # Divider: 1 logical pixel = `scale` window pixels wide
        divider_x = SCREEN_W * scale
        pygame.draw.rect(
            self._window, COLOR_DIVIDER,
            pygame.Rect(divider_x, 0, DIVIDER_W * scale, SCREEN_H * scale),
        )

        # Panel: blit scaled
        scaled_panel = pygame.transform.scale(
            self._panel_surface,
            (PANEL_W * scale, PANEL_H * scale),
        )
        self._window.blit(scaled_panel, ((SCREEN_W + DIVIDER_W) * scale, 0))

    def resize_window(self, scale: int) -> None:
        self.flags.scale = max(1, min(4, scale))
        self._window = pygame.display.set_mode(
            (self.window_width(), SCREEN_H * self.flags.scale)
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
            self.flags.needs_repaint = True
            return
        if event.key == pygame.K_F11:
            self.resize_window(1 if self.flags.scale == 2 else 2)
            self.flags.needs_repaint = True
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
