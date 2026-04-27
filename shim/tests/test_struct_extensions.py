"""Tests for the MicroPython struct module extension.

CPython requires struct.unpack(fmt, buf) to have len(buf) == calcsize(fmt)
exactly. MicroPython is lenient — extra bytes are silently ignored. The
deck's xbmreader.read_xbmr relies on this leniency: it passes the entire
file content to struct.unpack with an 8-byte format. The shim matches
MicroPython by truncating oversized buffers before delegating.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import struct

import pytest

from pdeck_sim import _stubs
_stubs.install_all()


def test_unpack_accepts_oversized_buffer():
    """The motivating case: deck code does struct.unpack on a buffer
    larger than the format requires."""
    # Pack 4 int16s = 8 bytes, append extra data
    raw = struct.pack("<hhhh", 1, 2, 3, 4) + b"extra padding bytes"
    # Real CPython would raise here. After our patch, it should work.
    result = struct.unpack("<hhhh", raw)
    assert result == (1, 2, 3, 4)

def test_unpack_exact_size_still_works():
    """The common case isn't broken by the patch."""
    raw = struct.pack("<hh", 100, 200)
    result = struct.unpack("<hh", raw)
    assert result == (100, 200)

def test_unpack_undersized_buffer_still_raises():
    """Buffers that are TOO SMALL should still error — that's a real bug
    in either CPython or MicroPython, and we shouldn't mask it."""
    too_short = b"\x01\x02"  # only 2 bytes, format wants 8
    with pytest.raises(struct.error):
        struct.unpack("<hhhh", too_short)

def test_xbmr_style_usage():
    """End-to-end: replicate the exact xbmreader.read_xbmr pattern that
    motivated the patch."""
    # XBMR header: <hhhh = reserved, num_frames, width, height, then data
    fake_xbmr = struct.pack("<hhhh", 0, 1, 8, 16) + b"\xff" * 16  # 8x16 = 16 bytes
    header = struct.unpack("<hhhh", fake_xbmr)
    assert header == (0, 1, 8, 16)
    # The deck code then slices to get the data portion via memoryview[8:]
    data = memoryview(fake_xbmr)[8:]
    assert len(data) == 16

def test_patch_is_idempotent():
    """Multiple install_all() calls don't double-wrap."""
    _stubs.install_all()
    _stubs.install_all()
    # Should still work after re-install
    raw = struct.pack("<hh", 1, 2) + b"extra"
    assert struct.unpack("<hh", raw) == (1, 2)
