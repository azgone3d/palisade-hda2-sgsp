"""Native LONG withdrawal arrives before the corresponding lateral-only axis."""
from openpilot.common.prefix import OpenpilotPrefix
import pytest
from openpilot.starpilot.aol.tests import test_ioniq_availability as fixture
from openpilot.starpilot.aol.tests.test_palisade_alpha_controls import alpha_params
from openpilot.starpilot.aol.transport_pause import TransportPauseFeedback
from openpilot.starpilot.aol.intent import AolSettings
from openpilot.starpilot.car.hyundai.aol import create_intent


@pytest.mark.parametrize('health_allowed', [False, True])
@pytest.mark.parametrize('publication', ['held', 'forward'])
@pytest.mark.parametrize('veto', ['none', 'lateral_denied', 'rx_fault', 'relay_fault', 'native_invalid',
                                 'expired', 'producer', 'seatbelt', 'new_proof', 'post_withdrawal_source', 'unlatched'])
def test_native_first_long_withdrawal_does_not_clear_existing_lateral_intent(health_allowed, publication, veto):
  case = fixture.IoniqAvailabilityTests(methodName='runTest')
  with OpenpilotPrefix():
    try:
      sd, _, step = case._authority_callers(True, cp=alpha_params(), genuine_events=True)
      feedback = TransportPauseFeedback(sd.CP)
      owner = create_intent(sd.CP, AolSettings(True, 0., 9, 0, (0, 0, 0), (0, 0, 0)))
      owner.allowed_latch = True
      class Snapshot(dict):
        pass
      def snapshot(axis, events):
        sm = Snapshot(aolAxisState=axis, onroadEvents=events.onroadEvents,
                      aolSafetyWire=sd.sm['aolSafetyWire'], pandaStates=sd.sm['pandaStates'])
        sm.seen = dict.fromkeys(sm, True)
        sm.valid = dict.fromkeys(sm, True)
        sm.alive = dict.fromkeys(sm, True)
        sm.valid['aolSafetyWire'] = sd.sm.valid['aolSafetyWire']
        sm.logMonoTime = {key: int(sd.sm.logMonoTime[key]) for key in ('aolSafetyWire', 'pandaStates')}
        sm.logMonoTime.update(aolAxisState=int(axis.observedMonoTime), onroadEvents=int(events.logMonoTime))
        return sm
      for tick in range(5):
        axis, _, command = step(tick)
        events = sd.pm.messages['onroadEvents']
        assert axis.longitudinalActive and command.latActive
        assert not feedback.observe(snapshot(axis, events), sd.CP, sd.CS_prev, int(axis.observedMonoTime),
                                    latched=True, intent_producer_session='authority-card')
      old_axis, old_events = axis, events
      faults = {'lateral_denied': {'allowed': False}, 'rx_fault': {'panda_fault': True},
                'relay_fault': {'relay_fault': True}, 'native_invalid': {'native_valid': False}}
      successor, _, command = step(5, long_allowed=False, panda_controls_allowed=health_allowed, **faults.get(veto, {}))
      # Native and Panda sockets have advanced, but Card's axis/event socket has
      # not. This is the recorded order, absent from the earlier successor test.
      assert old_axis.longitudinalActive and not successor.longitudinalActive
      assert not command.longActive
      now = int(successor.observedMonoTime)
      if publication == 'forward' or veto == 'post_withdrawal_source':
        old_axis = old_axis.as_builder()
        old_axis.sequence += 1
        old_axis.observedMonoTime = now + 1_000_000
        old_axis.validUntilMonoTime = old_axis.observedMonoTime + 30_000_000
        old_axis.sourceCarStateMonoTime = now - 5_000_000 if veto != 'post_withdrawal_source' else now + 1
        now += 2_000_000
      sm = snapshot(old_axis, old_events)
      producer = 'different-card' if veto == 'producer' else 'authority-card'
      signature = (str(old_axis.sessionId), int(old_axis.sequence), int(old_axis.observedMonoTime),
                   int(old_axis.observedMonoTime), int(old_axis.validUntilMonoTime), str(old_axis.faultReason),
                   int(old_axis.faultEventMonoTime), str(old_axis.faultSessionId), int(old_axis.sourceCarStateMonoTime),
                   bool(old_axis.lateralActive), bool(old_axis.longitudinalActive), bool(old_axis.desiredLateral),
                   bool(old_axis.desiredLongitudinal), bool(old_axis.nativeAcknowledged),
                   str(old_axis.intentProducerSessionId), int(old_axis.intentIntegrityEpoch))
      if veto == 'expired':
        now = int(old_axis.validUntilMonoTime) + 1
      if veto == 'seatbelt':
        sd.CS_prev = sd.CS_prev.as_builder()
        sd.CS_prev.seatbeltUnlatched = True
      if veto == 'new_proof':
        signature = (*signature[:14], 'different-card', *signature[15:])
      if veto != 'none':
        assert feedback._native_long_withdrawal_lateral_current(sm, sd.CP, sd.CS_prev, old_axis, now,
          latched=veto != 'unlatched', producer=producer, signature=signature) is None
        if veto in faults:
          assert not successor.lateralActive and not command.latActive
        return
      assert successor.lateralActive and command.latActive
      reset = feedback.observe(sm, sd.CP, sd.CS_prev, now,
                               latched=True, intent_producer_session='authority-card')
      owner.update(sd.CS_prev, now_ns=now, fault_active=reset)
      assert not reset
      assert owner.allowed_latch
      assert not feedback.failed
      successor, _, command = step(6, brake=True, long_allowed=False, panda_controls_allowed=False)
      assert successor.lateralActive and command.latActive and not command.longActive
      assert not feedback.observe(snapshot(successor, sd.pm.messages['onroadEvents']), sd.CP, sd.CS_prev, int(successor.observedMonoTime),
                                  latched=True, intent_producer_session='authority-card')
    finally:
      case.doCleanups()
