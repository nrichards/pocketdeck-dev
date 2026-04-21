# hello_world.py — the simplest possible Pocket Deck app.
# Writes to both the terminal (screen 1 on device, stderr in shim) and the
# vscreen stream (its own screen).

def main(vs, args):
  print("hello from screen 1 / stderr")
  print("hello Pocket deck!", file=vs)
