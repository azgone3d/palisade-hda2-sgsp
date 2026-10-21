"""Captured factory E-CAN display traffic is not isolated steering ownership."""
import pytest

from opendbc.car import structs
from opendbc.car.hyundai.interface import CarInterface
from opendbc.car.hyundai.tests.test_palisade_2023 import params, feed
from opendbc.car.hyundai.values import HyundaiFlags
from opendbc.safety.tests import common
from opendbc.safety.tests.libsafety import libsafety_py

CAPTURED_STATUS = bytes.fromhex('e150020000000000')


@pytest.mark.parametrize('experience', [0, 32])
@pytest.mark.parametrize('address,length', [(0x50, 16), (0x2A4, 24)])
def test_factory_status_keeps_steering_relay_shutdown(experience, address, length):
  safety = libsafety_py.libsafety
  safety.set_alternative_experience(experience)
  assert safety.set_safety_hooks(structs.CarParams.SafetyModel.hyundai, 0x2010) == 0
  safety.init_tests()
  safety.set_timer(2_000_000)
  safety.safety_rx_hook(common.make_msg(1, 0x485, dat=CAPTURED_STATUS))
  assert not safety.get_relay_malfunction()
  if experience == 32:
    # No host ownership of factory display traffic in the independent profile.
    assert not safety.safety_tx_hook(common.make_msg(1, 0x485, dat=CAPTURED_STATUS))
  safety.safety_rx_hook(common.make_msg(0, address, length))
  assert safety.get_relay_malfunction()
  assert not safety.safety_tx_hook(common.make_msg(0, 0x50, 16))
  assert safety.safety_fwd_hook(2, 0x50) == -1


def test_aol_controller_leaves_factory_display_even_with_optional_icon_flag():
  cp = params('hdaii')
  cp.alternativeExperience = 32
  cp.flags |= HyundaiFlags.SEND_LFA.value
  ci = CarInterface(cp)
  for tick in range(12):
    feed(ci, tick)
  command = structs.CarControl()
  for tick in range(10):
    _, messages = ci.apply(command.as_reader(), 1_200_000_000 + tick * 10_000_000)
    assert not any(address == 0x485 for address, _, _ in messages)
    assert any(address == 0x50 for address, _, _ in messages)
