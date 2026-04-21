"""xbm_render.py — blit u8g2-style XBM data into a pygame surface.

XBM stores pixels as a tightly-packed byte array, one bit per pixel,
LSB-first within each byte, row-major. A row is padded out to a byte
boundary: stride_bytes = (width + 7) // 8.

`draw_xbm` on the deck takes `xbm_data` as bytes. `draw_image` takes a
tuple from xbmreader. This module only handles the raw-bytes case; the
tuple unpacking happens in Vscreen.draw_image.
"""
from __future__ import annotations

import pygame


def blit_xbm(surface: pygame.Surface, x: int, y: int, w: int, h: int,
             data, color: int, transparent: bool) -> None:
    """Blit `data` (XBM bytes) of size w x h at (x, y) on `surface`.

    color: palette index to plot where the bit is set (1).
    transparent: if True, bits that are 0 do nothing; if False, they are
    plotted as the opposite palette index (i.e., the bitmap acts like a
    solid stamp).
    """
    if not data:
        return
    data = bytes(data)
    sw, sh = surface.get_size()
    stride = (w + 7) // 8
    bg = 1 - color if color in (0, 1) else 0

    # Fast-ish path: iterate only through on-screen pixels
    x_start = max(0, -x)
    y_start = max(0, -y)
    x_end = min(w, sw - x)
    y_end = min(h, sh - y)

    for row in range(y_start, y_end):
        row_offset = row * stride
        ty = y + row
        for col in range(x_start, x_end):
            byte_idx = row_offset + (col >> 3)
            if byte_idx >= len(data):
                break
            bit = (data[byte_idx] >> (col & 7)) & 1
            if bit:
                surface.set_at((x + col, ty), color)
            elif not transparent:
                surface.set_at((x + col, ty), bg)
