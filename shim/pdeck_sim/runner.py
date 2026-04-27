"""runner.py — entry point. `python -m pdeck_sim.runner path/to/app.py [args...]`

Bootstraps the environment a Pocket Deck app expects to run in, then calls
`main(vs, args)` and drives the frame loop until the app exits or the
window is closed.

Flow:
  1. Install all the fake modules (pdeck, pdeck_utils, xbmreader, etc) so
     the user's app's imports resolve.
  2. Open the pygame window.
  3. Import the user's module by file path.
  4. Create a vscreen + vscreen_stream, call main(vs, args) in a background
     thread so the main thread can own the event loop.
  5. Pump events and present frames at ~60fps. If the app has registered a
     vscreen callback, invoke it each frame (this is how graphical apps on
     the deck actually get redrawn).
  6. Handle F5 reload, C-S-D detach, and window close gracefully.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import threading
import time
import traceback
from pathlib import Path

# Install shims BEFORE the user's module imports anything.
from . import _stubs
_stubs.install_all()

# These imports must come after install_all() so they pick up shimmed deps.
from .framebuffer import get_framebuffer, FPS
from .vscreen import Vscreen
from .vscreen_stream import VscreenStream


def _load_user_module(path: Path):
    """Import a user app by file path. The app's directory is put on
    sys.path so its sibling imports (helpers, etc.) resolve."""
    path = path.resolve()
    app_dir = str(path.parent)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    mod_name = path.stem
    # Drop any stale copy so F5-style reloads work.
    sys.modules.pop(mod_name, None)

    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _run_main_in_thread(module, vs, args) -> threading.Thread:
    """Run user's main() on a worker thread so the main thread owns pygame.

    MicroPython apps often call blocking vs.read() from main(), which we
    want to work without freezing the window. The worker thread blocks on
    input; the main thread keeps the event pump alive.
    """
    def target():
        try:
            module.main(vs, args)
        except SystemExit:
            pass
        except Exception:
            from .shim_log import error
            error("runner", "app raised:")
            traceback.print_exc()
        finally:
            # Signal the main loop that the app is done.
            get_framebuffer().flags.quit_requested = True

    t = threading.Thread(target=target, name="pdeck-app", daemon=True)
    t.start()
    return t


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m pdeck_sim.runner",
        description="Run a Pocket Deck app on the desktop simulator.",
    )
    parser.add_argument("app", help="Path to the app's .py file")
    parser.add_argument("args", nargs="*", help="Arguments passed to main()")
    parser.add_argument("--screen", type=int, default=2,
                        help="Initial screen number (default: 2)")
    ns = parser.parse_args(argv)

    app_path = Path(ns.app)
    if not app_path.is_file():
        print(f"error: not a file: {app_path}", file=sys.stderr)
        return 1

    fb = get_framebuffer()
    Vscreen._current_screen = ns.screen

    # Build the vscreen + stream the app will receive.
    import pdeck  # resolves to fake_pdeck via sys.modules
    v = pdeck.vscreen(ns.screen)
    vs = VscreenStream(v)

    # Print the startup banner including where the virtual deck filesystem
    # is rooted. Users need to know this so they can drop /sd/... content
    # into the right place.
    from .paths import get_root
    from .shim_log import log, error
    deck_root = get_root()
    log("runner", f"loading {app_path.name} on screen {ns.screen}")
    log("runner", f"deck filesystem root: {deck_root}")
    try:
        user_module = _load_user_module(app_path)
    except Exception:
        traceback.print_exc()
        return 1

    if not hasattr(user_module, "main"):
        error("runner", f"{app_path} does not define main(vs, args)")
        return 1

    worker = _run_main_in_thread(user_module, vs, ns.args)

    # ---- main loop ----
    frame_time = 1.0 / FPS
    # The framebuffer tracks reload requests via a dynamic attribute set by
    # pump_events() on F5. Initialize here so hasattr is fine either way.
    fb.flags.reload_requested = False  # type: ignore[attr-defined]

    # Initial present so the window shows the off-white background instead
    # of whatever pygame defaults to. Apps without a callback (e.g. pure
    # terminal apps) will see this blank screen the whole time.
    fb.present()

    try:
        while not fb.flags.quit_requested:
            t0 = time.time()
            fb.pump_events()

            # If the app registered a frame callback, call it.
            # _begin_frame() arms the lazy-clear; a draw inside the callback
            # will clear buffer 0 before drawing. If the callback returns
            # without drawing, _drew_this_frame stays False and we skip
            # presenting — mirrors the deck's skip-update energy optimization.
            drew = False
            if v._callback is not None:
                v._begin_frame()
                try:
                    v._callback(False)
                except Exception:
                    error("runner", "callback raised:")
                    traceback.print_exc()
                    v._callback = None
                drew = v._drew_this_frame

            # Detach: C-S-D, mirrors real deck
            if fb.flags.detach_requested:
                v._callback = None
                fb.flags.detach_requested = False
                log("runner", "callback detached (C-S-D)")

            # Reload: F5
            if getattr(fb.flags, "reload_requested", False):
                fb.flags.reload_requested = False
                log("runner", f"reloading {app_path.name}...")
                # Detach callback, let the worker finish, reload, restart.
                v._callback = None
                fb.flags.quit_requested = True
                break

            # Present only if something changed. This is the skip-update
            # optimization mirroring the deck's energy savings — when the
            # callback returns without drawing, the LCD holds its last
            # frame and no work happens.
            #
            # When the debug panel is enabled, we present every frame so
            # the panel's live indicators (FPS, audio activity, LED state)
            # stay current. The panel only exists on the simulator; it
            # doesn't break the device-skip-update parity for app code.
            should_present = drew or fb.flags.needs_repaint or fb.panel_enabled
            if should_present:
                fb.present()
                fb.flags.needs_repaint = False
                # Producer hook: the FPS counter is driven by frame ticks.
                from .debug_state import get_debug_state
                get_debug_state().note_frame()

            elapsed = time.time() - t0
            if elapsed < frame_time:
                time.sleep(frame_time - elapsed)
    finally:
        # Give the worker a moment to notice and exit cleanly.
        fb.flags.quit_requested = True
        worker.join(timeout=0.5)

    # Handle F5-triggered reload by re-entering main()
    if getattr(fb.flags, "reload_requested", False):
        fb.flags.reload_requested = False
        fb.flags.quit_requested = False
        return main(argv)  # tail call into a fresh run

    import pygame
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
