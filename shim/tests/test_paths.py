"""Tests for the deck-path-to-host-path translator.

Uses monkeypatch to set POCKETDECK_ROOT to a tmp_path so tests don't touch
the real home directory.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest
from pathlib import Path

from pdeck_sim.paths import translate, get_root


@pytest.fixture(autouse=True)
def isolate_root(tmp_path, monkeypatch):
    """Every test gets its own POCKETDECK_ROOT under tmp."""
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))


def test_sd_path_translated():
    result = translate("/sd/lib/data/ghost1.xbm")
    assert result.endswith("/sd/lib/data/ghost1.xbm")
    # Should live under the configured root, not at host /sd
    assert not result.startswith("/sd/")

def test_config_path_translated():
    result = translate("/config/apps.json")
    assert result.endswith("/config/apps.json")
    assert not result.startswith("/config/")

def test_int_path_maps_to_root():
    """The deck's /int/ prefix is the internal-flash root, which maps to
    POCKETDECK_ROOT itself (not a /int subdirectory)."""
    root = get_root()
    result = translate("/int/main.py")
    assert result == str(root / "main.py")

def test_relative_path_unchanged():
    assert translate("foo/bar.xbm") == "foo/bar.xbm"

def test_unknown_absolute_path_unchanged():
    """A host-absolute path (like /tmp or /Users) passes through — we
    don't want to hijack legitimate file access."""
    assert translate("/tmp/scratch.txt") == "/tmp/scratch.txt"
    assert translate("/Users/nick/file") == "/Users/nick/file"

def test_none_returns_none():
    assert translate(None) is None

def test_pathlib_input_works():
    """translate() should accept Path objects too, not just strings."""
    result = translate(Path("/sd/foo"))
    assert isinstance(result, str)
    assert result.endswith("/sd/foo")

def test_root_autocreated():
    root = get_root()
    assert root.exists()
    assert root.is_dir()

def test_xbmreader_missing_file_returns_empty(tmp_path, monkeypatch):
    """When a /sd/... file doesn't exist under the host root, read()
    should warn and return an empty image rather than crash."""
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))
    import xbmreader
    with pytest.warns(UserWarning, match="XBM not found"):
        name, w, h, data, frames = xbmreader.read("/sd/lib/data/missing.xbm")
    assert name == "missing"
    assert w == 0 and h == 0
    assert data == b""

def test_xbmreader_finds_translated_file(tmp_path, monkeypatch):
    """A file placed under POCKETDECK_ROOT/sd/... should be found via
    its deck path."""
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))
    # Create a tiny XBM at the translated location
    sd_dir = tmp_path / "sd" / "lib" / "data"
    sd_dir.mkdir(parents=True)
    (sd_dir / "tiny.xbm").write_text(
        "#define tiny_width 8\n"
        "#define tiny_height 1\n"
        "static char tiny_bits[] = { 0xFF };\n"
    )
    import xbmreader
    name, w, h, data, frames = xbmreader.read("/sd/lib/data/tiny.xbm")
    assert name == "tiny"
    assert w == 8
    assert h == 1
    assert data == bytes([0xFF])
