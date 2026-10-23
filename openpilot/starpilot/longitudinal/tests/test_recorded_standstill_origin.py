"""Recorded model-origin roundoff is symmetric; real offsets remain unknown."""
from types import SimpleNamespace as NS
import pytest
from openpilot.starpilot.model_geometry import normalized_origin, standstill_clear_horizon


@pytest.mark.parametrize('origin', [-1.3520295993885156e-12, 1.9819701435608295e-12,
                                   6.105782546228511e-12, -1e-6, 0., 1e-6])
def test_recorded_origin_roundoff_does_not_invalidate_stationary_geometry(origin):
  xs=[origin,-.000147598,-.0000267015,-.00102718,-.000849645]
  xs += [46.57464599609375*i/28 for i in range(1,29)]
  model=NS(position=NS(x=xs))
  assert len(xs)==33
  assert standstill_clear_horizon(model)==xs[-1]
  assert xs[0]==origin
  assert normalized_origin(tuple(xs))[0]==0.


@pytest.mark.parametrize('origin', [-.001,.001,float('nan'),float('inf')])
def test_real_origin_offsets_remain_rejected(origin):
  xs=[origin]+[70.*i/32 for i in range(1,33)]
  assert standstill_clear_horizon(NS(position=NS(x=xs))) is None
