# primitive_tour.py — visual QA for the shim's drawing primitives.
#
# Renders one of each primitive so you can eyeball the shim against device
# output. Press any key to quit.

import esclib

def main(vs, args):
  v = vs.v
  el = esclib.esclib()
  v.print(el.erase_screen())
  v.print(el.display_mode(False))

  def frame(e):
    v.set_font("u8g2_font_profont15_mf")
    v.draw_str(10, 16, "Primitive tour")

    # Shapes (top row)
    v.draw_frame(10, 30, 40, 30)
    v.draw_box(60, 30, 40, 30)
    v.draw_rframe(110, 30, 40, 30, 6)
    v.draw_rbox(160, 30, 40, 30, 6)
    v.draw_circle(230, 45, 15)
    v.draw_disc(280, 45, 15)
    v.draw_triangle(320, 60, 340, 30, 360, 60)

    # Lines and pixels (middle band)
    v.draw_line(10, 80, 390, 80)
    for i in range(20):
      v.draw_pixel(10 + i * 2, 90)
    v.draw_h_line(10, 100, 100)
    v.draw_v_line(120, 85, 30)

    # Ellipse + polygon
    v.draw_ellipse(180, 100, 30, 15)
    v.draw_filled_ellipse(240, 100, 30, 15)
    v.draw_polygon([300, 320, 340, 360, 340, 90, 110, 110, 90, 110])

    # Text at multiple sizes
    v.set_font("u8g2_font_profont11_mf"); v.draw_str(10, 140, "profont 11")
    v.set_font("u8g2_font_profont15_mf"); v.draw_str(10, 160, "profont 15")
    v.set_font("u8g2_font_profont22_mf"); v.draw_str(10, 190, "profont 22")

    # Footer
    v.set_font("u8g2_font_profont11_mf")
    v.draw_str(10, 232, "any key to quit")
    v.finished()

  v.callback(frame)
  vs.read(1, 50)  # block until any key
  v.callback(None)
  v.print(el.display_mode(True))
