"""Tests for the audio + pie stubs.

These stubs exist so audio-using examples like pattern_example.py can run
to completion in the shim, exercising their control-flow logic. No actual
sound is produced — that's documented behavior, not a bug.
"""
from __future__ import annotations

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import time
import warnings

import pytest

from pdeck_sim import _stubs
_stubs.install_all()


# ---------------------------------------------------------------------------
# audio module
# ---------------------------------------------------------------------------

def test_audio_sample_rate_setter_and_getter():
    """sample_rate(N) sets, sample_rate() reads back the configured rate."""
    import audio
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        audio.sample_rate(48000)
        assert audio.sample_rate() == 48000
        audio.sample_rate(24000)
        assert audio.sample_rate() == 24000

def test_audio_get_current_tick_advances():
    """Audio tick must advance over wall-clock time, otherwise pattern
    sequencers deadlock waiting for cycles to elapse."""
    import audio
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t0 = audio.get_current_tick()
        time.sleep(0.05)
        t1 = audio.get_current_tick()
    assert t1 > t0

def test_audio_modules_are_context_managers():
    """All audio.* classes must support `with`."""
    import audio
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name in ("sampler", "wavetable", "router", "reverb",
                     "compressor", "filter", "echo", "mixer"):
            cls = getattr(audio, name)
            with cls() as instance:
                # Arbitrary method call must not crash
                instance.set_params(1, 2, 3)
                instance.active(True)

def test_audio_load_wavetable_returns_frame_count():
    """Apps inspect the return value of load_wavetable. The stub must
    return a number, not None."""
    import audio
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wv = audio.wavetable(4)
        result = wv.load_wavetable(0, "/sd/lib/data/x.wav", stride=1)
    assert isinstance(result, int)
    assert result > 0


# ---------------------------------------------------------------------------
# pie module: Pattern chaining
# ---------------------------------------------------------------------------

def test_pattern_chaining_returns_self():
    """Every modifier on Pattern must return self, so .strum().scale()
    chains compose. Without this, half the deck's audio examples crash
    on AttributeError when the second method is called."""
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = pie.Pie(bpm=120)
        pat = p.pattern(None, "<a2 c3 e3>")
    assert pat.strum(0.02) is pat
    assert pat.scale("Cmajor") is pat
    assert pat.transpose(-7) is pat
    assert pat.clip(0.5) is pat
    assert pat.fast(2) is pat
    assert pat.slow(2) is pat


def test_pattern_full_chain_doesnt_explode():
    """Compose all modifiers in one chain — the kind of thing a real
    deck app does."""
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = pie.Pie(bpm=120)
        result = (p.pattern(None, "0 1 2 3")
                  .scale("Ebmaj")
                  .clip("0.2 1.0")
                  .transpose(-7)
                  .strum(0.005))
    # Result is a Pattern object (whatever the type is, just ensure it
    # has the get_events method that Pie.process_event would call)
    assert hasattr(result, "get_events")


# ---------------------------------------------------------------------------
# pie module: Pie sequencer
# ---------------------------------------------------------------------------

def test_pie_context_manager():
    """Pie must support `with p:` to start/stop the sequencer."""
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = pie.Pie(bpm=120)
        assert not p._running
        with p:
            assert p._running
        assert not p._running

def test_playing_cycle_advances_with_wall_clock():
    """playing_cycle must advance during a `with p:` block. Apps poll
    this value via check_cycle() to decide when to move to the next
    pattern; if it stays at 0, the app deadlocks."""
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = pie.Pie(bpm=120)
        with p:
            c0 = p.playing_cycle
            time.sleep(0.1)
            c1 = p.playing_cycle
    assert c0 < c1
    # 120 bpm = 2 beats/s, 4 beats/cycle = 0.5 cycles/s.
    # 0.1s should give roughly 0.05 cycles. Allow a wide margin.
    delta = c1 - c0
    assert 0.01 < delta < 0.5

def test_playing_cycle_returns_zero_outside_with_block():
    """Before start() / outside `with`, playing_cycle is 0."""
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = pie.Pie(bpm=120)
    assert p.playing_cycle == 0

def test_pie_add_returns_index_for_update():
    """add() returns an int index that update() accepts. This roundtrip
    is how apps swap pattern strings live during playback."""
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        p = pie.Pie(bpm=120)
        idx = p.add("instrument", "0 1 2 3")
        assert isinstance(idx, int)
        assert p.update(idx, "4 5 6 7") == idx
        assert p.remove(idx) == idx


# ---------------------------------------------------------------------------
# pie module: instrument wrappers
# ---------------------------------------------------------------------------

def test_pie_wrappers_have_dev_attribute():
    """Every Pie* wrapper exposes a `dev` for low-level audio access.
    Apps poke `.dev.set_adsr(...)`, `.dev.volume(...)`, etc."""
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for cls_name in ("PieSampler", "PieWavetable", "PieReverb",
                         "PieRouter", "PieCompressor", "PieFilter",
                         "PieEcho", "PieMixer"):
            cls = getattr(pie, cls_name)
            obj = cls()
            assert hasattr(obj, "dev"), f"{cls_name} missing .dev"
            # And dev must accept any method call
            obj.dev.set_adsr(0, 10, 100, 0.5, 1000)
            obj.dev.volume(0, 0.5)
            obj.dev.active(True)

def test_pie_wrappers_are_context_managers():
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for cls_name in ("PieSampler", "PieWavetable", "PieReverb",
                         "PieRouter", "PieCompressor"):
            cls = getattr(pie, cls_name)
            with cls() as obj:
                pass

def test_pie_wavetable_load_returns_frame_count():
    """Apps inspect the return value to log how many frames they got."""
    import pie
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wv = pie.PieWavetable(6)
        frames = wv.load_wavetable(0, "/sd/lib/data/guitar_wt.wav",
                                   stride=5, max_frames=32, frame_size=256)
    assert isinstance(frames, int)
    assert frames > 0


# ---------------------------------------------------------------------------
# Integration: the whole import-and-setup phase of pattern_example
# ---------------------------------------------------------------------------

def test_pattern_example_setup_runs():
    """Smoke test: replicate the import + setup phase of pattern_example.py.
    If this passes, the example will at least not crash before the
    pattern playback loop. The loop itself is timing-dependent and
    tested separately if needed."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        import audio
        from pie import Pie, PieWavetable, PieReverb, PieRouter, PieCompressor

        audio.sample_rate(24000)
        p = Pie(bpm=120)
        master = PieRouter()
        rev = PieReverb()
        wv = PieWavetable(6)
        comp = PieCompressor()

        with master, wv, rev, comp:
            master.clear()
            master.add(wv)
            master.add(rev)
            master.add(comp)
            comp.set_params(1.2, 2.0)

            frames = wv.load_wavetable(0, "/sd/lib/data/guitar_wt.wav",
                                       stride=5, max_frames=32,
                                       frame_size=256)
            assert frames > 0

            wv.morph(0, 0)
            for i in range(5):
                wv.copy_table(i + 1, 0)
            for i in range(6):
                wv.dev.volume(i, 0.16)
                wv.dev.set_adsr(i, 10, 2000, 0.01, 1000)
                wv.dev.morph_adsr(i, 0, 4400, 0.1, 1000)
                wv.dev.morph_start(i, 1)
                wv.dev.morph(i, 0)
                wv.dev.morph_adsr_enable(i, True)

            rev.set_params(room_size=0.10, brightness=0.3,
                           predelay_ms=115.0, transition_ms=0, mix=0.4)

            # Pattern chaining
            pattern = (p.pattern(wv, "<[a2 c3 e3 g3]*2 [D2m7]*2>")
                       .strum(0.02))
            assert pattern is not None

            wv_idx = p.add(wv, pattern)
            assert wv_idx == 0

            comp.dev.active(True)

            # Briefly run the sequencer to verify cycle advancement
            with p:
                c0 = p.playing_cycle
                time.sleep(0.05)
                p.process_event()
                c1 = p.playing_cycle
                assert c1 > c0
