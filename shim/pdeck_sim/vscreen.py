"""vscreen.py — the drawing surface, mirrors the deck's vscreen object.

All drawing primitives rasterize into the current buffer as 1-bit values. We
pick 0 (background) or 1 (foreground) based on `set_draw_color`:
  0 -> force background (eraser)
  1 -> force foreground (pen)
  2 -> XOR (toggle)

Most primitives delegate to pygame.draw where possible, because that handles
clipping and edge cases for us. For XBM and fonts we do per-pixel work.
"""
from __future__ import annotations

from typing import Callable, Optional

import pygame

from .framebuffer import Framebuffer, SCREEN_W, SCREEN_H, get_framebuffer
from .fonts import FontRegistry
from .xbm_render import blit_xbm


class Vscreen:
    """One virtual screen (0..9) on the deck.

    In the shim we only actively render screen 2 (the typical app screen),
    but every Vscreen instance has its own state and you can create more. The
    `active` property tells the app whether it owns the display right now.
    """

    # Class-level: which screen number is currently the "visible" one
    _current_screen: int = 2

    def __init__(self, screen_num: int = 2) -> None:
        self.screen_num = screen_num
        self.fb = get_framebuffer()

        # u8g2 drawing state
        self._draw_color = 1       # 0 bg, 1 fg, 2 xor
        self._font_mode = 0        # 0 solid, 1 transparent
        self._bitmap_mode = 0      # 0 solid, 1 transparent
        self._dither = 16          # 0..16
        self._font = FontRegistry.get("u8g2_font_profont11_mf")

        # Frame callback
        self._callback: Optional[Callable[[bool], None]] = None
        self._drew_this_frame = False

        # I/O
        self._terminal_size = (80, 24)  # cols, rows — rough approximation

        self.suspend_inactive_screen = False

    # -----------------------------------------------------------------------
    # Properties and lifecycle
    # -----------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.screen_num == Vscreen._current_screen

    def callback(self, handler: Optional[Callable[[bool], None]]) -> None:
        """Register a frame-update callback (or None to unregister)."""
        self._callback = handler

    def callback_exists(self) -> bool:
        return self._callback is not None

    def finished(self) -> None:
        """App tells us it's done drawing this frame. Present and flip."""
        # On real deck, calling finished() without any draw saves energy. In
        # the shim we always present so the window stays responsive, but we
        # skip the scale/blit if nothing changed.
        if self._drew_this_frame:
            self.fb.present()
            self._drew_this_frame = False
        else:
            # Still need to flip so the window redraws; cheap.
            self.fb.present()

    # -----------------------------------------------------------------------
    # Internal drawing helpers
    # -----------------------------------------------------------------------

    def _buf(self) -> pygame.Surface:
        return self.fb.buffers[self.fb.active_buffer]

    def _mark(self) -> None:
        self._drew_this_frame = True

    def _pixel(self, x: int, y: int) -> None:
        if not (0 <= x < SCREEN_W and 0 <= y < SCREEN_H):
            return
        buf = self._buf()
        if self._draw_color == 2:
            cur = buf.get_at((x, y))[0]
            buf.set_at((x, y), 0 if cur == 1 else 1)
        else:
            buf.set_at((x, y), self._draw_color)

    def _draw_color_value(self) -> int:
        """Convert draw_color to a concrete palette index for pygame.draw.
        XOR mode falls back to foreground for primitives that can't XOR
        natively — acceptable approximation."""
        return 0 if self._draw_color == 0 else 1

    # -----------------------------------------------------------------------
    # Basic shapes
    # -----------------------------------------------------------------------

    def draw_pixel(self, x: int, y: int) -> None:
        self._pixel(int(x), int(y))
        self._mark()

    def draw_line(self, x1: int, y1: int, x2: int, y2: int) -> None:
        pygame.draw.line(
            self._buf(), self._draw_color_value(),
            (int(x1), int(y1)), (int(x2), int(y2)), 1,
        )
        self._mark()

    def draw_h_line(self, x: int, y: int, w: int) -> None:
        self.draw_line(x, y, x + w - 1, y)

    def draw_v_line(self, x: int, y: int, h: int) -> None:
        self.draw_line(x, y, x, y + h - 1)

    def draw_box(self, x: int, y: int, w: int, h: int) -> None:
        pygame.draw.rect(
            self._buf(), self._draw_color_value(),
            pygame.Rect(int(x), int(y), int(w), int(h)),
        )
        self._mark()

    def draw_frame(self, x: int, y: int, w: int, h: int) -> None:
        pygame.draw.rect(
            self._buf(), self._draw_color_value(),
            pygame.Rect(int(x), int(y), int(w), int(h)), 1,
        )
        self._mark()

    def draw_rframe(self, x: int, y: int, w: int, h: int, r: int) -> None:
        pygame.draw.rect(
            self._buf(), self._draw_color_value(),
            pygame.Rect(int(x), int(y), int(w), int(h)),
            width=1, border_radius=int(r),
        )
        self._mark()

    def draw_rbox(self, x: int, y: int, w: int, h: int, r: int) -> None:
        pygame.draw.rect(
            self._buf(), self._draw_color_value(),
            pygame.Rect(int(x), int(y), int(w), int(h)),
            width=0, border_radius=int(r),
        )
        self._mark()

    def draw_circle(self, x: int, y: int, rad: int, opt: int = 0) -> None:
        # u8g2 `opt` selects quadrants (0x0f = all). We ignore for simplicity.
        pygame.draw.circle(
            self._buf(), self._draw_color_value(),
            (int(x), int(y)), int(rad), 1,
        )
        self._mark()

    def draw_disc(self, x: int, y: int, rad: int, opt: int = 0) -> None:
        pygame.draw.circle(
            self._buf(), self._draw_color_value(),
            (int(x), int(y)), int(rad),
        )
        self._mark()

    def draw_triangle(self, x0, y0, x1, y1, x2, y2) -> None:
        pts = [(int(x0), int(y0)), (int(x1), int(y1)), (int(x2), int(y2))]
        pygame.draw.polygon(self._buf(), self._draw_color_value(), pts)
        self._mark()

    def draw_arc(self, x: int, y: int, rad: int, start, end) -> None:
        # u8g2 angles: 0..255 mapped to 0..2pi. Approximate with pygame.
        import math
        s = float(start) / 255.0 * 2 * math.pi
        e = float(end) / 255.0 * 2 * math.pi
        rect = pygame.Rect(int(x - rad), int(y - rad), int(rad * 2), int(rad * 2))
        pygame.draw.arc(self._buf(), self._draw_color_value(), rect, s, e, 1)
        self._mark()

    def draw_ellipse(self, x, y, rx, ry, opt=0) -> None:
        rect = pygame.Rect(int(x - rx), int(y - ry), int(rx * 2), int(ry * 2))
        pygame.draw.ellipse(self._buf(), self._draw_color_value(), rect, 1)
        self._mark()

    def draw_filled_ellipse(self, x, y, rx, ry, opt=0) -> None:
        rect = pygame.Rect(int(x - rx), int(y - ry), int(rx * 2), int(ry * 2))
        pygame.draw.ellipse(self._buf(), self._draw_color_value(), rect)
        self._mark()

    def draw_polygon(self, points_array) -> None:
        # u8g2 polygon is an int16 array [x1,...,xn,y1,...,yn].
        pts = list(points_array)
        n = len(pts) // 2
        xs, ys = pts[:n], pts[n:]
        pygame.draw.polygon(
            self._buf(), self._draw_color_value(),
            list(zip(xs, ys)),
        )
        self._mark()

    # -----------------------------------------------------------------------
    # Text
    # -----------------------------------------------------------------------

    def draw_str(self, x: int, y: int, text: str) -> None:
        self._font.render(self._buf(), int(x), int(y), text,
                          color=self._draw_color_value(),
                          transparent=(self._font_mode == 1))
        self._mark()

    def draw_utf8(self, x: int, y: int, text: str) -> None:
        self.draw_str(x, y, text)

    def draw_button_utf8(self, x, y, flags, width, pad_h, pad_v, text) -> None:
        w = max(int(width), self._font.width(text) + 2 * int(pad_h))
        h = self._font.height() + 2 * int(pad_v)
        self.draw_rframe(x, y - self._font.ascent(), w, h, 2)
        self.draw_str(x + int(pad_h), y, text)

    def get_str_width(self, text: str) -> int:
        return self._font.width(text)

    def get_utf8_width(self, text: str) -> int:
        return self._font.width(text)

    def set_font(self, name_or_data) -> None:
        if isinstance(name_or_data, str):
            self._font = FontRegistry.get(name_or_data)
        # raw font data ignored — we don't parse u8g2 font binaries

    def set_font_mode(self, mode: int) -> None:
        self._font_mode = int(mode)

    # -----------------------------------------------------------------------
    # Bitmaps
    # -----------------------------------------------------------------------

    def draw_xbm(self, x: int, y: int, w: int, h: int, xbm_data) -> None:
        blit_xbm(self._buf(), int(x), int(y), int(w), int(h), xbm_data,
                 color=self._draw_color_value(),
                 transparent=(self._bitmap_mode == 1))
        self._mark()

    def draw_image(self, x: int, y: int, image, frame: int = 0) -> None:
        """image is (name, width, height, data, num_frames) per xbmreader."""
        if image is None:
            return
        try:
            _name, w, h, data, num_frames = image
        except (ValueError, TypeError):
            return
        # Select frame from concatenated data
        frame = max(0, min(int(frame), max(1, int(num_frames)) - 1))
        stride = ((w + 7) // 8) * h
        start = frame * stride
        frame_data = data[start:start + stride] if num_frames > 1 else data
        self.draw_xbm(x, y, w, h, frame_data)

    def capture_as_xbm(self, x, y, w, h, buffer) -> None:
        # Very rarely used; implement if an app actually needs it.
        raise NotImplementedError("capture_as_xbm not implemented in shim")

    def set_bitmap_mode(self, mode: int) -> None:
        self._bitmap_mode = int(mode)

    # -----------------------------------------------------------------------
    # Color / dither
    # -----------------------------------------------------------------------

    def set_draw_color(self, color: int) -> None:
        self._draw_color = int(color) & 0x03

    def set_dither(self, level: int) -> None:
        self._dither = max(0, min(16, int(level)))
        # Note: true dithering would modulate draw ops by `level/16`. Not
        # implemented here; apps using it for splash effects will look off.

    # -----------------------------------------------------------------------
    # Buffers
    # -----------------------------------------------------------------------

    def clear_buffer(self) -> None:
        self._buf().fill(0)
        self._mark()

    def switch_buffer(self, buffer_num: int) -> None:
        self.fb.active_buffer = 0 if int(buffer_num) == 0 else 1

    def copy_buffer(self, to_buffer: int, from_buffer: int) -> None:
        src = self.fb.buffers[int(from_buffer) & 1]
        dst = self.fb.buffers[int(to_buffer) & 1]
        dst.blit(src, (0, 0))

    # -----------------------------------------------------------------------
    # Input
    # -----------------------------------------------------------------------

    def print(self, text) -> None:
        # Terminal output goes to stderr so stdout stays clean for debugging
        import sys
        sys.stderr.write(str(text))

    def send_char(self, data) -> None:
        if isinstance(data, str):
            self.fb.input_queue.extend(data.encode("utf-8"))
        elif isinstance(data, (bytes, bytearray)):
            self.fb.input_queue.extend(data)

    def send_key_event(self, key, modifier, event_type) -> None:
        # Minimal shim: treat as press-then-release of the given key code.
        self.fb.key_state[int(key)] = (int(event_type) == 1)

    def read_nb(self, max_bytes: int) -> tuple:
        if not self.fb.input_queue:
            return (0, b"")
        n = min(int(max_bytes), len(self.fb.input_queue))
        data = bytes(self.fb.input_queue[:n])
        del self.fb.input_queue[:n]
        return (n, data)

    def poll(self) -> bool:
        return len(self.fb.input_queue) > 0

    def get_key_state(self, key_code: int) -> bool:
        return bool(self.fb.key_state.get(int(key_code), False))

    def get_tp_keys(self) -> bytes:
        # 7 bytes of touchpad state; we don't have a touchpad, so return
        # all-unpressed (0xFF for analog fields, 0 for buttons).
        return bytes([0xFF, 0xFF, 0xFF, 0x00, 0xFF, 0x00, 0x00])

    def get_terminal_size(self) -> tuple:
        return self._terminal_size

    def set_terminal_font(self, normal, bold, width, height) -> None:
        cols = max(1, SCREEN_W // max(1, int(width)))
        rows = max(1, SCREEN_H // max(1, int(height)))
        self._terminal_size = (cols, rows)

    def set_terminal_font_size(self, size: int) -> None:
        # Rough: assume ~6px wide at size 1, scale proportionally.
        px = max(6, int(size))
        self.set_terminal_font(None, None, px, int(px * 1.6))
