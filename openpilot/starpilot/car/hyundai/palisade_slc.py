"""Palisade SLC cruise preference only; never suppress other braking candidates."""
import math


def coast_only(cp, *, slc_target, driver_cruise, curve_target=None, navigation_target=None, forced=False):
  if (cp.carFingerprint != 'HYUNDAI_PALISADE_2023' or not cp.openpilotLongitudinalControl or forced or
      slc_target is None or not all(type(v) in (int,float) and math.isfinite(v) for v in (slc_target,driver_cruise)) or
      not 0 < slc_target < driver_cruise):
    return False
  # Independent lower ceilings keep their ordinary braking treatment.
  for target in (curve_target,navigation_target):
    if target is not None and (not math.isfinite(target) or target <= slc_target):
      return False
  return True
