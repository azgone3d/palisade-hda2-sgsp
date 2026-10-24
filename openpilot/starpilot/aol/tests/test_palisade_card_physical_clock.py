"""Exercise Card's production CAN observation, not a hand-built proof tuple."""
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
from opendbc.car import Bus
from opendbc.car.hyundai.interface import CarInterface
from opendbc.car.hyundai.tests.test_blended_stock_aol import MixedReceiveStream, checksum
from openpilot.selfdrive.car import card as module
from openpilot.starpilot.aol.tests.test_palisade_alpha_controls import alpha_params
from openpilot.starpilot.car.hyundai.aol import palisade_physical_sources_supported


class ObservationComplete(Exception):
  pass


@pytest.mark.parametrize('unmarked', [False, True])
@pytest.mark.parametrize('physical', ['cancel', 'brake', 'gas_cancel'])
def test_card_samples_physical_source_clock_for_exact_palisade(unmarked, physical):
  cp = alpha_params()
  if unmarked:
    cp.alternativeExperience = 0
  ci = CarInterface(cp)
  stream = MixedReceiveStream(ci)
  for tick in range(28):
    stamp = stream.now + tick * 10_000_000
    ci.update([(stamp, stream.frames(tick))])
  stamp += 10_000_000
  batch = [(stamp, stream.frames(28, cruise_button=4))]
  if physical in ('brake', 'gas_cancel'):
    address = ci.can_parsers[Bus.pt].dbc.name_to_msg['TCS13'].address
    brake = checksum(stream.packer.make_can_msg('TCS13', stream.pt,
      {'AliveCounterTCS':28 % 8, 'ACCEnable':0, 'DriverOverride':2 if physical == 'brake' else 1}))
    batch[0][1][:] = [brake if frame[0] == address else frame for frame in batch[0][1]]
  if physical == 'gas_cancel':
    address = ci.can_parsers[Bus.pt].dbc.name_to_msg['EMS16'].address
    gas = stream.packer.make_can_msg('EMS16', stream.pt, {'AliveCounter':28 % 4, 'CF_Ems_AclAct':1})
    if address in (0x260, 0x394, 0x386): gas = checksum(gas)
    batch[0][1][:] = [gas if frame[0] == address else frame for frame in batch[0][1]]
  receipt = stamp - 1_000_000_000
  def complete(*args):
    raise ObservationComplete
  caller = NS(CP=cp, CI=ci, can_sock=None, can_rcv_cum_timeout_counter=0,
    sm=NS(update=lambda *a:None), observe_ioniq6_long_authority=lambda *a:None,
    update_vehicle_state_context=lambda *a:None, refresh_slc_configuration=complete)
  with (patch.object(module.messaging, 'drain_sock_raw', return_value=[b'can']),
        patch.object(module, 'can_capnp_to_list', return_value=batch),
        patch.object(module.time, 'monotonic_ns', return_value=receipt),
        patch.object(module.time, 'clock_gettime_ns', return_value=stamp+1000) as clock,
        patch.object(module, 'REPLAY', False), pytest.raises(ObservationComplete)):
    module.Car.state_update(caller, defer_radar=True)
  cs, received, source, boot = caller._aol_can_observation
  assert not ci.CS.ev6_aol_source_healthy  # This different vehicle's gate cannot select our clock.
  assert received == receipt and source == stamp
  assert palisade_physical_sources_supported(cp) is (not unmarked)
  if unmarked:
    clock.assert_not_called()
    assert boot == 0
  else:
    clock.assert_any_call(module.time.CLOCK_BOOTTIME)
    assert boot == stamp+1000
    if physical == 'brake':
      assert cs.brakePressed
      assert module.Car.aol_honda_brake_source(caller, cs, receipt) == receipt
    else:
      assert module.Car.aol_cancel_source(caller, cs, receipt) == receipt
      if physical == 'gas_cancel':
        assert cs.gasPressed
        parser = ci.can_parsers[Bus.pt]
        parser.vl['TCS13']['DriverOverride'] = 2
        assert module.Car.aol_cancel_source(caller, cs, receipt) == 0
        parser.vl['TCS13']['DriverOverride'] = 1
        parser.vl['TCS13']['ACCEnable'] = 1
        assert module.Car.aol_cancel_source(caller, cs, receipt) == 0
