"""Display-only de-duplication of nearly coincident vision lead hypotheses."""
import math


def duplicate_vision_lead(primary, secondary):
  # Keep distinct vehicles and radar-backed tracks. This only avoids painting
  # the same near-coincident pair of model hypotheses twice; planners retain both.
  if not primary.present or not secondary.present or primary.radar or secondary.radar:
    return False
  values = (primary.dRel, secondary.dRel, primary.yRel, secondary.yRel, primary.vRel, secondary.vRel)
  return (all(math.isfinite(value) for value in values) and
          abs(primary.dRel - secondary.dRel) <= .5 and
          abs(primary.yRel - secondary.yRel) <= .25 and
          abs(primary.vRel - secondary.vRel) <= 1.)
