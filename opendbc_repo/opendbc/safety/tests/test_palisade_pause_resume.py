"""Exact HDA2 alpha pause retains only an existing native lateral grant."""

import pytest

from opendbc.safety.tests import test_hyundai_blended_alpha as fixture


@pytest.fixture
def owner():
  case = fixture.TestHyundaiBlendedAlphaAol(methodName='runTest')
  case.setUp()
  case.reset(0x2014)
  case.warm()
  yield case
  case.tearDown()


def arm(owner):
  owner.feed(lda=True)
  assert owner.request(1) == 1
  owner.feed()


def test_pause_retains_existing_lateral_and_requires_second_pair_for_long(owner):
  arm(owner)
  owner.feed(button=4)
  assert owner.request(1) == 1
  owner.feed()
  assert owner.safety.get_controls_allowed()
  assert owner.request(3) == 3
  owner.feed(button=4)
  assert not owner.safety.get_controls_allowed()
  assert owner.request(3) == 1
  owner.feed(button=4)  # Held/duplicate cancel cannot resume.
  assert owner.request(3) == 1
  owner.feed()
  assert not owner.safety.get_controls_allowed()
  assert owner.request(1) == 1
  owner.feed()
  assert not owner.safety.get_controls_allowed()
  owner.feed(button=4)
  assert not owner.safety.get_controls_allowed()
  owner.feed()
  assert owner.safety.get_controls_allowed()
  assert owner.request(3) == 3


def test_paused_lateral_keeps_torque_limits_and_denies_acceleration(owner):
  arm(owner)
  owner.feed(button=4)
  owner.feed()
  assert owner.request(3) == 3
  owner.feed(button=4)
  assert owner.request(3) == 1
  assert not owner.safety.get_controls_allowed()
  primary = owner.packer.make_can_msg_safety('LKAS', 0,
    {'COUNTER': 0, 'TORQUE_REQUEST': 3, 'STEER_REQ': 1})
  assert owner.safety.safety_tx_hook(primary)
  assert owner.safety.safety_tx_hook(fixture.TestHyundaiBlendedAlpha.mirror(owner, 3, True))
  excessive = owner.packer.make_can_msg_safety('LKAS', 0,
    {'COUNTER': 1, 'TORQUE_REQUEST': 1000, 'STEER_REQ': 1})
  assert not owner.safety.safety_tx_hook(excessive)
  for accel in (-.1, .1):
    packet = owner.packer.make_can_msg_safety('SCC11', 1, {'aReqRaw': accel, 'aReqValue': accel})
    assert not owner.safety.safety_tx_hook(packet)


@pytest.mark.parametrize('cause', ['unarmed', 'withdrawn', 'heartbeat', 'expired', 'main_off'])
def test_cancel_cannot_create_independent_lateral_without_normal_engagement(owner, cause):
  if cause != 'unarmed':
    arm(owner)
  if cause == 'withdrawn':
    assert owner.request(0) == 0
  elif cause == 'heartbeat':
    owner.safety.set_aol_test_heartbeat(False)
  elif cause == 'expired':
    owner.now += 300_001
  elif cause == 'main_off':
    owner.feed(available=False)
  owner.feed(button=4, available=cause != 'main_off')
  assert owner.request(1) == 0
  owner.feed(available=cause != 'main_off')
  # A normal fresh release may authorize paired cruise under the existing
  # contract. It must not create an independent lateral token without it.
  owner.safety.set_controls_allowed(False)
  assert owner.request(1) == 0


@pytest.mark.parametrize('word', [0x2000, 0x2004, 0x2010])
def test_other_blended_profiles_keep_cancel_withdrawal(owner, word):
  owner.now, owner.counter = 1_000_000, 0
  owner.reset(word)
  # Stock profiles also require their stock SCC receiver graph; alpha HDAI
  # provides an independently armed comparison without those extra inputs.
  owner.warm()
  if word == 0x2004:
    arm(owner)
  owner.feed(button=4)
  assert owner.request(1) == 0
