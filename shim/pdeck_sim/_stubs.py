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
        """Force-reload a module from source. Equivalent to the real
        pdeck_utils.reimport on device.

        invalidate_caches() is required: Python caches the "finders" that
        map module names to source paths, and without this call, a brand-
        new module file on sys.path might not be picked up until the next
        process start. Also handles the case where a module was written,
        imported, then rewritten — without the invalidate, the importer
        may hand back the previously-loaded code.
        """
        importlib.invalidate_caches()
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
    """Stub for the deck's `audio` module.

    The deck's audio module is implemented in native C against ESP32
    hardware. We can't reasonably reproduce it on a Mac, so this stub
    provides API-shape compatibility: methods exist with the right
    signatures and return plausible values, but no sound is produced.

    Two pieces of state matter for pattern_example.py and friends:

    1. `sample_rate(rate)` is a setter; `sample_rate()` is a getter.
       Pattern timing depends on this value, so we track it.

    2. `get_current_tick()` must advance over wall-clock time. The
       Pie sequencer uses tick deltas to decide when to advance to
       the next cycle. A static tick deadlocks any pattern loop.

    All other audio module classes (sampler, wavetable, router,
    reverb, compressor, filter, echo, mixer) are accept-anything
    no-op classes with __enter__/__exit__ for context-manager use.
    """
    mod = types.ModuleType("audio")
    _warned = {"value": False}
    _state = {
        "sample_rate": 24000,
        "start_time": time.monotonic(),
    }

    def _warn_once():
        if not _warned["value"]:
            warnings.warn(
                "[pdeck_sim] audio calls are stubbed — no sound output.",
                stacklevel=3,
            )
            _warned["value"] = True

    def sample_rate(rate=None):
        _warn_once()
        if rate is not None:
            _state["sample_rate"] = int(rate)
        return _state["sample_rate"]

    def get_current_tick():
        """Returns simulated audio tick — sample count since 'start'.

        Real device: hardware-counted samples since boot. Stub: derived
        from wall-clock time × current sample rate. Close enough that
        Pattern-driven loops advance through their cycles in roughly
        the BPM-correct timeline, which is the only thing apps observe.
        """
        elapsed = time.monotonic() - _state["start_time"]
        return int(elapsed * _state["sample_rate"])

    class _NoopAudioModule:
        """Generic placeholder for audio.sampler / wavetable / etc.

        Accepts any positional/keyword args, supports `with`, and has
        every method return None or a sensible default. Avoids needing
        to enumerate every method the apps might call.
        """
        def __init__(self, *a, **kw):
            _warn_once()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def __getattr__(self, name):
            # Sensible defaults for the few methods whose return value
            # the app actually inspects:
            if name == "load_wavetable":
                # Returns the number of frames loaded
                return lambda *a, **kw: 32
            if name == "load_wav":
                return lambda *a, **kw: 0
            # Everything else: return-None no-op
            return lambda *a, **kw: None

    mod.sample_rate = sample_rate
    mod.get_current_tick = get_current_tick
    # Expose the stub class under every name apps construct from.
    for name in ("sampler", "wavetable", "router", "reverb",
                 "compressor", "filter", "echo", "mixer"):
        setattr(mod, name, _NoopAudioModule)
    return mod


# ---------------------------------------------------------------------------
# pie — the Pocket Deck pattern sequencer
# ---------------------------------------------------------------------------

def make_pie() -> types.ModuleType:
    """Stub for the deck's `pie` module.

    Pie is a wavetable-synth pattern sequencer with a TidalCycles-inspired
    mini-DSL. It's pure Python on top of the C `audio` module on device.
    In principle we could ship the real `pie.py` here unmodified, since
    its only external dependency is `audio` which we already stub —
    but the real Pattern parser is heavy and would just produce silent
    output anyway. The stub provides:

      - All Pie* classes as context managers with no-op methods.
      - A Pattern object whose chaining methods (.strum(), .scale(),
        .transpose(), .clip(), .fast(), .slow()) all return self.
      - A Pie sequencer with playing_cycle that advances over wall-clock
        time at the configured BPM, so apps that loop on cycle progression
        actually advance through their patterns.

    The result: audio examples run to completion silently, exercising
    their control-flow logic. Useful as a smoke test that the example
    imports cleanly and doesn't crash on its setup phase.
    """
    mod = types.ModuleType("pie")
    _warned = {"value": False}

    def _warn_once():
        if not _warned["value"]:
            warnings.warn(
                "[pdeck_sim] pie sequencer is stubbed — patterns advance "
                "in time but produce no sound.",
                stacklevel=3,
            )
            _warned["value"] = True

    class _Pattern:
        """Fluent no-op pattern. Every modifier returns self."""
        def __init__(self, data=None, preprocess=None):
            self._str = data if isinstance(data, str) else None
            self._data = data

        # Chainable modifiers. All return self so .strum().scale()... works.
        def fast(self, n): return self
        def slow(self, n): return self
        def clip(self, n): return self
        def strum(self, n): return self
        def scale(self, s): return self
        def transpose(self, n): return self

        def clear_cache(self): pass

        def get_events(self, cycle=0): return []

        def print_str(self): return self._str or ""

    class _Pie:
        """Sequencer with a wall-clock-driven playing_cycle.

        Real device: cycle = (audio_tick - base_tick) / cycle_samples.
        Stub: cycle = (now - start) * bpm / 60 / 4. Same semantics,
        different clock source. This makes `check_cycle()` in apps
        actually progress instead of looping forever.
        """
        def __init__(self, bpm=120, startup_delay_ms=100):
            _warn_once()
            self.bpm = bpm
            self.startup_delay_ms = startup_delay_ms
            self.patterns = []
            self._running = False
            self._start_time = None

        def __enter__(self):
            self.start()
            return self

        def __exit__(self, *a):
            self.stop()
            return False

        def start(self):
            self._running = True
            self._start_time = time.monotonic()

        def stop(self):
            self._running = False

        @property
        def playing_cycle(self):
            if not self._running or self._start_time is None:
                return 0
            elapsed = time.monotonic() - self._start_time
            # 4 beats per cycle; bpm beats per minute.
            return elapsed * self.bpm / 60.0 / 4.0

        def get_tick_from_cycle(self, cycle):
            return int(cycle * 24000 * 60 / self.bpm * 4)

        def pattern(self, instrument, data):
            return _Pattern(data)

        def add(self, instrument, pattern):
            self.patterns.append((instrument, pattern))
            return len(self.patterns) - 1

        def remove(self, index):
            if 0 <= index < len(self.patterns):
                del self.patterns[index]
            return index

        def update(self, index, pattern):
            if 0 <= index < len(self.patterns):
                self.patterns[index] = (self.patterns[index][0], pattern)
                return index
            return -1

        def clear(self):
            self.patterns = []

        def process_event(self):
            pass  # No real audio engine to drive

    class _PieInstrument:
        """Base for PieWavetable, PieReverb, PieRouter, PieCompressor, etc.

        All Pie* wrappers expose a `dev` attribute that delegates to the
        underlying audio.* object. We provide a no-op `dev` and accept
        any method call.
        """
        def __init__(self, *a, **kw):
            _warn_once()
            self.dev = _PieDev()

        def __enter__(self): return self
        def __exit__(self, *a): return False

        def __getattr__(self, name):
            if name == "load_wavetable":
                return lambda *a, **kw: 32  # apps use the return value
            return lambda *a, **kw: None

    class _PieDev:
        """No-op stand-in for Pie*.dev.

        Apps poke methods like `wv.dev.set_adsr(...)`, `comp.dev.active(True)`.
        We accept everything.
        """
        def __getattr__(self, name):
            return lambda *a, **kw: None

    mod.Pie = _Pie
    mod.Pattern = _Pattern
    # All instrument/effect wrappers share the same no-op behavior
    for name in ("PieSampler", "PieWavetable", "PieReverb", "PieRouter",
                 "PieCompressor", "PieFilter", "PieEcho", "PieMixer"):
        setattr(mod, name, _PieInstrument)
    return mod


# ---------------------------------------------------------------------------
# xbmreader — read XBM files into (name, w, h, data, frames) tuples
# ---------------------------------------------------------------------------

def make_xbmreader() -> types.ModuleType:
    mod = types.ModuleType("xbmreader")

    def read(path: str) -> tuple:
        """Parse a .xbm file. Returns (name, width, height, bytes, 1).

        Deck paths like /sd/lib/data/ghost1.xbm are rewritten to the host
        filesystem via pdeck_sim.paths.translate().
        """
        from .paths import translate
        host_path = translate(path)
        # Preserve the original basename as the XBM's `name` field — apps
        # don't expect to see the translated host path reflected back.
        name = Path(path).stem
        try:
            text = Path(host_path).read_text()
        except FileNotFoundError:
            import warnings
            warnings.warn(
                f"[pdeck_sim] XBM not found: {path} -> {host_path}. "
                f"Set POCKETDECK_ROOT or populate ~/.pocketdeck-root/. "
                f"Returning empty image.",
                stacklevel=2,
            )
            return (name, 0, 0, b"", 1)
        # XBM looks like:
        #   #define foo_width 16
        #   #define foo_height 16
        #   static char foo_bits[] = { 0x00, 0x01, ... };
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
    sys.modules["pie"] = make_pie()
    sys.modules["xbmreader"] = make_xbmreader()
    sys.modules["esclib"] = make_esclib()
    sys.modules["overlay"] = make_overlay()
    sys.modules["benchmark"] = make_benchmark()
    sys.modules["jp_input"] = make_jp_input()
    sys.modules["ls"] = make_ls()
