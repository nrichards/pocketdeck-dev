# Changelog

## [0.1.0] - 2026-05-09

### Added

- First version.
- Supports
    - Drawing graphics/bitmaps/text/dithering, scripting/callbacks/input-output/activity, keyboard, filesystem.
    - PocketDeck screens (1-9), LEDs
    - MicroPython pass-through no-op
- Doesn't simulate: 
    - sound, touchpad / buttons, accurate screen handling, accurate fonts, and anything smelling of hardware .. timing, memory, CPU architecture, MicroPython behaviors (shim is CPython underneath), and more.


## [0.2.0] - 2026-05-09

### Added

- Support for 3d math from PocketDeck dsplib. 
    - Now lib/examples/cube_test.py and sphere_test.py works.
- Support for Bayer dithering.

