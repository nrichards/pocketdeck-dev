"""fonts.py — approximations of the deck's built-in u8g2 fonts.

u8g2 fonts are bitmap fonts with specific metrics. We don't ship them.
Instead we pick a monospace TrueType at a size that roughly matches each
u8g2 font's cap height, so layouts come out close-but-not-exact.

If you need pixel-perfect font fidelity, this is the right module to swap
out — load the real u8g2 font binaries and rasterize per-character. Good
upgrade path for a v2.
"""
from __future__ import annotations

import pygame


# Map u8g2 font name -> (ttf size in px, bold?)
# Pixel sizes chosen to match approximate glyph height on the 400x240 screen.
_FONT_SPECS = {
    "u8g2_font_profont11_mf":   (10, False),
    "u8g2_font_profont15_mf":   (14, False),
    "u8g2_font_profont22_mf":   (22, False),
    "u8g2_font_profont29_mf":   (28, False),
    "u8g2_font_tenfatguys_tf":  (14, True),
    "u8g2_font_tenthinnerguys_tf": (12, False),
}


class _Font:
    """Wraps a pygame.Font with u8g2-ish draw semantics.

    u8g2 `draw_str(x, y, text)` uses y as the text **baseline**, not the top.
    Pygame renders with y as the top of the bounding box, so we offset.
    """

    def __init__(self, size: int, bold: bool) -> None:
        pygame.font.init()
        # SysFont("monospace", size) finds a monospace on all platforms.
        self._pg = pygame.font.SysFont("monospace", size, bold=bold)
        self._size = size
        # Ascent: distance from baseline to top of tallest glyph.
        self._ascent = self._pg.get_ascent()
        self._height = self._pg.get_height()

    def render(self, surface: pygame.Surface, x: int, y: int, text: str,
               color: int, transparent: bool) -> None:
        if not text:
            return
        # Render to a 1-channel bitmap-ish surface. pygame gives us RGBA
        # antialiased text; we threshold to match 1bpp.
        rendered = self._pg.render(text, False, (255, 255, 255), (0, 0, 0))
        rendered = rendered.convert()
        # For each non-black pixel in rendered, plot `color` onto surface.
        # This is the slow path but fine for per-frame text.
        rw, rh = rendered.get_size()
        sw, sh = surface.get_size()

        # Destination top-left: x unchanged, y minus ascent.
        dx = x
        dy = y - self._ascent

        for px in range(rw):
            tx = dx + px
            if tx < 0 or tx >= sw:
                continue
            for py in range(rh):
                ty = dy + py
                if ty < 0 or ty >= sh:
                    continue
                r, g, b, _ = rendered.get_at((px, py))
                if r + g + b > 200:  # threshold
                    surface.set_at((tx, ty), color)
                elif not transparent:
                    surface.set_at((tx, ty), 1 - color if color in (0, 1) else 0)

    def width(self, text: str) -> int:
        return self._pg.size(text)[0] if text else 0

    def height(self) -> int:
        return self._height

    def ascent(self) -> int:
        return self._ascent


class FontRegistry:
    _cache: dict[str, _Font] = {}

    @classmethod
    def get(cls, name: str) -> _Font:
        # Default to profont11 for unknown names.
        size, bold = _FONT_SPECS.get(name, _FONT_SPECS["u8g2_font_profont11_mf"])
        key = f"{size}_{bold}"
        if key not in cls._cache:
            cls._cache[key] = _Font(size, bold)
        return cls._cache[key]
