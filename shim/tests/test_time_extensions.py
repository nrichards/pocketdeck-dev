"""Tests for the MicroPython time module extensions.

CPython's time module is missing ticks_us, ticks_ms, ticks_diff, ticks_add,
sleep_ms, and sleep_us — all MicroPython-specific. We patch the real time
module rather than creating a separate stub, so apps that do `import time`
or `from time import sleep_ms` both work.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import time

import pytest

from pdeck_sim import _stubs
_stubs.install_all()

# Pull the constant for tests that need to know the wrap value
from pdeck_sim._stubs import _TICKS_PERIOD


# ---------------------------------------------------------------------------
# Presence
# ---------------------------------------------------------------------------

def test_ticks_functions_exist():
    """All MicroPython ticks_* functions are now on the time module."""
    assert callable(time.ticks_us)
    assert callable(time.ticks_ms)
    assert callable(time.ticks_diff)
    assert callable(time.ticks_add)
    assert callable(time.sleep_ms)
    assert callable(time.sleep_us)


# ---------------------------------------------------------------------------
# ticks_us / ticks_ms behavior
# ---------------------------------------------------------------------------

def test_ticks_us_returns_int():
    t = time.ticks_us()
    assert isinstance(t, int)
    assert 0 <= t < _TICKS_PERIOD

def test_ticks_us_advances():
    """Successive calls return non-decreasing values most of the time.

    Sleep a known duration and check the delta is in the right range.
    Allow margin because CPython sleep precision is OS-dependent.
    """
    t0 = time.ticks_us()
    time.sleep(0.05)  # 50 ms
    t1 = time.ticks_us()
    diff = time.ticks_diff(t1, t0)
    # 50ms = 50_000 us; allow generous margin for OS scheduler jitter
    assert 30_000 < diff < 200_000

def test_ticks_ms_advances():
    t0 = time.ticks_ms()
    time.sleep(0.05)
    t1 = time.ticks_ms()
    diff = time.ticks_diff(t1, t0)
    assert 30 < diff < 200

def test_ticks_us_advances_about_1000x_faster_than_ticks_ms():
    """Microseconds advance ~1000x faster than milliseconds during the
    same wall-clock interval.

    Original version of this test compared the *absolute* values of the
    two counters and asserted us ≈ ms * 1000. That broke whenever the
    process had been running long enough for the us counter (period
    2^30 ≈ 17.9 min at 1us/tick) to wrap while the ms counter (period
    ~298 hours) hadn't. The fix: only compare *deltas* over a known
    interval, never absolute values, and use ticks_diff so wrap is
    handled correctly even if it happens during the measurement.
    """
    sleep_s = 0.02
    us0 = time.ticks_us()
    ms0 = time.ticks_ms()
    time.sleep(sleep_s)
    us1 = time.ticks_us()
    ms1 = time.ticks_ms()

    us_delta = time.ticks_diff(us1, us0)
    ms_delta = time.ticks_diff(ms1, ms0)

    # Both should be positive (we slept forward in time)
    assert us_delta > 0
    assert ms_delta >= 0  # ms might be 0 if sleep was very short

    # us delta should be about 1000x ms delta. Allow generous slack
    # because the two reads happen at slightly different instants and
    # OS sleep precision is variable. The point of the test is to
    # catch a 100x or 10000x drift, not enforce tight precision.
    if ms_delta > 0:
        ratio = us_delta / ms_delta
        assert 500 < ratio < 2000, f"us/ms ratio {ratio} far from expected 1000"


# ---------------------------------------------------------------------------
# ticks_diff: the interesting one (wrap arithmetic)
# ---------------------------------------------------------------------------

def test_ticks_diff_simple():
    """Basic case, no wrap involved."""
    assert time.ticks_diff(100, 50) == 50
    assert time.ticks_diff(50, 100) == -50

def test_ticks_diff_zero():
    """a == b returns 0."""
    assert time.ticks_diff(12345, 12345) == 0

def test_ticks_diff_wrap_forward():
    """If b is just before the wrap and a is just after, the diff
    should be small and positive — matching MicroPython semantics.

    Without wrap-aware logic, naive subtraction (a - b) would give a
    huge negative number. ticks_diff handles this correctly."""
    just_before_wrap = _TICKS_PERIOD - 5
    just_after_wrap = 5
    diff = time.ticks_diff(just_after_wrap, just_before_wrap)
    # Expect: 10 (5 ticks to wrap + 5 ticks past)
    assert diff == 10

def test_ticks_diff_wrap_backward():
    """And the reverse — going backward across the wrap."""
    just_before_wrap = _TICKS_PERIOD - 5
    just_after_wrap = 5
    diff = time.ticks_diff(just_before_wrap, just_after_wrap)
    assert diff == -10

def test_ticks_diff_max_positive():
    """Half the period is the maximum representable positive delta."""
    diff = time.ticks_diff(_TICKS_PERIOD // 2 - 1, 0)
    assert diff == _TICKS_PERIOD // 2 - 1

def test_ticks_diff_at_max_negative():
    """Just past half the period flips sign — this is the boundary
    where MicroPython's ticks_diff treats the result as negative."""
    diff = time.ticks_diff(_TICKS_PERIOD // 2, 0)
    # _TICKS_PERIOD // 2 sits exactly at the boundary; per the doc, a
    # value >= half_period maps to a negative delta.
    assert diff == -(_TICKS_PERIOD // 2)


# ---------------------------------------------------------------------------
# ticks_add
# ---------------------------------------------------------------------------

def test_ticks_add_basic():
    assert time.ticks_add(100, 50) == 150

def test_ticks_add_wraps():
    """ticks_add at the boundary should wrap, not overflow."""
    near_max = _TICKS_PERIOD - 10
    assert time.ticks_add(near_max, 20) == 10  # 10 past wrap

def test_ticks_add_inverse_of_diff():
    """For any a, b: ticks_add(b, ticks_diff(a, b)) == a."""
    a, b = 100, 50
    assert time.ticks_add(b, time.ticks_diff(a, b)) == a


# ---------------------------------------------------------------------------
# sleep_ms / sleep_us
# ---------------------------------------------------------------------------

def test_sleep_ms_blocks_for_at_least_n_ms():
    t0 = time.monotonic()
    time.sleep_ms(50)
    elapsed = time.monotonic() - t0
    # Must sleep at least the requested time; allow OS overhead
    assert 0.04 <= elapsed <= 0.5

def test_sleep_us_runs_without_crash():
    """We can't assert microsecond accuracy on a desktop OS — CPython
    time.sleep is millisecond-accurate at best — but the call should
    succeed and return."""
    time.sleep_us(100)  # should not crash
    time.sleep_us(0)    # zero is a valid no-op


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

def test_install_all_is_idempotent():
    """Re-running install_all shouldn't double-wrap or break the patches."""
    _stubs.install_all()
    _stubs.install_all()
    # Functions should still work
    assert callable(time.ticks_us)
    diff = time.ticks_diff(100, 50)
    assert diff == 50


# ---------------------------------------------------------------------------
# Integration: hello2-style usage pattern
# ---------------------------------------------------------------------------

def test_hello2_style_usage():
    """Replicate hello2.py's frame-timing pattern."""
    current_tick = time.ticks_us()
    time.sleep(0.01)
    last_tick = current_tick
    current_tick = time.ticks_us()
    time_diff = (current_tick - last_tick) * 0.001  # ms
    # Should be a positive small number around 10ms
    # (Note: hello2.py uses naive subtraction not ticks_diff — works
    # except across a wrap, which is unlikely in any short test)
    assert 5 < time_diff < 100
