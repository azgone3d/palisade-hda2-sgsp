"""Cancel's raw Panda LONG veto can arrive before its coherent native wire."""
from dataclasses import replace
from openpilot.common.prefix import OpenpilotPrefix
from opendbc.car import structs as car
import pytest
from openpilot.starpilot.aol.tests import test_ioniq_availability as fixture
from openpilot.starpilot.aol.tests.test_palisade_alpha_controls import alpha_params
from openpilot.starpilot.aol.transport_pause import TransportPauseFeedback
from openpilot.starpilot.aol.wire import decode_safety, encode_safety


@pytest.mark.parametrize('veto', ['none', 'release', 'no_press', 'unlatched', 'old_panda', 'lateral_denied', 'rx_fault',
  'relay_fault', 'native_rx', 'native_heartbeat', 'native_invalid', 'producer', 'epoch', 'seatbelt', 'expired', 'can_timeout', 'other_user'])
def test_raw_panda_first_cancel_retains_only_existing_fresh_intent(veto):
  case = fixture.IoniqAvailabilityTests(methodName='runTest')
  with OpenpilotPrefix():
    try:
      sd, _, step = case._authority_callers(True, cp=alpha_params(), genuine_events=True)
      feedback = TransportPauseFeedback(sd.CP)
      class Snapshot(dict): pass
      def snapshot(axis, events):
        sm = Snapshot(aolAxisState=axis, onroadEvents=events.onroadEvents,
                      aolSafetyWire=sd.sm['aolSafetyWire'], pandaStates=sd.sm['pandaStates'])
        sm.seen = dict.fromkeys(sm, True); sm.valid = dict.fromkeys(sm, True); sm.alive = dict.fromkeys(sm, True)
        sm.logMonoTime = {key: int(sd.sm.logMonoTime[key]) for key in ('aolSafetyWire', 'pandaStates')}
        sm.logMonoTime.update(aolAxisState=int(axis.observedMonoTime), onroadEvents=int(events.logMonoTime))
        return sm
      for tick in range(5):
        axis, _, command = step(tick)
        sm = snapshot(axis, sd.pm.messages['onroadEvents'])
        assert command.latActive and command.longActive
        assert not feedback.observe(sm, sd.CP, sd.CS_prev, int(axis.observedMonoTime),
                                    latched=True, intent_producer_session='authority-card')
      now = int(axis.observedMonoTime) + 1_000_000
      press_ns = now
      cs = sd.CS_prev.as_builder()
      cs.buttonEvents = [car.CarState.ButtonEvent(type='cancel', pressed=True)] if veto != 'no_press' else []
      # Store the original physical source before the native status changes.
      assert not feedback.observe(sm, sd.CP, cs, now, latched=True, cancel_source_ns=press_ns,
                                  intent_producer_session='authority-card')
      if veto in ('none', 'release'):
        assert feedback.longitudinal_cancel_ns == press_ns
      now += 10_000_000
      cs.buttonEvents = []  # The button is held, with no new physical edge.
      if veto == 'release': cs.buttonEvents = [car.CarState.ButtonEvent(type='cancel', pressed=False)]
      native = decode_safety(bytes(sm['aolSafetyWire']))
      assert native.requestedLongitudinal and native.longitudinalAllowed and native.lateralAllowed
      pandas = [p.as_builder() for p in sm['pandaStates']]
      pandas[0].controlsAllowed = False
      sm['pandaStates'] = pandas
      sm.logMonoTime['pandaStates'] = native.sourcePandaStatesMonoTime + (1 if veto != 'old_panda' else 0)
      if veto == 'rx_fault': pandas[0].safetyRxChecksInvalid = True
      if veto == 'relay_fault': pandas[0].faults = ['relayMalfunction']
      if veto == 'lateral_denied': sm['aolSafetyWire'] = encode_safety(replace(native, lateralAllowed=False))
      if veto in ('native_rx', 'native_heartbeat'):
        slot = replace(native.pandaInventory[0], **({'safetyRxChecksInvalid': True} if veto == 'native_rx' else {'heartbeatLost': True}))
        sm['aolSafetyWire'] = encode_safety(replace(native, pandaInventory=(slot,)))
      if veto == 'native_invalid': sm.valid['aolSafetyWire'] = False
      if veto == 'seatbelt': cs.seatbeltUnlatched = True
      if veto == 'can_timeout': cs.canTimeout = True
      if veto == 'epoch':
        axis = axis.as_builder(); axis.intentIntegrityEpoch += 1; sm['aolAxisState'] = axis
      if veto == 'other_user':
        event = fixture.messaging.new_message('onroadEvents', 1)
        event.onroadEvents[0].name = 'pcmDisable'; event.onroadEvents[0].userDisable = True
        sm['onroadEvents'] = event.onroadEvents
      if veto == 'expired': now = press_ns + 200_000_001
      reset = feedback.observe(sm, sd.CP, cs, now, latched=veto != 'unlatched',
        intent_producer_session='wrong-producer' if veto == 'producer' else 'authority-card')
      if veto not in ('none', 'release'):
        if veto == 'unlatched':
          assert feedback._longitudinal_cancel_current(sm, sd.CP, cs, axis, now,
            latched=False, cancel_source_ns=0, producer='authority-card') is None
        else:
          assert reset
        return
      assert not reset
      # A duplicate observation cannot renew the press or any publication lease.
      original_deadline = axis.validUntilMonoTime
      assert not feedback.observe(sm, sd.CP, cs, now + 1, latched=True, intent_producer_session='authority-card')
      assert feedback.longitudinal_cancel_ns == press_ns
      assert axis.validUntilMonoTime == original_deadline
      successor, _, command = step(6, long_allowed=False, panda_controls_allowed=False)
      assert command.latActive and not command.longActive
      assert not feedback.observe(snapshot(successor, sd.pm.messages['onroadEvents']), sd.CP, sd.CS_prev,
        int(successor.observedMonoTime), latched=True, intent_producer_session='authority-card')
      # Once coherent LAT-only status arrives, a comfortably held pause button
      # does not disarm lateral or renew LONG. The handshake deadline stays fixed.
      for tick in range(7, 157):
        successor, _, command = step(tick, long_allowed=False, panda_controls_allowed=False)
        held_cs = sd.CS_prev.as_builder()
        held_cs.buttonEvents = []
        assert not feedback.observe(snapshot(successor, sd.pm.messages['onroadEvents']), sd.CP, held_cs,
          int(successor.observedMonoTime), latched=True, intent_producer_session='authority-card')
        assert command.latActive and not command.longActive
    finally:
      case.doCleanups()
