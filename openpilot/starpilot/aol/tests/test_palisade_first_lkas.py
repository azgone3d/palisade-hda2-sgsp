"""Palisade first-use LKAS with stock cruise off; no vehicle I/O."""

from openpilot.common.prefix import OpenpilotPrefix
import pytest
from openpilot.cereal import messaging
from opendbc.car import structs as car
from opendbc.car.hyundai.tests.test_blended_stock_aol import params
from openpilot.starpilot.aol.intent import AolSettings
from openpilot.starpilot.aol.tests import test_ioniq_availability as authority_fixture
from openpilot.starpilot.aol.transport_pause import TransportPauseFeedback
from openpilot.starpilot.aol.wire import IntentState, encode_intent
from openpilot.starpilot.car.hyundai.aol import create_intent, policy_for

BASE = 10_000_000_000


def test_only_exact_palisade_hda2_profiles_have_independent_cruise_readiness():
  stock = params(hda2=True)
  assert not policy_for(stock).cruise_main_required
  assert policy_for(params(hda2=False)).cruise_main_required
  longitudinal = stock.as_reader().as_builder()
  longitudinal.openpilotLongitudinalControl = True
  longitudinal.pcmCruise = False
  longitudinal.safetyConfigs[0].safetyParam = 0x2014
  assert not policy_for(longitudinal).cruise_main_required
  stock.safetyConfigs[0].safetyParam |= 4
  assert policy_for(stock).cruise_main_required


class Snapshot(dict):
  pass


@pytest.mark.parametrize('alpha', [False, True])
def test_first_lkas_without_any_prior_cruise_then_brake_and_main(alpha):
  cp = params(hda2=True)
  if alpha:
    cp.openpilotLongitudinalControl, cp.pcmCruise = True, False
    cp.safetyConfigs[0].safetyParam = 0x2014
  cp.alternativeExperience = 32
  owner = create_intent(cp, AolSettings(True, 0.0, 9, 0, (0, 0, 0), (0, 0, 0)))
  cs = car.CarState(canValid=True, gearShifter='drive', vEgo=10.0)
  feedback = TransportPauseFeedback(cp)
  feedback.failed = True  # Recorded startup Park/communication fault, before the first LKAS press.
  case = authority_fixture.IoniqAvailabilityTests(methodName='runTest')
  previous = None
  with OpenpilotPrefix():
    try:
      sd, _, step = case._authority_callers(False, cp=cp, genuine_events=True)
      for tick in range(6):
        now = BASE + tick * 10_000_000
        cs.buttonEvents = []
        if tick in (1, 5):
          cs.buttonEvents = [car.CarState.ButtonEvent(type='lkas', pressed=True)]
        elif tick == 2:
          cs.buttonEvents = [car.CarState.ButtonEvent(type='lkas', pressed=False)]
        elif tick == 4:
          cs.buttonEvents = [car.CarState.ButtonEvent(type='mainCruise', pressed=True)]
        cs.brakePressed = tick == 3
        fault = False if previous is None else feedback.observe(previous, cp, cs, now, latched=owner.allowed_latch, intent_producer_session='authority-card')
        assert not fault
        owner.update(cs, now_ns=now, fault_active=fault)
        expected = 1 <= tick < 5
        assert owner.allowed_latch == expected
        state = messaging.new_message('carState', valid=True, logMonoTime=now)
        state.carState = cs
        selected = messaging.new_message('aolIntentWire', 0, valid=True, logMonoTime=now)
        allowed, pause_lat, pause_long = owner.output(cs)
        selected.aolIntentWire = encode_intent(
          IntentState('authority-card', tick + 1, now, now, now + 200_000_000, allowed, pause_lat, pause_long, True, owner.allowed_latch)
        )
        axis, host, command = step(
          tick,
          car_state_message=state,
          intent_message=selected,
          allowed=tick >= 2,
          latched=allowed,
          native_request_lat=tick >= 2,
          native_request_long=False,
          long_allowed=False,
        )
        assert str(axis.faultReason) == 'none'
        assert axis.desiredLateral == expected
        # The initial request alone cannot activate steering without its native response.
        assert axis.lateralActive == (expected and tick >= 2)
        assert command.latActive == axis.lateralActive
        assert not axis.longitudinalActive and not command.longActive and not host.enabled
        assert not cs.cruiseState.available and not cs.cruiseState.enabled
        previous = Snapshot(
          aolAxisState=axis, onroadEvents=sd.pm.messages['onroadEvents'].onroadEvents, aolSafetyWire=sd.sm['aolSafetyWire'], pandaStates=sd.sm['pandaStates']
        )
        previous.seen = previous.valid = previous.alive = dict.fromkeys(previous, True)
        previous.logMonoTime = {k: int(sd.sm.logMonoTime[k]) for k in ('aolSafetyWire', 'pandaStates')}
        previous.logMonoTime.update(aolAxisState=int(axis.observedMonoTime), onroadEvents=int(sd.pm.messages['onroadEvents'].logMonoTime))
    finally:
      case.doCleanups()
