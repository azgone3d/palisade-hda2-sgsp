from types import SimpleNamespace as NS
import pytest
from opendbc.car import Bus
from openpilot.starpilot.ui.brake_lights import observe
from openpilot.starpilot.car.hyundai.palisade_brake_lights import reported


@pytest.mark.parametrize('on', [False,True])
def test_feedback_requires_current_matching_source(on):
  cp=NS(carFingerprint='HYUNDAI_PALISADE_2023');car=NS(canValid=True,canTimeout=False,brakePressed=False)
  companion=NS(sourceCarStateMonoTime=1000,brakeLights=on)
  assert observe(cp,car,companion,car_ns=1000,companion_ns=1000,now_ns=2000,long_active=True) is on
  assert observe(cp,car,companion,car_ns=1000,companion_ns=1000,now_ns=200_001_001,long_active=True) is None
  companion.sourceCarStateMonoTime=999
  assert observe(cp,car,companion,car_ns=1000,companion_ns=1000,now_ns=2000,long_active=True) is None


@pytest.mark.parametrize('long_active,pedal,shown', [(True,False,True),(True,True,False),
                                                  (False,False,False),(False,True,False)])
def test_indicator_is_only_for_active_long_without_driver_braking(long_active,pedal,shown):
  cp=NS(carFingerprint='HYUNDAI_PALISADE_2023')
  car=NS(canValid=True,canTimeout=False,brakePressed=pedal)
  companion=NS(sourceCarStateMonoTime=1000,brakeLights=True)
  result=observe(cp,car,companion,car_ns=1000,companion_ns=1000,now_ns=2000,long_active=long_active)
  assert (result is True) is shown


def test_driver_pedal_and_deceleration_are_not_used_to_infer_lamps():
  cp=NS(carFingerprint='HYUNDAI_PALISADE_2023');cs=NS(canValid=True,canTimeout=False,brakePressed=False)
  p=NS(dbc=NS(name_to_msg={'TCS13':NS(address=1)}),message_states={1:NS(timestamps=[100],timeout_threshold=30000000)},
       vl={'TCS13':{'BrakeLight':1}})
  ci=NS(CP=cp,can_parsers={Bus.pt:p})
  assert reported(ci,cs,(cs,100,100,100)) is True
  p.vl['TCS13']['BrakeLight']=0
  assert reported(ci,cs,(cs,100,100,100)) is False
  assert reported(ci,cs,(cs,100,100,30000101)) is None
  assert reported(ci,cs,None) is None
