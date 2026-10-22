"""Reference-style Palisade blinker intent, through the real desire helper."""

import pytest
from openpilot.cereal import log
from opendbc.car import structs as car
from opendbc.car.hyundai.tests.test_blended_stock_aol import params
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper
from openpilot.starpilot.car.hyundai.palisade_turn import turn_desire, MAX_TURN_SPEED

NOW = 10_000_000_000


class Snapshot(dict):
  pass


def fixture(alpha=False):
  cp = params(hda2=True)
  cp.alternativeExperience = 32
  if alpha:
    cp.openpilotLongitudinalControl, cp.pcmCruise = True, False
    cp.safetyConfigs[0].safetyParam = 0x2014
  sm = Snapshot(carState=car.CarState(canValid=True, gearShifter='drive', vEgo=5.0, leftBlinker=True), carControl=car.CarControl(latActive=True))
  sm.seen = sm.valid = sm.alive = dict.fromkeys(sm, True)
  sm.logMonoTime = dict.fromkeys(sm, NOW)
  return cp, sm


@pytest.mark.parametrize('alpha', [False, True])
def test_immediate_signal_direction_without_navigation_and_no_lane_change_conflict(alpha):
  cp, sm = fixture(alpha)
  dh = DesireHelper()
  for left, right, expected in [
    (True, False, log.Desire.turnLeft),
    (True, False, log.Desire.turnLeft),
    (False, False, log.Desire.none),
    (False, True, log.Desire.turnRight),
  ]:
    sm['carState'].leftBlinker, sm['carState'].rightBlinker = left, right
    selected = turn_desire(cp, sm, NOW, dh.desire, supported=True)
    assert selected == expected
    dh.update(sm['carState'], True, 0.0, navigation_turn=selected in (log.Desire.turnLeft, log.Desire.turnRight))
    assert dh.lane_change_state == log.LaneChangeState.off
  assert not sm['carControl'].longActive  # Independent lateral also qualifies.


@pytest.mark.parametrize(
  'fault',
  [
    'unsupported',
    'inactive',
    'hazards',
    'blindspot',
    'high_speed',
    'nan_speed',
    'negative_speed',
    'park',
    'can_invalid',
    'eps',
    'seatbelt',
    'stale',
    'future',
    'unseen',
    'bad_profile',
  ],
)
def test_restrictions_leave_no_turn_hint(fault):
  cp, sm = fixture()
  supported = fault != 'unsupported'
  cs = sm['carState']
  if fault == 'inactive':
    sm['carControl'].latActive = False
  elif fault == 'hazards':
    cs.rightBlinker = True
  elif fault == 'blindspot':
    cs.leftBlindspot = True
  elif fault == 'high_speed':
    cs.vEgo = MAX_TURN_SPEED + 0.001
  elif fault == 'nan_speed':
    cs.vEgo = float('nan')
  elif fault == 'negative_speed':
    cs.vEgo = -1.0
  elif fault == 'park':
    cs.gearShifter = 'park'
  elif fault == 'can_invalid':
    cs.canValid = False
  elif fault == 'eps':
    cs.steerFaultTemporary = True
  elif fault == 'seatbelt':
    cs.seatbeltUnlatched = True
  elif fault == 'stale':
    sm.logMonoTime['carControl'] = NOW - 100_000_001
  elif fault == 'future':
    sm.logMonoTime['carState'] = NOW + 1
  elif fault == 'unseen':
    sm.seen['carState'] = False
  elif fault == 'bad_profile':
    cp.safetyConfigs[0].safetyParam = 0x2000
  assert turn_desire(cp, sm, NOW, log.Desire.none, supported=supported) == log.Desire.none


@pytest.mark.parametrize('existing', [log.Desire.laneChangeLeft, log.Desire.laneChangeRight, log.Desire.turnRight])
def test_existing_maneuver_keeps_priority(existing):
  cp, sm = fixture()
  assert turn_desire(cp, sm, NOW, existing, supported=True) == existing
