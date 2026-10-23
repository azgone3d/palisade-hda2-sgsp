"""Bounded glows over existing projected geometry; never a tracking source."""
from functools import lru_cache
import numpy as np
import pyray as rl
from openpilot.system.ui.lib.shader_polygon import Gradient


def expanded_lane(points, factor):
  if points.ndim != 2 or points.shape[1] != 2 or not 4 <= len(points) <= 132 or len(points) % 2 or not np.isfinite(points).all():
    return None
  half = len(points) // 2
  left, right = points[:half], points[half:][::-1]
  middle = (left + right) / 2
  return np.concatenate((middle + (left - middle) * factor, (middle + (right - middle) * factor)[::-1]))


@lru_cache(maxsize=32)
def lane_gradient(rgb, alpha):
  return Gradient(start=(0., 1.), end=(0., 0.),
    colors=[rl.Color(*rgb, alpha), rl.Color(*rgb, alpha // 2), rl.Color(*rgb, 0)], stops=[0., .55, 1.])


def draw_lane(rect, points, rgb, probability, draw_polygon):
  # At most two additional bounded polygons per lane; absent evidence draws none.
  if not np.isfinite(probability) or probability <= 0:
    return
  for factor, alpha in ((3.8, 76), (2.2, 112)):
    expanded = expanded_lane(points, factor)
    if expanded is not None:
      draw_polygon(rect, expanded, gradient=lane_gradient(tuple(rgb), int(min(.7, probability) * alpha)))


def draw_chevron(lead, rgb):
  points = lead.chevron
  if len(points) != 3 or not np.isfinite(points).all():
    return False
  right, tip, left = (rl.Vector2(*point) for point in points)
  # Keep the same outline at every distance; close/closing warnings turn it red.
  if lead.fill_alpha >= 200:
    rgb = (201, 34, 49)
  for width, alpha in ((24, 45), (14, 90), (7, 255)):
    color = rl.Color(*rgb, alpha)
    rl.draw_line_ex(left, tip, width, color)
    rl.draw_line_ex(tip, right, width, color)
  return True
