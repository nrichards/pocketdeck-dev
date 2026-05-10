"""Tests for re_test and dsplib stubs.

re_test is opaque; we only verify it imports without crashing.
dsplib's matrix multiplication has math-correct implementations, so we
test those against hand-computed expected values. The 3D-projection
stubs are no-ops; we verify they don't crash but don't check output.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math
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

def test_set_transform_matrix_4x4_zero_rotation_is_scale_translate():
    """With rotation = [0,0,0], the matrix is just scale * translation.
    Replaces the old all-identity test which was testing the stub
    behavior."""
    import dsplib
    matrix = array.array('f', [99.0] * 16)
    dsplib.set_transform_matrix_4x4(
        matrix,
        [0.0, 0.0, 0.0],         # zero rotation
        [10.0, 20.0, 30.0],      # translation
        [2.0, 3.0, 4.0],         # non-uniform scale
    )
    # Diagonal of upper-left 3x3 is the scale
    assert matrix[0] == pytest.approx(2.0)
    assert matrix[5] == pytest.approx(3.0)
    assert matrix[10] == pytest.approx(4.0)
    # Off-diagonal of upper-left 3x3 is zero
    assert matrix[1] == pytest.approx(0.0, abs=1e-6)
    assert matrix[2] == pytest.approx(0.0, abs=1e-6)
    # Translation column = position vector exactly (independent of scale,
    # per the doc's "Translation is independent of model scale")
    assert matrix[3] == pytest.approx(10.0)
    assert matrix[7] == pytest.approx(20.0)
    assert matrix[11] == pytest.approx(30.0)
    # Bottom row is [0,0,0,1]
    assert matrix[12] == pytest.approx(0.0)
    assert matrix[13] == pytest.approx(0.0)
    assert matrix[14] == pytest.approx(0.0)
    assert matrix[15] == pytest.approx(1.0)

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


# ---------------------------------------------------------------------------
# set_transform_matrix_4x4 — the real implementation
# ---------------------------------------------------------------------------

def test_set_transform_matrix_4x4_90deg_y_rotation():
    """Rotation of 90° around Y axis maps (1,0,0) to (0,0,-1).

    Verifies the rotation math is composed correctly (R = Rz·Ry·Rx
    with the standard Euler convention).
    """
    import dsplib
    matrix = array.array('f', [0.0] * 16)
    dsplib.set_transform_matrix_4x4(
        matrix,
        [0.0, math.pi / 2, 0.0],   # 90° around Y
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
    )
    # Apply the matrix to (1, 0, 0). With 90° Y rotation, (1,0,0) → (0,0,-1).
    # Using the row-major convention: result_x = m00*1 + m01*0 + m02*0 + m03 = m00
    # So m00 should be 0, m04 should be 0 (y component), m08 should be -1 (z).
    assert matrix[0] == pytest.approx(0.0, abs=1e-6)
    assert matrix[4] == pytest.approx(0.0, abs=1e-6)
    assert matrix[8] == pytest.approx(-1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# project_3d_indexed — the heart of this work
# ---------------------------------------------------------------------------

@pytest.fixture
def cube_geometry():
    """Replicates cube_test.py's geometry exactly.

    Returns a dict with all the buffers the projection function needs.
    """
    unique_v_raw = [
        [-1, -1, -1], [ 1, -1, -1], [ 1,  1, -1], [-1,  1, -1],
        [-1, -1,  1], [ 1, -1,  1], [ 1,  1,  1], [-1,  1,  1]
    ]
    face_indices_raw = [
        (0, 1, 2), (2, 3, 0),  # Front (z=-1, near camera)
        (1, 5, 6), (6, 2, 1),  # Right (x=+1)
        (7, 6, 5), (5, 4, 7),  # Back (z=+1, far from camera)
        (4, 0, 3), (3, 7, 4),  # Left (x=-1)
        (4, 5, 1), (1, 0, 4),  # Bottom (y=-1)
        (3, 2, 6), (6, 7, 3),  # Top (y=+1)
    ]
    num_uni_verts = len(unique_v_raw)
    num_faces = len(face_indices_raw)

    unique_verts = array.array('f', [0.0] * (num_uni_verts * 3))
    for i, v in enumerate(unique_v_raw):
        unique_verts[i*3 : i*3+3] = array.array('f', v)

    indices = array.array('H', [0] * (num_faces * 3))
    for i, f in enumerate(face_indices_raw):
        indices[i*3 : i*3+3] = array.array('H', f)

    # Negated cross-product normals — same as cube_test.py
    face_normals = array.array('f', [0.0] * (num_faces * 3))
    for i, f in enumerate(face_indices_raw):
        p0, p1, p2 = unique_v_raw[f[0]], unique_v_raw[f[1]], unique_v_raw[f[2]]
        u = [p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2]]
        w = [p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2]]
        nx = u[1]*w[2] - u[2]*w[1]
        ny = u[2]*w[0] - u[0]*w[2]
        nz = u[0]*w[1] - u[1]*w[0]
        n_len = math.sqrt(nx*nx + ny*ny + nz*nz)
        face_normals[i*3 : i*3+3] = array.array(
            'f', [-nx/n_len, -ny/n_len, -nz/n_len]
        )

    return {
        'verts': unique_verts,
        'indices': indices,
        'normals': face_normals,
        'num_uni_verts': num_uni_verts,
        'num_faces': num_faces,
    }


def test_project_3d_indexed_unit_cube_screen_bounds(cube_geometry):
    """A unit cube at z=120 with scale=40, fov=120, projects to screen
    coords within the 400x240 viewport.
    """
    import dsplib
    g = cube_geometry
    matrix = array.array('f', [0.0] * 16)
    dsplib.set_transform_matrix_4x4(
        matrix,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 120.0],
        [40.0, 40.0, 40.0],
    )
    light = array.array('f', [0.5, 0.7, -1.0])
    out_poly = array.array('h', [0] * (g['num_faces'] * 6))
    out_dither = array.array('b', [0] * g['num_faces'])
    out_depths = array.array('i', [0] * g['num_faces'])
    temp_verts = array.array('f', [0.0] * (g['num_uni_verts'] * 3))
    temp_norms = array.array('f', [0.0] * (g['num_faces'] * 3))

    dsplib.project_3d_indexed(
        matrix, g['verts'], g['indices'], g['normals'], light,
        g['num_faces'], g['num_uni_verts'],
        120.0, 200.0, 120.0,
        out_poly, out_dither, out_depths,
        temp_verts, temp_norms,
    )

    # All visible-face screen coords should be within the screen.
    for fi in range(g['num_faces']):
        if out_dither[fi] < 0:
            continue
        for vi in range(3):
            x = out_poly[fi * 6 + vi]
            y = out_poly[fi * 6 + 3 + vi]
            assert 0 <= x <= 400, f"Face {fi} x[{vi}] out of bounds: {x}"
            assert 0 <= y <= 240, f"Face {fi} y[{vi}] out of bounds: {y}"


def test_project_3d_indexed_dither_in_valid_range(cube_geometry):
    """Every face's out_dither is either -1 (culled) or 0..16."""
    import dsplib
    g = cube_geometry
    matrix = array.array('f', [0.0] * 16)
    dsplib.set_transform_matrix_4x4(
        matrix,
        [0.5, 0.7, 0.0],
        [0.0, 0.0, 120.0],
        [40.0, 40.0, 40.0],
    )
    light = array.array('f', [0.5, 0.7, -1.0])
    out_poly = array.array('h', [0] * (g['num_faces'] * 6))
    out_dither = array.array('b', [0] * g['num_faces'])
    out_depths = array.array('i', [0] * g['num_faces'])
    temp_verts = array.array('f', [0.0] * (g['num_uni_verts'] * 3))
    temp_norms = array.array('f', [0.0] * (g['num_faces'] * 3))

    dsplib.project_3d_indexed(
        matrix, g['verts'], g['indices'], g['normals'], light,
        g['num_faces'], g['num_uni_verts'],
        120.0, 200.0, 120.0,
        out_poly, out_dither, out_depths,
        temp_verts, temp_norms,
    )

    for fi in range(g['num_faces']):
        d = out_dither[fi]
        assert d == -1 or 0 <= d <= 16, f"Face {fi} dither {d} out of valid range"


def test_project_3d_indexed_zero_rotation_culls_back_faces(cube_geometry):
    """At zero rotation, the camera-facing front face is visible and the
    far back face is culled."""
    import dsplib
    g = cube_geometry
    matrix = array.array('f', [0.0] * 16)
    dsplib.set_transform_matrix_4x4(
        matrix,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 120.0],
        [40.0, 40.0, 40.0],
    )
    light = array.array('f', [0.5, 0.7, -1.0])
    out_poly = array.array('h', [0] * (g['num_faces'] * 6))
    out_dither = array.array('b', [0] * g['num_faces'])
    out_depths = array.array('i', [0] * g['num_faces'])
    temp_verts = array.array('f', [0.0] * (g['num_uni_verts'] * 3))
    temp_norms = array.array('f', [0.0] * (g['num_faces'] * 3))

    dsplib.project_3d_indexed(
        matrix, g['verts'], g['indices'], g['normals'], light,
        g['num_faces'], g['num_uni_verts'],
        120.0, 200.0, 120.0,
        out_poly, out_dither, out_depths,
        temp_verts, temp_norms,
    )

    # Front faces (indices 0, 1) face camera at zero rotation → visible
    assert out_dither[0] >= 0, f"Front-tri1 should be visible, got {out_dither[0]}"
    assert out_dither[1] >= 0, f"Front-tri2 should be visible, got {out_dither[1]}"

    # Back faces (indices 4, 5) face away → culled
    assert out_dither[4] == -1, f"Back-tri1 should be culled, got {out_dither[4]}"
    assert out_dither[5] == -1, f"Back-tri2 should be culled, got {out_dither[5]}"


def test_project_3d_indexed_backface_normal_pointing_positive_z():
    """A single triangle whose normal points in +Z (away from camera at
    +Z) is culled. This exercises the backface rule directly."""
    import dsplib

    # One triangle in front of camera. Normal explicitly points +Z.
    verts = array.array('f', [
        -1.0, -1.0, 0.0,
         1.0, -1.0, 0.0,
         0.0,  1.0, 0.0,
    ])
    indices = array.array('H', [0, 1, 2])
    normals = array.array('f', [0.0, 0.0, 1.0])  # points away from camera

    matrix = array.array('f', [0.0] * 16)
    dsplib.set_transform_matrix_4x4(
        matrix,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 5.0],   # in front of camera
        [1.0, 1.0, 1.0],
    )
    light = array.array('f', [0.0, 0.0, -1.0])

    out_poly = array.array('h', [0] * 6)
    out_dither = array.array('b', [0])
    out_depths = array.array('i', [0])
    temp_verts = array.array('f', [0.0] * 9)
    temp_norms = array.array('f', [0.0] * 3)

    dsplib.project_3d_indexed(
        matrix, verts, indices, normals, light,
        1, 3, 60.0, 200.0, 120.0,
        out_poly, out_dither, out_depths,
        temp_verts, temp_norms,
    )

    # Normal points +Z → backface → culled
    assert out_dither[0] == -1


def test_project_3d_indexed_near_plane_culls_behind_camera():
    """A triangle with one vertex behind the near plane (tz < 1) is culled
    rather than projected (avoids divide-by-zero / wrap artifacts)."""
    import dsplib

    # One vertex in front, one near, one BEHIND the camera (negative z).
    verts = array.array('f', [
        -1.0, -1.0,  5.0,
         1.0, -1.0,  5.0,
         0.0,  1.0, -1.0,   # behind camera
    ])
    indices = array.array('H', [0, 1, 2])
    normals = array.array('f', [0.0, 0.0, -1.0])  # toward camera

    matrix = array.array('f', [0.0] * 16)
    dsplib.set_transform_matrix_4x4(
        matrix,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        [1.0, 1.0, 1.0],
    )
    light = array.array('f', [0.0, 0.0, -1.0])

    out_poly = array.array('h', [0] * 6)
    out_dither = array.array('b', [0])
    out_depths = array.array('i', [0])
    temp_verts = array.array('f', [0.0] * 9)
    temp_norms = array.array('f', [0.0] * 3)

    dsplib.project_3d_indexed(
        matrix, verts, indices, normals, light,
        1, 3, 60.0, 200.0, 120.0,
        out_poly, out_dither, out_depths,
        temp_verts, temp_norms,
    )

    assert out_dither[0] == -1, "Near-plane cull should set dither = -1"


def test_project_3d_indexed_depths_scaled_by_1024():
    """out_depths[fi] should be the centroid Z multiplied by 1024,
    per the doc. We check against a known geometry."""
    import dsplib

    # Triangle with centroid at z = 5.0
    verts = array.array('f', [
        -1.0, -1.0, 5.0,
         1.0, -1.0, 5.0,
         0.0,  1.0, 5.0,
    ])
    indices = array.array('H', [0, 1, 2])
    normals = array.array('f', [0.0, 0.0, -1.0])

    matrix = array.array('f', [0.0] * 16)
    # Identity transform (no scale, position, or rotation)
    dsplib.set_transform_matrix_4x4(
        matrix, [0.0]*3, [0.0]*3, [1.0]*3,
    )
    light = array.array('f', [0.0, 0.0, -1.0])
    out_poly = array.array('h', [0]*6)
    out_dither = array.array('b', [0])
    out_depths = array.array('i', [0])
    temp_verts = array.array('f', [0.0]*9)
    temp_norms = array.array('f', [0.0]*3)

    dsplib.project_3d_indexed(
        matrix, verts, indices, normals, light,
        1, 3, 60.0, 200.0, 120.0,
        out_poly, out_dither, out_depths,
        temp_verts, temp_norms,
    )

    # Centroid Z = 5.0; depth = 5 * 1024 = 5120
    assert out_depths[0] == 5120


# ---------------------------------------------------------------------------
# project_2d_indexed and set_transform_matrix_3x3
# ---------------------------------------------------------------------------

def test_set_transform_matrix_3x3_identity():
    """Zero rotation, zero translation, unit scale → 2D identity."""
    import dsplib
    matrix = array.array('f', [99.0] * 9)
    dsplib.set_transform_matrix_3x3(matrix, 0.0, [0.0, 0.0], [1.0, 1.0])
    assert matrix[0] == pytest.approx(1.0)
    assert matrix[1] == pytest.approx(0.0, abs=1e-6)
    assert matrix[2] == pytest.approx(0.0)
    assert matrix[3] == pytest.approx(0.0, abs=1e-6)
    assert matrix[4] == pytest.approx(1.0)
    assert matrix[5] == pytest.approx(0.0)


def test_set_transform_matrix_3x3_90deg_rotation():
    """90° rotation maps (1,0) to (0,1) in the 2D plane."""
    import dsplib
    matrix = array.array('f', [0.0] * 9)
    dsplib.set_transform_matrix_3x3(
        matrix, math.pi / 2, [0.0, 0.0], [1.0, 1.0],
    )
    # m00 should be cos(90) = 0, m10 should be sin(90) = 1
    assert matrix[0] == pytest.approx(0.0, abs=1e-6)
    assert matrix[3] == pytest.approx(1.0, abs=1e-6)


def test_project_2d_indexed_basic():
    """A square at origin scaled by 60 should project to a 120×120
    square centered at (cx, cy)."""
    import dsplib

    # Unit square (matches square_test.py)
    verts = array.array('f', [
        -1, -1,
         1, -1,
         1,  1,
        -1,  1,
    ])
    indices = array.array('H', [0, 1, 2, 0, 2, 3])
    colors = array.array('f', [16.0, 12.0, 8.0, 4.0])

    matrix = array.array('f', [0.0] * 9)
    dsplib.set_transform_matrix_3x3(
        matrix, 0.0, [0.0, 0.0], [60.0, 60.0],
    )
    out_poly = array.array('h', [0]*12)
    out_dither = array.array('b', [0, 0])
    temp_verts = array.array('f', [0.0]*8)

    dsplib.project_2d_indexed(
        matrix, verts, indices, colors, 1.0,
        2, 4, 200, 120,
        out_poly, out_dither, temp_verts,
    )

    # Vertices should project to ±60 from (200, 120):
    #   (-1,-1) → (140, 180)  (note Y is inverted: cy - ty)
    #   (1,-1)  → (260, 180)
    #   (1,1)   → (260, 60)
    #   (-1,1)  → (140, 60)
    # First triangle (indices 0,1,2) gets vertices 0, 1, 2 = those first three
    assert out_poly[0] == 140  # x[0]
    assert out_poly[1] == 260  # x[1]
    assert out_poly[2] == 260  # x[2]
    assert out_poly[3] == 180  # y[0]
    assert out_poly[4] == 180  # y[1]
    assert out_poly[5] == 60   # y[2]

    # Average color of vertices 0,1,2 = (16+12+8)/3 = 12.0, multiplied by light=1.0
    assert out_dither[0] == 12
    # Second triangle (vertices 0,2,3) avg = (16+8+4)/3 ≈ 9.33 → int 9
    assert out_dither[1] == 9
