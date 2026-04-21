# bouncing_box.py — exercises the graphics callback loop.
#
# A box bounces around the 400x240 screen. Arrow keys nudge it. Pressing 'q'
# quits by unregistering the callback (same pattern as real deck apps).
#
# Run in the shim:
#   python -m pdeck_sim.runner examples/bouncing_box.py

import pdeck
import esclib

class bouncing_box:
  def __init__(self, vs):
    self.vs = vs
    self.v = vs.v
    self.x = 50.0
    self.y = 50.0
    self.vx = 2.3
    self.vy = 1.7
    self.w = 32
    self.h = 24
    self.frame = 0

  def update(self, e):
    # Step physics
    self.x += self.vx
    self.y += self.vy
    if self.x <= 0 or self.x + self.w >= 400:
      self.vx = -self.vx
      self.x = max(0, min(400 - self.w, self.x))
    if self.y <= 0 or self.y + self.h >= 240:
      self.vy = -self.vy
      self.y = max(0, min(240 - self.h, self.y))

    # Draw
    self.v.set_font("u8g2_font_profont15_mf")
    self.v.draw_str(10, 20, "Bouncing box demo")
    self.v.set_font("u8g2_font_profont11_mf")
    self.v.draw_str(10, 232, "q: quit   arrows: nudge")

    self.v.draw_frame(0, 0, 400, 240)
    self.v.draw_rbox(int(self.x), int(self.y), self.w, self.h, 4)

    self.frame += 1
    if self.frame % 60 == 0:
      # Light up LED 1 briefly every second (prints in shim)
      pdeck.led(1, 100)

    self.v.finished()


def main(vs, args):
  v = vs.v
  el = esclib.esclib()
  v.print(el.erase_screen())
  v.print(el.home())
  v.print(el.display_mode(False))

  obj = bouncing_box(vs)
  v.callback(obj.update)

  # Input loop: nudge the box, or quit on 'q'.
  # On the real deck, vs.read blocks forever until a key arrives. In the
  # shim it returns b"" if the window is closed — break out in that case.
  while v.callback_exists():
    data = vs.read(1, 50)
    if data == b"":
      # window closed (shim-specific)
      break
    c = data[0:1]
    if c == b"q":
      break
    # Arrow keys arrive as escape sequences
    if c == b"\x1b":
      rest = vs.async_read(2)
      if rest == b"[A": obj.vy -= 0.5
      elif rest == b"[B": obj.vy += 0.5
      elif rest == b"[C": obj.vx += 0.5
      elif rest == b"[D": obj.vx -= 0.5

  v.callback(None)
  v.print(el.display_mode(True))
