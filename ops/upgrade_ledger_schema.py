"""Pinned non-trading compatibility upgrade; never relax daily model guards."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import pandas as pd
from backtest_state import STATE,model_digest,verify_manifest
from value_investing import read,write


def run():
    spec=read(ROOT/'config/ledger-schema-compat-v1.json');saved=read(STATE/'manifest.json')
    if model_digest()!=spec['new_model_sha256']:raise ValueError('Unreviewed runtime change')
    for p,digest in spec['unchanged_source_sha256'].items():
        if hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:raise ValueError('Trading source changed: '+p)
    if saved['model_sha256']==spec['new_model_sha256']:
        verify_manifest(saved,pd.to_datetime(saved['calendar']),saved['memberships'])
        print('Ledger schema compatibility already verified');return
    if saved['model_sha256']!=spec['previous_model_sha256']:raise ValueError('Unexpected previous model')
    verify_manifest(saved,pd.to_datetime(saved['calendar']),saved['memberships'],model=spec['previous_model_sha256'])
    prior=hashlib.sha256((STATE/'manifest.json').read_bytes()).hexdigest()
    saved['model_sha256']=spec['new_model_sha256']
    write(STATE/'migrations/ledger-schema-v1.json',dict(status='verified_non_trading_compatibility',previous_model_sha256=spec['previous_model_sha256'],new_model_sha256=spec['new_model_sha256'],prior_manifest_sha256=prior,last_session=saved['last_session'],checkpoint_sha256=saved['checkpoint_sha256'],scope=spec['scope'],strategy_sources_unchanged=True,checkpoint_files_unchanged=True))
    write(STATE/'manifest.json',saved)
    status=read(ROOT/'site/backtest-status.json');status['model_sha256']=spec['new_model_sha256'];write(ROOT/'site/backtest-status.json',status)
    print('Verified unchanged strategy sources, real inputs, and every saved account checkpoint')


if __name__=='__main__':run()
