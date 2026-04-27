"""xbm_render.py — blit deck-style packed bitmap data into a pygame surface.

The deck uses MSB-first bit order — bit 7 of byte 0 is the leftmost
pixel. This is opposite of the standard XBM spec (LSB-first) but matches
what the deck's xbmreader produces: it bit-reverses standard XBM data
at parse time so the blitter only ever sees MSB-first. XBMR files are
already MSB-first on disk by the same convention.

A row is padded out to a byte boundary: stride_bytes = (width + 7) // 8.

`draw_xbm` on the deck takes `xbm_data` as bytes. `draw_image` takes a
tuple from xbmreader. This module only handles the raw-bytes case; the
tuple unpacking happens in Vscreen.draw_image.

Critical fidelity note: the LSB-vs-MSB choice is not aesthetic. If the
shim got this wrong, real deck data would render scrambled — every byte
would have its 8 pixels mirrored horizontally. The visible bug pattern
is "image is the right size and roughly the right shape, but unrecognizable
in detail" — exactly what hello_graphic.py showed before this fix.
"""
from __future__ import annotations

import pygame


def blit_xbm(surface: pygame.Surface, x: int, y: int, w: int, h: int,
             data, color: int, transparent: bool) -> None:
    """Blit `data` (MSB-first packed bytes) of size w x h at (x, y) on `surface`.

    color: palette index to plot where the bit is set (1).
    transparent: if True, bits that are 0 do nothing; if False, they are
    plotted as the opposite palette index (i.e., the bitmap acts like a
    solid stamp).

    Bit order: MSB-first within each byte. Pixel at column c in a row
    lives in bit (7 - (c & 7)) of byte (c >> 3). This matches the deck's
    xbmreader output and the XBMR file format.
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
            # MSB-first: bit 7 is leftmost pixel
            bit = (data[byte_idx] >> (7 - (col & 7))) & 1
            if bit:
                surface.set_at((x + col, ty), color)
            elif not transparent:
                surface.set_at((x + col, ty), bg)
