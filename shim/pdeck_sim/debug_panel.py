"""debug_panel.py — renders the debug side panel to a pygame surface.

Layout (panel is 199 px wide, 240 tall):

    +-----------------------+
    | SCREEN 2              |  <- active screen, big text
    |                       |
    | LEDs                  |
    | ●○●○ ○○○○             |  <- 8 LEDs, filled = on, hollow = off
    |                       |
    | Audio  ● active       |  <- pulses when audio engine in use
    |                       |
    |                       |
    |                       |
    |                       |
    | 60 fps  frame 1234    |  <- bottom of panel
    +-----------------------+

The panel is rendered by `render_to(surface)` once per frame from the
main thread. State comes from `DebugState`; the panel itself is
stateless beyond a small font cache.
"""
from __future__ import annotations

import pygame

from .debug_state import DebugState


# Geometry — kept as constants so it's easy to tune without hunting
# through render code.
PANEL_W = 199
PANEL_H = 240
PADDING = 10

# Colors. The panel intentionally uses a slightly cooler, more "computer
# screen" palette than the LCD's warm off-white — visual cue that this
# area isn't the device.
COLOR_PANEL_BG = (240, 242, 245)   # slightly cooler than LCD bg
COLOR_DIVIDER = (140, 140, 140)    # the 1px line between LCD and panel
COLOR_TEXT = (60, 60, 70)          # neutral dark
COLOR_TEXT_DIM = (140, 140, 150)   # secondary info
COLOR_ACTIVE = (40, 130, 80)       # green for "active" indicators
COLOR_INACTIVE = (200, 200, 200)   # light gray for "off" indicators
COLOR_LED_ON = (220, 140, 40)      # warm amber for lit LEDs
COLOR_LED_OFF_RING = (180, 180, 185)


class DebugPanel:
    """Renders DebugState into a pygame surface for blitting.

    Holds font references for performance; otherwise stateless. Construct
    once at startup, call render_to() each frame.
    """

    def __init__(self) -> None:
        pygame.font.init()
        # SysFont gives us platform monospace; size chosen for readability
        # at the deck's native scale (no smaller than 10 to stay legible
        # when the window is rendered at 1×).
        self._font_big = pygame.font.SysFont("monospace", 16, bold=True)
        self._font_med = pygame.font.SysFont("monospace", 11, bold=False)
        self._font_small = pygame.font.SysFont("monospace", 10, bold=False)

    def render_to(self, surface: pygame.Surface, state: DebugState) -> None:
        """Render the panel into the given surface (assumed PANEL_W x PANEL_H).

        The surface is filled with the panel background, then text and
        indicators are drawn on top in a fixed layout.
        """
        surface.fill(COLOR_PANEL_BG)

        y = PADDING

        # --- Active screen ---
        label = self._font_med.render("SCREEN", True, COLOR_TEXT_DIM)
        surface.blit(label, (PADDING, y))
        y += label.get_height()
        num_text = self._font_big.render(str(state.active_screen),
                                         True, COLOR_TEXT)
        surface.blit(num_text, (PADDING, y))
        y += num_text.get_height() + 8

        # --- LEDs ---
        label = self._font_med.render("LEDS", True, COLOR_TEXT_DIM)
        surface.blit(label, (PADDING, y))
        y += label.get_height() + 2
        self._draw_leds(surface, PADDING, y, state.led_brightness)
        y += 24  # space for LEDs + label below

        # Numbered labels under each LED for orientation
        for i in range(8):
            cx = PADDING + 8 + i * 20
            n = self._font_small.render(str(i), True, COLOR_TEXT_DIM)
            surface.blit(n, (cx - n.get_width() // 2, y))
        y += 14

        # --- Audio activity indicator ---
        label = self._font_med.render("AUDIO", True, COLOR_TEXT_DIM)
        surface.blit(label, (PADDING, y))
        y += label.get_height() + 2
        active = state.is_audio_active()
        self._draw_dot(surface, PADDING + 4, y + 4,
                       COLOR_ACTIVE if active else COLOR_INACTIVE)
        status = "active" if active else "idle"
        status_text = self._font_med.render(status, True, COLOR_TEXT)
        surface.blit(status_text, (PADDING + 18, y))
        y += 18

        # --- FPS / frame count at the bottom of the panel ---
        fps_text = self._font_small.render(
            f"{state.fps_smoothed:>4.0f} fps   frame {state.frames_rendered}",
            True, COLOR_TEXT_DIM,
        )
        # Anchored to bottom rather than flowing — this stays stable as
        # other rows grow above it.
        surface.blit(fps_text, (PADDING, PANEL_H - PADDING - fps_text.get_height()))

    def _draw_leds(self, surface: pygame.Surface, x: int, y: int,
                   brightness: list) -> None:
        """Draw 8 small LED indicators in a row.

        Filled circle = lit (intensity scales with brightness); hollow
        circle = off. We intentionally don't show the exact brightness
        number — the visual feedback is enough at panel scale.
        """
        for i, b in enumerate(brightness):
            cx = x + 8 + i * 20
            cy = y + 8
            if b > 0:
                # Lit: filled circle, alpha-ish via color blend with bg
                t = max(0.3, min(1.0, b / 255.0))
                color = self._blend(COLOR_PANEL_BG, COLOR_LED_ON, t)
                pygame.draw.circle(surface, color, (cx, cy), 6)
            else:
                # Off: hollow ring
                pygame.draw.circle(surface, COLOR_LED_OFF_RING,
                                   (cx, cy), 6, 1)

    def _draw_dot(self, surface: pygame.Surface, x: int, y: int,
                  color: tuple) -> None:
        pygame.draw.circle(surface, color, (x, y), 5)

    @staticmethod
    def _blend(a: tuple, b: tuple, t: float) -> tuple:
        """Linear-blend two RGB colors. t=0 -> a, t=1 -> b."""
        return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
