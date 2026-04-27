"""Tests for the debug panel and its producer wiring.

The panel itself is rendered to a pygame surface; we don't try to
pixel-test the rendering (that's golden-image territory). Instead we
verify:

  - The state object accumulates updates from producers correctly
  - Window sizing changes when the panel is enabled/disabled
  - Producers wire to debug_state through their public APIs (calling
    pdeck.led updates the state, calling audio.get_current_tick marks
    activity, etc.)
  - The reset hook clears debug state alongside framebuffer state

Pixel-level correctness of the panel rendering is deferred to the
golden-image phase we discussed earlier.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import time
import warnings

import pytest

from pdeck_sim import _stubs
_stubs.install_all()

import pdeck
from pdeck_sim.framebuffer import (
    get_framebuffer, SCREEN_W, SCREEN_H, DEBUG_PANEL_W, DIVIDER_W,
)
from pdeck_sim.debug_state import get_debug_state


@pytest.fixture
def fb_fresh(monkeypatch):
    """Reset the framebuffer's mutable state and the debug state.

    Note: we can't recreate the framebuffer instance itself (pygame
    window already initialized), but reset_for_testing() handles
    everything we care about for these tests.
    """
    monkeypatch.delenv("POCKETDECK_DEBUG_PANEL", raising=False)
    fb = get_framebuffer()
    fb.reset_for_testing()
    return fb


# ---------------------------------------------------------------------------
# DebugState basics
# ---------------------------------------------------------------------------

def test_debug_state_singleton():
    """get_debug_state always returns the same instance."""
    a = get_debug_state()
    b = get_debug_state()
    assert a is b

def test_debug_state_initial_values(fb_fresh):
    """A reset state has no LEDs lit, default screen, no audio activity."""
    s = get_debug_state()
    assert s.active_screen == 2
    assert s.led_brightness == [0] * 8
    assert not s.is_audio_active()

def test_note_frame_advances_counter(fb_fresh):
    s = get_debug_state()
    initial = s.frames_rendered
    s.note_frame()
    s.note_frame()
    assert s.frames_rendered == initial + 2

def test_note_frame_computes_fps(fb_fresh):
    s = get_debug_state()
    # Simulate ~60fps by spacing notes 16ms apart
    s.note_frame()
    time.sleep(0.016)
    s.note_frame()
    time.sleep(0.016)
    s.note_frame()
    # FPS should be in the right ballpark — this is a smoothed value so
    # it'll be lower than instant on the first sample
    assert 0 < s.fps_smoothed < 100

def test_audio_active_window():
    """is_audio_active returns True only within ACTIVITY_WINDOW_S."""
    from pdeck_sim.debug_state import reset_debug_state, ACTIVITY_WINDOW_S
    reset_debug_state()
    s = get_debug_state()
    assert not s.is_audio_active()
    s.note_audio_tick()
    assert s.is_audio_active()
    # Manually set the timestamp in the past to simulate stale activity
    s.last_audio_tick = time.monotonic() - ACTIVITY_WINDOW_S - 0.1
    assert not s.is_audio_active()


# ---------------------------------------------------------------------------
# Producer wiring — public APIs update the state
# ---------------------------------------------------------------------------

def test_pdeck_led_updates_state(fb_fresh):
    """Calling pdeck.led(idx, b) reflects in DebugState.led_brightness."""
    pdeck.led(3, 200)
    assert get_debug_state().led_brightness[3] == 200

def test_pdeck_led_clamps_brightness(fb_fresh):
    """Out-of-range brightness values are clamped to 0..255."""
    pdeck.led(0, -50)
    assert get_debug_state().led_brightness[0] == 0
    pdeck.led(0, 999)
    assert get_debug_state().led_brightness[0] == 255

def test_pdeck_led_ignores_invalid_index(fb_fresh):
    """An out-of-range LED index doesn't crash; just no-op."""
    pdeck.led(99, 100)  # only 8 LEDs exist
    # No exception raised; state unchanged
    assert all(b == 0 for b in get_debug_state().led_brightness)

def test_pdeck_change_screen_updates_state(fb_fresh):
    pdeck.change_screen(7)
    assert get_debug_state().active_screen == 7
    pdeck.change_screen(2)  # restore for other tests

def test_audio_get_current_tick_marks_activity(fb_fresh):
    """Calling audio.get_current_tick() should mark audio as active."""
    import audio
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        s = get_debug_state()
        assert not s.is_audio_active()
        audio.get_current_tick()
        assert s.is_audio_active()


# ---------------------------------------------------------------------------
# Framebuffer window sizing with/without panel
# ---------------------------------------------------------------------------

def test_window_width_with_panel_default():
    """Default (no env var) enables the panel: window is wider."""
    fb = get_framebuffer()
    if fb.panel_enabled:
        expected = (SCREEN_W + DIVIDER_W + DEBUG_PANEL_W) * fb.flags.scale
        assert fb.window_width() == expected
    else:
        # If the test process started with POCKETDECK_DEBUG_PANEL=0 in env,
        # the default applies — skip rather than fail
        pytest.skip("framebuffer constructed with panel disabled")

def test_window_width_calculation_correctness():
    """Verify the expected logical-pixel arithmetic regardless of
    which mode the framebuffer happens to be in."""
    fb = get_framebuffer()
    # LCD-only: SCREEN_W * scale
    # With panel: (SCREEN_W + DIVIDER_W + DEBUG_PANEL_W) * scale
    expected_lcd_only = SCREEN_W * fb.flags.scale
    expected_with_panel = (SCREEN_W + DIVIDER_W + DEBUG_PANEL_W) * fb.flags.scale
    assert fb.window_width() in (expected_lcd_only, expected_with_panel)


# ---------------------------------------------------------------------------
# Reset hook
# ---------------------------------------------------------------------------

def test_reset_clears_debug_state():
    """fb.reset_for_testing() must wipe debug state too, otherwise tests
    using LED brightness / screen number / audio activity leak across."""
    pdeck.led(0, 200)
    pdeck.change_screen(9)
    s = get_debug_state()
    # Note the audio tick directly to avoid the warnings dance
    s.note_audio_tick()

    assert s.led_brightness[0] == 200
    assert s.active_screen == 9
    assert s.is_audio_active()

    get_framebuffer().reset_for_testing()

    s = get_debug_state()  # may now be a different instance
    assert s.led_brightness[0] == 0
    assert s.active_screen == 2
    assert not s.is_audio_active()


# ---------------------------------------------------------------------------
# Panel rendering smoke test (does not crash on real surface)
# ---------------------------------------------------------------------------

def test_panel_renders_without_crash():
    """The panel can render arbitrary state into a real pygame surface
    without error. Guards against typos in font calls or color tuples."""
    import pygame
    from pdeck_sim.debug_panel import DebugPanel, PANEL_W, PANEL_H

    panel = DebugPanel()
    surface = pygame.Surface((PANEL_W, PANEL_H))

    # Render with a variety of states to exercise different code paths
    s = get_debug_state()
    s.active_screen = 1
    s.led_brightness = [0] * 8
    s.fps_smoothed = 0.0
    panel.render_to(surface, s)

    s.active_screen = 9
    s.led_brightness = [255, 128, 64, 32, 16, 8, 4, 2]
    s.fps_smoothed = 60.0
    s.frames_rendered = 99999
    s.note_audio_tick()
    panel.render_to(surface, s)
