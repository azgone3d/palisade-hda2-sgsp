"""Low-speed Palisade model intent; never creates lateral authority."""

import math

from openpilot.cereal import log
from openpilot.common.constants import CV
from opendbc.car.hyundai.blended_stock_aol import qualified, qualified_alpha

MAX_TURN_SPEED = 20 * CV.MPH_TO_MS
MAX_SOURCE_AGE_NS = 100_000_000


def turn_desire(cp, sm, now_ns, current_desire, *, supported):
  # Match the reference's blinker-only low-speed hint. Existing lane changes
  # and navigation desires retain priority; unsupported model inputs stay off.
  if (
    not supported
    or current_desire != log.Desire.none
    or not (
      (qualified(cp, marked_only=True) and cp.safetyConfigs[0].safetyParam == 0x2010)
      or (qualified_alpha(cp, marked_only=True) and cp.safetyConfigs[0].safetyParam == 0x2014)
    )
  ):
    return current_desire
  try:
    for service in ('carState', 'carControl'):
      stamp = int(sm.logMonoTime[service])
      if not sm.seen[service] or not sm.valid[service] or not sm.alive[service] or not 0 < stamp <= now_ns <= stamp + MAX_SOURCE_AGE_NS:
        return current_desire
    cs, cc = sm['carState'], sm['carControl']
    if (
      not cc.latActive
      or not cs.canValid
      or cs.canTimeout
      or str(cs.gearShifter) != 'drive'
      or cs.steerFaultTemporary
      or cs.steerFaultPermanent
      or cs.doorOpen
      or cs.seatbeltUnlatched
      or not math.isfinite(cs.vEgo)
      or not 0 <= cs.vEgo < MAX_TURN_SPEED
      or cs.leftBlinker == cs.rightBlinker
    ):
      return current_desire
    if cs.leftBlinker and not cs.leftBlindspot:
      return log.Desire.turnLeft
    if cs.rightBlinker and not cs.rightBlindspot:
      return log.Desire.turnRight
  except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
    pass
  return current_desire
