"""Cold Palisade selection feedback; this never grants a control axis."""

import math

from opendbc.car.structs import car
from opendbc.car.hyundai.values import CAR
from openpilot.cereal import log
from openpilot.starpilot.car.hyundai.aol import qualified_blended_stock, qualified_blended_alpha


def cold_park_readiness(cp, cs, native, events):
  """An idle native response can acknowledge selection while output stays off.

  Callers must validate native identity/freshness and calibration separately.
  In particular, startup communication/calibration faults are not Park waits.
  """
  return bool(
    cp.carFingerprint == CAR.HYUNDAI_PALISADE_2023
    and (qualified_blended_stock(cp, marked_only=True) and cp.safetyConfigs[0].safetyParam == 0x2010
         or qualified_blended_alpha(cp, marked_only=True) and cp.safetyConfigs[0].safetyParam == 0x2014)
    and cs.gearShifter == car.CarState.GearShifter.park
    and cs.standstill
    and math.isfinite(cs.vEgo)
    and abs(cs.vEgo) <= 0.3
    and cs.canValid
    and not cs.canTimeout
    and not cs.cruiseState.enabled
    and not cs.steerFaultTemporary
    and not cs.steerFaultPermanent
    and not cs.accFaulted
    and not cs.doorOpen
    and not cs.seatbeltUnlatched
    and not cs.gasPressed
    and not cs.steeringDisengage
    and native is not None
    and native.pandaInventory
    and not native.requestedLateral
    and not native.lateralAllowed
    and not native.requestedLongitudinal
    and not native.longitudinalAllowed
    and not any(
      event.immediateDisable
      or event.softDisable
      and event.name != log.OnroadEvent.EventName.wrongGear
      or event.userDisable
      and event.name not in (log.OnroadEvent.EventName.wrongGear, log.OnroadEvent.EventName.wrongCarMode, log.OnroadEvent.EventName.pcmDisable)
      for event in events
    )
  )
