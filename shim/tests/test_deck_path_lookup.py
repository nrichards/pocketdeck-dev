"""Tests for deck library path resolution and fallback-shim behavior.

The shim mimics MicroPython's sys.path on the deck: /sd/py first, then
/sd/lib. When POCKETDECK_ROOT is populated with real deck source, the
shim should use it; when it isn't, fall back to internal stubs.
"""
from __future__ import annotations

import importlib
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import sys

import pytest

from pdeck_sim.paths import get_deck_library_paths
from pdeck_sim._stubs import (
    _real_module_available_on_deck_path,
    _ALWAYS_SHIM,
    _FALLBACK_SHIM,
)


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """Each test gets a fresh POCKETDECK_ROOT."""
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))
    monkeypatch.delenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", raising=False)
    return tmp_path


# ---------------------------------------------------------------------------
# get_deck_library_paths basics
# ---------------------------------------------------------------------------

def test_no_deck_paths_when_dirs_missing(isolated_root):
    """If /sd/py and /sd/lib don't exist under the root, return empty."""
    paths = get_deck_library_paths()
    assert paths == []

def test_returns_existing_dirs_in_priority_order(isolated_root):
    """sd/py comes before sd/lib (matches deck behavior: user apps
    override library)."""
    py_dir = isolated_root / "sd" / "py"
    lib_dir = isolated_root / "sd" / "lib"
    py_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)

    paths = get_deck_library_paths()
    assert len(paths) == 2
    assert paths[0].endswith("/sd/py")
    assert paths[1].endswith("/sd/lib")

def test_returns_only_existing_dirs(isolated_root):
    """If only /sd/lib exists (no /sd/py), only return /sd/lib."""
    lib_dir = isolated_root / "sd" / "lib"
    lib_dir.mkdir(parents=True)

    paths = get_deck_library_paths()
    assert len(paths) == 1
    assert paths[0].endswith("/sd/lib")


# ---------------------------------------------------------------------------
# _real_module_available_on_deck_path
# ---------------------------------------------------------------------------

def test_finds_py_file_on_path(tmp_path):
    """Detection works for .py files."""
    (tmp_path / "fakemod.py").write_text("# fake")
    assert _real_module_available_on_deck_path("fakemod", [str(tmp_path)])

def test_finds_mpy_file_on_path(tmp_path):
    """Detection works for .mpy files (MicroPython compiled bytecode)."""
    (tmp_path / "fakemod.mpy").write_bytes(b"\x00\x00")  # not a real mpy, just exists
    assert _real_module_available_on_deck_path("fakemod", [str(tmp_path)])

def test_missing_module_not_detected(tmp_path):
    """Module that's not on disk returns False."""
    assert not _real_module_available_on_deck_path("nonexistent", [str(tmp_path)])

def test_searches_multiple_paths(tmp_path):
    """If multiple paths are given, finds the module in any of them."""
    p1 = tmp_path / "first"
    p2 = tmp_path / "second"
    p1.mkdir()
    p2.mkdir()
    (p2 / "found_here.py").write_text("# x")
    assert _real_module_available_on_deck_path(
        "found_here", [str(p1), str(p2)],
    )


# ---------------------------------------------------------------------------
# Module categorization is consistent
# ---------------------------------------------------------------------------

def test_always_shim_modules_are_native_only():
    """The always-shim list should only contain modules with no
    real-Python equivalent on the deck — either C native modules in the
    firmware (pdeck, audio, pie, dsplib), MicroPython builtins
    (micropython), or Nunomo-internal harness modules (re_test)."""
    expected = {"pdeck", "audio", "pie", "dsplib", "re_test",
                "micropython", "network"}
    assert set(_ALWAYS_SHIM.keys()) == expected

def test_fallback_shim_modules_have_factories():
    """Every fallback-shim entry should map to a callable factory."""
    import pdeck_sim._stubs as stubs_module
    for mod_name, factory_name in _FALLBACK_SHIM.items():
        assert hasattr(stubs_module, factory_name), (
            f"Factory {factory_name} for {mod_name} not found"
        )
        assert callable(getattr(stubs_module, factory_name))

def test_no_overlap_between_categories():
    """A module is either always-shim or fallback-shim, not both."""
    assert not (set(_ALWAYS_SHIM) & set(_FALLBACK_SHIM))


# ---------------------------------------------------------------------------
# Integration: install_all behaves correctly with real-on-disk
# ---------------------------------------------------------------------------

def test_install_all_uses_real_xbmreader_when_available(isolated_root, monkeypatch):
    """If a real xbmreader.py exists under /sd/lib, install_all should
    NOT pre-register a fallback stub — Python's normal import machinery
    will find the real one via sys.path."""
    lib_dir = isolated_root / "sd" / "lib"
    lib_dir.mkdir(parents=True)
    # Write a sentinel module that's identifiable
    (lib_dir / "xbmreader.py").write_text(
        "REAL_FROM_DISK = True\n"
        "def read(p): return ('marker', 0, 0, b'', 1)\n"
        "def read_xbmr(p): return ('marker_xbmr', 0, 0, b'', 1)\n"
        "def scale(img, n): return img\n"
    )

    # Wipe any prior xbmreader registration from previous tests
    sys.modules.pop("xbmreader", None)

    from pdeck_sim import _stubs
    _stubs.install_all()

    # With real on disk, the shim should NOT have pre-registered a
    # fallback. Python's import lookup will find the real one when the
    # user does `import xbmreader`.
    if "xbmreader" in sys.modules:
        # If something pre-loaded it earlier, force re-import from disk
        del sys.modules["xbmreader"]
    import xbmreader
    assert getattr(xbmreader, "REAL_FROM_DISK", False)

def test_install_all_uses_fallback_stub_when_no_disk(isolated_root):
    """If POCKETDECK_ROOT exists but /sd/lib has no xbmreader.py,
    install_all should install the fallback stub."""
    # Ensure no xbmreader.py exists
    lib_dir = isolated_root / "sd" / "lib"
    lib_dir.mkdir(parents=True)
    # explicitly do NOT write xbmreader.py here

    sys.modules.pop("xbmreader", None)

    from pdeck_sim import _stubs
    _stubs.install_all()

    import xbmreader
    # Fallback stub doesn't have REAL_FROM_DISK
    assert not hasattr(xbmreader, "REAL_FROM_DISK")
    # But should have read/read_xbmr/scale (the API surface)
    assert hasattr(xbmreader, "read")
    assert hasattr(xbmreader, "read_xbmr")
    assert hasattr(xbmreader, "scale")

def test_pdeck_always_shimmed_even_with_disk_file(isolated_root):
    """Even if a hostile /sd/lib/pdeck.py existed, the shim should
    still install fake_pdeck — pdeck is in ALWAYS_SHIM because there's
    no real-Python implementation that would actually work."""
    lib_dir = isolated_root / "sd" / "lib"
    lib_dir.mkdir(parents=True)
    # Write a file that should NOT be loaded
    (lib_dir / "pdeck.py").write_text(
        "raise RuntimeError('this should never be imported')\n"
    )

    sys.modules.pop("pdeck", None)

    from pdeck_sim import _stubs
    _stubs.install_all()

    import pdeck
    # If this import works, we got our fake_pdeck (the disk one would
    # have raised RuntimeError on import).
    assert hasattr(pdeck, "vscreen")  # API surface, not the disk file


def test_sys_path_extended_with_deck_paths(isolated_root):
    """install_all should add deck library paths to sys.path so the
    real modules are findable."""
    lib_dir = isolated_root / "sd" / "lib"
    py_dir = isolated_root / "sd" / "py"
    lib_dir.mkdir(parents=True)
    py_dir.mkdir(parents=True)

    # Snapshot then refresh
    from pdeck_sim import _stubs
    _stubs.install_all()

    # Both paths should be on sys.path
    lib_resolved = str(lib_dir.resolve())
    py_resolved = str(py_dir.resolve())
    assert lib_resolved in sys.path
    assert py_resolved in sys.path

    # py should appear before lib in priority order
    assert sys.path.index(py_resolved) < sys.path.index(lib_resolved)
