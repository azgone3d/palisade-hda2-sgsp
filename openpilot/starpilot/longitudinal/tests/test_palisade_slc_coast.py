from types import SimpleNamespace as NS
import pytest
from openpilot.starpilot.car.hyundai.palisade_slc import coast_only
from openpilot.starpilot.aol.tests.test_palisade_alpha_controls import alpha_params
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
from openpilot.starpilot.longitudinal.cruise_ceiling import CruiseCeiling
from openpilot.starpilot.longitudinal.tests.test_cruise_ceiling import ACTIVE,V_EGO,messages


@pytest.mark.parametrize('target', [5.,10.,19.])
def test_large_and_small_limit_drops_do_not_request_cruise_braking(target):
  planner=LongitudinalPlanner(alpha_params(),init_v=V_EGO)
  for _ in range(65):
    sm,_=messages();sm['carControl'].longActive=True
    planner.update(sm,cruise_ceiling=CruiseCeiling(target,ACTIVE))
  assert planner.a_cruise >= 0.


def test_other_platforms_and_other_braking_owners_are_not_coast_limited():
  cp=NS(carFingerprint='HYUNDAI_PALISADE_2023',openpilotLongitudinalControl=True)
  kwargs=dict(slc_target=19.,driver_cruise=25.)
  assert coast_only(cp,**kwargs)
  for extra in [dict(forced=True),dict(curve_target=18.),dict(navigation_target=18.)]:
    assert not coast_only(cp,**kwargs,**extra)
  cp.carFingerprint='OTHER'
  assert not coast_only(cp,**kwargs)


def test_slc_coast_does_not_suppress_lead_braking():
  planner=LongitudinalPlanner(alpha_params(),init_v=V_EGO)
  for _ in range(65):
    sm,_=messages(lead=True);sm['carControl'].longActive=True
    planner.update(sm,cruise_ceiling=CruiseCeiling(19.,ACTIVE))
  assert planner.a_cruise >= 0.
  assert planner.output_a_target < 0.
