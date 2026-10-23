from types import SimpleNamespace as NS
import pytest
from openpilot.starpilot.ui.lead_markers import duplicate_vision_lead


def lead(**changes):
  return NS(**(dict(present=True, radar=False, dRel=32.33, yRel=-.0013, vRel=.353) | changes))


def test_recorded_pair_is_one_display_marker_without_mutating_tracks():
  first, second = lead(), lead(dRel=32.426, yRel=-.0030, vRel=.332)
  original = vars(second).copy()
  assert duplicate_vision_lead(first, second)
  assert vars(second) == original


@pytest.mark.parametrize('changes', [dict(present=False), dict(radar=True), dict(dRel=35.),
  dict(yRel=1.), dict(vRel=3.), dict(dRel=float('nan')), dict(vRel=float('inf'))])
def test_distinct_or_unusable_tracks_are_not_merged(changes):
  assert not duplicate_vision_lead(lead(), lead(**changes))
  assert not duplicate_vision_lead(lead(**changes), lead())


def test_renderer_draws_recorded_pair_once_but_keeps_adjacent_vehicle():
  import numpy as np
  import pyray as rl
  from unittest.mock import Mock
  from openpilot.selfdrive.ui.onroad.model_renderer import ModelRenderer
  renderer = object.__new__(ModelRenderer)
  renderer._path = NS(raw_points=np.zeros((2, 3)))
  renderer._path_offset_z = 0.
  renderer._rect = rl.Rectangle(0, 0, 1600, 800)
  renderer._map_to_screen = Mock(return_value=(800., 300.))
  radar = NS(leadOne=lead(), leadTwo=lead(dRel=32.426, yRel=-.003, vRel=.332))
  renderer._update_leads(radar, np.array([0., 100.]))
  assert [bool(l.chevron) for l in renderer._lead_vehicles] == [True, False]
  radar.leadTwo.yRel = 3.
  renderer._update_leads(radar, np.array([0., 100.]))
  assert [bool(l.chevron) for l in renderer._lead_vehicles] == [True, True]
