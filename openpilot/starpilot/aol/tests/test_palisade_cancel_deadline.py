"""Palisade physical pause and unchanged absolute output deadlines."""

from unittest.mock import patch
from types import SimpleNamespace

import pytest
from opendbc.car import structs as car
from openpilot.cereal import messaging
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.starpilot.aol.intent import AolSettings
from openpilot.starpilot.aol.tests import test_ioniq_availability as fixture
from openpilot.starpilot.aol.tests.test_input_deadline_continuity import BASE, intent
from openpilot.starpilot.aol.tests.test_palisade_alpha_controls import alpha_params
from openpilot.starpilot.car.hyundai.aol import create_intent


@pytest.mark.parametrize('full_op', [False, True])
@pytest.mark.parametrize('startup_experience', [0, 32])
def test_cancel_retains_existing_lateral_without_resuming_long_or_false_mismatch(full_op, startup_experience):
  cp = alpha_params()
  cp.alternativeExperience = startup_experience
  settings = AolSettings(True, 0.0, 9, 0, (0, 0, 0), (0, 0, 0))
  owner = create_intent(cp, settings)
  # This is Card's real order: construct intent, then finalize CP's AOL marker.
  cp.alternativeExperience = 32
  assert not owner.cancel_disarms_lateral
  cs = car.CarState(canValid=True, gearShifter='drive', vEgo=10.0)
  cs.cruiseState.available = True
  owner.update(cs, now_ns=1, fault_active=False)
  cs.buttonEvents = [car.CarState.ButtonEvent(type='lkas', pressed=True)]
  owner.update(cs, now_ns=2, fault_active=False)
  assert owner.allowed_latch
  case = fixture.IoniqAvailabilityTests(methodName='runTest')
  with OpenpilotPrefix():
    try:
      sd, _, step = case._authority_callers(full_op, cp=cp, genuine_events=True)
      sd.aol_settings = settings
      for tick in range(5):
        axis, _, command = step(tick)
        assert axis.lateralActive and command.latActive
      cs.buttonEvents = [car.CarState.ButtonEvent(type='cancel', pressed=True)]
      owner.update(cs, now_ns=10_050_000_000, fault_active=False)
      assert owner.allowed_latch
      msg = messaging.new_message('carState', valid=True, logMonoTime=10_050_000_000)
      msg.carState = cs
      axis, _, command = step(5, car_state_message=msg, latched=True, allowed=True, long_allowed=False, panda_controls_allowed=False)
      assert str(axis.faultReason) == 'none'
      assert not sd.aol_authority_lost
      assert command.latActive and not command.longActive
      assert axis.desiredLateral and not axis.longitudinalActive
      assert fixture.log.OnroadEvent.EventName.controlsMismatch not in sd.events.names
      cs.buttonEvents = [car.CarState.ButtonEvent(type='cancel', pressed=False)]
      owner.update(cs, now_ns=10_060_000_000, fault_active=False)
      assert owner.allowed_latch  # Release preserves intent; native still owns each axis.
    finally:
      case.doCleanups()


def test_cancel_press_release_cannot_arm_unselected_lateral():
  owner = create_intent(alpha_params(), AolSettings(True, 0., 9, 0, (0, 0, 0), (0, 0, 0)))
  cs = car.CarState(canValid=True, gearShifter='drive')
  for tick, event in enumerate([[], [car.CarState.ButtonEvent(type='cancel', pressed=True)],
                              [car.CarState.ButtonEvent(type='cancel', pressed=False)], []]):
    cs.buttonEvents = event
    owner.update(cs, now_ns=tick + 1, fault_active=False)
    assert not owner.allowed_latch


@pytest.mark.parametrize('failure', ['none', 'old_receipt', 'future_receipt', 'wrong_bus', 'synthetic', 'unmarked'])
def test_cancel_source_requires_actual_current_palisade_can(failure):
  from opendbc.car.hyundai.interface import CarInterface
  from opendbc.car.hyundai.tests.test_blended_stock_aol import MixedReceiveStream
  from openpilot.selfdrive.car.card import Car
  cp = alpha_params()
  if failure == 'unmarked':
    cp.alternativeExperience = 0
  ci = CarInterface(cp)
  stream = MixedReceiveStream(ci)
  for tick in range(29):
    now = stream.now + tick * 10_000_000
    frames = stream.frames(tick, cruise_button=4 if tick == 28 and failure != 'synthetic' else 0)
    if tick == 28 and failure == 'wrong_bus':
      frames = [(address, data, 2 if address == 0x4F1 else bus) for address, data, bus in frames]
    cs = ci.update([(now, frames)])
  if failure in ('synthetic', 'wrong_bus'):
    cs.buttonEvents = [car.CarState.ButtonEvent(type='cancel', pressed=True)]
  receipt = now - 30_000_001 if failure == 'old_receipt' else now + 1 if failure == 'future_receipt' else now
  caller = SimpleNamespace(CI=ci, _aol_can_observation=(cs, receipt, now, now))
  assert Car.aol_cancel_source(caller, cs, now) == (now if failure == 'none' else 0)


@pytest.mark.parametrize('successor', ['before', 'after', 'absent'])
def test_short_source_cutoff_can_use_only_original_unexpired_publication(successor):
  case = fixture.IoniqAvailabilityTests(methodName='runTest')
  with OpenpilotPrefix():
    try:
      sd, controls, step = case._authority_callers(True, cp=alpha_params(), genuine_events=True)
      axis, _, command = step(2, offset_ns=4_530_833, state_stamp=BASE, intent_message=intent(BASE, 3))
      assert axis.lateralActive and command.latActive
      saved = sd.pm.messages['aolAxisState'].as_builder().to_bytes()
      deadline = axis.validUntilMonoTime
      clock = [BASE + 29_999_000]
      original_drain = sd.drain_axis_intent

      def drain(companion, **kwargs):
        result = original_drain(companion, **kwargs)
        clock[0] = BASE + 30_010_236
        return result

      with (
        patch('openpilot.selfdrive.selfdrived.selfdrived.time.monotonic_ns', side_effect=lambda: clock[0]),
        patch.object(sd, 'drain_axis_intent', side_effect=drain),
      ):
        held, _, _ = step(5, timeout=True, offset_ns=-1_000, intent_message=intent(BASE, 3))
      assert sd.aol_axis_publication_deferred
      assert sd.pm.messages['aolAxisState'].as_builder().to_bytes() == saved
      assert held.validUntilMonoTime == deadline
      if successor != 'before':
        with patch('openpilot.selfdrive.selfdrived.selfdrived.time.monotonic_ns', return_value=deadline + 1):
          expired, _ = controls.state_control()
        assert not expired.latActive and not expired.longActive
      if successor == 'absent':
        axis, _, command = step(6, timeout=True, intent_message=intent(BASE, 3))
        assert not sd.aol_axis_publication_deferred
        assert not command.latActive and not command.longActive
      else:
        source = BASE + 31_546_896
        decision = BASE + (32_000_000 if successor == 'before' else 36_068_506)
        axis, _, command = step(6, offset_ns=decision - (BASE + 40_000_000), state_stamp=source, intent_message=intent(source, 4))
        assert axis.sourceCarStateMonoTime == source
        assert command.latActive and command.longActive
        assert axis.validUntilMonoTime == decision + 30_000_000
      assert held.validUntilMonoTime == deadline
    finally:
      case.doCleanups()
