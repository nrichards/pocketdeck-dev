"""Tests for sandbox escape prevention.

Two separate defense layers, independently tested:

1. Logical-escape (`..` traversal) — always on. Apps cannot construct
   deck paths that climb out of the deck filesystem root.

2. Symlink-escape — strict mode only. By default, symlinks inside the
   root pointing outside are allowed (developers often configure the
   root that way intentionally). Opt in with POCKETDECK_ALLOW_SYMLINK_ESCAPE=0
   for paranoid setups.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest
from pathlib import Path

from pdeck_sim import _stubs
_stubs.install_all()

from pdeck_sim.paths import translate, SandboxEscapeError


@pytest.fixture(autouse=True)
def isolate_root(tmp_path, monkeypatch):
    """Every test gets its own POCKETDECK_ROOT under tmp.

    Also ensures POCKETDECK_ALLOW_SYMLINK_ESCAPE isn't inherited from the
    process env — tests set it explicitly when they care.
    """
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))
    monkeypatch.delenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", raising=False)


# ---------------------------------------------------------------------------
# Baseline: legitimate paths still work under default settings
# ---------------------------------------------------------------------------

def test_normal_sd_path_accepted():
    result = translate("/sd/lib/data/ghost.xbm")
    assert result.endswith("/sd/lib/data/ghost.xbm")

def test_normal_config_path_accepted():
    result = translate("/config/apps.json")
    assert result.endswith("/config/apps.json")

def test_nonexistent_file_inside_root_accepted():
    """Validation must work for files that don't exist yet — writes need
    to be able to reference future output paths."""
    result = translate("/sd/Documents/journal_2099.md")
    assert "journal_2099.md" in result


# ---------------------------------------------------------------------------
# Logical-escape check (layer 1): always enabled, regardless of strict mode
# ---------------------------------------------------------------------------

def test_dotdot_escape_rejected_by_default():
    """The classic app-controlled attack: use .. to climb out of the
    deck filesystem. Must be rejected even with the strict mode off."""
    with pytest.raises(SandboxEscapeError):
        translate("/sd/../../../etc/passwd")

def test_dotdot_escape_rejected_in_strict_mode(monkeypatch):
    monkeypatch.setenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", "0")
    with pytest.raises(SandboxEscapeError):
        translate("/sd/../../../etc/passwd")

def test_deeply_nested_dotdot_rejected():
    with pytest.raises(SandboxEscapeError):
        translate("/sd/lib/data/../../../../../../etc/passwd")

def test_dotdot_that_climbs_to_root_only_is_rejected():
    """/sd/.. normalizes to /, which isn't a deck prefix — reject."""
    with pytest.raises(SandboxEscapeError):
        translate("/sd/..")

def test_dotdot_that_crosses_deck_prefixes_is_allowed():
    """/sd/../config normalizes to /config — still inside the deck tree,
    so cross-prefix traversal is fine. Documenting this as an explicit
    choice so the boundary is clear."""
    result = translate("/sd/../config")
    assert result.endswith("/config") or result.endswith("/config/")

def test_dotdot_that_stays_inside_is_allowed():
    """..s that don't actually escape are fine. /sd/a/../b is /sd/b."""
    result = translate("/sd/lib/../lib/data/ghost.xbm")
    assert "ghost.xbm" in result


# ---------------------------------------------------------------------------
# Symlink-escape check (layer 2): off by default, on in strict mode
# ---------------------------------------------------------------------------

def test_symlink_escape_allowed_by_default(tmp_path):
    """DEFAULT BEHAVIOR: a symlink inside the root that points outside
    is permitted. This is the setup many developers want — symlink the
    real deck repo into the sandbox so apps see live source-of-truth
    content."""
    (tmp_path / "sd").mkdir()
    os.symlink("/etc", str(tmp_path / "sd" / "lib"))

    # Under default (permissive) config, this must not raise.
    result = translate("/sd/lib/hosts")
    assert result.endswith("/sd/lib/hosts")

def test_symlink_escape_rejected_in_strict_mode(tmp_path, monkeypatch):
    """In strict mode, the same symlink setup is rejected."""
    monkeypatch.setenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", "0")
    (tmp_path / "sd").mkdir()
    os.symlink("/etc", str(tmp_path / "sd" / "lib"))

    with pytest.raises(SandboxEscapeError, match="symlink"):
        translate("/sd/lib/hosts")

def test_symlink_inside_root_works_in_strict_mode(tmp_path, monkeypatch):
    """Symlinks that stay inside the root are fine in both modes."""
    monkeypatch.setenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", "0")
    (tmp_path / "sd" / "lib").mkdir(parents=True)
    (tmp_path / "sd" / "alt").mkdir()
    (tmp_path / "sd" / "lib" / "real.txt").write_text("hello")
    os.symlink(str(tmp_path / "sd" / "lib"),
               str(tmp_path / "sd" / "alt" / "linked"))

    result = translate("/sd/alt/linked/real.txt")
    assert result.endswith("real.txt")


# ---------------------------------------------------------------------------
# Edge cases on the POCKETDECK_ALLOW_SYMLINK_ESCAPE value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["0", "false", "False", "NO", "no", ""])
def test_strict_mode_triggers(tmp_path, monkeypatch, value):
    """Values that should all enable strict mode."""
    monkeypatch.setenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", value)
    (tmp_path / "sd").mkdir()
    os.symlink("/etc", str(tmp_path / "sd" / "lib"))
    with pytest.raises(SandboxEscapeError):
        translate("/sd/lib/hosts")

@pytest.mark.parametrize("value", ["1", "true", "yes", "anything-else"])
def test_permissive_mode_triggers(tmp_path, monkeypatch, value):
    """Any non-strict value keeps the default (permissive) behavior."""
    monkeypatch.setenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", value)
    (tmp_path / "sd").mkdir()
    os.symlink("/etc", str(tmp_path / "sd" / "lib"))
    result = translate("/sd/lib/hosts")
    assert result.endswith("hosts")


# ---------------------------------------------------------------------------
# Untranslated paths pass through unchanged regardless of sandbox mode
# ---------------------------------------------------------------------------

def test_host_path_not_sandboxed():
    """/tmp/foo is a host path, not a deck path. Never sandboxed."""
    result = translate("/tmp/legit.txt")
    assert result == "/tmp/legit.txt"

def test_relative_path_not_sandboxed():
    result = translate("./relative/foo")
    assert result == "./relative/foo"


# ---------------------------------------------------------------------------
# Integration via xbmreader
# ---------------------------------------------------------------------------

def test_xbmreader_rejects_dotdot_escape(tmp_path, monkeypatch):
    """The `..` check applies end-to-end through xbmreader."""
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))
    import xbmreader
    with pytest.raises(SandboxEscapeError):
        xbmreader.read("/sd/../../../etc/passwd")

def test_xbmreader_allows_symlink_out_by_default(tmp_path, monkeypatch):
    """By default, an XBM accessed via symlink-out should succeed in
    reaching the translation layer. Since the target doesn't exist,
    xbmreader returns its 'not found' response (warning + empty image)
    rather than a SandboxEscapeError."""
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))
    (tmp_path / "sd").mkdir()
    os.symlink("/nonexistent-dir", str(tmp_path / "sd" / "lib"))
    import xbmreader
    with pytest.warns(UserWarning, match="XBM not found"):
        result = xbmreader.read("/sd/lib/data/ghost.xbm")
    assert result[1] == 0  # empty image

def test_xbmreader_rejects_symlink_out_in_strict_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("POCKETDECK_ROOT", str(tmp_path))
    monkeypatch.setenv("POCKETDECK_ALLOW_SYMLINK_ESCAPE", "0")
    (tmp_path / "sd").mkdir()
    os.symlink("/etc", str(tmp_path / "sd" / "lib"))
    import xbmreader
    with pytest.raises(SandboxEscapeError):
        xbmreader.read("/sd/lib/hosts")
