"""dither.py — ordered Bayer dithering for filled shapes.

The deck's u8g2-based renderer applies dither levels 0..16 as stipple
patterns: level 0 means "draw nothing", level 16 means "fully solid",
intermediate levels draw a fraction of pixels in a fixed pattern.

This module provides:
  - apply_polygon_dither: draws a polygon with the current dither level,
    using a 4x4 ordered Bayer pattern aligned to screen coordinates.
  - apply_disc_dither: same idea for filled circles.
  - apply_box_dither: same idea for filled rectangles.

Why ordered Bayer instead of random/probabilistic dithering: ordered
patterns are stable across frames, give clean perceptual greys, and
don't flicker on rotating geometry. Random dither would shimmer on
the cube's rotating faces.

The 4x4 Bayer matrix has 16 distinct threshold values 0..15. A pixel
at screen position (x, y) is drawn iff `level > bayer[y%4][x%4]`.
This produces 17 distinct visual levels:
  level 0:  no pixels (0 > any threshold is always false)
  level 16: all pixels (16 > any threshold 0..15 is always true)
  level 8:  ~half of pixels (those with thresholds 0..7)
  level N:  N/16 of pixels in a stable, screen-aligned pattern
"""
from __future__ import annotations

import pygame


# Standard 4x4 Bayer threshold matrix. Values 0..15 distributed so that
# adjacent pixels have maximally-different thresholds, which produces
# a perceptually-uniform stipple at every level.
_BAYER_4x4 = (
    ( 0,  8,  2, 10),
    (12,  4, 14,  6),
    ( 3, 11,  1,  9),
    (15,  7, 13,  5),
)


def _passes(x: int, y: int, level: int) -> bool:
    """True iff the pixel at (x, y) should be drawn at this dither level.

    Uses absolute screen coordinates so the dither pattern stays anchored
    to the screen, not to the shape — which keeps the texture stable when
    a polygon moves across the screen, exactly like real hardware stipple.
    """
    if level >= 16:
        return True
    if level <= 0:
        return False
    return level > _BAYER_4x4[y & 3][x & 3]


def apply_polygon_dither(surface: pygame.Surface,
                         points: list,
                         color: int,
                         level: int) -> None:
    """Fill the polygon defined by `points` (list of (x, y) tuples) with
    `color`, applying ordered dither at the given level (0..16).

    Uses pygame.draw.polygon to compute the polygon's filled mask in a
    scratch surface, then blits only the pixels that pass the dither
    test onto the target surface.
    """
    if level <= 0:
        return  # level 0: nothing drawn
    if level >= 16:
        # Fast path: solid fill, skip per-pixel check
        pygame.draw.polygon(surface, color, points)
        return
    if not points:
        return

    # Compute bounding box. Used both to size the scratch mask and to
    # iterate only the pixels that could possibly be filled.
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    sw, sh = surface.get_size()
    # Clip to surface bounds
    min_x = max(0, min_x)
    min_y = max(0, min_y)
    max_x = min(sw - 1, max_x)
    max_y = min(sh - 1, max_y)
    if min_x > max_x or min_y > max_y:
        return  # entirely off-screen

    bw = max_x - min_x + 1
    bh = max_y - min_y + 1

    # Build a mono mask of the polygon at bounding-box origin
    mask = pygame.Surface((bw, bh), depth=8)
    mask.set_palette([(0, 0, 0), (255, 255, 255)] + [(0, 0, 0)] * 254)
    mask.fill(0)
    shifted = [(p[0] - min_x, p[1] - min_y) for p in points]
    pygame.draw.polygon(mask, 1, shifted)

    # Walk the mask, plot dithered pixels onto the destination
    bayer = _BAYER_4x4
    for ly in range(bh):
        sy = min_y + ly
        row = bayer[sy & 3]
        for lx in range(bw):
            if mask.get_at_mapped((lx, ly)) == 1:
                sx = min_x + lx
                if level > row[sx & 3]:
                    surface.set_at((sx, sy), color)


def apply_disc_dither(surface: pygame.Surface,
                      cx: int, cy: int, radius: int,
                      color: int, level: int) -> None:
    """Fill a disc (filled circle) with ordered dither."""
    if level <= 0:
        return
    if level >= 16:
        pygame.draw.circle(surface, color, (cx, cy), radius)
        return
    if radius <= 0:
        return

    sw, sh = surface.get_size()
    bayer = _BAYER_4x4
    r2 = radius * radius
    # Clip iteration to the bounding box of the circle, intersected with screen
    x_lo = max(0, cx - radius)
    x_hi = min(sw - 1, cx + radius)
    y_lo = max(0, cy - radius)
    y_hi = min(sh - 1, cy + radius)

    for y in range(y_lo, y_hi + 1):
        dy = y - cy
        dy2 = dy * dy
        row = bayer[y & 3]
        for x in range(x_lo, x_hi + 1):
            dx = x - cx
            if dx * dx + dy2 <= r2:
                if level > row[x & 3]:
                    surface.set_at((x, y), color)


def apply_box_dither(surface: pygame.Surface,
                     x: int, y: int, w: int, h: int,
                     color: int, level: int) -> None:
    """Fill an axis-aligned rectangle with ordered dither."""
    if level <= 0:
        return
    if level >= 16:
        pygame.draw.rect(surface, color, pygame.Rect(x, y, w, h))
        return
    if w <= 0 or h <= 0:
        return

    sw, sh = surface.get_size()
    x_lo = max(0, x)
    y_lo = max(0, y)
    x_hi = min(sw - 1, x + w - 1)
    y_hi = min(sh - 1, y + h - 1)
    if x_lo > x_hi or y_lo > y_hi:
        return

    bayer = _BAYER_4x4
    for sy in range(y_lo, y_hi + 1):
        row = bayer[sy & 3]
        for sx in range(x_lo, x_hi + 1):
            if level > row[sx & 3]:
                surface.set_at((sx, sy), color)
