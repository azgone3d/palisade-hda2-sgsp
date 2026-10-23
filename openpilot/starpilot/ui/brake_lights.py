"""Vehicle-reported stop-lamp feedback, independent of requested deceleration."""


def observe(cp, car, companion, *, car_ns, companion_ns, now_ns, long_active=False):
  try:
    if long_active is not True or car.brakePressed is not False:
      return None
    source = int(companion.sourceCarStateMonoTime)
    if (cp.carFingerprint != 'HYUNDAI_PALISADE_2023' or not car.canValid or car.canTimeout or
        not 0 < source == companion_ns <= car_ns <= now_ns or now_ns-source > 200_000_000):
      return None
    return bool(companion.brakeLights)
  except (AttributeError,TypeError,ValueError,OverflowError):
    return None
