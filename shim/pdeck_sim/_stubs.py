"""_stubs.py — minimal shims for the smaller device modules that apps import.

We inject each of these into sys.modules under its real name. None of them
do anything interesting on desktop, but making them importable keeps user
apps running without code changes.
"""
from __future__ import annotations

import sys
import importlib
import time
import types
import warnings
from pathlib import Path


# ---------------------------------------------------------------------------
# pdeck_utils
# ---------------------------------------------------------------------------

def make_pdeck_utils() -> types.ModuleType:
    mod = types.ModuleType("pdeck_utils")

    # Module-level attributes the real one has
    mod.timezone = 0
    mod.autosleep = 0

    def reimport(module_name: str):
        """Force-reload a module. Equivalent to real pdeck_utils.reimport."""
        if module_name in sys.modules:
            del sys.modules[module_name]
        return importlib.import_module(module_name)

    def launch(command, screen_num: int):
        print(f"[pdeck_sim] pdeck_utils.launch ignored: {command} -> scr {screen_num}")

    mod.reimport = reimport
    mod.launch = launch
    return mod


# ---------------------------------------------------------------------------
# audio — noisy but non-fatal stub
# ---------------------------------------------------------------------------

def make_audio() -> types.ModuleType:
    mod = types.ModuleType("audio")
    _warned = {"value": False}

    def _warn_once():
        if not _warned["value"]:
            warnings.warn(
                "[pdeck_sim] audio calls are stubbed — no sound output.",
                stacklevel=3,
            )
            _warned["value"] = True

    class _Wavetable:
        def __init__(self, *a, **kw): _warn_once()
        def __enter__(self): return self
        def __exit__(self, *a): return False

        # Any attribute access returns a no-op
        def __getattr__(self, name):
            def _noop(*a, **kw): return None
            return _noop

    def sample_rate(*a, **kw): _warn_once()

    mod.wavetable = _Wavetable
    mod.sample_rate = sample_rate
    return mod


# ---------------------------------------------------------------------------
# xbmreader — read XBM files into (name, w, h, data, frames) tuples
# ---------------------------------------------------------------------------

def make_xbmreader() -> types.ModuleType:
    mod = types.ModuleType("xbmreader")

    def read(path: str) -> tuple:
        """Parse a .xbm file. Returns (name, width, height, bytes, 1)."""
        text = Path(path).read_text()
        # XBM looks like:
        #   #define foo_width 16
        #   #define foo_height 16
        #   static char foo_bits[] = { 0x00, 0x01, ... };
        name = Path(path).stem
        width = height = 0
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("#define") and "_width" in line:
                width = int(line.rsplit(None, 1)[-1])
            elif line.startswith("#define") and "_height" in line:
                height = int(line.rsplit(None, 1)[-1])
        # Find hex bytes
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or width == 0 or height == 0:
            return (name, 0, 0, b"", 1)
        blob = text[start + 1:end]
        data = bytearray()
        for tok in blob.replace("\n", "").split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                data.append(int(tok, 0) & 0xFF)
            except ValueError:
                pass
        return (name, width, height, bytes(data), 1)

    def scale(image: tuple, factor: int) -> tuple:
        """Scale an XBM up by integer factor, 1bpp nearest-neighbor."""
        name, w, h, data, frames = image
        if factor <= 1 or not data:
            return image
        new_w, new_h = w * factor, h * factor
        src_stride = (w + 7) // 8
        dst_stride = (new_w + 7) // 8
        out = bytearray(dst_stride * new_h)
        for y in range(new_h):
            sy = y // factor
            for x in range(new_w):
                sx = x // factor
                b = data[sy * src_stride + (sx >> 3)]
                bit = (b >> (sx & 7)) & 1
                if bit:
                    out[y * dst_stride + (x >> 3)] |= (1 << (x & 7))
        return (name, new_w, new_h, bytes(out), frames)

    def read_xbmr(path: str) -> tuple:
        # XBMR is the deck's binary format. We don't parse it; apps that use
        # it will get an empty image. Add a parser here if needed.
        warnings.warn(f"[pdeck_sim] xbmreader.read_xbmr('{path}') stubbed")
        return (Path(path).stem, 0, 0, b"", 1)

    mod.read = read
    mod.scale = scale
    mod.read_xbmr = read_xbmr
    return mod


# ---------------------------------------------------------------------------
# esclib — ANSI escape helpers
# ---------------------------------------------------------------------------

def make_esclib() -> types.ModuleType:
    mod = types.ModuleType("esclib")

    class _EscLib:
        def erase_screen(self):     return "\x1b[2J"
        def home(self):              return "\x1b[H"
        def display_mode(self, on):  return f"\x1b[?25{'h' if on else 'l'}"
        def move(self, r, c):        return f"\x1b[{r};{c}H"
        def __getattr__(self, _name):
            # Any other esc helper returns empty string — harmless.
            return lambda *a, **kw: ""

    mod.esclib = _EscLib
    return mod


# ---------------------------------------------------------------------------
# overlay — show_fps and other overlays
# ---------------------------------------------------------------------------

def make_overlay() -> types.ModuleType:
    mod = types.ModuleType("overlay")
    _last = {"t": time.time(), "frames": 0, "fps": 0.0}

    def show_fps(v) -> None:
        _last["frames"] += 1
        now = time.time()
        if now - _last["t"] >= 0.5:
            _last["fps"] = _last["frames"] / (now - _last["t"])
            _last["frames"] = 0
            _last["t"] = now
        try:
            v.set_font("u8g2_font_profont11_mf")
            v.draw_str(350, 12, f"{_last['fps']:.0f}fps")
        except Exception:
            pass

    mod.show_fps = show_fps
    return mod


# ---------------------------------------------------------------------------
# benchmark — timer helper used by pem.py
# ---------------------------------------------------------------------------

def make_benchmark() -> types.ModuleType:
    mod = types.ModuleType("benchmark")

    class _Bench:
        def __init__(self, enabled=False): self.enabled = bool(enabled); self.t = 0
        def start(self): self.t = time.time()
        def end(self, label=""):
            if self.enabled:
                print(f"[bench {label}] {(time.time() - self.t) * 1000:.1f}ms")
        def __getattr__(self, _n): return lambda *a, **kw: None

    mod.benchmark = _Bench
    return mod


# ---------------------------------------------------------------------------
# jp_input / ls — tiny stubs pem.py pulls in
# ---------------------------------------------------------------------------

def make_jp_input() -> types.ModuleType:
    mod = types.ModuleType("jp_input")
    class _JpInput:
        def __init__(self, *a, **kw): pass
        def __getattr__(self, _n): return lambda *a, **kw: None
    mod.jp_input = _JpInput
    return mod


def make_ls() -> types.ModuleType:
    mod = types.ModuleType("ls")
    def ls_main(*a, **kw): return []
    mod.ls = ls_main
    return mod


# ---------------------------------------------------------------------------
# MicroPython const() builtin — pem.py uses it at module scope
# ---------------------------------------------------------------------------

def patch_builtins() -> None:
    import builtins
    if not hasattr(builtins, "const"):
        builtins.const = lambda x: x


# ---------------------------------------------------------------------------
# Install all stubs
# ---------------------------------------------------------------------------

def install_all() -> None:
    """Install every shim module into sys.modules."""
    patch_builtins()

    # pdeck and related
    from . import fake_pdeck
    sys.modules["pdeck"] = fake_pdeck

    sys.modules["pdeck_utils"] = make_pdeck_utils()
    sys.modules["audio"] = make_audio()
    sys.modules["xbmreader"] = make_xbmreader()
    sys.modules["esclib"] = make_esclib()
    sys.modules["overlay"] = make_overlay()
    sys.modules["benchmark"] = make_benchmark()
    sys.modules["jp_input"] = make_jp_input()
    sys.modules["ls"] = make_ls()
