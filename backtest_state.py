"""Versioned simulation checkpoints, distinct from the retained raw market bank."""
import hashlib,json
from pathlib import PurePosixPath
from value_investing import ROOT,read
from paper_replay import MARKET,pack,unpack

STATE=ROOT/'state/backtest_continuous'
MODEL_FILES=('engine.py','fast_engine.py','hybrid_backtest.py','pit_intraday.py',
    'pit_context.py','minute_arena.py','pit_minute_data.py','portfolio.py',
    'execution.py','value_investing.py','value_intraday.py','pit_daily.py','replay_rules.py',
    'education_bots.py','paper_replay.py','paper_fixed146.py','vn30.py','config/value-fundamentals.json','config/value-fundamentals-300.json',
    'config/market-classification.json','intraday_data.py','historical_minute.py',
    'collect_pit_daily.py','pit_universe.py','vn30_current.py',
    'continuous_backtest.py','backtest_state.py','requirements.txt')


def model_digest():
    # Canonical newlines: Windows bootstrap and Linux Actions must agree.
    return hashlib.sha256(b''.join(p.encode()+b'\0'+(ROOT/p).read_bytes().replace(b'\r\n',b'\n') for p in MODEL_FILES)).hexdigest()


def frozen_sources():
    return {p.relative_to(MARKET).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in MARKET.rglob('*.gz')}


def verify_manifest(saved,dates,memberships,*,market=MARKET,model=None,state_root=STATE):
    if saved['model_sha256']!=(model or model_digest()):
        raise ValueError('Strategy changed: bootstrap from retained original candles; never append incompatible state')
    prefix=[str(d.date()) for d in dates if str(d.date())<=saved['last_session']]
    if saved['calendar']!=prefix:raise ValueError('Previously used benchmark sessions changed')
    for cohort,rows in memberships.items():
        known=[r for r in rows if r['effective']<=saved['last_session']]
        if saved['memberships'][cohort]!=known:raise ValueError('Previously used membership changed: '+cohort)
    for name,digest in saved['input_sha256'].items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid source checkpoint path')
        if hashlib.sha256(market.joinpath(*relative.parts).read_bytes()).hexdigest()!=digest:
            raise ValueError('Previously consumed real market input changed: '+name)
    for name,digest in saved.get('checkpoint_sha256',{}).items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid account-state checkpoint path')
        if hashlib.sha256(state_root.joinpath(*relative.parts).read_bytes()).hexdigest()!=digest:
            raise ValueError('Previously saved account state changed: '+name)


def options(end):
    import pandas as pd
    stop=pd.Timestamp(end)
    return [dict(key=key,label=label,start=str((stop-pd.DateOffset(months=n)).date()) if n else '2023-11-12',end=end)
        for key,label,n in [('3M','3 tháng',3),('6M','6 tháng',6),('1Y','1 năm',12),('2Y','2 năm',24),('ALL','Toàn kỳ',0)]]
