"""Optional native telemetry panel; rendering only, no IPC or control writes."""
import math
import pyray as rl

from openpilot.starpilot.ui.onroad_customization import placement
from openpilot.starpilot.ui.onroad_large_widgets import SteeringWheelWidget
from openpilot.starpilot.ui.onroad_state import AlertSize
from openpilot.starpilot.ui.presentation import FontRole
from openpilot.starpilot.ui.wheel_feedback import wheel_rotation

KEY = 'telemetry_overlay'
MINI_KEY = 'telemetry_wheel'
WIDTH, HEIGHT = 440, 900
WHITE = rl.Color(240, 247, 250, 255)
MUTED = rl.Color(163, 180, 190, 255)
TRACK = rl.Color(39, 57, 68, 255)
COLORS = (rl.Color(136, 218, 250, 255), rl.Color(134, 234, 190, 255),
          rl.Color(255, 215, 122, 255), rl.Color(255, 168, 112, 255))
THEME_COLORS = (rl.Color(0, 140, 255, 255), rl.Color(0, 255, 128, 255),
                rl.Color(128, 0, 255, 255), rl.Color(255, 128, 0, 255))


def shown(value, suffix='', scale=1., digits=2):
  return '—' if value is None else f'{value * scale:+.{digits}f}{suffix}'


class TelemetryOverlay:
  def __init__(self, fonts, assets):
    self.fonts = fonts
    self.wheel = SteeringWheelWidget(assets)

  def render(self, state, *, mini=False):
    saved = placement(state.customization, 'large', MINI_KEY if mini else KEY)
    # Never cover any alert. Resources stay unallocated while the option is off.
    if not saved['enabled'] or state.alert.size != AlertSize.NONE:
      return
    x, y = saved['x'], saved['y']
    if mini:
      x += state.viewport_width - 1860
    observation = state.telemetry
    from openpilot.starpilot.ui.onroad_neon import enabled, circle_glow, decoration_color
    neon = enabled(state)
    colors = THEME_COLORS if neon else COLORS
    if not mini:
      rl.draw_rectangle_rec(rl.Rectangle(x, y, WIDTH, HEIGHT), rl.Color(4, 15, 23, 232))

    def text(value, dx, dy, color=MUTED, size=23):
      self.fonts.draw(value, FontRole.NORMAL, size, x + dx, y + dy, color)

    if not mini:
      text('TELEMETRY', 18, 16)
    scale = .68 if mini else 1.
    cx, cy = (x + 120, y + 120) if mini else (x + 190, y + 184)
    # Four fixed-cost arcs share a signed centre and fixed +/-180 degree scales.
    # No history, live allocations of textures, or per-frame file reads.
    values = (None if observation.desired_lateral is None else observation.desired_lateral / 3.,
              None if observation.actual_lateral is None else observation.actual_lateral / 3.,
              observation.target_torque, observation.applied_torque)
    for index, (value, color) in enumerate(zip(values, colors, strict=True)):
      radius = ((155 - index * 12) if neon else (151 - index * 8)) * scale
      rl.draw_ring(rl.Vector2(cx, cy), radius, radius + (5 if neon else 3) * scale, 145, 395, 48, TRACK)
      if value is not None:
        angle = 270 + max(-1., min(1., value)) * 125
        rl.draw_ring(rl.Vector2(cx, cy), radius, radius + (8 if neon else 4) * scale, min(270, angle), max(270, angle) + .15, 24, color)
    experimental = bool(mini and state.experimental_enabled)
    circle_glow(rl.Vector2(cx, cy), 112 * scale, state, subtle=True)
    self.wheel.prepare(experimental=experimental)
    texture = self.wheel._experimental_texture if experimental else self.wheel._texture
    rl.draw_texture_pro(texture, rl.Rectangle(0, 0, 144, 144),
                        rl.Rectangle(cx, cy, 220 * scale, 220 * scale), rl.Vector2(110 * scale, 110 * scale),
                        wheel_rotation(observation.angle), (decoration_color(state) or WHITE) if observation.angle is not None else MUTED)
    text('<', 7 if mini else 24, 107 if mini else 165, colors[1] if observation.left_blinker else TRACK, 24 if mini else 36)
    text('>', 215 if mini else 330, 107 if mini else 165, colors[1] if observation.right_blinker else TRACK, 24 if mini else 36)
    if mini:
      return
    rows = (('DES LAT', shown(observation.desired_lateral, ' m/s²'), colors[0]),
            ('ACT LAT', shown(observation.actual_lateral, ' m/s²'), colors[1]),
            ('TGT %', shown(observation.target_torque, '%', 100, 0), colors[2]),
            ('APP %', shown(observation.applied_torque, '%', 100, 0), colors[3]),
            ('ACTUAL', shown(observation.angle, ' deg', digits=1), WHITE))
    for index, (label, value, color) in enumerate(rows):
      text(label, 18, 355 + index * 43, size=21)
      text(value, 170, 352 + index * 43, color, 25)
    text('DRIVER TORQUE', 18, 582, size=19)
    text('—' if observation.driver_torque is None else 'DETECTED' if observation.driver_torque else 'NOT DETECTED',
         180, 582, WHITE, 21)
    text('LATERAL', 18, 621, size=19)
    text('—' if observation.lateral_active is None else 'ACTIVE' if observation.lateral_active else 'OFF', 180, 621, WHITE)
    for index, (label, value) in enumerate((('GAS PEDAL', observation.gas_pressed), ('BRAKE PEDAL', observation.brake_pressed))):
      text(label, 18, 665 + index * 42, size=20)
      text('—' if value is None else 'PRESSED' if value else 'RELEASED', 180, 665 + index * 42, WHITE, 22)
    for index, (label, value) in enumerate((('A EGO', observation.acceleration), ('A TARGET', observation.target_acceleration),
                                          ('CMD', observation.command_acceleration), ('OUT', observation.output_acceleration))):
      text(label, 16 + index * 100, 763, size=18)
      text(shown(value), 16 + index * 100, 793, WHITE, 24)
    text('Acceleration: m/s² · CMD/OUT are requests', 16, 843, size=18)
    text('Arcs: lat ±3 m/s² · torque ±100%', 16, 870, size=17)
    # This is SGSP's existing model score, not a probability of safe steering.
    confidence = state.model_confidence if state.stock_confidence_source_fresh else None
    text('MODEL', 362, 53, size=17)
    text('SCORE', 362, 74, size=17)
    rl.draw_rectangle_rec(rl.Rectangle(x + 390, y + 110, 5, 620), TRACK)
    if confidence is not None and math.isfinite(confidence) and 0 <= confidence <= 1:
      rl.draw_circle(int(x + 392), int(y + 730 - confidence * 620), 10, COLORS[1])
    else:
      text('—', 382, 745, size=22)

  def close(self):
    self.wheel.close()
