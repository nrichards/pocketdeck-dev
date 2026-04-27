"""Tests for the micropython module stub and the audio.power addition.

micropython is a MicroPython builtin module — provides decorators for
performance optimization (viper, native, asm_thumb), the const() helper,
and intrinsics like ptr8/ptr16/ptr32 used inside viper-decorated functions.

audio.power() is the codec power on/off; setter and getter.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import warnings

import pytest

from pdeck_sim import _stubs
_stubs.install_all()


# ---------------------------------------------------------------------------
# micropython module
# ---------------------------------------------------------------------------

def test_micropython_module_imports():
    """The whole point: import works."""
    import micropython
    assert micropython is not None

def test_micropython_available_in_builtins():
    """Some deck files (dsp_utils.py) use @micropython.viper at module
    scope without `import micropython`. The deck makes it available
    implicitly; we mimic that by adding it to builtins."""
    import builtins
    assert hasattr(builtins, "micropython")

def test_viper_decorator_is_passthrough():
    """@micropython.viper should leave the decorated function functional
    on CPython, just without the native-code optimization."""
    import micropython

    @micropython.viper
    def doubled(x: int) -> int:
        return x * 2

    assert doubled(5) == 10
    assert doubled(0) == 0

def test_native_decorator_is_passthrough():
    import micropython

    @micropython.native
    def square(x: int) -> int:
        return x * x

    assert square(7) == 49

def test_viper_decorator_injects_ptr_intrinsics():
    """Inside a viper-decorated function, ptr8/ptr16/ptr32 should resolve
    to identity functions. This is how dsp_utils.py's fp_sin_d works:

        @micropython.viper
        def fp_sin_d(index: int) -> int:
            table: ptr32 = ptr32(fp_sin_table)
            ...
    """
    import micropython
    import array

    table = array.array('i', [10, 20, 30, 40])

    @micropython.viper
    def lookup(index: int) -> int:
        # ptr32 should be available in this function's scope as identity
        t = ptr32(table)  # noqa: F821 (injected by decorator)
        return int(t[index])

    assert lookup(0) == 10
    assert lookup(2) == 30

def test_micropython_const():
    """const() is a hint for the MicroPython compiler; on CPython it's
    a pass-through."""
    import micropython
    X = micropython.const(42)
    assert X == 42

def test_micropython_const_in_builtins():
    """const() is also injected into builtins because some modules use
    it at module scope without importing."""
    import builtins
    assert hasattr(builtins, "const")
    assert builtins.const(99) == 99

def test_dsp_utils_style_pattern_works():
    """End-to-end: replicate the exact pattern from dsp_utils.py — a
    bare `@micropython.viper` decorator at module scope without
    `import micropython`. This is what was failing for dither_test.py."""
    # We can't easily test "no import statement" inline in a test, but
    # we can verify that micropython is reachable from a module that
    # didn't import it. This works because patch_builtins() puts it on
    # builtins.
    code = """
@micropython.viper
def viper_func(x: int) -> int:
    return x + 1
result = viper_func(41)
"""
    namespace = {}  # No imports; relies on builtins
    exec(code, namespace)
    assert namespace['result'] == 42


# ---------------------------------------------------------------------------
# audio.power
# ---------------------------------------------------------------------------

def test_audio_power_setter_and_getter():
    """audio.power(True) sets, audio.power() gets."""
    import audio
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        audio.power(True)
        assert audio.power() is True
        audio.power(False)
        assert audio.power() is False

def test_audio_power_initial_value():
    """Without explicit setting, power should be False (codec off)."""
    # Force a fresh audio module
    from pdeck_sim._stubs import make_audio
    fresh = make_audio()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert fresh.power() is False
