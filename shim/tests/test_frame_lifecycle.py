"""Tests for the auto-clear and skip-update behaviors.

The shim should mirror the deck's behavior: buffer 0 is implicitly cleared
before each frame's first draw, and if a callback calls finished() without
drawing, no clear and no present happens (LCD holds its last frame).
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

from pdeck_sim import _stubs
_stubs.install_all()

import pdeck
from pdeck_sim.framebuffer import get_framebuffer


def is_fg(surface, x, y):
    return surface.get_at_mapped((x, y)) == 1

def is_bg(surface, x, y):
    return surface.get_at_mapped((x, y)) == 0


@pytest.fixture
def v():
    fb = get_framebuffer()
    fb.reset_for_testing()
    v = pdeck.vscreen(2)
    v._draw_color = 1
    v._drew_this_frame = False
    return v


# ---------------------------------------------------------------------------
# Auto-clear of buffer 0
# ---------------------------------------------------------------------------

def test_first_draw_of_frame_clears_buffer_0(v):
    """Previous frame's pixels are erased before the new frame's first draw."""
    # Simulate previous frame: draw something.
    v._begin_frame()
    v.draw_box(0, 0, 50, 50)
    assert is_fg(v.fb.buffers[0], 10, 10)

    # Now simulate the next frame: begin, then draw somewhere ELSE.
    v._begin_frame()
    v.draw_box(100, 100, 30, 30)

    # The old box at (10, 10) should be gone — auto-cleared.
    assert is_bg(v.fb.buffers[0], 10, 10)
    # The new box at (110, 110) should be visible.
    assert is_fg(v.fb.buffers[0], 110, 110)

def test_multiple_draws_in_same_frame_do_not_reclear(v):
    """Only the FIRST draw of a frame triggers the clear."""
    v._begin_frame()
    v.draw_box(0, 0, 50, 50)
    v.draw_box(100, 100, 30, 30)
    # Both boxes should be present.
    assert is_fg(v.fb.buffers[0], 10, 10)
    assert is_fg(v.fb.buffers[0], 110, 110)

def test_buffer_1_is_not_auto_cleared(v):
    """Buffer 1 is user scratch and should persist across frames."""
    # Draw on buffer 1.
    v._begin_frame()
    v.switch_buffer(1)
    v.draw_box(0, 0, 50, 50)
    v.switch_buffer(0)  # switch back so next frame's draw targets buffer 0

    # Next frame.
    v._begin_frame()
    v.draw_box(200, 0, 10, 10)  # draw something on buffer 0 to trigger its clear

    # Buffer 1 should still have its contents.
    assert is_fg(v.fb.buffers[1], 10, 10)

def test_explicit_clear_buffer_marks_frame_drawn(v):
    """Calling clear_buffer() explicitly should count as drawing."""
    v._begin_frame()
    assert not v._drew_this_frame
    v.clear_buffer()
    assert v._drew_this_frame


# ---------------------------------------------------------------------------
# Skip-update: finished() with no drawing
# ---------------------------------------------------------------------------

def test_finished_without_drawing_leaves_frame_clean(v):
    """If a frame begins and finished() is called with no draws between,
    _drew_this_frame stays False — the signal the runner uses to skip
    present()."""
    v._begin_frame()
    v.finished()
    assert not v._drew_this_frame

def test_finished_after_drawing_keeps_frame_marked(v):
    """After drawing + finished(), the frame is still marked so the runner
    knows to present. _begin_frame() resets for the next frame."""
    v._begin_frame()
    v.draw_pixel(1, 1)
    assert v._drew_this_frame
    v.finished()
    assert v._drew_this_frame  # NOT cleared by finished

def test_begin_frame_resets_drew_flag(v):
    """_begin_frame is the thing that arms a new frame."""
    v._begin_frame()
    v.draw_pixel(1, 1)
    assert v._drew_this_frame
    v._begin_frame()
    assert not v._drew_this_frame

def test_skip_update_preserves_previous_frame_pixels(v):
    """If frame N drew, and frame N+1 is a skip-update, frame N's pixels
    stay visible in buffer 0. This is the LCD-holds-last-frame behavior."""
    # Frame N: draw a box.
    v._begin_frame()
    v.draw_box(10, 10, 30, 30)
    v.finished()
    assert is_fg(v.fb.buffers[0], 20, 20)

    # Frame N+1: skip-update (no draws between begin and finished).
    v._begin_frame()
    v.finished()

    # Box from frame N should still be there.
    assert is_fg(v.fb.buffers[0], 20, 20)


# ---------------------------------------------------------------------------
# Interaction with bouncing_box-style apps
# ---------------------------------------------------------------------------

def test_repeated_frames_no_smearing(v):
    """Simulates what happens when an app draws a moving object without
    explicit clear_buffer(). The auto-clear should keep each frame's
    presentation clean."""
    for frame_i in range(5):
        v._begin_frame()
        # Object at position frame_i * 20
        x = frame_i * 20
        v.draw_box(x, 50, 10, 10)
        v.finished()

    # Only the final frame's box should be visible.
    # First four positions should be background.
    for i in range(4):
        x = i * 20
        assert is_bg(v.fb.buffers[0], x + 5, 55), (
            f"frame {i}'s box at x={x} should have been cleared"
        )
    # The fifth frame (x=80) should be visible.
    assert is_fg(v.fb.buffers[0], 85, 55)
