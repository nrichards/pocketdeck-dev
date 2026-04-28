Project: Pocket Deck dev kit (Mac-side simulator + sync tooling for
ESP32/MicroPython device with 400×240 mono LCD).

Repo: github.com/nrichards/pocketdeck-dev (MIT). 

Key dirs:
  shim/pdeck_sim/   — pygame-backed pdeck/vscreen reimplementation
  shim/tests/       — ~190 passing headless tests
  sync/             — bash + fswatch + sshpass push-and-run

Architecture I won't re-explain:
  - sys.modules injection via _stubs.install_all()
  - _ALWAYS_SHIM (no Python equivalent) vs _FALLBACK_SHIM (real .py
    on disk preferred)
  - Path translation for /sd/... in builtins.open/os.stat/os.listdir
  - Producer-tagged logging, debug panel on right side of LCD

Me: senior engineer, want technical depth, push back rather than agree.
Mac dev. Don't search project knowledge unless I ask. I'll paste files.
