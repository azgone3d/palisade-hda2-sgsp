"""Account lifetime aggregates, kept separate from analyzed local recordings."""
import hashlib
import json
import math
import os
import time
from pathlib import Path

from openpilot.starpilot.storage import galaxy_storage_root


def valid_stats(data):
  if not isinstance(data, dict):
    return False
  for period in ('all', 'week'):
    row = data.get(period)
    if not isinstance(row, dict):
      return False
    for key in ('distance', 'minutes', 'routes'):
      value = row.get(key)
      if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return False
    if int(row['routes']) != row['routes']:
      return False
  return True


def identity():
  from openpilot.common.params import Params
  from openpilot.starpilot.connect.provider import active_provider
  device = Params().get('DongleId')
  if isinstance(device, bytes):
    device = device.decode()
  provider = active_provider().name
  if not device or provider not in ('comma', 'konik'):
    raise ValueError('Account history unavailable')
  return provider, device, hashlib.sha256(f'{provider}:{device}'.encode()).hexdigest()


def read_history(path=None):
  try:
    path = Path(path) if path is not None else galaxy_storage_root() / 'account-drive-stats.json'
    with path.open('rb') as stream:
      raw = stream.read(16385)
    if len(raw) > 16384:
      return None
    saved = json.loads(raw)
    provider, _, key = identity()
    if (saved.get('schemaVersion') != 1 or saved.get('identity') != key or saved.get('provider') != provider or
        type(saved.get('fetchedAt')) not in (int, float) or not math.isfinite(saved['fetchedAt']) or
        saved['fetchedAt'] < 0 or not valid_stats(saved.get('stats'))):
      return None
    return saved
  except (OSError, ValueError, TypeError, AttributeError):
    return None


def refresh_history():
  """Called by Galaxy's existing parked worker; never by the drawing thread."""
  try:
    path = galaxy_storage_root() / 'account-drive-stats.json'
    previous = read_history(path)
    if previous and time.time() - previous.get('fetchedAt', 0) < 21600:
      return
    from openpilot.common.api import Api, api_get
    provider, device, key = identity()
    response = api_get(f'v1.1/devices/{device}/stats', timeout=15,
                       access_token=Api(device).get_token(expiry_hours=.1))
    if response.status_code != 200:
      return
    data = response.json()
    if not valid_stats(data) or identity() != (provider, device, key):
      return
    saved = dict(schemaVersion=1, provider=provider, identity=key, fetchedAt=time.time(), stats=data)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f'.account-drive-stats.{os.getpid()}.tmp')
    with temporary.open('w') as stream:
      os.chmod(temporary, 0o600)
      json.dump(saved, stream, allow_nan=False)
    os.replace(temporary, path)
  except Exception:
    # Offline/provider errors retain the last validated account snapshot.
    return
