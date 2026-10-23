"""Display-only neon edge: bounded immediate-mode gradients, no cached frames."""
import math
import pyray as rl

from openpilot.starpilot.ui.onroad_state import AlertSize


COLORS = {
  (22, 127, 64): (0, 255, 128),
  (10, 186, 181): (0, 140, 255),
  (255, 105, 180): (255, 0, 128),
  (218, 111, 37): (255, 128, 0),
  (139, 108, 197): (128, 0, 255),
}


def enabled(state):
  return state.customization.get('statusStyle', 'classic') == 'neon'


def status_color(state, classic):
  if not enabled(state):
    return classic
  rgb = COLORS.get((classic.r, classic.g, classic.b))
  return rl.Color(*rgb, classic.a) if rgb is not None else classic


def render(rect, state, color, *, border_width, time_s):
  # Warnings and driver overrides always retain their existing steady treatment.
  if (not enabled(state) or not state.camera_available or state.alert.size != AlertSize.NONE or
      state.alert.critical or not (state.lateral_active or state.longitudinal_active) or
      state.driver_override_active or state.longitudinal_overridden or not math.isfinite(time_s) or
      (color.r, color.g, color.b) not in COLORS.values()):
    return
  if state.show_curve_status and state.curve is not None and state.curve.configured and state.curve.glow:
    return
  x, y, width, height = int(rect.x), int(rect.y), int(rect.width), int(rect.height)
  if min(width, height, border_width) <= 0:
    return
  phase = (time_s % 4.5) * 2 * math.pi / 4.5
  pulse = .76 + .2 * math.sin(phase)
  span = min(int(border_width * 1.8), min(width, height) // 5)
  alpha = int(76 * pulse)
  edge = rl.Color(color.r, color.g, color.b, alpha)
  fade = rl.Color(color.r, color.g, color.b, 0)
  rl.draw_rectangle_gradient_v(x, y, width, span, edge, fade)
  rl.draw_rectangle_gradient_v(x, y + height - span, width, span, fade, edge)
  rl.draw_rectangle_gradient_h(x, y, span, height, edge, fade)
  rl.draw_rectangle_gradient_h(x + width - span, y, span, height, fade, edge)


def decoration_color(state):
  if (not enabled(state) or state.alert.size != AlertSize.NONE or state.alert.critical or
      state.driver_override_active or state.longitudinal_overridden or not state.camera_available or
      not (state.lateral_active or state.longitudinal_active)):
    return None
  from openpilot.starpilot.ui.onroad import axis_status_color
  color = axis_status_color(state)
  return color if (color.r, color.g, color.b) in COLORS.values() else None


def frame_glow(rect, state, *, roundness=.15):
  color = decoration_color(state)
  if color is None:
    return
  for width, alpha in ((14, 12), (8, 22), (3, 55)):
    rl.draw_rectangle_rounded_lines_ex(rect, roundness, 10, width, rl.Color(color.r, color.g, color.b, alpha))


def circle_glow(center, radius, state):
  color = decoration_color(state)
  if color is None:
    return
  for width, alpha in ((10, 14), (5, 30), (1, 60)):
    rl.draw_ring(center, radius, radius + width, 0, 360, 48, rl.Color(color.r, color.g, color.b, alpha))


def model_style(state, profile):
  style = state.customization['roadColors'][profile]
  color = decoration_color(state)
  if color is None or not state.lead_indicator_source_fresh:
    return style
  return {**style, '_neonRgb': (color.r, color.g, color.b)}
