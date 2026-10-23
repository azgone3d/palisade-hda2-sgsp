"""Exact Palisade physical brake withdrawal retains intent, never LONG authority."""
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from opendbc.car import Bus, structs
from openpilot.starpilot.aol.tests.test_honda_brake_intent_health import fixture, NOW, Peers
from openpilot.starpilot.aol.tests.test_palisade_alpha_controls import alpha_params
from openpilot.starpilot.aol.transport_pause import TransportPauseFeedback
from openpilot.starpilot.aol.runtime import decide_axes
from openpilot.starpilot.aol.wire import encode_safety
from openpilot.starpilot.car.hyundai.aol import palisade_brake_source


def peers():
  _, cs, old, native, _ = fixture(coherent=True, long_allowed=False)
  cp = alpha_params()
  cfg = cp.safetyConfigs[0]
  slot = replace(native.pandaInventory[0], safetyModel=cfg.safetyModel.raw, safetyParam=cfg.safetyParam,
                 alternativeExperience=cp.alternativeExperience)
  native = replace(native, safetyModel=cfg.safetyModel.raw, safetyParam=cfg.safetyParam, pandaInventory=(slot,))
  messages = {k:m.as_builder() for k,m in old.messages.items()}
  messages['aolSafetyWire'].aolSafetyWire = encode_safety(native)
  p = messages['pandaStates'].pandaStates[0]
  p.safetyModel,p.safetyParam,p.alternativeExperience = cfg.safetyModel,cfg.safetyParam,cp.alternativeExperience
  a = messages['aolAxisState'].aolAxisState
  a.intentProducerSessionId,a.intentIntegrityEpoch = 'card-unit',1
  sm = Peers([m.as_reader() for m in messages.values()])
  fb = TransportPauseFeedback(cp)
  fb.session = native.axisSessionId
  fb.healthy_feedback_ns,fb.healthy_native_ns = NOW-10_000_000,native.observedMonoTime
  fb.healthy_inventory = (native.pandaSerial,tuple(p.hardwareSerial for p in native.pandaInventory))
  fb.availability_producer,fb.availability_epoch = 'card-unit',1
  return cp,cs,sm,native,fb


@pytest.mark.parametrize('veto', ['none','no_source','stale_source','unlatched','producer','epoch','door','gas',
                                 'steering','no_brake','native_denial','rx','fault','expired'])
def test_physical_brake_retains_only_existing_granted_lateral(veto):
  cp,cs,sm,native,fb = peers()
  source=NOW-1000;producer='card-unit';latched=True
  if veto=='no_source':source=0
  if veto=='stale_source':source=NOW-30_000_001
  if veto=='unlatched':latched=False
  if veto=='producer':producer='other'
  if veto=='epoch':fb.availability_epoch=2
  if veto=='door':cs.doorOpen=True
  if veto=='gas':cs.gasPressed=True
  if veto=='steering':cs.steeringDisengage=True
  if veto=='no_brake':cs.brakePressed=False
  if veto in ('native_denial','rx','fault','expired'):
    if veto=='native_denial':native=replace(native,lateralAllowed=False)
    if veto=='rx':native=replace(native,pandaInventory=(replace(native.pandaInventory[0],safetyRxChecksInvalid=True),))
    if veto=='fault':native=replace(native,pandaInventory=(replace(native.pandaInventory[0],faults=1),))
    if veto=='expired':native=replace(native,validUntilMonoTime=NOW-1)
    m=sm.messages['aolSafetyWire'].as_builder();m.aolSafetyWire=encode_safety(native);sm.messages['aolSafetyWire']=m.as_reader()
  result=fb._honda_brake_lateral_current(sm,cp,cs,sm['aolAxisState'],NOW,latched=latched,
                                         brake_source_ns=source,producer=producer)
  assert (result is not None) is (veto=='none')
  if result is not None:
    assert result.lateralAllowed and not result.longitudinalAllowed
    assert result.validUntilMonoTime==native.validUntilMonoTime
    assert not fb.observe(sm,cp,cs,NOW,latched=True,brake_source_ns=source,intent_producer_session=producer)


def test_brake_source_requires_exact_current_physical_parser_sample():
  cp=alpha_params();cs=structs.CarState(canValid=True,brakePressed=True)
  sample=NS(timestamps=[NOW+9_000_000_000],timeout_threshold=100_000_000)
  parser=NS(message_states={1:sample},dbc=NS(name_to_msg={'TCS13':NS(address=1)}),vl={'TCS13':{'DriverOverride':2}})
  ci=NS(CP=cp,can_parsers={Bus.pt:parser})
  observation=(cs,NOW-1000,NOW+9_000_000_000,NOW+9_000_001_000)
  assert palisade_brake_source(ci,cs,observation,NOW)==NOW-1000
  sample.timestamps[0]-=30_000_001
  assert palisade_brake_source(ci,cs,observation,NOW)==0
  sample.timestamps[0]+=30_000_001
  parser.vl['TCS13']['DriverOverride']=0
  assert palisade_brake_source(ci,cs,observation,NOW)==0


@pytest.mark.parametrize('pause_speed,active', [(0.,True),(5.,True),(15.,False)])
def test_retained_brake_intent_still_obeys_configured_lateral_pause(pause_speed,active):
  _,cs,_,native,_=peers()
  decision=decide_axes(standard_lateral=False,standard_longitudinal=False,
    intent=NS(pauseLateral=False,allowedLatch=True,pauseLongitudinal=False),native=native,car_state=cs,
    initialized=True,model_ready=True,no_entry=False,immediate_disable=False,dm_lockout=False,
    pause_brake_mps=pause_speed)
  assert decision.lateral_active is active
  assert not decision.longitudinal_active
