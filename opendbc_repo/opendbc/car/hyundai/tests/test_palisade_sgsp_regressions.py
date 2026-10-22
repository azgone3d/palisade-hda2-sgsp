"""Logged Palisade firmware and physical AOL gestures; no vehicle validation."""
from unittest.mock import patch
from types import SimpleNamespace

import pytest

from opendbc.car import structs
from opendbc.car.fw_versions import match_fw_to_car_exact
from opendbc.car.hyundai.canfd_stock_aol import qualified, qualified_long
from opendbc.car.hyundai.tests.test_blended_stock_aol import params, MixedReceiveStream
from opendbc.car.hyundai.interface import CarInterface
from opendbc.car.hyundai.values import CAR
from opendbc.safety.tests.libsafety import libsafety_py
from opendbc.safety.tests.test_hyundai import checksum
from openpilot.starpilot.aol.intent import AolSettings, AOL_TOGGLE
from openpilot.starpilot.aol.runtime import decide_axes
from openpilot.starpilot.car.hyundai.aol import create_intent, independent_cruise_buttons_supported


# Essential ECU responses recorded in two local working StarPilot captures.
LIVE_FW = {
  (0x7d4, None): {b'\xf1\x00LXP MDPS C 1.00 1.00 56310S8620\x00 4LXPC100'},
  (0x7c4, None): {b'\xf1\x00LX2 MFC  AT USA LHD 1.00 1.00 99211-S8700 240221'},
  (0x7d0, None): {b'\xf1\x00LX2_ SCC -----      1.00 1.01 99110-S8700         '},
}


def test_logged_firmware_matches_exactly_without_relaxing_matcher():
  assert match_fw_to_car_exact(LIVE_FW, match_brand='hyundai', log=False) == {CAR.HYUNDAI_PALISADE_2023}
  for address in LIVE_FW:
    changed = dict(LIVE_FW)
    changed[address] = {b'unknown firmware'}
    assert CAR.HYUNDAI_PALISADE_2023 not in match_fw_to_car_exact(changed, match_brand='hyundai', log=False)


def owner_and_state():
  cp = params(True)
  cp.alternativeExperience = 32
  owner = create_intent(cp, AolSettings(True, 0., AOL_TOGGLE, 0, (0, 0, 0), (0, 0, 0)))
  cs = structs.CarState(canValid=True, gearShifter='drive')
  cs.cruiseState.available = True
  owner.update(cs, now_ns=1, fault_active=False)
  return cp, owner, cs


def event(name, pressed):
  return structs.CarState.ButtonEvent(type=name, pressed=pressed)


def test_hda2_stock_uses_its_existing_mixed_safety_profile():
  cp, _, _ = owner_and_state()
  assert independent_cruise_buttons_supported(cp, marked_only=True)
  assert not qualified(cp) and not qualified_long(cp)
  assert cp.safetyConfigs[0].safetyModel == structs.CarParams.SafetyModel.hyundai
  assert cp.safetyConfigs[0].safetyParam == 0x2010
  cp.safetyConfigs[0].safetyParam |= 4
  assert not independent_cruise_buttons_supported(cp, marked_only=True)


def test_unassigned_main_does_not_toggle_lkas_owned_lateral():
  _, owner, cs = owner_and_state()
  cs.buttonEvents = [event('lkas', True)]
  owner.update(cs, now_ns=2, fault_active=False)
  assert owner.allowed_latch
  cs.buttonEvents = [event('lkas', False)]
  owner.update(cs, now_ns=3, fault_active=False)
  edge = owner._last_latch_edge_ns
  cs.buttonEvents = [event('mainCruise', True)]
  owner.update(cs, now_ns=4, fault_active=False, standard_enabled=True)
  assert owner.allowed_latch and not owner.pause_lateral
  assert owner._last_latch_edge_ns == edge


@pytest.mark.parametrize('consumed', [False, True])
def test_complete_lkas_pulse_in_one_update_is_observed_once(consumed):
  _, owner, cs = owner_and_state()
  cs.buttonEvents = [event('lkas', True), event('lkas', False)]
  owner.update(cs, now_ns=2, fault_active=False,
               consumed_buttons=frozenset((int(structs.CarState.ButtonEvent.Type.lkas),)) if consumed else frozenset())
  assert owner.allowed_latch == (not consumed)
  cs.buttonEvents = []
  owner.update(cs, now_ns=3, fault_active=False)
  assert owner.allowed_latch == (not consumed)


@pytest.mark.parametrize('initial_main', [False, True])
def test_native_main_and_brake_keep_previously_authorized_stock_lateral(initial_main):
  cp, owner, _ = owner_and_state()
  ci = CarInterface(cp)
  stream = MixedReceiveStream(ci)
  safety = libsafety_py.libsafety
  safety.set_alternative_experience(32)
  assert safety.set_safety_hooks(cp.safetyConfigs[0].safetyModel.raw, 0x2010) == 0
  safety.init_tests()
  for tick in range(80):
    now = stream.now + tick * 10_000_000
    frames = stream.frames(tick, lda=20 <= tick < 30, main=40 <= tick < 44, stock_main=initial_main and tick < 40)
    if tick >= 50:
      frames = [(addr, stream.packer.make_can_msg('TCS13', bus, {
        'AliveCounterTCS': (data[1] >> 5) & 7, 'DriverOverride': 2, 'ACCEnable': 0,
      })[1], bus) if addr == 0x394 else (addr, data, bus) for addr, data, bus in frames]
      frames = [checksum(frame) if frame[0] == 0x394 else frame for frame in frames]
    safety.set_timer((now // 1000) & 0xffffffff)
    for address, data, bus in frames:
      assert safety.safety_rx_hook(libsafety_py.make_CANPacket(address, bus, data))
    safety.set_aol_test_heartbeat(True)
    safety.safety_tick()
    with patch('time.clock_gettime_ns', return_value=now):
      cs = ci.update([(now, frames)])
    owner.update(cs, now_ns=now, fault_active=not cs.canValid)
    safety.aol_set_host_request(int(owner.output(cs)[0]))
    if tick >= 30:
      assert cs.canValid and owner.allowed_latch
      assert safety.aol_get_permission_mask() == 1
    if tick >= 50:
      assert cs.brakePressed and not safety.get_controls_allowed()
  # Real CAN failure still withdraws the host's intent.
  cs.canValid = False
  owner.update(cs, now_ns=now + 1, fault_active=True)
  assert not owner.allowed_latch


@pytest.mark.parametrize('threshold,speed,allowed', [(0., 5., True), (10., 5., False), (10., 20., True)])
@pytest.mark.parametrize('native_grant', [False, True])
def test_brake_retention_obeys_configuration_and_native_ack(threshold, speed, allowed, native_grant):
  _, owner, cs = owner_and_state()
  cs.buttonEvents = [event('lkas', True)]
  owner.update(cs, now_ns=2, fault_active=False)
  cs.buttonEvents = [event('lkas', False)]
  cs.brakePressed, cs.vEgo = True, speed
  cs.cruiseState.enabled = False
  owner.update(cs, now_ns=3, fault_active=False)
  assert owner.allowed_latch
  result = decide_axes(
    standard_lateral=False, standard_longitudinal=False,
    intent=SimpleNamespace(allowedLatch=owner.allowed_latch, pauseLateral=False, pauseLongitudinal=False),
    native=SimpleNamespace(requestedLateral=allowed, lateralAllowed=native_grant,
                           requestedLongitudinal=False, longitudinalAllowed=False),
    car_state=cs, initialized=True, model_ready=True, no_entry=False,
    immediate_disable=False, dm_lockout=False, pause_brake_mps=threshold,
  )
  assert result.desired_lateral == allowed
  assert result.lateral_active == (allowed and native_grant)
  assert not result.longitudinal_active


def test_held_startup_and_cancel_batch_do_not_arm():
  cp, _, cs = owner_and_state()
  owner = create_intent(cp, AolSettings(True, 0., AOL_TOGGLE, 0, (0, 0, 0), (0, 0, 0)))
  cs.buttonEvents = [event('lkas', True)]
  owner.update(cs, now_ns=1, fault_active=False)
  assert not owner.allowed_latch
  cs.buttonEvents = [event('lkas', False)]
  owner.update(cs, now_ns=2, fault_active=False)
  cs.buttonEvents = [event('lkas', True), event('lkas', False), event('cancel', True)]
  owner.update(cs, now_ns=3, fault_active=False)
  assert not owner.allowed_latch
