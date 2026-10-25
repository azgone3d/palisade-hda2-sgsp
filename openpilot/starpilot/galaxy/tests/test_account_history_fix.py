import json
from unittest.mock import patch
import pytest
from openpilot.starpilot.galaxy import account_history as account
from openpilot.starpilot.ui.history_view import HistoryView

STATS = {'all': {'distance':4200.886388542363,'minutes':12806,'routes':772},
         'week': {'distance':116.096,'minutes':468,'routes':49}}


@pytest.mark.parametrize('bad', [None, {}, {'all':{}}, {'all':STATS['all'],'week':None}])
def test_invalid_stats_rejected(bad):
  assert not account.valid_stats(bad)


@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf'), '4000'])
def test_invalid_distance_rejected(value):
  data=json.loads(json.dumps(STATS));data['all']['distance']=value
  assert not account.valid_stats(data)


def test_identity_bound_cache(tmp_path):
  path=tmp_path/'account.json'
  saved=dict(schemaVersion=1,provider='comma',identity='same',fetchedAt=100,stats=STATS)
  path.write_text(json.dumps(saved))
  with patch.object(account,'identity',return_value=('comma','device','same')):
    assert account.read_history(path)['stats']==STATS
  with patch.object(account,'identity',return_value=('comma','other','different')):
    assert account.read_history(path) is None
  path.write_text('x'*17000)
  assert account.read_history(path) is None


@pytest.mark.parametrize('metric', [False,True])
def test_home_uses_account_without_adding_local_totals(metric):
  from openpilot.starpilot.galaxy import drive_stats
  local={'totals':{'drives':40,'distanceMeters':99999,'durationSeconds':1234},
         'week':{'drives':40,'distanceMeters':99999,'durationSeconds':1234,'days':[]}}
  with patch.object(drive_stats.DriveStatsOwner,'snapshot',return_value=local), \
       patch.object(account,'read_history',return_value={'stats':STATS}):
    view=HistoryView(); data=view.snapshot(metric=metric,offroad=True)
    assert data is not None
    assert data.all_time.drives==772
    assert data.all_time.distance==pytest.approx(STATS['all']['distance']*(1.609344 if metric else 1))
    assert data.all_time.hours==pytest.approx(12806/60)
    assert data.this_week.distance==pytest.approx(99999*(.001 if metric else 1/1609.344))
    assert view.snapshot(metric=metric,offroad=False) is data


def test_home_does_not_load_history_onroad():
  from openpilot.starpilot.galaxy import drive_stats
  with patch.object(drive_stats,'DriveStatsOwner',side_effect=AssertionError('onroad read')):
    assert HistoryView().snapshot(metric=False,offroad=False) is None
