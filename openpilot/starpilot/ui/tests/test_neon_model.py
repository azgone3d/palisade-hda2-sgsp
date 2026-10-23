from types import SimpleNamespace as NS
from dataclasses import replace
from unittest.mock import Mock, patch
import numpy as np
import pyray as rl
import pytest
from openpilot.starpilot.ui import neon_model, onroad_neon
from openpilot.starpilot.ui.tests.test_onroad_neon import state


def test_lane_glow_preserves_centre_and_has_bounded_geometry():
  points = np.array([[10., 100.], [20., 20.], [22., 20.], [14., 100.]])
  expanded = neon_model.expanded_lane(points, 3.)
  np.testing.assert_allclose((expanded[:2]+expanded[2:][::-1])/2, (points[:2]+points[2:][::-1])/2)
  np.testing.assert_allclose(points, [[10.,100.],[20.,20.],[22.,20.],[14.,100.]])
  draw = Mock()
  neon_model.draw_lane(rl.Rectangle(0,0,1800,1080), points, (0,140,255), .7, draw)
  assert draw.call_count == 2
  for invalid in (np.zeros((3,2)), np.full((4,2), np.nan), np.zeros((134,2))):
    assert neon_model.expanded_lane(invalid, 3.) is None
  draw.reset_mock()
  neon_model.draw_lane(None, points, (0,140,255), 0, draw)
  draw.assert_not_called()


def test_forward_chevron_uses_existing_tip_and_keeps_warning():
  lead=NS(chevron=[(120.,130.),(90.,100.),(60.,130.)], fill_alpha=0)
  with patch.object(neon_model.rl, 'draw_line_ex') as draw:
    assert neon_model.draw_chevron(lead,(0,140,255))
  assert draw.call_count == 6
  assert all(call.args[1].y == 100 or call.args[0].y == 100 for call in draw.call_args_list)
  lead.fill_alpha=220
  with patch.object(neon_model.rl,'draw_line_ex') as draw, patch.object(neon_model.rl,'draw_triangle_fan') as fill:
    assert neon_model.draw_chevron(lead,(0,140,255))
  assert draw.call_count == 6
  assert all(tuple(getattr(call.args[-1], c) for c in 'rgb') == (201,34,49) for call in draw.call_args_list)
  fill.assert_not_called()


def test_model_decorations_require_fresh_sources_and_leave_saved_document_untouched():
  s=state()
  assert '_neonRgb' not in onroad_neon.model_style(s,'large')
  s=replace(s,lead_indicator_source_fresh=True)
  assert onroad_neon.model_style(s,'large')['_neonRgb']==(0,140,255)
  assert '_neonRgb' not in s.customization['roadColors']['large']


@pytest.mark.parametrize('alpha', [0, 100, 199, 200, 255])
def test_neon_chevron_never_reverts_to_filled_triangle(alpha):
  lead = NS(chevron=[(120.,130.),(90.,100.),(60.,130.)], fill_alpha=alpha)
  with patch.object(neon_model.rl,'draw_line_ex') as draw, patch.object(neon_model.rl,'draw_triangle_fan') as fill:
    assert neon_model.draw_chevron(lead,(0,140,255))
  assert draw.call_count == 6
  fill.assert_not_called()


def test_neon_shape_is_retained_when_axes_are_inactive():
  s = replace(state(), lateral_active=False, longitudinal_active=False, lead_indicator_source_fresh=True)
  assert '_neonRgb' in onroad_neon.model_style(s, 'large')


def test_projection_uses_shared_neon_style_and_hides_stale_leads():
  from openpilot.starpilot.system.android_auto.projection_onroad import ProjectionOnroad
  view = object.__new__(ProjectionOnroad)
  view.camera = Mock(stream_type='road')
  for fresh in (False, True):
    s = replace(state(), lead_indicator_source_fresh=fresh)
    s = replace(s, appearance=replace(s.appearance, show_lead_indicator=True))
    view._camera_layer(None, s)
    kwargs = view.camera.render_camera_model_layer.call_args.kwargs
    assert kwargs['lead_display'][0] is fresh
    assert ('_neonRgb' in kwargs['road_style']) is fresh
    if fresh:
      assert kwargs['road_style']['_neonRgb'] == (0, 140, 255)
    assert view.camera_stream == 'road'
