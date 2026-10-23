"""Read-only TCS13 brake-light signal for the observed Palisade platform."""
from opendbc.car import Bus


def reported(ci, cs, observation):
  try:
    if (ci.CP.carFingerprint != 'HYUNDAI_PALISADE_2023' or not cs.canValid or cs.canTimeout or
        observation is None or observation[0] is not cs):
      return None
    _,_,source,boot=observation
    parser=ci.can_parsers[Bus.pt]
    sample=parser.message_states[parser.dbc.name_to_msg['TCS13'].address]
    stamp=int(sample.timestamps[-1])
    if not 0 < stamp <= source <= boot or boot-stamp > min(sample.timeout_threshold,30_000_000):
      return None
    value=parser.vl['TCS13']['BrakeLight']
    return bool(value) if value in (0,1) else None
  except (AttributeError,KeyError,IndexError,TypeError,ValueError,OverflowError):
    return None
