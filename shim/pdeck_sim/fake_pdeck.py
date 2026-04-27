"""fake_pdeck.py — shim for the `pdeck` top-level module.

The runner installs this as `sys.modules['pdeck']`. User apps write
`import pdeck` and get this object.
"""
from __future__ import annotations

import time
from typing import Optional

try:
    import pyperclip
    _clipboard_available = True
except ImportError:
    pyperclip = None  # type: ignore
    _clipboard_available = False

from .vscreen import Vscreen
from .framebuffer import SCREEN_W, SCREEN_H, get_framebuffer


# Module state that real `pdeck` tracks internally.
_default_terminal_font_size = 12
_vscreens: dict[int, Vscreen] = {}


def vscreen(screen_num: Optional[int] = None) -> Vscreen:
    """Return (and cache) a Vscreen for the given number (default: current)."""
    num = Vscreen._current_screen if screen_num is None else int(screen_num)
    if num not in _vscreens:
        _vscreens[num] = Vscreen(num)
    return _vscreens[num]


def get_screen_size() -> tuple:
    return (SCREEN_W, SCREEN_H)


def get_screen_num() -> int:
    return Vscreen._current_screen


def change_screen(screen: int) -> None:
    Vscreen._current_screen = int(screen)
    # Producer hook for the debug panel
    from .debug_state import get_debug_state
    get_debug_state().active_screen = int(screen)


def change_priority(priority: bool) -> None:
    # No-op on desktop
    pass


def show_screen_num() -> None:
    # Could draw a small overlay; skip for simplicity.
    pass


def clipboard_copy(s: str) -> None:
    if _clipboard_available:
        try:
            pyperclip.copy(str(s))
        except Exception:
            pass


def clipboard_paste() -> str:
    if _clipboard_available:
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""
    return ""


def cmd_exists(screen_num: int) -> bool:
    # In shim, only the launched app exists.
    return int(screen_num) == Vscreen._current_screen


def cmd_execute(command: str, screen_num_cmdshell: int,
                screen_num_dest: int) -> None:
    # Could spawn a subprocess; for most dev workflows not needed.
    from .shim_log import log
    log("pdeck", f"cmd_execute ignored: {command}")


def delay_tick(tick: int) -> None:
    # One tick ~ 10ms on ESP32 MicroPython
    time.sleep(int(tick) * 0.01)


def init() -> None:
    pass


def led(led_index: int, brightness: int) -> None:
    # Producer hook for the debug panel: store brightness so the panel
    # can render the LED state. Also log to stderr for headless use.
    from .shim_log import log
    from .debug_state import get_debug_state
    state = get_debug_state()
    if 0 <= led_index < len(state.led_brightness):
        state.led_brightness[led_index] = max(0, min(255, int(brightness)))
    log("pdeck", f"led {led_index} = {brightness}")


def rtc(t: Optional[tuple] = None) -> tuple:
    if t is not None:
        # Ignore — we don't mess with system time.
        return t
    lt = time.localtime()
    return (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_wday + 1,
            lt.tm_hour, lt.tm_min, lt.tm_sec)


def screen_invert(value: Optional[bool] = None) -> bool:
    fb = get_framebuffer()
    if value is not None:
        fb.flags.invert = bool(value)
    return fb.flags.invert


def shutdown() -> None:
    import pygame
    import sys
    pygame.quit()
    sys.exit(0)


def update_app_list(screen_num: int, value) -> None:
    pass


def set_default_terminal_font_size(size: int) -> None:
    global _default_terminal_font_size
    _default_terminal_font_size = int(size)


def get_default_terminal_font_size() -> int:
    return _default_terminal_font_size


def set_autosleep(seconds: int) -> None:
    pass
