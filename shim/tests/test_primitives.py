"""Unit tests for the pdeck_sim shim.

Run with: SDL_VIDEODRIVER=dummy pytest

The SDL dummy driver is required because the shim's Framebuffer opens a
pygame window at import time, and CI / headless runs don't have a display.

Tests share a module-level Framebuffer singleton. The `v` fixture calls
`fb.reset_for_testing()` to wipe state between tests — without this,
writes leak and assertions fight each other.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

from pdeck_sim import _stubs
_stubs.install_all()

import pdeck
from pdeck_sim.framebuffer import get_framebuffer, SCREEN_W, SCREEN_H
from pdeck_sim.xbm_render import blit_xbm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
# We use get_at_mapped to read the raw palette index (0 or 1) rather than
# get_at()[0] which resolves to an RGB tuple. get_at_mapped mirrors exactly
# what the draw primitives wrote.

def is_fg(surface, x, y):
    return surface.get_at_mapped((x, y)) == 1

def is_bg(surface, x, y):
    return surface.get_at_mapped((x, y)) == 0


@pytest.fixture
def v():
    """Fresh vscreen with clean state for each test."""
    fb = get_framebuffer()
    fb.reset_for_testing()
    v = pdeck.vscreen(2)
    # Vscreen holds draw state too; the reset above only handles
    # framebuffer-level data. Reset vscreen-level state explicitly.
    v._draw_color = 1
    v._font_mode = 0
    v._bitmap_mode = 0
    v._dither = 16
    v._callback = None
    return v


# ---------------------------------------------------------------------------
# Basic primitives (the ones from round one, now with correct assertions)
# ---------------------------------------------------------------------------

def test_draw_pixel_sets_foreground(v):
    v.draw_pixel(10, 10)
    assert is_fg(v.fb.buffers[0], 10, 10)

def test_draw_pixel_out_of_bounds_is_noop(v):
    v.draw_pixel(-5, 10)
    v.draw_pixel(10, 9999)
    v.draw_pixel(99999, 99999)

def test_draw_box_fills_interior(v):
    v.draw_box(10, 10, 20, 20)
    assert is_fg(v.fb.buffers[0], 20, 20)
    assert is_bg(v.fb.buffers[0], 100, 100)

def test_draw_frame_is_hollow(v):
    """draw_frame is outline only — interior should stay empty."""
    v.draw_frame(50, 50, 40, 40)
    # Corner of frame should be foreground
    assert is_fg(v.fb.buffers[0], 50, 50)
    # Interior should be background
    assert is_bg(v.fb.buffers[0], 70, 70)

def test_set_draw_color_zero_erases(v):
    v.draw_box(10, 10, 20, 20)
    assert is_fg(v.fb.buffers[0], 15, 15)
    v.set_draw_color(0)
    v.draw_box(12, 12, 10, 10)
    assert is_bg(v.fb.buffers[0], 15, 15)
    assert is_fg(v.fb.buffers[0], 28, 28)

def test_clear_buffer_empties(v):
    v.draw_box(0, 0, 400, 240)
    v.clear_buffer()
    assert is_bg(v.fb.buffers[0], 100, 100)

def test_buffer_switching_isolates_writes(v):
    v.switch_buffer(1)
    v.draw_box(0, 0, 50, 50)
    v.switch_buffer(0)
    assert is_bg(v.fb.buffers[0], 10, 10)
    assert is_fg(v.fb.buffers[1], 10, 10)

def test_copy_buffer_moves_pixels(v):
    v.switch_buffer(1)
    v.draw_pixel(5, 5)
    v.switch_buffer(0)
    v.copy_buffer(0, 1)  # copy from buffer 1 into buffer 0
    assert is_fg(v.fb.buffers[0], 5, 5)


# ---------------------------------------------------------------------------
# Line / h-line / v-line
# ---------------------------------------------------------------------------

def test_draw_h_line_horizontal_only(v):
    v.draw_h_line(10, 50, 20)
    # Pixels along the line
    for x in range(10, 30):
        assert is_fg(v.fb.buffers[0], x, 50), f"pixel ({x}, 50) should be fg"
    # Pixels above and below — should be background
    assert is_bg(v.fb.buffers[0], 15, 49)
    assert is_bg(v.fb.buffers[0], 15, 51)

def test_draw_v_line_vertical_only(v):
    v.draw_v_line(100, 30, 15)
    for y in range(30, 45):
        assert is_fg(v.fb.buffers[0], 100, y), f"pixel (100, {y}) should be fg"
    assert is_bg(v.fb.buffers[0], 99, 35)
    assert is_bg(v.fb.buffers[0], 101, 35)


# ---------------------------------------------------------------------------
# XBM rendering — highest-risk bit-manipulation code
# ---------------------------------------------------------------------------

def test_xbm_blit_single_byte_pattern(v):
    """An 8x1 bitmap with pattern 0b10000000 should set pixel 0 only.

    The deck uses MSB-first packing: bit 7 of each byte is the leftmost
    pixel. (Standard XBM is LSB-first, but the deck's xbmreader bit-
    reverses at parse time so the blitter sees MSB-first uniformly.)
    """
    data = bytes([0b10000000])
    blit_xbm(v.fb.buffers[0], 0, 0, 8, 1, data, color=1, transparent=True)
    assert is_fg(v.fb.buffers[0], 0, 0)
    for x in range(1, 8):
        assert is_bg(v.fb.buffers[0], x, 0), f"pixel {x} should be bg"

def test_xbm_blit_msb_pattern(v):
    """0b00000001 should set pixel 7 only (MSB-first means bit 0 = rightmost pixel)."""
    data = bytes([0b00000001])
    blit_xbm(v.fb.buffers[0], 0, 0, 8, 1, data, color=1, transparent=True)
    for x in range(0, 7):
        assert is_bg(v.fb.buffers[0], x, 0), f"pixel {x} should be bg"
    assert is_fg(v.fb.buffers[0], 7, 0)

def test_xbm_blit_row_padding(v):
    """A 9-pixel-wide image needs 2 bytes per row (stride = (9+7)//8 = 2).

    With MSB-first, pixel 8 is bit 7 of the second byte = 0x80.
    """
    # Row 0: first byte all-set (pixels 0-7), second byte 0x80 (pixel 8)
    # Row 1: blank row for comparison
    data = bytes([0xFF, 0x80,  # row 0
                  0x00, 0x00])  # row 1
    blit_xbm(v.fb.buffers[0], 0, 0, 9, 2, data, color=1, transparent=True)
    for x in range(9):
        assert is_fg(v.fb.buffers[0], x, 0), f"row 0 pixel {x} should be fg"
    for x in range(9):
        assert is_bg(v.fb.buffers[0], x, 1), f"row 1 pixel {x} should be bg"

def test_xbm_blit_offset(v):
    """Blit with nonzero x/y offset."""
    data = bytes([0xFF])  # 8 pixels all set
    blit_xbm(v.fb.buffers[0], 100, 50, 8, 1, data, color=1, transparent=True)
    for x in range(100, 108):
        assert is_fg(v.fb.buffers[0], x, 50)
    # Verify it's exactly 8 wide
    assert is_bg(v.fb.buffers[0], 99, 50)
    assert is_bg(v.fb.buffers[0], 108, 50)

def test_xbm_blit_clipping_left(v):
    """Blit partly off-screen to the left — no crash, visible pixels correct."""
    data = bytes([0xFF])
    blit_xbm(v.fb.buffers[0], -4, 10, 8, 1, data, color=1, transparent=True)
    # Only x=0..3 should be visible (pixels 4-7 of the bitmap)
    for x in range(0, 4):
        assert is_fg(v.fb.buffers[0], x, 10)

def test_xbm_blit_transparent_vs_solid(v):
    """Transparent mode leaves background alone for 0-bits; solid mode plots bg."""
    # Pre-fill buffer with foreground
    v.draw_box(0, 0, 20, 10)
    # Now blit a pattern with transparent=False; 0-bits should erase.
    # MSB-first: 0b10000000 = pixel 0 only
    data = bytes([0b10000000])
    blit_xbm(v.fb.buffers[0], 0, 0, 8, 1, data, color=1, transparent=False)
    # Pixel 0 still foreground (from the bitmap)
    assert is_fg(v.fb.buffers[0], 0, 0)
    # Pixel 5 should now be bg (erased by 0-bit in solid mode)
    assert is_bg(v.fb.buffers[0], 5, 0)
    # Pixel below the bitmap should still be fg (untouched)
    assert is_fg(v.fb.buffers[0], 5, 5)


# ---------------------------------------------------------------------------
# xbmreader stub — parses XBM text files
# ---------------------------------------------------------------------------

def test_xbmreader_parses_basic_xbm(tmp_path):
    """Hand-written XBM file parses and bit-reverses to MSB-first.

    Standard XBM is LSB-first on disk. The deck (and the shim's
    fallback) bit-reverse each byte at parse time so the blitter sees
    MSB-first uniformly. So 0xFF stays 0xFF (palindromic), 0x00 stays
    0x00, but a non-palindromic byte like 0x01 becomes 0x80.
    """
    xbm_text = """#define test_width 8
#define test_height 2
static char test_bits[] = {
  0xFF, 0x00 };
"""
    p = tmp_path / "test.xbm"
    p.write_text(xbm_text)

    import xbmreader
    name, w, h, data, frames = xbmreader.read(str(p))
    assert name == "test"
    assert w == 8
    assert h == 2
    # 0xFF and 0x00 are palindromic — bit-reversal is a no-op for these
    assert data == bytes([0xFF, 0x00])
    assert frames == 1

def test_xbmreader_bit_reverses_non_palindromic(tmp_path):
    """Verify the bit-reversal explicitly with a non-palindromic byte.

    0x81 = 0b10000001 reversed = 0b10000001 (also palindromic — try 0x01)
    0x01 = 0b00000001 reversed = 0b10000000 = 0x80
    """
    xbm_text = """#define test_width 8
#define test_height 1
static char test_bits[] = { 0x01 };
"""
    p = tmp_path / "rev.xbm"
    p.write_text(xbm_text)

    import xbmreader
    name, w, h, data, frames = xbmreader.read(str(p))
    # 0x01 (LSB-first source) -> 0x80 (MSB-first deck convention)
    assert data == bytes([0x80])

def test_xbmreader_scale_doubles_image():
    """Scale factor 2 produces 2x width, 2x height, same pattern doubled."""
    import xbmreader
    # 8x1 image, single byte 0xFF = all pixels set
    img = ("tiny", 8, 1, bytes([0xFF]), 1)
    scaled = xbmreader.scale(img, 2)
    name, w, h, data, frames = scaled
    assert w == 16
    assert h == 2
    # stride = (16+7)//8 = 2, so 2 bytes per row, 2 rows = 4 bytes total
    assert len(data) == 4
    # All bits should be set
    assert data == bytes([0xFF, 0xFF, 0xFF, 0xFF])

def test_xbmreader_scale_factor_one_is_identity():
    import xbmreader
    img = ("tiny", 4, 1, bytes([0x0F]), 1)
    assert xbmreader.scale(img, 1) == img


# ---------------------------------------------------------------------------
# Input system
# ---------------------------------------------------------------------------

def test_input_queue_roundtrip(v):
    v.send_char("hello")
    n, data = v.read_nb(10)
    assert n == 5
    assert data == b"hello"

def test_poll_reflects_queue(v):
    assert not v.poll()
    v.send_char("x")
    assert v.poll()
    v.read_nb(1)
    assert not v.poll()

def test_read_nb_partial(v):
    """Reading fewer bytes than queued leaves the rest for next call."""
    v.send_char("abcde")
    n1, d1 = v.read_nb(3)
    assert n1 == 3
    assert d1 == b"abc"
    n2, d2 = v.read_nb(10)
    assert n2 == 2
    assert d2 == b"de"

def test_read_nb_empty_queue(v):
    n, data = v.read_nb(5)
    assert n == 0
    assert data == b""

def test_key_state_via_send_key_event(v):
    # send_key_event(key, modifier, event_type): event_type 1 = press
    v.send_key_event(42, 0, 1)
    assert v.get_key_state(42)
    v.send_key_event(42, 0, 0)  # release
    assert not v.get_key_state(42)

def test_get_tp_keys_returns_seven_bytes(v):
    """Touchpad stub returns 7 bytes with unpressed sentinels."""
    tp = v.get_tp_keys()
    assert len(tp) == 7
    # Slider, touchpad-y, touchpad-x should be 0xFF when unpressed
    assert tp[0] == 0xFF
    assert tp[1] == 0xFF
    assert tp[2] == 0xFF


# ---------------------------------------------------------------------------
# pdeck module surface
# ---------------------------------------------------------------------------

def test_screen_size_matches_device():
    assert pdeck.get_screen_size() == (400, 240)

def test_change_screen_updates_current():
    pdeck.change_screen(5)
    assert pdeck.get_screen_num() == 5
    pdeck.change_screen(2)  # restore
    assert pdeck.get_screen_num() == 2

def test_screen_invert_toggle():
    assert pdeck.screen_invert() is False
    pdeck.screen_invert(True)
    assert pdeck.screen_invert() is True
    pdeck.screen_invert(False)
    assert pdeck.screen_invert() is False

def test_rtc_returns_seven_tuple():
    """RTC should return (year, month, day, weekday, hour, minute, second)."""
    t = pdeck.rtc()
    assert len(t) == 7
    year, month, day, weekday, hour, minute, second = t
    assert year >= 2024
    assert 1 <= month <= 12
    assert 1 <= day <= 31
    assert 1 <= weekday <= 7
    assert 0 <= hour <= 23
    assert 0 <= minute <= 59
    assert 0 <= second <= 60  # leap second

def test_terminal_font_size_roundtrip():
    pdeck.set_default_terminal_font_size(16)
    assert pdeck.get_default_terminal_font_size() == 16
    pdeck.set_default_terminal_font_size(12)  # restore


# ---------------------------------------------------------------------------
# Font / text metrics
# ---------------------------------------------------------------------------

def test_get_str_width_scales_with_length(v):
    v.set_font("u8g2_font_profont15_mf")
    w1 = v.get_str_width("x")
    w3 = v.get_str_width("xxx")
    assert w3 > w1
    # Roughly 3x — monospace font, so should be very close to exact
    assert 2.5 * w1 <= w3 <= 3.5 * w1

def test_get_str_width_empty_is_zero(v):
    assert v.get_str_width("") == 0

def test_draw_str_produces_pixels(v):
    """After drawing text, at least some pixels in the text region should be set."""
    v.set_font("u8g2_font_profont22_mf")
    v.draw_str(10, 30, "A")
    # Look in the bounding box around the letter for any foreground pixel
    found = False
    for x in range(10, 30):
        for y in range(10, 35):
            if is_fg(v.fb.buffers[0], x, y):
                found = True
                break
        if found:
            break
    assert found, "draw_str should have plotted some pixels"


# ---------------------------------------------------------------------------
# Callback system
# ---------------------------------------------------------------------------

def test_callback_registration(v):
    assert not v.callback_exists()
    def handler(e): pass
    v.callback(handler)
    assert v.callback_exists()
    v.callback(None)
    assert not v.callback_exists()


# ---------------------------------------------------------------------------
# Clipboard (via fake_pdeck)
# ---------------------------------------------------------------------------

def test_clipboard_copy_paste_roundtrip():
    """Clipboard should round-trip a string through pyperclip."""
    try:
        pdeck.clipboard_copy("pocket deck test")
        result = pdeck.clipboard_paste()
        # On CI without a real clipboard pyperclip may return "" — skip in
        # that case rather than failing
        if result == "":
            pytest.skip("no system clipboard available")
        assert result == "pocket deck test"
    except Exception:
        pytest.skip("pyperclip not functional in this environment")


# ---------------------------------------------------------------------------
# Stub modules sanity
# ---------------------------------------------------------------------------

def test_esclib_escape_codes():
    """esclib should produce the standard ANSI escape sequences."""
    import esclib
    el = esclib.esclib()
    assert el.erase_screen() == "\x1b[2J"
    assert el.home() == "\x1b[H"
    # display_mode(True) shows cursor, False hides
    assert "h" in el.display_mode(True)
    assert "l" in el.display_mode(False)

def test_esclib_unknown_method_returns_empty():
    """Any unrecognized method returns a function producing empty string —
    prevents crashes when apps call obscure escape helpers."""
    import esclib
    el = esclib.esclib()
    assert el.some_random_method("arg") == ""

def test_pdeck_utils_reimport_reloads_module(tmp_path, monkeypatch):
    """pdeck_utils.reimport should force-reload a module from disk.

    NOTE: this test rewrites a source file in rapid succession. Python's
    bytecode cache uses second-granularity mtime checks, so we explicitly
    bump the mtime forward to simulate real-world editing timescales.
    In normal dev use (a human typing), this is never an issue.
    """
    import os
    import time

    mod_file = tmp_path / "tempmod.py"
    mod_file.write_text("VALUE = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    import pdeck_utils
    m1 = pdeck_utils.reimport("tempmod")
    assert m1.VALUE == 1

    # Rewrite the file and bump mtime so Python's bytecode cache
    # recognizes the source as changed.
    mod_file.write_text("VALUE = 2\n")
    future = time.time() + 2
    os.utime(mod_file, (future, future))

    m2 = pdeck_utils.reimport("tempmod")
    assert m2.VALUE == 2


# ---------------------------------------------------------------------------
# Framebuffer reset smoke test — meta-test for the fixture's cleanup
# ---------------------------------------------------------------------------

def test_reset_clears_both_buffers(v):
    v.switch_buffer(0); v.draw_box(0, 0, 50, 50)
    v.switch_buffer(1); v.draw_box(0, 0, 50, 50)
    v.fb.reset_for_testing()
    assert is_bg(v.fb.buffers[0], 10, 10)
    assert is_bg(v.fb.buffers[1], 10, 10)

def test_reset_clears_input_queue(v):
    v.send_char("garbage")
    v.fb.reset_for_testing()
    assert not v.poll()
