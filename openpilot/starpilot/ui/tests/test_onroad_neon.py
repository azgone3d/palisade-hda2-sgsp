from dataclasses import replace
from unittest.mock import patch

import pyray as rl
import pytest

from openpilot.starpilot.ui import onroad_neon as neon
from openpilot.starpilot.ui.onroad import axis_status_color
from openpilot.starpilot.ui.onroad_customization import default_document, validate_document
from openpilot.starpilot.ui.onroad_state import AlertSize, OnroadAlert
from openpilot.starpilot.ui.preview_shell import reference_onroad


def state():
  doc = default_document()
  doc['statusStyle'] = 'neon'
  return replace(reference_onroad('onroad_engaged_no_camera'), camera_available=True,
                 customization=validate_document(doc), lateral_active=True, longitudinal_active=False)


def test_saved_style_roundtrip_and_legacy_default():
  assert 'statusStyle' not in validate_document(default_document())
  assert state().customization['statusStyle'] == 'neon'
  for invalid in (True, None, [], {}, 'fire', 1):
    doc = default_document(); doc['statusStyle'] = invalid
    with pytest.raises(ValueError):
      validate_document(doc)


def test_neon_retains_distinct_axes_and_override():
  s = state()
  assert tuple(getattr(axis_status_color(s), c) for c in 'rgb') == (0, 140, 255)
  combined = replace(s, longitudinal_active=True, experimental_enabled=False)
  assert tuple(getattr(axis_status_color(combined), c) for c in 'rgb') == (0, 255, 128)
  override = replace(s, driver_override_active=True)
  assert tuple(getattr(axis_status_color(override), c) for c in 'rgba') == (145, 155, 149, 255)


def test_stopped_ready_keeps_border_without_claiming_active_steering():
  stopped = replace(state(), lateral_active=False, lateral_standstill_ready=True)
  assert tuple(getattr(axis_status_color(stopped), c) for c in 'rgb') == (0, 140, 255)
  assert not stopped.lateral_active
  with patch.object(neon.rl, 'draw_rectangle_gradient_v') as vertical, patch.object(neon.rl, 'draw_rectangle_gradient_h'):
    neon.render(rl.Rectangle(30,30,1800,1020), stopped, axis_status_color(stopped), border_width=30, time_s=1.)
  assert vertical.call_count == 2


@pytest.mark.parametrize('change', [dict(alert=OnroadAlert(size=AlertSize.SMALL)),
  dict(alert=OnroadAlert(critical=True)), dict(camera_available=False),
  dict(lateral_active=False), dict(driver_override_active=True), dict(longitudinal_overridden=True)])
def test_alerts_off_and_override_never_animate(change):
  s = replace(state(), **change)
  with patch.object(neon.rl, 'draw_rectangle_gradient_v') as vertical, patch.object(neon.rl, 'draw_rectangle_gradient_h') as horizontal:
    neon.render(rl.Rectangle(30, 30, 1800, 1020), s, axis_status_color(s), border_width=30, time_s=1.)
  vertical.assert_not_called(); horizontal.assert_not_called()


def test_bounded_draw_count_transparency_and_finite_clock():
  s = state()
  for t in (0., 1.125, 2.25, 3.375):
    with patch.object(neon.rl, 'draw_rectangle_gradient_v') as vertical, patch.object(neon.rl, 'draw_rectangle_gradient_h') as horizontal:
      neon.render(rl.Rectangle(30, 30, 1800, 1020), s, axis_status_color(s), border_width=30, time_s=t)
    assert vertical.call_count == horizontal.call_count == 2
    for call in vertical.call_args_list + horizontal.call_args_list:
      assert sorted(c.a for c in call.args[-2:])[0] == 0
      assert 70 <= max(c.a for c in call.args[-2:]) <= 140
  with patch.object(neon.rl, 'draw_rectangle_gradient_v') as draw:
    neon.render(rl.Rectangle(0, 0, 476, 240), s, axis_status_color(s), border_width=8, time_s=float('nan'))
  draw.assert_not_called()
