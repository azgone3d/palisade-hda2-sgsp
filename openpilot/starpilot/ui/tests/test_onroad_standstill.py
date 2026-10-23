from types import SimpleNamespace as NS
from dataclasses import replace
import pytest
from openpilot.starpilot.ui.onroad_standstill import lateral_ready
from openpilot.starpilot.ui.onroad import driving_mode_description
from openpilot.starpilot.ui.preview_shell import reference_onroad


@pytest.mark.parametrize('veto', ['none', 'moving', 'can', 'timeout', 'eps', 'active', 'latch', 'ack', 'fault', 'profile', 'missing'])
def test_ready_label_requires_current_qualified_intent_and_inactive_steering(veto):
  cp = NS(carFingerprint='HYUNDAI_PALISADE_2023', steerAtStandstill=False)
  car = NS(standstill=True, canValid=True, canTimeout=False, steerFaultTemporary=False, steerFaultPermanent=False)
  control = NS(latActive=False)
  axis = NS(nativeAcknowledged=True, desiredLateral=True, lateralActive=True, faultReason='none')
  if veto == 'moving': car.standstill = False
  if veto == 'can': car.canValid = False
  if veto == 'timeout': car.canTimeout = True
  if veto == 'eps': car.steerFaultTemporary = True
  if veto == 'active': control.latActive = True
  if veto == 'latch': axis.desiredLateral = False
  if veto == 'ack': axis.nativeAcknowledged = False
  if veto == 'fault': axis.faultReason = 'critical'
  if veto == 'profile': cp.carFingerprint = 'OTHER'
  if veto == 'missing': axis = None
  assert lateral_ready(cp, car, control, axis) is (veto == 'none')


def test_ready_is_distinct_from_active_or_disengaged():
  state = replace(reference_onroad('onroad_disengaged_no_camera'), lateral_standstill_ready=True)
  assert driving_mode_description(state) == 'Always On Lateral'
  assert not state.lateral_active and not state.engaged


def test_display_readiness_expires_with_axis_or_car_source():
  from openpilot.starpilot.ui.tests.test_runtime_snapshot import ui_fake, RuntimeSnapshotAdapter, NOW
  from openpilot.starpilot.ui.shell import ShellMode
  ui = ui_fake()
  ui.aol_runtime = True
  ui.CP = NS(carFingerprint='HYUNDAI_PALISADE_2023', steerAtStandstill=False,
             openpilotLongitudinalControl=True, pcmCruise=False)
  car = ui.sm['carState']
  car.canValid, car.canTimeout, car.standstill = True, False, True
  car.steerFaultTemporary = car.steerFaultPermanent = False
  ui.sm['carControl'].latActive = False
  axis = NS(qualified=True, sessionId='stop', observedMonoTime=NOW, validUntilMonoTime=NOW + 30_000_000,
            nativeAcknowledged=True, desiredLateral=True, lateralActive=True,
            desiredLongitudinal=False, faultReason='none')
  ui.sm.put('aolAxisState', axis)
  adapter = RuntimeSnapshotAdapter(ui)
  assert adapter.build(ShellMode.ONROAD, now_ns=NOW).onroad.lateral_standstill_ready
  ui.sm.logMonoTime['aolAxisState'] = NOW - 31_000_000
  assert not adapter.build(ShellMode.ONROAD, now_ns=NOW).onroad.lateral_standstill_ready
  ui.sm.logMonoTime['aolAxisState'] = NOW
  ui.sm.logMonoTime['carState'] = NOW - 1_000_000_000
  assert not adapter.build(ShellMode.ONROAD, now_ns=NOW).onroad.lateral_standstill_ready
