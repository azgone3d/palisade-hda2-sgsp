"""Exact Palisade experimental profile, mapped buttons and pedal ordering."""
from openpilot.common.prefix import OpenpilotPrefix
import pytest
from opendbc.car import structs as car
from opendbc.car.hyundai.tests.test_blended_stock_aol import params
from openpilot.starpilot.aol.intent import AolSettings
from openpilot.starpilot.aol.tests import test_ioniq_availability as authority_fixture
from openpilot.starpilot.aol.transport_pause import TransportPauseFeedback
from openpilot.starpilot.car.hyundai.aol import create_intent, independent_cruise_buttons_supported, policy_for


def alpha_params():
  cp = params(hda2=True)
  cp.openpilotLongitudinalControl, cp.pcmCruise = True, False
  cp.safetyConfigs[0].safetyParam, cp.alternativeExperience = 0x2014, 32
  return cp


def test_alpha_lkas_and_main_use_the_configured_separate_actions():
  cp = alpha_params()
  assert independent_cruise_buttons_supported(cp, marked_only=True)
  assert not policy_for(cp).cruise_main_required
  owner = create_intent(cp, AolSettings(True, 0., 9, 0, (0, 0, 0), (0, 0, 0)))
  assert owner.independent_cruise_buttons
  cs = car.CarState(canValid=True, gearShifter='drive')
  owner.update(cs, now_ns=1, fault_active=False)
  cs.buttonEvents = [car.CarState.ButtonEvent(type='lkas', pressed=True), car.CarState.ButtonEvent(type='lkas', pressed=False)]
  owner.update(cs, now_ns=2, fault_active=False)
  assert owner.allowed_latch
  cs.buttonEvents = [car.CarState.ButtonEvent(type='mainCruise', pressed=True)]
  owner.update(cs, now_ns=3, fault_active=False)
  assert owner.allowed_latch
  cs.buttonEvents = []
  cs.brakePressed = True
  owner.update(cs, now_ns=4, fault_active=False)
  assert owner.allowed_latch
  cp.safetyConfigs[0].safetyParam = 0x2010
  assert not independent_cruise_buttons_supported(cp, marked_only=True)
  assert policy_for(cp).cruise_main_required


@pytest.mark.parametrize('health_allowed', [False, True])
def test_native_long_withdrawal_before_parsed_brake_keeps_acknowledged_lateral(health_allowed):
  case = authority_fixture.IoniqAvailabilityTests(methodName='runTest')
  with OpenpilotPrefix():
    try:
      sd, _, step = case._authority_callers(True, cp=alpha_params(), genuine_events=True)
      feedback = TransportPauseFeedback(sd.CP)
      def receive(axis):
        class Snapshot(dict):
          pass
        sm = Snapshot(aolAxisState=axis, onroadEvents=sd.pm.messages['onroadEvents'].onroadEvents,
                      aolSafetyWire=sd.sm['aolSafetyWire'], pandaStates=sd.sm['pandaStates'])
        sm.seen = sm.valid = sm.alive = dict.fromkeys(sm, True)
        sm.logMonoTime = {key: int(sd.sm.logMonoTime[key]) for key in ('aolSafetyWire', 'pandaStates')}
        sm.logMonoTime.update(aolAxisState=int(axis.observedMonoTime), onroadEvents=int(sd.pm.messages['onroadEvents'].logMonoTime))
        assert not feedback.observe(sm, sd.CP, sd.CS_prev, int(axis.observedMonoTime), latched=True,
                                    intent_producer_session='authority-card')
      for tick in range(5):
        axis, _, command = step(tick)
        assert str(axis.faultReason) == 'none'
        receive(axis)
      axis, _, command = step(5, long_allowed=False, panda_controls_allowed=health_allowed)
      assert not command.longActive
      assert str(axis.faultReason) == 'none'
      assert axis.lateralActive and command.latActive
      receive(axis)
      axis, _, command = step(6, brake=True, long_allowed=False, panda_controls_allowed=False)
      assert str(axis.faultReason) == 'none'
      assert axis.lateralActive and command.latActive
      assert not axis.longitudinalActive and not command.longActive
      assert not sd.aol_authority_lost
      receive(axis)
    finally:
      case.doCleanups()


@pytest.mark.parametrize('failure', ['lateral_denied', 'rx_fault', 'relay', 'native_invalid', 'expired_intent'])
def test_real_fault_still_withdraws_both_axes(failure):
  case = authority_fixture.IoniqAvailabilityTests(methodName='runTest')
  with OpenpilotPrefix():
    try:
      _, _, step = case._authority_callers(True, cp=alpha_params(), genuine_events=True)
      for tick in range(5):
        axis, _, command = step(tick)
        assert axis.lateralActive and command.latActive
      kwargs = {'long_allowed': False, 'panda_controls_allowed': False}
      kwargs.update({
        'lateral_denied': {'allowed': False}, 'rx_fault': {'panda_fault': True},
        'relay': {'relay_fault': True}, 'native_invalid': {'native_valid': False},
        'expired_intent': {'old_intent': True},
      }[failure])
      axis, _, command = step(5, **kwargs)
      assert not command.longActive and not command.latActive
      assert not axis.longitudinalActive and not axis.lateralActive
    finally:
      case.doCleanups()
