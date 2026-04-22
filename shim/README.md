# pdeck-sim

A desktop Python shim for the Pocket Deck `pdeck` and `vscreen` modules. Develop limited Pocket Deck apps on your Mac; a pygame window stands in for the 400×240 monochrome LCD. Headless tests are included.

## What's covered

- `pdeck` module: `vscreen()`, `get_screen_size()`, `clipboard_copy/paste`, `led()` (prints), `delay_tick()`, `change_screen()`, `show_screen_num()`, `cmd_exists()`, `screen_invert()`, `rtc()`, basic terminal-font getters.
- `vscreen` object:
  - All primitive shapes: `draw_pixel`, `draw_line`, `draw_h_line`, `draw_v_line`, `draw_box`, `draw_frame`, `draw_rframe`, `draw_rbox`, `draw_circle`, `draw_disc`, `draw_triangle`, `draw_arc`, `draw_ellipse`, `draw_filled_ellipse`, `draw_polygon`.
  - Text: `draw_str`, `draw_utf8`, `get_str_width`, `get_utf8_width`, `set_font`, `set_font_mode`.
  - Bitmaps: `draw_xbm`, `draw_image`, `capture_as_xbm`, `set_bitmap_mode`.
  - Color / dither: `set_draw_color`, `set_dither`.
  - Buffers: `clear_buffer`, `switch_buffer`, `copy_buffer`.
  - Callback system: `callback`, `callback_exists`, `finished`.
  - I/O: `print`, `send_char`, `send_key_event`, `read_nb`, `poll`, `get_key_state`, `get_tp_keys`, `get_terminal_size`.
  - Property: `active`, `suspend_inactive_screen`.
- `pdeck_utils` with `reimport()` and `launch()` stubs.
- `xbmreader` and a small `esclib` stub to support the common example shape.

## What's not covered

- `audio` module. Stubbed with no-ops so imports don't fail. You'll see a warning printed when you call into it. Open an issue or add to `_stubs.py` if you need specific audio calls mocked.
- Exact u8g2 font metrics. `get_str_width` uses a fixed-width approximation based on the selected font's nominal size. For pixel-perfect parity, use option 2 from the design doc (ctypes over a real u8g2 dylib).
- Multi-threaded multi-screen behavior. The shim renders **one active screen** at a time (screen 2 by default). You can switch with keyboard shortcuts but there's no concurrent background-thread rendering like the real deck does.

## Future

## Install

```bash
cd shim
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

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
    lib/data/ghost1.xbm       <- resolves /sd/lib/data/ghost1.xbm
    py/my_app.py
    Documents/
  config/
    apps.json
```

The simplest way to populate it is to SCP a subtree off your deck:

```bash
mkdir -p ~/.pocketdeck-root/sd/lib
scp -r user@<deck-ip>:/sd/lib/data ~/.pocketdeck-root/sd/lib/
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
- `F5` — reload the currently-running app module from disk (handy with an editor)
- `F6` — toggle the invert flag (just like `screen_invert` on device)
- `F11` — toggle 2× scale for readability
- `Ctrl+Shift+D` — detach the current vscreen callback (mirrors the deck's "kill graphic app" shortcut)
- Any printable key — fed to `read_nb()` and `get_key_state()`

## How the app lookup works

The runner takes a path to a `.py` file that defines `main(vs, args)`. It:

1. Adds the file's directory to `sys.path`.
2. Imports the module by basename (minus `.py`).
3. Creates a `vscreen_stream`, opens a pygame window, calls `main(vs, args)`.

If your app imports sibling modules (e.g. `import overlay`), as long as they sit in the same directory they'll resolve.

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
