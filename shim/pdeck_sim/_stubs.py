"""_stubs.py — minimal shims for the smaller device modules that apps import.

We inject each of these into sys.modules under its real name. None of them
do anything interesting on desktop, but making them importable keeps user
apps running without code changes.
"""
from __future__ import annotations

import os
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
        from .shim_log import log
        log("pdeck_utils", f"launch ignored: {command} -> scr {screen_num}")

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
        "power": False,  # audio.power() — codec on/off
    }

    def _warn_once():
        if not _warned["value"]:
            from .shim_log import warn
            warn("audio",
                 "audio calls are stubbed — no sound output.",
                 stacklevel=3)
            _warned["value"] = True

    def sample_rate(rate=None):
        _warn_once()
        if rate is not None:
            _state["sample_rate"] = int(rate)
        return _state["sample_rate"]

    def power(state=None):
        """Audio power on/off. setter: power(True); getter: power().

        On the deck this controls the audio codec's power rail. On the
        shim it's just a tracked boolean — affects nothing audible (we
        don't produce audio either way) but apps that read it back via
        e.g. home.py's `set_audio_power()` need a coherent answer."""
        _warn_once()
        if state is not None:
            _state["power"] = bool(state)
        return _state["power"]

    def get_current_tick():
        """Returns simulated audio tick — sample count since 'start'.

        Real device: hardware-counted samples since boot. Stub: derived
        from wall-clock time × current sample rate. Close enough that
        Pattern-driven loops advance through their cycles in roughly
        the BPM-correct timeline, which is the only thing apps observe.
        """
        # Producer hook: this being called is our signal that an audio
        # engine is running. The debug panel uses last_audio_tick to
        # decide whether to show the audio indicator as active.
        from .debug_state import get_debug_state
        get_debug_state().note_audio_tick()
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
    mod.power = power
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
            from .shim_log import warn
            warn("pie",
                 "pie sequencer is stubbed — patterns advance "
                 "in time but produce no sound.",
                 stacklevel=3)
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

        Bit order: standard XBM is LSB-first on disk, but the deck's
        xbmreader bit-reverses each byte to MSB-first (so the blitter
        only ever sees one convention). We do the same.
        """
        from .paths import translate
        host_path = translate(path)
        # Preserve the original basename as the XBM's `name` field — apps
        # don't expect to see the translated host path reflected back.
        name = Path(path).stem
        try:
            text = Path(host_path).read_text()
        except FileNotFoundError:
            from .shim_log import warn
            warn("xbmreader",
                 f"XBM not found: {path} -> {host_path}. "
                 f"Set POCKETDECK_ROOT or populate ~/.pocketdeck-root/. "
                 f"Returning empty image.",
                 stacklevel=2)
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
                # Bit-reverse to convert XBM's LSB-first to deck's MSB-first
                b = int(tok, 0) & 0xFF
                b = (((b & 0x80) >> 7) | ((b & 0x40) >> 5) |
                     ((b & 0x20) >> 3) | ((b & 0x10) >> 1) |
                     ((b & 0x08) << 1) | ((b & 0x04) << 3) |
                     ((b & 0x02) << 5) | ((b & 0x01) << 7))
                data.append(b)
            except ValueError:
                pass
        return (name, width, height, bytes(data), 1)

    def scale(image: tuple, factor: int) -> tuple:
        """Scale an XBM up by integer factor, 1bpp nearest-neighbor.

        Operates on MSB-first packed data (deck convention)."""
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
                # MSB-first: bit 7 is leftmost
                bit = (b >> (7 - (sx & 7))) & 1
                if bit:
                    out[y * dst_stride + (x >> 3)] |= (0x80 >> (x & 7))
        return (name, new_w, new_h, bytes(out), frames)

    def read_xbmr(path: str) -> tuple:
        # XBMR is the deck's binary format. We don't parse it; apps that use
        # it will get an empty image. Add a parser here if needed.
        from .shim_log import warn
        warn("xbmreader", f"read_xbmr('{path}') stubbed")
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
# micropython — MicroPython's builtin module providing decorators and
# intrinsics for performance optimization.
#
# What's there:
#   - @micropython.viper, @micropython.native, @micropython.asm_thumb:
#     decorators that on the device tell the compiler to use special
#     codegen paths. On CPython we make them pass-throughs.
#   - micropython.const(): wraps a constant for the compiler to inline.
#     We expose this via patch_builtins() too, but apps that explicitly
#     `import micropython` and use `micropython.const` need it here.
#   - ptr8, ptr16, ptr32: type hints used INSIDE viper-decorated functions
#     to declare typed memory pointers. On the device these are compiler
#     intrinsics; on CPython we make them identity functions so code like
#     `table = ptr32(arr)` then `table[i]` still works (arr already
#     supports indexing).
#
# The trick: `ptr8`/`ptr16`/`ptr32` are referenced as free variables
# inside viper-decorated function bodies. They aren't imported by the
# user's module — they're injected by viper at decoration time on the
# device. To make this work on CPython, our @viper decorator patches
# the decorated function's __globals__ to include these names. When the
# function executes, Python looks them up in the function's globals
# (per the LEGB rule) and finds our identity functions.
# ---------------------------------------------------------------------------

def _identity(x):
    """Identity function used for ptr8/ptr16/ptr32 stand-ins on CPython.

    On the deck these convert an array/bytearray into a typed pointer
    for fast indexing. On CPython, the array already supports indexing
    natively, so we just return it unchanged.
    """
    return x


def _viper_decorator(fn):
    """Pass-through decorator that injects viper intrinsics into the
    function's globals.

    On the device this would compile fn to native code with type-aware
    pointer access. On CPython we just inject the names viper code
    references (ptr8, ptr16, ptr32) into the function's globals so the
    function body can execute as plain Python.
    """
    # Inject pointer-conversion intrinsics into the function's module-level
    # globals. setdefault is critical here — we must NOT overwrite a name
    # the user's module has defined intentionally (unlikely, but be safe).
    globs = fn.__globals__
    globs.setdefault("ptr8", _identity)
    globs.setdefault("ptr16", _identity)
    globs.setdefault("ptr32", _identity)
    return fn


def _native_decorator(fn):
    """Pass-through. On the device, compiles fn to native CPU code. On
    CPython, no-op."""
    return fn


def _asm_thumb_decorator(fn):
    """Pass-through. On ARM Cortex-M devices this is inline assembly;
    we'd need to actually parse and emulate the assembly to run such
    functions on CPython. None of the deck's apps appear to use this,
    but stub it anyway so any future use doesn't crash at decoration."""
    return fn


def make_micropython() -> types.ModuleType:
    """Stub for the deck's `micropython` builtin module."""
    mod = types.ModuleType("micropython")
    mod.viper = _viper_decorator
    mod.native = _native_decorator
    mod.asm_thumb = _asm_thumb_decorator
    mod.const = lambda x: x
    # alloc_emergency_exception_buf is for memory-pressure handling on
    # constrained devices. Irrelevant on CPython but stub it for compat.
    mod.alloc_emergency_exception_buf = lambda n: None
    # mem_info / qstr_info are diagnostics. No-ops on desktop.
    mod.mem_info = lambda *a, **kw: None
    mod.qstr_info = lambda *a, **kw: None
    return mod


# ---------------------------------------------------------------------------
# re_test — opaque stub
#
# Imported by lib/examples/dither_test.py but never referenced. Almost
# certainly a leftover from Nunomo's internal regression-test harness:
# their automated runs presumably ship a `re_test` module that activates
# frame-capture or timing instrumentation, while the example itself
# works fine without those hooks. On a normal device or developer Mac,
# the import fails because the module isn't part of the public deck
# distribution.
#
# We provide a minimal module so the import succeeds. No attribute
# access from the example file ever reaches it — but if a future
# example actually does reference re_test.something, the __getattr__
# returns a no-op so it won't crash.
# ---------------------------------------------------------------------------

def make_re_test() -> types.ModuleType:
    """Empty placeholder for Nunomo's private regression-test harness."""
    mod = types.ModuleType("re_test")
    # If anything ever tries to access an attribute, return a no-op
    # callable rather than AttributeError-ing.
    class _Anything:
        def __getattr__(self, _n): return lambda *a, **kw: None
        def __call__(self, *a, **kw): return None
    mod.__getattr__ = lambda name: _Anything()  # type: ignore[attr-defined]
    return mod


# ---------------------------------------------------------------------------
# dsplib — DSP/3D math native module
#
# A real C native module on the deck providing matrix math (matrix_mul_f32,
# matrix_mul_s16) and 3D projection helpers (project_3d_indexed,
# project_2d_indexed, set_transform_matrix_4x4, sort_indices). These are
# used by graphics-heavy examples like dither_test, sphere_test, cube_test,
# bounce_sphere, zen_chamber.
#
# Implementing this faithfully on desktop would require numpy or careful
# pure-Python matrix math. For the shim's smoke-test goal we provide
# math-correct implementations of the matrix multiplications (the DSP
# operations dither_test actually uses) and stubs for the 3D pipeline
# that write zeros to output buffers without crashing. Apps using the 3D
# pipeline will run but produce blank/incorrect visuals — same fate as
# audio examples without the audio engine.
# ---------------------------------------------------------------------------

def make_dsplib() -> types.ModuleType:
    """Stub for the deck's `dsplib` C native module.

    Provides math-correct matrix_mul_f32 and matrix_mul_s16 so dither_test
    and zen_chamber rotate their geometry as intended. The 3D-projection
    functions are no-ops — apps using the indexed 3D pipeline will run
    but render nothing.
    """
    mod = types.ModuleType("dsplib")

    def matrix_mul_f32(A, B, m, n, k, C=None):
        """Multiply A (m x n floats) by B (n x k floats), result m x k floats.

        On the deck this is a viper-optimized C function. Pure Python here.
        If C is None, allocate and return a new array. If C is provided,
        write into it.
        """
        import array
        if C is None:
            C = array.array('f', [0.0] * (m * k))
        for i in range(m):
            for j in range(k):
                s = 0.0
                for x in range(n):
                    s += A[i * n + x] * B[x * k + j]
                C[i * k + j] = s
        return C

    def matrix_mul_s16(A, B, m, n, k, shift, C):
        """Fixed-point 16-bit matrix multiply with right-shift after sum.

        A is (m x n) signed int16; B is (n x k) signed int16; C is (m x k).
        After accumulating the int32 sum, shift right by `shift` bits to
        produce a fixed-point result. This is what the deck's int16 path
        does for fast rotation in dither_test.
        """
        for i in range(m):
            for j in range(k):
                s = 0
                for x in range(n):
                    s += int(A[i * n + x]) * int(B[x * k + j])
                # Arithmetic shift, clamp to int16 range
                s = s >> shift
                if s > 32767: s = 32767
                elif s < -32768: s = -32768
                C[i * k + j] = s
        return C

    def set_transform_matrix_4x4(matrix, rotation, position, scale):
        """Build a 4x4 transform from rotation/position/scale. No-op stub
        — fills the matrix with identity, which means apps using it for
        3D rendering will see un-rotated, un-translated output. Visuals
        will be wrong but the app won't crash."""
        # Identity 4x4 in row-major order
        identity = [1.0, 0.0, 0.0, 0.0,
                    0.0, 1.0, 0.0, 0.0,
                    0.0, 0.0, 1.0, 0.0,
                    0.0, 0.0, 0.0, 1.0]
        for i in range(min(16, len(matrix))):
            matrix[i] = identity[i]

    def set_transform_matrix_3x3(matrix, rotation, position, scale):
        """3x3 2D transform stub. Fills with identity."""
        identity = [1.0, 0.0, 0.0,
                    0.0, 1.0, 0.0,
                    0.0, 0.0, 1.0]
        for i in range(min(9, len(matrix))):
            matrix[i] = identity[i]

    def project_3d_indexed(*a, **kw):
        """3D projection — stub. The output buffers are not populated,
        so the deck's `draw_3d_faces(points, indices, dither)` will draw
        whatever happened to be in the buffer at allocation time."""
        # In a future round we could implement this against the actual
        # geometry math, but it's a substantial effort and only matters
        # for cube/sphere/etc tests.
        return None

    def project_2d_indexed(*a, **kw):
        return None

    def sort_indices(indices, depths, start_id=None):
        """Sort indices by depth descending. Useful enough that we
        implement it correctly — small data, no perf concern."""
        if start_id is not None:
            for i in range(len(indices)):
                indices[i] = start_id + i
        # Pair, sort by depth desc, write back
        n = min(len(indices), len(depths))
        pairs = sorted(
            ((int(indices[i]), int(depths[i])) for i in range(n)),
            key=lambda p: -p[1],
        )
        for i, (idx, _) in enumerate(pairs):
            indices[i] = idx

    mod.matrix_mul_f32 = matrix_mul_f32
    mod.matrix_mul_s16 = matrix_mul_s16
    mod.set_transform_matrix_4x4 = set_transform_matrix_4x4
    mod.set_transform_matrix_3x3 = set_transform_matrix_3x3
    mod.project_3d_indexed = project_3d_indexed
    mod.project_2d_indexed = project_2d_indexed
    mod.sort_indices = sort_indices
    return mod


# ---------------------------------------------------------------------------
# MicroPython const() builtin — pem.py uses it at module scope
# ---------------------------------------------------------------------------

def patch_builtins() -> None:
    """Inject MicroPython-style names into builtins.

    Two things are added:

    1. `const(x)` — MicroPython's constant-folding hint. CPython doesn't
       optimize this, but having the builtin available prevents
       NameError when modules use it without `from micropython import const`.

    2. `micropython` — the MicroPython-builtin module. Some deck library
       files (notably dsp_utils.py) use `@micropython.viper` as a
       module-level decorator without doing `import micropython` first.
       This works on the device because MicroPython's interpreter
       provides the name implicitly. We mimic that here.
    """
    import builtins
    if not hasattr(builtins, "const"):
        builtins.const = lambda x: x
    if not hasattr(builtins, "micropython"):
        # Lazy-construct the micropython module so this function stays
        # cheap to call. The module gets registered in sys.modules in
        # install_all() too — for the case where code DOES do
        # `import micropython` explicitly (like wav_loader.py).
        builtins.micropython = make_micropython()


# ---------------------------------------------------------------------------
# MicroPython time extensions
#
# MicroPython adds ticks_ms, ticks_us, ticks_diff, sleep_ms, sleep_us to the
# stdlib `time` module. CPython's time module is otherwise the same, so we
# extend the real module rather than shadowing it — no import-cycle risk,
# no surprise when an app does `import time as t; t.time()`.
#
# Wrap behavior: MicroPython's ticks counters wrap at 2**30 on most ports.
# Apps that use ticks_diff() correctly handle the wrap; apps that subtract
# directly can break around the wrap point. We match the device's wrap so
# that any app sensitive to wrap behavior fails the same way in both
# environments rather than only in one.
# ---------------------------------------------------------------------------

# 2**30 — matches MicroPython's typical port. Apps shouldn't depend on the
# exact value, only that it wraps; but if one ever does, this is the
# constant they're seeing.
_TICKS_PERIOD = 1 << 30
_TICKS_HALF_PERIOD = _TICKS_PERIOD >> 1


def patch_time_module() -> None:
    """Add MicroPython's ticks_*/sleep_* helpers to the stdlib `time` module.

    Idempotent: re-running install_all() doesn't double-patch. Skips any
    name that already exists, so if a future CPython release adds a real
    `ticks_us` (unlikely), we wouldn't shadow it.
    """
    import time as _t

    if not hasattr(_t, "ticks_us"):
        def ticks_us():
            """Microsecond counter, wraps at 2**30. MicroPython-compatible."""
            return int(_t.monotonic() * 1_000_000) & (_TICKS_PERIOD - 1)
        _t.ticks_us = ticks_us  # type: ignore[attr-defined]

    if not hasattr(_t, "ticks_ms"):
        def ticks_ms():
            """Millisecond counter, wraps at 2**30. MicroPython-compatible."""
            return int(_t.monotonic() * 1_000) & (_TICKS_PERIOD - 1)
        _t.ticks_ms = ticks_ms  # type: ignore[attr-defined]

    if not hasattr(_t, "ticks_diff"):
        def ticks_diff(a, b):
            """Signed delta between two tick values, accounting for wrap.

            Returns the smallest signed integer d such that (b + d) wraps
            to a within the period. This is the canonical MicroPython
            semantic and the only correct way to compare ticks.
            """
            d = (a - b) & (_TICKS_PERIOD - 1)
            # If d is in the upper half of the range, it represents a
            # negative delta (a is "before" b in modular time)
            if d >= _TICKS_HALF_PERIOD:
                d -= _TICKS_PERIOD
            return d
        _t.ticks_diff = ticks_diff  # type: ignore[attr-defined]

    if not hasattr(_t, "ticks_add"):
        def ticks_add(ticks, delta):
            """Add delta to ticks, with wrap. Inverse of ticks_diff."""
            return (ticks + delta) & (_TICKS_PERIOD - 1)
        _t.ticks_add = ticks_add  # type: ignore[attr-defined]

    if not hasattr(_t, "sleep_ms"):
        def sleep_ms(n):
            """Sleep for n milliseconds."""
            _t.sleep(n / 1000.0)
        _t.sleep_ms = sleep_ms  # type: ignore[attr-defined]

    if not hasattr(_t, "sleep_us"):
        def sleep_us(n):
            """Sleep for n microseconds. CPython's time.sleep is at best
            millisecond-accurate on most OSes, so very short sleeps may be
            quantized — this matches a busy-loop expectation poorly but is
            the standard CPython contract."""
            _t.sleep(n / 1_000_000.0)
        _t.sleep_us = sleep_us  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# MicroPython struct module — lenient buffer length
#
# CPython's struct.unpack(fmt, buf) requires len(buf) == struct.calcsize(fmt)
# exactly. MicroPython is more lenient — extra bytes past the expected size
# are silently ignored. This shows up in deck library code like:
#
#     header = struct.unpack("<hhhh", content)   # content is the WHOLE file
#
# This works on the device because MicroPython truncates `content` to 8
# bytes implicitly. CPython raises `struct.error: unpack requires a buffer
# of 8 bytes` because it sees a length mismatch.
#
# We match MicroPython's behavior by wrapping struct.unpack to truncate
# oversized buffers down to calcsize(fmt) before delegating to CPython's
# real unpack. Undersized buffers still raise — that's a real error in
# either environment.
# ---------------------------------------------------------------------------

_struct_patches_installed = False


def patch_struct_module() -> None:
    """Make struct.unpack accept buffers larger than the format expects.

    Idempotent: re-running install_all() doesn't double-wrap. Tracking
    via a module-level flag.

    Why wrap unpack and not pack? `struct.pack` with too many arguments
    already errors uniformly across CPython and MicroPython. The
    asymmetric leniency is specifically on the unpack/decode side, where
    MicroPython treats the buffer as "at least N bytes" while CPython
    treats it as "exactly N bytes". We only fix the lenient side.
    """
    global _struct_patches_installed
    if _struct_patches_installed:
        return

    import struct

    _real_unpack = struct.unpack
    _real_unpack_from = struct.unpack_from
    _real_calcsize = struct.calcsize

    def _lenient_unpack(fmt, buffer):
        """MicroPython-style: silently truncate oversized buffers."""
        expected = _real_calcsize(fmt)
        if len(buffer) > expected:
            buffer = buffer[:expected]
        return _real_unpack(fmt, buffer)

    _lenient_unpack.__wrapped__ = _real_unpack  # type: ignore[attr-defined]
    struct.unpack = _lenient_unpack

    # unpack_from already accepts an offset+length pair, so it's already
    # tolerant of larger buffers. Don't wrap it. But document the choice
    # so future-me doesn't wonder why only one was patched.

    _struct_patches_installed = True


# ---------------------------------------------------------------------------
# Install all stubs
# ---------------------------------------------------------------------------

# Modules that have no real-Python equivalent — these are C native modules
# in the deck firmware. The shim must always provide stubs because there's
# nothing to load from disk.
_ALWAYS_SHIM = {
    "pdeck": None,         # special: comes from fake_pdeck submodule
    "audio": None,
    "pie": None,
    "dsplib": None,
    "re_test": None,       # opaque private harness
    "micropython": None,   # MicroPython builtin module
}

# Modules where a real .py exists in the deck repo (under /sd/lib). The
# shim provides a fallback for cases where POCKETDECK_ROOT isn't set or
# isn't populated, but if the real source is reachable on disk we prefer
# it — closer to device behavior, eliminates shim/device drift.
#
# Each entry maps module name -> factory that produces the fallback stub.
_FALLBACK_SHIM = {
    "pdeck_utils": "make_pdeck_utils",
    "xbmreader":   "make_xbmreader",
    "esclib":      "make_esclib",
    "overlay":     "make_overlay",
    "benchmark":   "make_benchmark",
    "jp_input":    "make_jp_input",
    "ls":          "make_ls",
}


def _real_module_available_on_deck_path(module_name: str, deck_paths: list) -> bool:
    """Check if a module file exists in any of the deck library paths.

    Looks for `<module_name>.py` or `<module_name>.mpy` under each given
    path. Doesn't actually import — just checks file presence. Used to
    decide whether to install a fallback stub.
    """
    for path in deck_paths:
        for ext in (".py", ".mpy"):
            candidate = os.path.join(path, module_name + ext)
            if os.path.isfile(candidate):
                return True
    return False


def install_all() -> None:
    """Install shim stubs into sys.modules and extend sys.path with deck
    library directories.

    Three categories of modules:
      1. Always-shim (pdeck, audio, pie, dsplib, re_test): no real-Python
         equivalent exists. Stub unconditionally.
      2. Fallback-shim (xbmreader, esclib, etc.): real .py exists in the
         deck repo. If reachable via $POCKETDECK_ROOT/sd/lib, leave alone
         and let normal imports find the real one. Otherwise, install
         stub fallback.
      3. CPython stdlib (math, time, struct, etc.): never touched. Time
         module gets MicroPython extensions (ticks_*) added in
         patch_time_module.

    The deck-faithful priority order (sd/py before sd/lib) is established
    by prepending those paths to sys.path here. User app modules get
    their own directory added to sys.path by the runner separately.
    """
    patch_builtins()
    patch_time_module()
    patch_struct_module()

    # Install path translation for builtins.open/os.stat/os.listdir so
    # deck library code can use deck-absolute paths transparently. This
    # is what lets the real /sd/lib/xbmreader.py read /sd/lib/data/*.xbmr
    # without modification — its open() call gets routed through the
    # translation layer before reaching the host filesystem.
    from .paths import install_path_translation_in_builtins
    install_path_translation_in_builtins()

    # Establish the deck's MicroPython sys.path priority. We prepend so
    # they take priority over CPython stdlib (matters for things like
    # `pathlib.mpy` which the deck ships under that name even though
    # CPython has its own `pathlib`). Within these two, /sd/py is first
    # so user overrides win, exactly as on device.
    from .paths import get_deck_library_paths
    deck_paths = get_deck_library_paths()
    for p in reversed(deck_paths):
        if p not in sys.path:
            sys.path.insert(0, p)

    # Always-shim modules — install unconditionally.
    from . import fake_pdeck
    sys.modules["pdeck"] = fake_pdeck
    sys.modules["audio"] = make_audio()
    sys.modules["pie"] = make_pie()
    sys.modules["dsplib"] = make_dsplib()
    sys.modules["re_test"] = make_re_test()
    # micropython: reuse the same instance patched into builtins so that
    # `import micropython` and the implicit-builtins access return the
    # same object. Otherwise a module that does `import micropython` and
    # one that uses bare `@micropython.viper` would get two different
    # objects, which is fine functionally but confusing if anyone debugs
    # by `id()`.
    import builtins
    sys.modules["micropython"] = builtins.micropython

    # Fallback-shim modules — only install if the real one isn't on disk.
    # Skipping installation here lets Python's normal import machinery
    # find the real .py via the sys.path entries we just added.
    for mod_name, factory_name in _FALLBACK_SHIM.items():
        if _real_module_available_on_deck_path(mod_name, deck_paths):
            # Real source is reachable — let imports find it naturally.
            # Don't pre-register a stub.
            continue
        # No real source — install fallback stub.
        factory = globals()[factory_name]
        sys.modules[mod_name] = factory()
