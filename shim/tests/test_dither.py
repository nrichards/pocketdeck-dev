"""Tests for ordered-Bayer dither in vscreen.

Verifies:
- Level 0 draws nothing
- Level 16 draws a fully-solid shape (fast path)
- Intermediate levels draw a fraction of pixels roughly matching level/16
- The pattern is stable (same shape at same position gives same pixels)
- The pattern is screen-aligned (the Bayer matrix is applied to absolute
  screen coords, so a polygon at (10,10) and a polygon at (50,50) covering
  the same pixels in absolute terms have the same dither output)
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

from pdeck_sim import _stubs
_stubs.install_all()

import pdeck


# Helpers from the existing primitives test file
def is_fg(surface, x, y):
    return surface.get_at_mapped((x, y)) == 1

def is_bg(surface, x, y):
    return surface.get_at_mapped((x, y)) == 0


@pytest.fixture
def v():
    """A fresh vscreen with cleared buffer."""
    fb = pdeck.vscreen(2)
    fb.fb.reset_for_testing()
    return fb


def _count_fg(surface, x, y, w, h):
    """Count foreground pixels in a region."""
    n = 0
    for sy in range(y, y + h):
        for sx in range(x, x + w):
            if surface.get_at_mapped((sx, sy)) == 1:
                n += 1
    return n


# ---------------------------------------------------------------------------
# Box dither
# ---------------------------------------------------------------------------

def test_box_dither_level_0_draws_nothing(v):
    """Dither 0 = empty; no foreground pixels appear."""
    v.set_dither(0)
    v.set_draw_color(1)
    v.draw_box(10, 10, 40, 40)
    assert _count_fg(v.fb.buffers[0], 10, 10, 40, 40) == 0

def test_box_dither_level_16_fully_solid(v):
    """Dither 16 = solid; every pixel in the rectangle is foreground."""
    v.set_dither(16)
    v.set_draw_color(1)
    v.draw_box(10, 10, 40, 40)
    assert _count_fg(v.fb.buffers[0], 10, 10, 40, 40) == 40 * 40

def test_box_dither_level_8_about_half(v):
    """Dither 8 should fill roughly half the pixels (8/16 = 50%).

    With 4x4 ordered Bayer, level 8 hits exactly 8 of 16 thresholds, so
    the count is exact, not statistical: a 40x40 box (1600 pixels)
    should give exactly 800 foreground pixels.
    """
    v.set_dither(8)
    v.set_draw_color(1)
    v.draw_box(10, 10, 40, 40)
    count = _count_fg(v.fb.buffers[0], 10, 10, 40, 40)
    assert count == 800, f"Expected 800/1600 foreground at level 8, got {count}"

def test_box_dither_level_4_about_quarter(v):
    """Dither 4 = 4/16 = 25%."""
    v.set_dither(4)
    v.set_draw_color(1)
    v.draw_box(10, 10, 40, 40)
    count = _count_fg(v.fb.buffers[0], 10, 10, 40, 40)
    assert count == 400, f"Expected 400/1600 at level 4, got {count}"

def test_box_dither_level_12_about_three_quarters(v):
    v.set_dither(12)
    v.set_draw_color(1)
    v.draw_box(10, 10, 40, 40)
    count = _count_fg(v.fb.buffers[0], 10, 10, 40, 40)
    assert count == 1200, f"Expected 1200/1600 at level 12, got {count}"

def test_box_dither_levels_monotonic(v):
    """Higher dither level always produces >= pixels than lower."""
    counts = []
    for level in range(17):
        v.fb.reset_for_testing()
        v.set_dither(level)
        v.set_draw_color(1)
        v.draw_box(10, 10, 40, 40)
        counts.append(_count_fg(v.fb.buffers[0], 10, 10, 40, 40))
    # Each level should give equal or more pixels than the prior
    for i in range(1, len(counts)):
        assert counts[i] >= counts[i-1], \
            f"Level {i} ({counts[i]}) < level {i-1} ({counts[i-1]})"
    # And there should be variety — not just 0s and 1600s
    assert 0 < counts[8] < 1600


# ---------------------------------------------------------------------------
# Pattern stability and screen alignment
# ---------------------------------------------------------------------------

def test_dither_pattern_stable_across_redraws(v):
    """Drawing the same box twice gives identical pixel patterns."""
    v.set_dither(8)
    v.set_draw_color(1)
    v.draw_box(10, 10, 16, 16)
    snapshot1 = [(x, y, v.fb.buffers[0].get_at_mapped((x, y)))
                 for y in range(10, 26) for x in range(10, 26)]

    v.fb.reset_for_testing()
    v.set_dither(8)
    v.set_draw_color(1)
    v.draw_box(10, 10, 16, 16)
    snapshot2 = [(x, y, v.fb.buffers[0].get_at_mapped((x, y)))
                 for y in range(10, 26) for x in range(10, 26)]

    assert snapshot1 == snapshot2

def test_dither_screen_aligned_not_shape_aligned(v):
    """The Bayer pattern is anchored to absolute screen coordinates.
    Two boxes at different positions but covering pixels at coordinates
    differing by multiples of 4 should have identical patterns at those
    aligned pixels."""
    v.set_dither(8)
    v.set_draw_color(1)
    v.draw_box(0, 0, 8, 8)
    pat_a = [v.fb.buffers[0].get_at_mapped((x, y))
             for y in range(8) for x in range(8)]

    v.fb.reset_for_testing()
    v.set_dither(8)
    v.set_draw_color(1)
    v.draw_box(40, 40, 8, 8)  # offset by 40 on both axes (multiple of 4)
    pat_b = [v.fb.buffers[0].get_at_mapped((40 + x, 40 + y))
             for y in range(8) for x in range(8)]

    # Patterns should be identical because both shapes are aligned to the
    # 4x4 Bayer grid in the same way (40 % 4 == 0)
    assert pat_a == pat_b


# ---------------------------------------------------------------------------
# Polygon dither (the cube_test path)
# ---------------------------------------------------------------------------

def test_polygon_dither_level_0_draws_nothing(v):
    v.set_dither(0)
    v.set_draw_color(1)
    # A triangle covering ~half a 40x40 region
    v.draw_polygon([10, 50, 50, 10, 50, 10])  # x1,x2,x3,y1,y2,y3
    assert _count_fg(v.fb.buffers[0], 0, 0, 100, 100) == 0

def test_polygon_dither_level_16_solid(v):
    v.set_dither(16)
    v.set_draw_color(1)
    # Rectangle expressed as two triangles via polygon
    v.draw_polygon([10, 50, 50, 10, 10, 10, 50, 50])  # triangle (10,10)-(50,10)-(50,50)
    # At least some pixels should be drawn
    assert _count_fg(v.fb.buffers[0], 10, 10, 41, 41) > 100

def test_polygon_dither_intermediate_partial_fill(v):
    """A triangle drawn at dither 8 should have roughly half its pixels
    set. We can't easily count the exact triangle area, but we can
    compare against the same triangle at dither 16."""
    v.set_dither(16)
    v.set_draw_color(1)
    v.draw_polygon([10, 50, 50, 10, 10, 10, 50, 50])
    full_count = _count_fg(v.fb.buffers[0], 0, 0, 100, 100)

    v.fb.reset_for_testing()
    v.set_dither(8)
    v.set_draw_color(1)
    v.draw_polygon([10, 50, 50, 10, 10, 10, 50, 50])
    half_count = _count_fg(v.fb.buffers[0], 0, 0, 100, 100)

    # Half should be roughly half of full. Allow generous slack because
    # the triangle's edge pixels and the Bayer pattern interact.
    assert 0.4 * full_count < half_count < 0.6 * full_count, \
        f"At level 8, expected ~50% of {full_count}, got {half_count}"


# ---------------------------------------------------------------------------
# Disc dither
# ---------------------------------------------------------------------------

def test_disc_dither_level_0_draws_nothing(v):
    v.set_dither(0)
    v.set_draw_color(1)
    v.draw_disc(50, 50, 20)
    assert _count_fg(v.fb.buffers[0], 0, 0, 100, 100) == 0

def test_disc_dither_level_16_solid(v):
    v.set_dither(16)
    v.set_draw_color(1)
    v.draw_disc(50, 50, 20)
    # A disc of radius 20 should have ~pi*20^2 = ~1256 pixels filled
    count = _count_fg(v.fb.buffers[0], 0, 0, 100, 100)
    assert 1100 < count < 1400

def test_disc_dither_level_8_partial(v):
    v.set_dither(16)
    v.set_draw_color(1)
    v.draw_disc(50, 50, 20)
    full = _count_fg(v.fb.buffers[0], 0, 0, 100, 100)

    v.fb.reset_for_testing()
    v.set_dither(8)
    v.set_draw_color(1)
    v.draw_disc(50, 50, 20)
    half = _count_fg(v.fb.buffers[0], 0, 0, 100, 100)

    assert 0.4 * full < half < 0.6 * full


# ---------------------------------------------------------------------------
# Frame and other unaffected primitives still work
# ---------------------------------------------------------------------------

def test_frame_unaffected_by_dither(v):
    """Frames are outlines; we don't dither them. They should look the
    same regardless of set_dither value."""
    v.set_dither(4)
    v.set_draw_color(1)
    v.draw_frame(10, 10, 30, 30)
    # The four corners should be foreground regardless of dither
    assert is_fg(v.fb.buffers[0], 10, 10)
    assert is_fg(v.fb.buffers[0], 39, 10)
    assert is_fg(v.fb.buffers[0], 10, 39)
    assert is_fg(v.fb.buffers[0], 39, 39)
