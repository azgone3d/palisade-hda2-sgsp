"""Cached offroad presentation; no network requests in the UI."""
import time
from datetime import datetime
from openpilot.starpilot.ui.home_state import DriveStatsData, DriveSummary, DailyDistance, PersonalRecord


class HistoryView:
  def __init__(self):
    self.updated = float('-inf')
    self.metric = None
    self.value = None

  def snapshot(self, *, metric, offroad):
    if not offroad:
      return self.value
    now = time.monotonic()
    if self.metric == metric and 0 <= now - self.updated < 60:
      return self.value
    self.metric, self.updated = metric, now
    try:
      from openpilot.starpilot.galaxy.drive_stats import DriveStatsOwner
      from openpilot.starpilot.galaxy.account_history import read_history
      local = DriveStatsOwner(metric=lambda: metric).snapshot(time.tzname[0] or 'UTC')
      account = read_history()
      unit = 'kilometers' if metric else 'miles'
      scale = .001 if metric else 1 / 1609.344
      def summary(row):
        return DriveSummary(row['drives'], row['distanceMeters'] * scale, row['durationSeconds'] / 3600, unit)
      def cloud(row):
        return DriveSummary(int(row['routes']), row['distance'] * (1.609344 if metric else 1), row['minutes'] / 60, unit)
      all_time = cloud(account['stats']['all']) if account else summary(local['totals'])
      week = local['week']
      past_week = cloud(account['stats']['week']) if account else summary(week)
      today = datetime.now().astimezone().date()
      days = tuple(DailyDistance(datetime.fromisoformat(row['date']).strftime('%a'), row['distanceMeters'] * scale,
                                 row['date'] == today.isoformat(), row['date'] > today.isoformat()) for row in week['days'])
      records = (PersonalRecord('History source', 'Account' if account else 'Local', 'Saved driving totals'),
                 PersonalRecord('Local recordings', str(local['totals']['drives']), 'Kept separate'),
                 PersonalRecord('Totals combined', 'Never', 'No double counting'))
      self.value = DriveStatsData(all_time, past_week, summary(week), days, records)
    except Exception:
      pass  # Keep the last displayed snapshot if a local cache is being replaced.
    return self.value
