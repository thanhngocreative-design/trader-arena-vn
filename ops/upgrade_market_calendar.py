"""Pinned calendar compatibility receipt; never bypass strategy/state checks."""
import hashlib
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from backtest_state import STATE, model_digest, verify_manifest
from market_calendar import closed_dates
from value_investing import read, write


def run():
    spec = read(ROOT / 'config/market-calendar-compat-v1.json')
    saved = read(STATE / 'manifest.json')
    if model_digest() != spec['new_model_sha256']:
        raise ValueError('Unreviewed runtime change')
    for path, digest in spec['unchanged_source_sha256'].items():
        actual = hashlib.sha256((ROOT / path).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if actual != digest:
            raise ValueError('Trading source changed: ' + path)
    if set(saved['calendar']) & closed_dates():
        raise ValueError('A published trading session cannot become a closure')
    if saved['model_sha256'] == spec['new_model_sha256']:
        verify_manifest(saved, pd.to_datetime(saved['calendar']), saved['memberships'])
        return
    if saved['model_sha256'] != spec['previous_model_sha256']:
        raise ValueError('Unexpected previous model')
    verify_manifest(saved, pd.to_datetime(saved['calendar']), saved['memberships'], model=spec['previous_model_sha256'])
    prior = hashlib.sha256((STATE / 'manifest.json').read_bytes()).hexdigest()
    receipt = dict(status='verified_calendar_compatibility', previous_model_sha256=saved['model_sha256'],
        new_model_sha256=spec['new_model_sha256'], prior_manifest_sha256=prior,
        last_session=saved['last_session'], closures=sorted(closed_dates()),
        checkpoint_sha256=saved['checkpoint_sha256'], checkpoint_files_unchanged=True,
        scope=spec['scope'], trading_sources_unchanged=True)
    saved['model_sha256'] = spec['new_model_sha256']
    write(STATE / 'migrations/market-calendar-v1.json', receipt)
    write(STATE / 'manifest.json', saved)
    status = read(ROOT / 'site/backtest-status.json')
    status['model_sha256'] = spec['new_model_sha256']
    write(ROOT / 'site/backtest-status.json', status)
    print('Verified calendar-only migration; every prior account checkpoint remains unchanged')


if __name__ == '__main__':
    run()
