"""Read-only telemetry from already freshness-qualified UI messages."""
from dataclasses import dataclass
import math


def number(obj, name, limit=None):
  value = getattr(obj, name, None)
  if type(value) not in (int, float) or not math.isfinite(value):
    return None
  return float(value) if limit is None or abs(value) <= limit else None


def flag(obj, name):
  value = getattr(obj, name, None)
  return value if type(value) is bool else None


@dataclass(frozen=True)
class TelemetryObservation:
  angle: float | None = None
  desired_lateral: float | None = None
  actual_lateral: float | None = None
  target_torque: float | None = None
  applied_torque: float | None = None
  driver_torque: bool | None = None
  gas_pressed: bool | None = None
  brake_pressed: bool | None = None
  acceleration: float | None = None
  target_acceleration: float | None = None
  command_acceleration: float | None = None
  output_acceleration: float | None = None
  left_blinker: bool | None = None
  right_blinker: bool | None = None
  lateral_active: bool | None = None


def observe_telemetry(car=None, control=None, controls=None, output=None, plan=None):
  # The caller rejects stale/pre-drive/invalid transport messages. CAN validity
  # also gates the remaining sources so a lost vehicle never looks current.
  if car is None or getattr(car, 'canValid', None) is not True or getattr(car, 'canTimeout', None) is not False:
    return TelemetryObservation()
  lateral = None
  try:
    if controls.lateralControlState.which() == 'torqueState':
      candidate = controls.lateralControlState.torqueState
      if candidate.active:
        lateral = candidate
  except (AttributeError, TypeError, ValueError):
    pass
  target = None
  accels = getattr(plan, 'accels', ())
  if len(accels):
    value = accels[0]
    if type(value) in (int, float) and math.isfinite(value):
      target = float(value)
  command = getattr(control, 'actuators', None)
  sent = getattr(output, 'actuatorsOutput', None)
  return TelemetryObservation(
    angle=number(car, 'steeringAngleDeg'), desired_lateral=number(lateral, 'desiredLateralAccel'),
    actual_lateral=number(lateral, 'actualLateralAccel'),
    target_torque=number(command, 'torque', 1), applied_torque=number(sent, 'torque', 1),
    driver_torque=flag(car, 'steeringPressed'), gas_pressed=flag(car, 'gasPressed'),
    brake_pressed=flag(car, 'brakePressed'), acceleration=number(car, 'aEgo'),
    target_acceleration=target, command_acceleration=number(command, 'accel'),
    output_acceleration=number(sent, 'accel'), left_blinker=flag(car, 'leftBlinker'),
    right_blinker=flag(car, 'rightBlinker'), lateral_active=flag(control, 'latActive'))
