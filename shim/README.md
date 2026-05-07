# pdeck-sim

A desktop Python shim for the Pocket Deck `pdeck` and `vscreen` modules. Develop limited Pocket Deck apps on your Mac; a pygame window stands in for the 400×240 monochrome LCD. Headless tests are included.

## What's covered

- `pdeck` module: `vscreen()`, `get_screen_size()`, `clipboard_copy/paste`,
  `led()` (prints), `delay_tick()`, `change_screen()`, `show_screen_num()`,
  `cmd_exists()`, `screen_invert()`, `rtc()`, basic terminal-font getters.
- `vscreen` object:
  - All primitive shapes: `draw_pixel`, `draw_line`, `draw_h_line`,
    `draw_v_line`, `draw_box`, `draw_frame`, `draw_rframe`, `draw_rbox`,
    `draw_circle`, `draw_disc`, `draw_triangle`, `draw_arc`, `draw_ellipse`,
    `draw_filled_ellipse`, `draw_polygon`.
  - Text: `draw_str`, `draw_utf8`, `get_str_width`, `get_utf8_width`,
    `set_font`, `set_font_mode`.
  - Bitmaps: `draw_xbm`, `draw_image`, `capture_as_xbm`, `set_bitmap_mode`.
  - Color / dither: `set_draw_color`, `set_dither`.
  - Buffers: `clear_buffer`, `switch_buffer`, `copy_buffer`.
  - Callback system: `callback`, `callback_exists`, `finished`.
  - I/O: `print`, `send_char`, `send_key_event`, `read_nb`, `poll`,
    `get_key_state`, `get_tp_keys`, `get_terminal_size`.
  - Property: `active`, `suspend_inactive_screen`.
- `pdeck_utils` with `reimport()` and `launch()` stubs.
- `xbmreader` and a small `esclib` stub to support the common example shape.

## What's not covered

- **Audio output**. The `audio` and `pie` modules are stubbed for
  API-shape compatibility — examples like `pattern_example.py` and
  `reverb_example.py` will run to completion exercising their
  control-flow logic, but no sound is produced. The `Pie` sequencer's
  `playing_cycle` does advance over wall-clock time at the configured
  BPM, so apps that use cycle progression to advance through patterns
  work correctly. For actually hearing sound, run on device via the
  sync tooling.
- Exact u8g2 font metrics. `get_str_width` uses a fixed-width approximation
  based on the selected font's nominal size. For pixel-perfect parity, use
  option 2 from the design doc (ctypes over a real u8g2 dylib).
- Multi-threaded multi-screen behavior. The shim renders **one active
  screen** at a time (screen 2 by default). You can switch with keyboard
  shortcuts but there's no concurrent background-thread rendering like the
  real deck does.

## Simulator-device divergences

The shim runs on CPython; the device runs MicroPython on ~256 KB of RAM.
Most app code is portable, but several classes of divergence can silently
produce code that passes all simulator tests and then breaks on device.

### Silent divergences (highest risk)

**Memory exhaustion.** The sim has no heap limit. Object-heavy loops,
large list comprehensions, or string buffers that work fine on the desktop
will hit `MemoryError` on-device with no prior warning. Tighten allocation
in any loop that creates temporaries, and test memory-heavy paths on device
early.

**Integer and float precision.** CPython integers have arbitrary precision;
MicroPython uses 30-bit small ints on 32-bit ARM (range ≈ ±536M). Arithmetic
that silently overflows stays silent — the device produces a wrong number, not
an exception. Floats are 32-bit on device vs 64-bit in the sim; graphics code
using trigonometry or physics will accumulate slightly different rounding
errors.

**Unshimmed stdlib modules.** `import re`, `import json`, `import math`
(for CPython-only additions like `math.gcd`, `math.comb`, `math.isqrt`),
`import traceback`, `import functools` — all succeed in the sim, all raise
`ImportError` on device. These are green paths in the simulator that only
reveal themselves on first deploy.

**`os` module partial coverage.** `os.listdir()` and `os.stat()` are
sandboxed correctly. `os.mkdir()`, `os.makedirs()`, `os.rename()`, and
`os.remove()` are not shimmed — they operate on the host filesystem directly
and may succeed in the sim while failing differently on device.

**Audio tick drift.** `audio.get_current_tick()` returns synthetic ticks
derived from wall-clock time, not actual audio-interrupt ticks. Patterns
that appear tightly synced in the sim will drift on-device if the app does
not poll frequently enough.

**`set_dither()` is a no-op.** The sim tracks the dither level but does not
render it. Visual quality decisions — gradient rendering, aliasing on curved
shapes — cannot be validated in the sim.

### Divergences that crash early on device

**CPython 3.8+ syntax.** Walrus operator (`:=`), `match`/`case`, positional-only
parameters (`/`), and `int | str` union type hints are valid CPython but are
syntax errors on MicroPython. Avoid them in app code.

**`threading`.** Fully functional in the sim; raises `ImportError` on device.
Background threads used for periodic updates need a redesign for device
deployment.

**Relative file paths.** MicroPython has no concept of a working directory.
`open("data.txt")` resolves against the host shell's cwd in the sim and raises
`FileNotFoundError` on device. Always use deck-absolute paths: `/sd/…`,
`/config/…`, `/int/…`.

### Behavioral differences

**`struct.unpack()` leniency.** The sim patches `struct` to silently truncate
oversized buffers. MicroPython's `struct` is stricter about buffer sizes and
will raise an error where the sim succeeds.

**`@micropython.viper` and `@micropython.native` are no-ops.** Decorated
functions run as ordinary CPython. Code that is only fast enough under viper
compilation will be too slow on-device, with no warning emitted by the sim.

**`str` method gaps.** MicroPython's `str` is missing CPython methods added in
3.9+: `removeprefix()`, `removesuffix()`, and `casefold()`. Code using these
will raise `AttributeError` on device.

### Planned guardrails

The following simulator-side checks are not yet implemented but would catch
most of the above early:

- **Import warnings** — intercept `import re`, `import json`, `import traceback`,
  and other device-absent modules at import time and emit a `[pdeck_sim] WARNING`
  before allowing the import to proceed.
- **Heap budget mode** — a `POCKETDECK_HEAP_LIMIT` env var (default `262144`)
  that raises `MemoryError` once a configurable allocation threshold is
  exceeded, making memory pressure visible in the sim.
- **Relative path warnings** — warn in `paths.translate()` when a path does not
  start with `/sd/`, `/config/`, or `/int/`, as the device has no cwd to resolve
  against.
- **`@viper` annotation notice** — emit a one-time `[pdeck_sim] @viper is a
  no-op in the simulator` when the decorator is first applied.
- **Startup syntax check** — before running the app, scan source files for
  CPython 3.8+ syntax tokens and warn before execution.
- **Float32 mode** — a `POCKETDECK_FLOAT32=1` env var that caps float precision
  to 32-bit so accumulation differences are visible during sim runs.

## Install

```bash
cd shim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Confirm installation by launching the simulator with an example application:

```bash
python3 -m pdeck_sim.runner ../examples/primitive_tour.py
```

## Debug panel

The shim displays a side panel to the right of the LCD showing runtime
state that wouldn't be visible on the device:

- Active virtual screen number (1-9)
- LED brightness for all 8 LEDs (filled amber circle = lit; intensity
  encodes brightness; hollow ring = off)
- Audio activity indicator — a green dot lights up while the audio
  engine is being polled, idle gray when silent
- FPS counter and total frame count

The panel is visually separated from the LCD by a 1-pixel divider and
uses a slightly cooler background tint. Everything to the right of the
divider is shim-only — never visible on the actual device.

Disable the panel with `POCKETDECK_DEBUG_PANEL=0`. Useful when taking
screenshots of just the LCD content, or when running automated tests
that pin window dimensions.

## Run an app

```bash
# Assuming your Pocket Deck apps are in ~/code/pocketdeck-apps/
python3 -m pdeck_sim.runner ~/code/pocketdeck-apps/my_app.py
```

Or with args:

```bash
python3 -m pdeck_sim.runner ~/code/pocketdeck-apps/my_app.py foo bar
```

Define a virtual filesystem (see [discussion](#deck-filesystem-root) on sandbox escape safety, and symlink usage), then specify a root for assets needed by the app:

```bash
POCKETDECK_ROOT=../../sd-root python3 -m pdeck_sim.runner ~/code/pocketdeck-apps/my_app.py foo bar
```

## Deck filesystem root

Deck apps reference absolute paths like `/sd/lib/data/ghost1.xbm` or
`/config/apps.json`. Those paths don't exist on macOS. The shim rewrites
them to live under a single host directory:

- Default: `~/.pocketdeck-root/`
- Override: set the `POCKETDECK_ROOT` env var

Mirror the deck's layout inside that root:

```
$POCKETDECK_ROOT/
  sd/
    py/
      my_app.py             <- user apps (highest sys.path priority)
    lib/
      xbmreader.py          <- deck library modules (real source)
      esclib.py
      data/ghost1.xbm
    Documents/
  config/
    apps.json
```

The shim mirrors MicroPython's import priority on the deck: `/sd/py`
takes priority over `/sd/lib`, matching the device's behavior where
user code can override library modules.

## Real modules vs fallback stubs

When `$POCKETDECK_ROOT/sd/lib/<module>.py` exists, the shim uses the
real deck source — no stub, no behavioral approximation, just the
actual library code. This applies to `xbmreader`, `esclib`,
`pdeck_utils`, `overlay`, `benchmark`, `jp_input`, and `ls`.

When the real module isn't available (POCKETDECK_ROOT unset, or sd/lib
not populated), the shim installs a fallback stub instead.

A few modules are **always stubbed** because they're C-native on the
deck and have no Python implementation: `pdeck`, `audio`, `pie`,
`dsplib`, `re_test`. Even if a `.py` of the same name exists in your
deck root, the shim uses its own stubs for these.

The simplest way to populate the root is to symlink your deck source
checkout:

```bash
mkdir -p ~/.pocketdeck-root/sd
ln -s ~/proj/pocket-deck/pocketdeck/lib ~/.pocketdeck-root/sd/lib
```

If an app references a `/sd/...` path that doesn't exist under the root,
the shim prints a warning and returns an empty image rather than crashing —
so you can see which assets are missing at a glance.

**Sandbox enforcement.** Two layers:

1. `..` traversal is blocked unconditionally. An app that asks for
   `/sd/../../../etc/passwd` raises `SandboxEscapeError` before any file
   operation runs. This is the defense against app-generated path tricks.

2. Symlink escape is permitted by default. If `$POCKETDECK_ROOT/sd/lib`
   is a symlink pointing at your real deck repo (a common setup), apps
   can read through it normally. Set `POCKETDECK_ALLOW_SYMLINK_ESCAPE=0`
   to opt into strict mode — any resolved path landing outside the root
   will then be rejected. Strict mode is useful if you're running
   untrusted app code and you haven't set up any intentional symlinks.

Untranslated paths (host absolutes like `/tmp/foo`, relative paths) pass
through unchanged in both modes — the shim only sandboxes what it
translates.

## Runtime controls

Inside the pygame window:

- `ESC` or window close — quit
- `F5` — reload the currently-running app module from disk (handy with an
  editor)
- `F6` — toggle the invert flag (just like `screen_invert` on device)
- `F11` — toggle 2× scale for readability
- `Ctrl+Shift+D` — detach the current vscreen callback (mirrors the deck's
  "kill graphic app" shortcut)
- Any printable key — fed to `read_nb()` and `get_key_state()`

## How the app lookup works

The runner takes a path to a `.py` file that defines `main(vs, args)`. It:

1. Adds the file's directory to `sys.path`.
2. Imports the module by basename (minus `.py`).
3. Creates a `vscreen_stream`, opens a pygame window, calls `main(vs, args)`.

If your app imports sibling modules (e.g. `import overlay`), as long as they
sit in the same directory they'll resolve.

# Testing

Basic tests are included -- headless,  platform independent. See [tests/](tests).

Add tests as features are changed or introduced, or be sorry!

## Set up and running
Ensure requirements for testing:

```python
pip install pytest
```

Execute tests for each significant change:

```python
SDL_VIDEODRIVER=dummy pytest
# or with output
SDL_VIDEODRIVER=dummy pytest -v
# or a single test
SDL_VIDEODRIVER=dummy pytest -v -k reimport
```

# Architecture

See [diagram](docs/pdeck_sim_architecture.png).