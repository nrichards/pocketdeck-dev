"""Tests for re_test and dsplib stubs.

re_test is opaque; we only verify it imports without crashing.
dsplib's matrix multiplication has math-correct implementations, so we
test those against hand-computed expected values. The 3D-projection
stubs are no-ops; we verify they don't crash but don't check output.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import array

import pytest

from pdeck_sim import _stubs
_stubs.install_all()


# ---------------------------------------------------------------------------
# re_test — opaque stub
# ---------------------------------------------------------------------------

def test_re_test_imports():
    """The whole point: just import succeeds."""
    import re_test
    assert re_test is not None

def test_re_test_attribute_access_no_crash():
    """If a future example accesses re_test.something, it returns a
    no-op rather than raising."""
    import re_test
    # Anything we access shouldn't crash
    obj = re_test.some_arbitrary_name
    # Anything we call on what we got back also shouldn't crash
    obj.do_thing("arg", kwarg=42)
    obj()


# ---------------------------------------------------------------------------
# dsplib.matrix_mul_f32
# ---------------------------------------------------------------------------

def test_matrix_mul_f32_2x2_identity():
    """Multiplying by identity returns the original matrix."""
    import dsplib
    A = array.array('f', [1.0, 0.0, 0.0, 1.0])  # 2x2 identity
    B = array.array('f', [3.0, 4.0, 5.0, 6.0])  # arbitrary 2x2
    C = array.array('f', [0.0] * 4)
    dsplib.matrix_mul_f32(A, B, 2, 2, 2, C)
    # I*B = B
    assert list(C) == pytest.approx([3.0, 4.0, 5.0, 6.0])

def test_matrix_mul_f32_2x2_rotation():
    """A 90-degree rotation matrix applied to point (1, 0) gives (0, 1).

    This is the actual operation dither_test.py is doing — rotating
    points by an angle. If this works, the example's geometry rotates
    correctly."""
    import dsplib
    # 90-deg rotation: cos=0, -sin=-1, sin=1, cos=0
    rot = array.array('f', [0.0, -1.0, 1.0, 0.0])
    # Single point as 2x1 column: x=1, y=0
    pt = array.array('f', [1.0, 0.0])
    out = array.array('f', [0.0, 0.0])
    dsplib.matrix_mul_f32(rot, pt, 2, 2, 1, out)
    # Expected: (0, 1)
    assert out[0] == pytest.approx(0.0, abs=1e-6)
    assert out[1] == pytest.approx(1.0, abs=1e-6)

def test_matrix_mul_f32_returns_new_array_when_no_C():
    """If the caller doesn't provide C, allocate and return one. This
    mirrors the deck's API."""
    import dsplib
    A = array.array('f', [1.0, 2.0, 3.0, 4.0])
    B = array.array('f', [5.0, 6.0, 7.0, 8.0])
    result = dsplib.matrix_mul_f32(A, B, 2, 2, 2)
    assert result is not None
    assert len(result) == 4


# ---------------------------------------------------------------------------
# dsplib.matrix_mul_s16
# ---------------------------------------------------------------------------

def test_matrix_mul_s16_basic():
    """Fixed-point multiply with shift — verify by hand calc.

    A = [[2, 0], [0, 2]] (in shifted form: [[128, 0], [0, 128]] with shift=6)
    B = [[100], [100]]
    Expected: [[2*100], [2*100]] = [[200], [200]] after shift
    """
    import dsplib
    # 6-bit shift → multiplier 64 represents 1.0
    A = array.array('h', [128, 0, 0, 128])  # 2.0 * 64 = 128
    B = array.array('h', [100, 100])
    C = array.array('h', [0, 0])
    dsplib.matrix_mul_s16(A, B, 2, 2, 1, 6, C)
    # 128 * 100 + 0 * 100 = 12800; 12800 >> 6 = 200
    assert C[0] == 200
    assert C[1] == 200

def test_matrix_mul_s16_clamps_to_int16():
    """Overflow gets clamped, not wrapped."""
    import dsplib
    # Build a multiply that overflows
    A = array.array('h', [32000, 0, 0, 32000])
    B = array.array('h', [32000, 32000])
    C = array.array('h', [0, 0])
    # Use shift=0 to make overflow obvious
    dsplib.matrix_mul_s16(A, B, 2, 2, 1, 0, C)
    # 32000 * 32000 = 1,024,000,000 → clamps to 32767
    assert C[0] == 32767
    assert C[1] == 32767


# ---------------------------------------------------------------------------
# dsplib.sort_indices
# ---------------------------------------------------------------------------

def test_sort_indices_descending_by_depth():
    import dsplib
    indices = array.array('H', [0, 1, 2, 3])
    depths = array.array('i', [10, 50, 20, 40])
    dsplib.sort_indices(indices, depths)
    # Sorted by depth desc: 50, 40, 20, 10 → indices 1, 3, 2, 0
    assert list(indices) == [1, 3, 2, 0]

def test_sort_indices_with_start_id():
    """When start_id is given, indices is filled sequentially first."""
    import dsplib
    indices = array.array('H', [0, 0, 0, 0])  # will be overwritten
    depths = array.array('i', [30, 10, 40, 20])
    dsplib.sort_indices(indices, depths, start_id=100)
    # Should fill with [100, 101, 102, 103] then sort by depths
    # depths=[30,10,40,20] desc → 40,30,20,10 → indices 102,100,103,101
    assert list(indices) == [102, 100, 103, 101]


# ---------------------------------------------------------------------------
# dsplib stub functions don't crash
# ---------------------------------------------------------------------------

def test_set_transform_matrix_4x4_writes_identity():
    """Stub fills with identity rather than computing rotation. Apps
    using this for 3D will see un-rotated geometry — wrong but won't
    crash."""
    import dsplib
    matrix = array.array('f', [99.0] * 16)
    dsplib.set_transform_matrix_4x4(matrix, [0, 0, 0], [0, 0, 0], [1, 1, 1])
    # First row: 1,0,0,0
    assert matrix[0] == 1.0
    assert matrix[1] == 0.0
    assert matrix[5] == 1.0   # diagonal
    assert matrix[10] == 1.0
    assert matrix[15] == 1.0

def test_project_3d_indexed_no_crash():
    """3D projection is stubbed. Any call should return without raising."""
    import dsplib
    # Pass empty buffers — the stub doesn't inspect them
    dsplib.project_3d_indexed(
        array.array('f', [0]*16),       # matrix
        array.array('f'),               # verts
        array.array('H'),               # indices
        array.array('f'),               # normals
        array.array('f', [0, 0, 1]),    # light
        0, 0,                            # num_faces, num_verts
        1.0,                             # fov
        200, 120,                        # cx, cy
        array.array('h'),                # out_poly
        array.array('b'),                # out_dither
        array.array('i'),                # out_depths
        array.array('f'),                # temp_verts
        array.array('f'),                # temp_norms
    )


# ---------------------------------------------------------------------------
# Integration: dither_test.py imports work
# ---------------------------------------------------------------------------

def test_dither_test_imports_complete():
    """Replicate dither_test.py's import surface and verify all resolve.

    We don't run the module-level pu.reimport("dsp_utils") that the
    real example does — that's a disk operation that requires the deck
    repo on sys.path, and it's tested separately in test_audio_pie.py.
    The point of THIS test is just that all the bare imports work."""
    import esclib
    import time
    import pdeck
    import random
    import re_test
    import array
    import xbmreader
    import pdeck_utils as pu
    import dsplib as dl
    import gc
    # All imports resolved — that's the whole assertion.
