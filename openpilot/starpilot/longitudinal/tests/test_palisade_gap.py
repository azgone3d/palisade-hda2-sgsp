"""Real MPC constraints and solver response for the requested Palisade buffer."""

import numpy as np
import pytest

from openpilot.cereal import log
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
from openpilot.starpilot.aol.tests.test_palisade_alpha_controls import alpha_params
from openpilot.starpilot.car.hyundai.palisade_gap import lead_buffer
from openpilot.starpilot.longitudinal.tests.test_conditional_handoff import Frame, NOW, DRIVE
from openpilot.starpilot.longitudinal.cruise_ceiling import CruiseCeiling
from openpilot.starpilot.speed_limits.acceptance import Authority, LongitudinalOwner, Mode


def frame():
  sm = Frame()
  sm['carState'].gearShifter = 'drive'
  return sm


def radar(distance=30.0):
  rr = log.RadarState.new_message()
  rr.leadOne.present = True
  rr.leadOne.dRel, rr.leadOne.vLead, rr.leadOne.aLeadTau = distance, 0.0, 1.5
  rr.leadOne.modelProb = 0.99
  return rr


@pytest.mark.parametrize('extra_gap', [1.5, 2.0])
def test_actual_solver_matches_closer_obstacle_without_changing_measured_lead(extra_gap):
  buffered, translated, normal = LongitudinalMpc(), LongitudinalMpc(), LongitudinalMpc()
  actual = radar()
  for mpc, lead, buffer in [(buffered, actual, extra_gap), (translated, radar(30.0-extra_gap), 0.0), (normal, actual, 0.0)]:
    mpc.set_cur_state(8.0, 0.0)
    mpc.set_weights()
    mpc.update(lead, lead_buffer_m=buffer)
    assert mpc.solution_status == 0
  np.testing.assert_allclose(buffered.a_solution, translated.a_solution, atol=1e-7)
  assert np.min(buffered.a_solution) <= np.min(normal.a_solution)
  assert actual.leadOne.dRel == 30.0
  np.testing.assert_allclose(normal.params[:, 2] - buffered.params[:, 2], extra_gap)


@pytest.mark.parametrize('invalid', [float('nan'), -1.0, 2.01])
def test_invalid_offset_cannot_change_native_mpc(invalid):
  normal, invalid_mpc = LongitudinalMpc(), LongitudinalMpc()
  for mpc, offset in [(normal, 0.0), (invalid_mpc, invalid)]:
    mpc.set_cur_state(8.0, 0.0)
    mpc.update(radar(), lead_buffer_m=offset)
  np.testing.assert_array_equal(normal.params, invalid_mpc.params)


def test_missing_leads_do_not_move_fake_obstacles_or_stop_lines():
  normal, buffered = LongitudinalMpc(), LongitudinalMpc()
  empty = log.RadarState.new_message()
  for mpc, offset in [(normal, 0.0), (buffered, 1.5)]:
    mpc.set_cur_state(8.0, 0.0)
    mpc.update(empty, stop_line_m=10.0, lead_buffer_m=offset)
  np.testing.assert_array_equal(normal.params, buffered.params)


def test_real_planner_receives_buffer_only_on_exact_active_profile():
  cp = alpha_params()
  sm = frame()
  sm['radarState'].leadOne = radar().leadOne
  planner = LongitudinalPlanner(cp)
  planner.update(sm, now_ns=NOW, drive_id=DRIVE)
  assert lead_buffer(cp, sm, NOW) == 2.0
  assert planner.mpc.params[0, 2] == 28.0
  sm['carControl'].longActive = False
  assert lead_buffer(cp, sm, NOW) == 0.0
  sm['carControl'].longActive = True
  sm.logMonoTime['radarState'] = NOW - 250_000_001
  assert lead_buffer(cp, sm, NOW) == 0.0
  sm.logMonoTime['radarState'] = NOW - 1
  cp.safetyConfigs[0].safetyParam = 0x2010
  assert lead_buffer(cp, sm, NOW) == 0.0


def test_speed_limit_ceiling_reaches_actual_palisade_planner():
  cp = alpha_params()
  sm = frame()
  sm['carState'].vCruise = 90.0
  authority = Authority(Mode.LONGITUDINAL_ONLY, LongitudinalOwner.SYSTEM, False, True, False, False)
  planner = LongitudinalPlanner(cp)
  planner.update(sm, now_ns=NOW, drive_id=DRIVE, cruise_ceiling=CruiseCeiling(15.0, authority))
  assert planner.last_cruise_ceiling_status == 'applied'


def test_gap_change_is_restricted_to_palisade_fingerprint():
  cp = alpha_params()
  cp.carFingerprint = 'OTHER_CAR'
  assert lead_buffer(cp, frame(), NOW) == 0.0
