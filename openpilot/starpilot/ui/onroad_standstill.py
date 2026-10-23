"""Explain current Palisade lateral intent while steering is gated at rest."""


def lateral_ready(cp, car, control, axis):
  # The caller supplies only freshness-qualified display messages/current_axis.
  return bool(cp is not None and getattr(cp, 'carFingerprint', '') == 'HYUNDAI_PALISADE_2023' and
    not getattr(cp, 'steerAtStandstill', True) and car is not None and control is not None and axis is not None and
    car.standstill and car.canValid and not car.canTimeout and not car.steerFaultTemporary and
    not car.steerFaultPermanent and not control.latActive and axis.nativeAcknowledged and
    axis.desiredLateral and axis.lateralActive and str(axis.faultReason) == 'none')
