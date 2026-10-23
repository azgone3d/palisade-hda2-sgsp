"""Live telemetry remains read-only, opt-in, freshness-bound and alert subordinate."""
from dataclasses import replace
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

from openpilot.starpilot.ui.telemetry_observation import TelemetryObservation, observe_telemetry
from openpilot.starpilot.ui.onroad_telemetry import TelemetryOverlay
from openpilot.starpilot.ui.onroad_customization import TELEMETRY_WIDGET, TELEMETRY_WHEEL_WIDGET, default_document, validate_document
from openpilot.starpilot.ui.onroad_state import OnroadState, OnroadAlert, AlertSize, SpeedLimitObservation
from openpilot.starpilot.ui.shell import ShellMode
from openpilot.starpilot.ui.tests.test_runtime_snapshot import NOW, ui_fake, RuntimeSnapshotAdapter


def sources():
  car = NS(canValid=True, canTimeout=False, steeringAngleDeg=5.1, steeringPressed=False,
           gasPressed=False, brakePressed=True, aEgo=-.23, leftBlinker=True, rightBlinker=False)
  control = NS(latActive=True, actuators=NS(torque=.18, accel=-.5))
  controls = NS(lateralControlState=NS(which=lambda: 'torqueState', torqueState=NS(
    active=True, desiredLateralAccel=-.11, actualLateralAccel=-.08)))
  output = NS(actuatorsOutput=NS(torque=.17, accel=-.4))
  plan = NS(accels=[-.6])
  return car, control, controls, output, plan


def state():
  document = default_document()
  document['layouts']['large'][TELEMETRY_WIDGET]['enabled'] = True
  return OnroadState(True, True, 20., 90., SpeedLimitObservation(), customization=document,
                     telemetry=observe_telemetry(*sources()))


def test_signed_live_readings_preserve_their_meaning():
  value = observe_telemetry(*sources())
  assert value.angle == 5.1
  assert (value.desired_lateral, value.actual_lateral) == (-.11, -.08)
  assert (value.target_torque, value.applied_torque) == (.18, .17)
  assert (value.acceleration, value.target_acceleration, value.command_acceleration, value.output_acceleration) == (-.23, -.6, -.5, -.4)
  assert value.driver_torque is False and value.brake_pressed is True


@pytest.mark.parametrize('bad', ['absent', 'invalid', 'timeout'])
def test_missing_or_bad_can_does_not_expose_other_sources(bad):
  car, *others = sources()
  if bad == 'absent':
    car = None
  elif bad == 'invalid':
    car.canValid = False
  else:
    car.canTimeout = True
  assert observe_telemetry(car, *others) == TelemetryObservation()


def test_partial_sources_and_unsupported_controller_are_not_zero_filled():
  car, control, controls, output, plan = sources()
  controls.lateralControlState.which = lambda: 'angleState'
  assert observe_telemetry(car, control, controls, output, plan).desired_lateral is None
  value = observe_telemetry(car)
  assert value.angle == 5.1 and value.acceleration == -.23
  assert value.applied_torque is None and value.command_acceleration is None and value.lateral_active is None
  control.actuators.torque = float('nan')
  output.actuatorsOutput.torque = 1.1
  plan.accels = [float('inf')]
  value = observe_telemetry(car, control, controls, output, plan)
  assert value.target_torque is None and value.applied_torque is None and value.target_acceleration is None


def test_old_saved_layout_gains_disabled_option_without_moving_widgets():
  old = default_document()
  del old['layouts']['large'][TELEMETRY_WIDGET]
  if 'large' in old.get('widgetOrder', {}):
    old['widgetOrder']['large'].remove(TELEMETRY_WIDGET)
  upgraded = validate_document(old)
  assert not upgraded['layouts']['large'][TELEMETRY_WIDGET]['enabled']
  assert upgraded['layouts']['large']['current_speed'] == old['layouts']['large']['current_speed']


def test_native_option_does_not_change_existing_android_auto_layout_schema():
  from openpilot.starpilot.system.android_auto.projection_layout import (
    default_layout_for_viewport, validate_layout_for_viewport, projection_customization)
  projection = default_layout_for_viewport((2160, 1080))
  assert TELEMETRY_WIDGET not in projection['widgets']
  assert validate_layout_for_viewport(projection, (2160, 1080))['widgets'] == projection['widgets']
  native = default_document()
  native['layouts']['large'][TELEMETRY_WIDGET]['enabled'] = True
  assert not projection_customization(projection, native)['layouts']['large'][TELEMETRY_WIDGET]['enabled']
  assert native['layouts']['large'][TELEMETRY_WIDGET]['enabled']


@pytest.mark.parametrize('size', [AlertSize.SMALL, AlertSize.MID, AlertSize.FULL])
def test_alerts_hide_panel_before_any_drawing_or_resource_work(size):
  widget = TelemetryOverlay(Mock(), '/unused')
  with patch.object(widget.wheel, 'prepare', side_effect=AssertionError('texture allocation')):
    widget.render(replace(state(), alert=OnroadAlert(size=size)))


def test_disabled_panel_allocates_no_texture():
  widget = TelemetryOverlay(Mock(), '/unused')
  sample = state()
  sample.customization['layouts']['large'][TELEMETRY_WIDGET]['enabled'] = False
  with patch.object(widget.wheel, 'prepare', side_effect=AssertionError('texture allocation')):
    widget.render(sample)


@pytest.mark.parametrize('widget_key', [TELEMETRY_WIDGET, TELEMETRY_WHEEL_WIDGET])
def test_runtime_missing_and_expired_sources_clear_values(monkeypatch, widget_key):
  ui = ui_fake()
  adapter = RuntimeSnapshotAdapter(ui)
  doc = default_document()
  doc['layouts']['large'][widget_key]['enabled'] = True
  monkeypatch.setattr('openpilot.starpilot.ui.runtime_snapshot.read_customization', lambda params: doc)
  car, control, controls, output, plan = sources()
  car.vEgo = car.vEgoCluster = 20.0
  car.vCruiseCluster = 90.0
  control.longActive = False
  for name, message in zip(('carState', 'carControl', 'controlsState', 'carOutput', 'longitudinalPlan'),
                           (car, control, controls, output, plan), strict=True):
    ui.sm.put(name, message)
  sample = adapter.build(ShellMode.ONROAD, now_ns=NOW).onroad
  assert sample.telemetry.angle == 5.1
  ui.sm.logMonoTime['carOutput'] = NOW - 1_000_000_000
  ui.sm.logMonoTime['controlsState'] = NOW - 1_000_000_000
  sample = adapter.build(ShellMode.ONROAD, now_ns=NOW).onroad
  assert sample.telemetry.applied_torque is None and sample.telemetry.desired_lateral is None
  ui.sm.logMonoTime['carState'] = NOW - 1_000_000_000
  assert adapter.build(ShellMode.ONROAD, now_ns=NOW).onroad.telemetry == TelemetryObservation()


def test_renderer_rotates_measured_angle_and_does_not_invent_hands_or_pedal_percentages():
  fonts = Mock()
  widget = TelemetryOverlay(fonts, '/unused')
  widget.wheel._texture = object()
  with ExitStack() as stack:
    stack.enter_context(patch.object(widget.wheel, 'prepare'))
    for name in ('draw_rectangle_rec', 'draw_ring', 'draw_circle'):
      stack.enter_context(patch('openpilot.starpilot.ui.onroad_telemetry.rl.' + name))
    draw = stack.enter_context(patch('openpilot.starpilot.ui.onroad_telemetry.rl.draw_texture_pro'))
    widget.render(state())
  assert draw.call_args.args[-2] == -5.1
  labels = [call.args[0] for call in fonts.draw.call_args_list]
  assert 'NOT DETECTED' in labels and 'RELEASED' in labels and 'PRESSED' in labels
  assert 'OFF WHEEL' not in labels and '0%' not in labels
  assert '-0.11 m/s²' in labels and '+18%' in labels


def test_mini_is_only_wheel_arcs_and_indicators_without_panel_or_readouts():
  fonts = Mock()
  widget = TelemetryOverlay(fonts, '/unused')
  widget.wheel._texture = object()
  sample = state()
  sample.customization['layouts']['large'][TELEMETRY_WHEEL_WIDGET]['enabled'] = True
  with ExitStack() as stack:
    stack.enter_context(patch.object(widget.wheel, 'prepare'))
    background = stack.enter_context(patch('openpilot.starpilot.ui.onroad_telemetry.rl.draw_rectangle_rec'))
    rings = stack.enter_context(patch('openpilot.starpilot.ui.onroad_telemetry.rl.draw_ring'))
    texture = stack.enter_context(patch('openpilot.starpilot.ui.onroad_telemetry.rl.draw_texture_pro'))
    widget.render(sample, mini=True)
    background.assert_not_called()
    assert rings.call_count == 8
    assert texture.call_args.args[2].width == pytest.approx(149.6)
    assert texture.call_args.args[-2] == -5.1
    assert [call.args[0] for call in fonts.draw.call_args_list] == ['<', '>']
    texture.reset_mock()
    widget.render(replace(sample, alert=OnroadAlert(size=AlertSize.MID)), mini=True)
    texture.assert_not_called()


def test_mini_is_opt_in_and_migrates_missing_saved_placement():
  document = default_document()
  assert not document['layouts']['large'][TELEMETRY_WHEEL_WIDGET]['enabled']
  del document['layouts']['large'][TELEMETRY_WHEEL_WIDGET]
  upgraded = validate_document(document)
  assert not upgraded['layouts']['large'][TELEMETRY_WHEEL_WIDGET]['enabled']
