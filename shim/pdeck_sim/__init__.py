"""pdeck_sim — desktop Python shim for the Pocket Deck pdeck/vscreen API.

This package exists so that `import pdeck` on a Mac resolves to something
useful. The runner arranges sys.path so user apps (and this package's fake
`pdeck`, `vscreen`, `xbmreader`, etc modules) are all importable.
"""

__version__ = "0.1.0"
