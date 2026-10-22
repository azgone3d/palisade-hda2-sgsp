"""Recorded Park/LKAS regression: selection only, no vehicle I/O or axis grant."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from opendbc.car import structs as car
from opendbc.car.hyundai.tests.test_blended_stock_aol import params
from openpilot.cereal import messaging, log
from openpilot.selfdrive.selfdrived.selfdrived import SelfdriveD
from openpilot.selfdrive.selfdrived.events import Events, EventName
from openpilot.starpilot.aol.intent import AolSettings, AolCardIntent
from openpilot.starpilot.aol.transport_pause import TransportPauseFeedback
from openpilot.starpilot.aol.wire import IntentState
from openpilot.starpilot.car.hyundai.palisade_park import cold_park_readiness

NOW = 10_000_000_000


class SM(dict):
  def all_checks(self, services):
    return self.healthy


def fixture():
  cp = params(hda2=True)
  cp.alternativeExperience = 32
  cs = car.CarState(canValid=True, standstill=True, gearShifter='park')
  events = Events()
  for name in (EventName.wrongGear, EventName.wrongCarMode, EventName.pcmDisable):
    events.add(name)
  native = SimpleNamespace(pandaInventory=[object()], requestedLateral=False, lateralAllowed=False, requestedLongitudinal=False, longitudinalAllowed=False)
  sm = SM(extrinsicsCalibration=SimpleNamespace(calStatus=log.ExtrinsicsCalibration.Status.calibrated))
  sm.healthy = True
  intent = IntentState('a' * 32, 1, NOW - 10, NOW - 5, NOW + 100_000_000, False, False, False, True, False)
  sd = SimpleNamespace(
    CP=cp,
    initialized=True,
    enabled=False,
    active=False,
    aol_authority_lost=False,
    conditional_car_state_valid=True,
    aol_car_state_log_ns=NOW - 10,
    aol_session_id='b' * 32,
    sm=sm,
    events=events,
  )
  return cp, cs, events, native, intent, sd


def readiness(sd, cs, intent, native):
  with patch('openpilot.starpilot.aol.transport_pause._healthy_transport_native', return_value=native):
    return SelfdriveD.cold_palisade_park_readiness(sd, cs, intent, NOW)


def test_recorded_park_is_idle_readiness_not_critical():
  _, cs, _, native, intent, sd = fixture()
  assert readiness(sd, cs, intent, native)
  # This is the preexisting output contract: selection never authorizes Park.
  owner = AolCardIntent(AolSettings(True, 0.0, 9, 0, (0, 0, 0), (0, 0, 0)), explicit_latch=True, independent_cruise_buttons=True)
  owner.update(cs, fault_active=False, now_ns=NOW)
  cs.buttonEvents = [car.CarState.ButtonEvent(type='lkas', pressed=True)]
  owner.update(cs, fault_active=False, now_ns=NOW + 1)
  assert owner.allowed_latch
  assert owner.output(cs) == (False, False, False)
  cs.buttonEvents = [car.CarState.ButtonEvent(type='lkas', pressed=False)]
  owner.update(cs, fault_active=False, now_ns=NOW + 2)
  assert owner.allowed_latch and not owner.output(cs)[0]


@pytest.mark.parametrize(
  'field,value',
  [
    ('gearShifter', 'drive'),
    ('gearShifter', 'reverse'),
    ('standstill', False),
    ('vEgo', 1.0),
    ('vEgo', float('nan')),
    ('canValid', False),
    ('canTimeout', True),
    ('seatbeltUnlatched', True),
    ('doorOpen', True),
    ('gasPressed', True),
    ('steerFaultTemporary', True),
    ('steerFaultPermanent', True),
    ('accFaulted', True),
  ],
)
def test_vehicle_restrictions_are_not_park_readiness(field, value):
  cp, cs, events, native, _, _ = fixture()
  setattr(cs, field, value)
  assert not cold_park_readiness(cp, cs, native, events.to_msg())


@pytest.mark.parametrize('name', ['calibrationIncomplete', 'commIssue', 'controlsMismatch', 'processNotRunning', 'relayMalfunction'])
def test_real_faults_remain_disarming(name):
  cp, cs, events, native, _, _ = fixture()
  events.add(getattr(EventName, name))
  assert not cold_park_readiness(cp, cs, native, events.to_msg())


@pytest.mark.parametrize('field', ['requestedLateral', 'lateralAllowed', 'requestedLongitudinal', 'longitudinalAllowed'])
def test_any_native_axis_prevents_idle_exception(field):
  cp, cs, events, native, _, _ = fixture()
  setattr(native, field, True)
  assert not cold_park_readiness(cp, cs, native, events.to_msg())


def test_other_profile_and_missing_native_are_refused():
  cp, cs, events, native, _, _ = fixture()
  assert not cold_park_readiness(cp, cs, None, events.to_msg())
  cp.safetyConfigs[0].safetyParam = 0x2000
  assert not cold_park_readiness(cp, cs, native, events.to_msg())


@pytest.mark.parametrize('change', ['stale', 'uncalibrated', 'model', 'active', 'prior_active', 'lost', 'intent_output', 'no_native'])
def test_host_readiness_guards(change):
  _, cs, _, native, intent, sd = fixture()
  if change == 'stale':
    intent = IntentState('a' * 32, 1, 1, 2, 3, False, False, False, True, False)
    sd.aol_car_state_log_ns = 1
  elif change == 'uncalibrated':
    sd.sm['extrinsicsCalibration'].calStatus = log.ExtrinsicsCalibration.Status.uncalibrated
  elif change == 'model':
    sd.sm.healthy = False
  elif change == 'active':
    sd.active = True
  elif change == 'prior_active':
    sd.aol_ever_active = True
  elif change == 'lost':
    sd.aol_authority_lost = True
  elif change == 'intent_output':
    intent = IntentState('a' * 32, 1, NOW - 10, NOW - 5, NOW + 100_000_000, True, False, False, True, True)
  elif change == 'no_native':
    native = None
  assert not readiness(sd, cs, intent, native)


def test_parked_selection_feedback_does_not_revoke_latch():
  cp, cs, events, native, _, _ = fixture()
  axis = messaging.new_message('aolAxisState', valid=True, logMonoTime=NOW)
  a = axis.aolAxisState
  a.sessionId = 'b' * 32
  a.faultSessionId = a.sessionId
  a.sequence = 1
  a.observedMonoTime = NOW
  a.validUntilMonoTime = NOW + 20_000_000
  a.sourceCarStateMonoTime = NOW - 10
  a.qualified = True
  a.nativeAcknowledged = True
  a.faultReason = 'none'
  a.faultEventMonoTime = NOW - 5
  a.intentProducerSessionId = 'a' * 32
  a.intentIntegrityEpoch = 1
  sm = SM(aolAxisState=a, onroadEvents=events.to_msg())
  sm.seen = sm.valid = sm.alive = {'aolAxisState': True, 'onroadEvents': True}
  sm.logMonoTime = {'aolAxisState': NOW, 'onroadEvents': NOW - 5}
  feedback = TransportPauseFeedback(cp)
  with patch('openpilot.starpilot.aol.transport_pause._healthy_transport_native', return_value=native):
    assert not feedback.observe(sm, cp, cs, NOW, latched=True, intent_producer_session='a' * 32)
  assert feedback.cold_park_waiting and not feedback.failed
  # No axis request/permission is invented by waiting selection feedback.
  assert not a.desiredLateral and not a.lateralActive and not native.lateralAllowed


def test_actual_selfdrived_publishes_idle_proof_for_palisade_park():
  from openpilot.common.prefix import OpenpilotPrefix
  from openpilot.starpilot.aol.tests.test_ioniq_availability import IoniqAvailabilityTests
  from openpilot.starpilot.aol.wire import encode_intent

  cp, cs, _, _, _, _ = fixture()
  case = IoniqAvailabilityTests(methodName='runTest')
  with OpenpilotPrefix():
    try:
      sd, _, step = case._authority_callers(False, cp=cp, genuine_events=True)
      for tick in range(3):
        now = NOW + tick * 10_000_000
        state = messaging.new_message('carState', valid=True, logMonoTime=now)
        state.carState = cs
        selected = messaging.new_message('aolIntentWire', 0, valid=True, logMonoTime=now)
        selected.aolIntentWire = encode_intent(IntentState('authority-card', tick + 1, now, now, now + 200_000_000, False, False, False, True, tick > 0))
        axis, host, command = step(
          tick,
          car_state_message=state,
          intent_message=selected,
          allowed=False,
          latched=False,
          native_request_lat=False,
          native_request_long=False,
          long_allowed=False,
        )
        assert str(axis.faultReason) == 'none'
        assert axis.nativeAcknowledged
        assert not axis.desiredLateral and not axis.desiredLongitudinal
        assert not axis.lateralActive and not axis.longitudinalActive
        assert not host.enabled and not command.latActive and not command.longActive
    finally:
      case.doCleanups()
