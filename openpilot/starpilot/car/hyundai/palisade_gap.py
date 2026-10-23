"""Requested additional lead stand-off for this Palisade's system LONG owner."""

from opendbc.car.hyundai.blended_stock_aol import qualified_alpha
from opendbc.car.hyundai.values import CAR

EXTRA_GAP_M = 2.0
SOURCES = ('carState', 'carControl', 'selfdriveState', 'radarState', 'modelV2')


def lead_buffer(cp, sm, now_ns):
  if (cp.carFingerprint != CAR.HYUNDAI_PALISADE_2023 or
      not qualified_alpha(cp, marked_only=True) or cp.safetyConfigs[0].safetyParam != 0x2014):
    return 0.0
  try:
    if any(not sm.valid[name] or not sm.alive[name] or not 0 < sm.logMonoTime[name] <= now_ns <= sm.logMonoTime[name] + 250_000_000 for name in SOURCES):
      return 0.0
    cs = sm['carState']
    if (
      not sm['carControl'].longActive
      or not sm['selfdriveState'].enabled
      or not cs.canValid
      or cs.canTimeout
      or cs.gasPressed
      or cs.brakePressed
      or cs.seatbeltUnlatched
      or cs.doorOpen
      or str(cs.gearShifter) != 'drive'
    ):
      return 0.0
    return EXTRA_GAP_M
  except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
    return 0.0
