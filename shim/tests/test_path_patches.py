"""Tests for the path-translation patches on builtins.open and os APIs.

These patches make deck-style absolute paths (/sd/..., /config/..., /int/...)
work transparently with file APIs, so deck library code that does
`open("/sd/lib/data/x.xbm")` or `os.stat("/sd/foo")` Just Works on a Mac
without modification.

Critical: the patches must not affect host-style paths (/tmp/, /Users/,
relative paths) — those should pass through unchanged.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import builtins
import pytest

from pdeck_sim import _stubs
_stubs.install_all()


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """Each test gets a fresh POCKETDECK_ROOT and a populated sd/lib."""
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))
    monkeypatch.delenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", raising=False)
    (tmp_path / "sd" / "lib" / "data").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# builtins.open with deck paths
# ---------------------------------------------------------------------------

def test_open_deck_path_reads_translated(isolated_root):
    """open('/sd/lib/x.txt', 'r') should translate to the host path."""
    target = isolated_root / "sd" / "lib" / "hello.txt"
    target.write_text("hello from deck path")
    with open("/sd/lib/hello.txt", "r") as f:
        assert f.read() == "hello from deck path"

def test_open_deck_path_writes_translated(isolated_root):
    """open('/sd/lib/x.txt', 'w') should write to the translated host path."""
    with open("/sd/lib/written.txt", "w") as f:
        f.write("written via deck path")
    # File should physically exist at the translated location
    assert (isolated_root / "sd" / "lib" / "written.txt").read_text() == \
           "written via deck path"

def test_open_config_path(isolated_root):
    """/config/ paths translate too."""
    (isolated_root / "config" / "apps.json").write_text('{"k": 1}')
    with open("/config/apps.json", "r") as f:
        assert f.read() == '{"k": 1}'

def test_open_int_path_maps_to_root(isolated_root):
    """/int/ maps to root itself, equivalent to deck's /."""
    (isolated_root / "boot.py").write_text("# boot")
    with open("/int/boot.py", "r") as f:
        assert f.read() == "# boot"

def test_open_xbmr_binary(isolated_root):
    """Binary mode works too — important for XBMR which is the original
    motivating use case."""
    target = isolated_root / "sd" / "lib" / "data" / "x.xbmr"
    target.write_bytes(b"\x00\x01\x08\x00\x10\x00\xff\xff")
    with open("/sd/lib/data/x.xbmr", "rb") as f:
        assert f.read() == b"\x00\x01\x08\x00\x10\x00\xff\xff"

def test_open_pathlib_input(isolated_root):
    """open() accepts pathlib.Path; deck-path Paths should also translate."""
    from pathlib import Path
    target = isolated_root / "sd" / "lib" / "p.txt"
    target.write_text("path obj")
    with open(Path("/sd/lib/p.txt"), "r") as f:
        assert f.read() == "path obj"


# ---------------------------------------------------------------------------
# Non-deck paths must not be touched
# ---------------------------------------------------------------------------

def test_open_host_path_passes_through(tmp_path):
    """A host-style absolute path should reach the real filesystem
    unmolested. The patches must not interfere with non-deck paths."""
    host_file = tmp_path / "host.txt"
    host_file.write_text("host content")
    # tmp_path is a plain host path like /tmp/pytest-..., NOT under /sd
    with open(str(host_file), "r") as f:
        assert f.read() == "host content"

def test_open_relative_path_passes_through(tmp_path, monkeypatch):
    """Relative paths pass through unchanged."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "rel.txt").write_text("relative content")
    with open("rel.txt", "r") as f:
        assert f.read() == "relative content"

def test_open_file_descriptor_passes_through(tmp_path):
    """open() accepts file descriptors (ints). Those must not be
    interpreted as paths."""
    # Open the real file the host way to get an fd
    host_file = tmp_path / "fd.txt"
    host_file.write_text("fd content")
    fd = os.open(str(host_file), os.O_RDONLY)
    try:
        # Now use builtins.open with the integer fd — patches should
        # leave this alone (fd is not str/Path)
        with open(fd, "r", closefd=False) as f:
            assert f.read() == "fd content"
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Sandbox enforcement still applies through the patched open
# ---------------------------------------------------------------------------

def test_open_dotdot_escape_rejected(isolated_root):
    """The patched open() goes through translate(), which enforces
    sandbox rules. So `..` traversal raises SandboxEscapeError."""
    from pdeck_sim.paths import SandboxEscapeError
    with pytest.raises(SandboxEscapeError):
        open("/sd/../../../etc/passwd", "r")


# ---------------------------------------------------------------------------
# os.stat / os.listdir
# ---------------------------------------------------------------------------

def test_os_stat_deck_path(isolated_root):
    """os.stat() on a deck path translates to the host equivalent."""
    target = isolated_root / "sd" / "lib" / "stat_me.txt"
    target.write_text("x" * 100)
    st = os.stat("/sd/lib/stat_me.txt")
    assert st.st_size == 100

def test_os_stat_host_path_passes_through(tmp_path):
    host_file = tmp_path / "host_stat.txt"
    host_file.write_text("y" * 50)
    st = os.stat(str(host_file))
    assert st.st_size == 50

def test_os_listdir_deck_path(isolated_root):
    """os.listdir() on a deck path lists the translated host directory."""
    (isolated_root / "sd" / "lib" / "a.txt").write_text("a")
    (isolated_root / "sd" / "lib" / "b.txt").write_text("b")
    entries = sorted(e for e in os.listdir("/sd/lib")
                     if e in ("a.txt", "b.txt"))
    assert entries == ["a.txt", "b.txt"]


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_install_path_translation_is_idempotent(isolated_root):
    """Calling install_path_translation twice doesn't double-wrap.

    If it did, deck paths would be translated twice — first to host
    path, then trying to translate the host path (which would no-op
    since host paths don't start with deck prefixes). So the user-
    visible bug from double-wrap is subtle, but the architectural
    issue is real. Verify the open function is the same object before
    and after a second install.
    """
    from pdeck_sim.paths import install_path_translation_in_builtins
    snapshot = builtins.open
    install_path_translation_in_builtins()
    install_path_translation_in_builtins()
    # Same wrapped function — not re-wrapped
    assert builtins.open is snapshot
