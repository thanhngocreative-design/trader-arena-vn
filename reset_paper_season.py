"""Archive all prior paper accounts, then start one new forward-only season.

Backtests are never touched. Prior daily signals can seed next-session orders
after the reset; no positions, fills or NAV history are copied into the season.
"""
import argparse,hashlib,json,shutil
from datetime import datetime
from pathlib import Path
import pandas as pd
from historical_minute import VN
from engine import Settings,TRADERS,backtest
from fast_engine import FastContext,CORE,build_hybrid_signals
from datafeed import load_prices
from paper_forward import _base_bot,RULES_REVISION,update_paper
from paper_intraday import atomic,publish
from minute_arena import new_accounts
ROOT=Path(__file__).resolve().parent

def reset(start):
    day=pd.Timestamp(start).date().isoformat(); reset_id='paper-'+day
    now=datetime.now(VN).isoformat(); begins=day+'T00:00:00+07:00'
    existing=json.loads((ROOT/'state/paper_state.json').read_text(encoding='utf8'))
    if existing.get('reset_id')==reset_id:
        raise ValueError('This season is already active; refuse to reset it again')
    if pd.Timestamp(begins)<=pd.Timestamp(now): raise ValueError('Choose a future start date')
    dashboard=json.loads((ROOT/'site/dashboard.json').read_text(encoding='utf8'))
    # Prepare observable daily facts BEFORE making any change to live ledgers.
    prices,benchmark,missing=load_prices(dashboard['stock_symbols'])
    if missing:raise ValueError('Missing real daily data: '+str(missing))
    if str(benchmark.index.max().date())>=day:raise ValueError('Reset cannot replay a completed contest session')
    settings=Settings(portfolio_policy='atr_v1');ctx=FastContext(prices,benchmark,settings)
    reference={k:backtest(prices,benchmark,k,'2022-01-03',settings=settings,features_cache=ctx) for k in CORE}
    build_hybrid_signals(ctx,{k:r['curve'] for k,r in reference.items()})
    idx=len(ctx.dates)-1
    rows={sym:pd.Series({**{k:float(ctx.a[k][i,idx]) for k in ctx.a},**{f'buy_{k}':bool(ctx.buy[k][i,idx]) for k in TRADERS}}) for i,sym in enumerate(ctx.symbols)}
    archive=ROOT/'state/paper_archive'/('before-'+day)
    if archive.exists():raise ValueError('Archive already exists; refuse to overwrite history')
    archive.mkdir(parents=True)
    sources=('state/paper_state.json','state/paper_intraday.json','site/paper-intraday.json')
    hashes={}
    for relative in sources:
        p=ROOT/relative; dest=archive/relative.replace('/','__')
        shutil.copy2(p,dest);hashes[relative]=hashlib.sha256(p.read_bytes()).hexdigest()
    atomic(archive/'paper-dashboard.json',{'paper':dashboard['paper'],'paper_started_at':dashboard.get('paper_started_at')})
    atomic(archive/'manifest.json',dict(reset_id=reset_id,archived_at=now,start=begins,sha256=hashes))
    active={k for k,v in json.loads((ROOT/'config/bots.json').read_text(encoding='utf8')).items() if v}
    daily=dict(version=1,started_at=begins,contest_start_session=day,reset_id=reset_id,reset_at=now,last_session=None,bots={k:_base_bot(settings) for k in TRADERS},warnings=[],rules_revision=RULES_REVISION)
    atomic(ROOT/'state/paper_state.json',daily)
    daily,_=update_paper(prices,benchmark,settings=settings,active_ids=active,prepared_rows=rows)
    intraday=dict(started_at=begins,contest_start_session=day,reset_id=reset_id,reset_at=now,last_observed_at=None,sessions=[],symbols_observed=[],marks={},watermarks={},paper_minute=new_accounts(),paper_combo=new_accounts(),combo_gate_date=str(benchmark.index.max().date()),combo_gate_valid=False)
    publish(intraday,'scheduled_start')
    dashboard.update(paper={k:dict(cash=100_000_000,nav=100_000_000,return_pct=0,holdings=[],orders_next=b['orders_next'][:10],trades=[],history=[]) for k,b in daily['bots'].items()},paper_started_at=begins,paper_contest_start=day,paper_reset_id=reset_id)
    atomic(ROOT/'site/dashboard.json',dashboard)
    print('Archived previous paper; all 33 accounts reset to 100m. Start:',day,flush=True)
    print('Fresh prior-day plans queued:',sum(len(b['orders_next']) for b in daily['bots'].values()),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--start',required=True);a=p.parse_args();reset(a.start)
