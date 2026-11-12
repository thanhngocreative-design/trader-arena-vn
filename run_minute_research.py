"""Run only the missing minute-only study; retain existing daily/combo results."""
import argparse,hashlib,json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
import numpy as np
from engine import TRADERS
from intraday_data import normalize_minute
from minute_arena import features,darvas_features,new_accounts,step,snapshot
from bot_timeframes import timeframe_manifest
ROOT=Path(__file__).resolve().parent

def run(bot=None):
    targets=[bot] if bot else list(TRADERS)
    research=json.loads((ROOT/'site/research-146.json').read_text(encoding='utf8'))
    audit=research['hybrid_backtest_audit']; frames={}; daily={}
    for n,sym in enumerate(research['universe'],1):
        path=ROOT/'data/minute_history'/f'{sym}.csv.gz'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=audit['coverage_by_symbol'][sym]['sha256']: raise ValueError('Minute input changed: '+sym)
        f=normalize_minute(pd.read_csv(path),'vnd'); frames[sym]=f
        daily[sym]={str(d.date()):g for d,g in f.groupby(f.index.normalize())}
        if n%20==0:print('Verified real minute input:',n,'/146',flush=True)
    accounts={k:v for k,v in new_accounts().items() if k in targets}; marks={}; curves={k:[] for k in targets}
    dates=sorted(set(d for groups in daily.values() for d in groups)); benchmark=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv').set_index('date').close
    engine_hash=hashlib.sha256(b''.join((ROOT/name).read_bytes() for name in ('minute_arena.py','paper_metrics.py','run_minute_research.py'))+json.dumps(audit['coverage_by_symbol'],sort_keys=True).encode()).hexdigest()
    checkpoint=ROOT/'data/minute_history'/('checkpoint-'+(bot or 'all')+'-v2.json')
    done=-1
    if checkpoint.exists():
        saved=json.loads(checkpoint.read_text(encoding='utf8'))
        if saved.get('engine_hash')==engine_hash and saved.get('targets')==targets and saved.get('dates')==dates:
            accounts=saved['accounts'];marks=saved['marks'];curves=saved['curves'];done=saved['seq']
            print('Resuming after completed session',done+1,flush=True)
    for seq,date in enumerate(dates):
        if seq<=done:continue
        held={sym for b in accounts.values() for sym in b['positions']}; events=[]
        for sym in research['universe']:
            raw=daily[sym].get(date)
            if raw is None: continue
            f=darvas_features(raw) if targets==['Darvas'] else features(raw)
            if sym in held: chosen=np.ones(len(f),dtype=bool)
            else:
                signal=f[targets].any(axis=1).to_numpy(); chosen=signal|np.r_[False,signal[:-1]]
            events.extend((ts,sym,row) for ts,row in f.loc[chosen].to_dict('index').items())
        for ts,sym,row in sorted(events,key=lambda e:(e[0],e[1])): step(accounts,sym,row,ts,seq,marks)
        # Last OBSERVED continuous minute marks, no daily price dependency.
        for sym,groups in daily.items():
            if date in groups: marks[sym]=float(groups[date].close.iloc[-1])
        values=snapshot(accounts,marks)
        for k,b in values.items(): curves[k].append(dict(date=date,nav=b['nav'],bot=b['return_pct'],index=(float(benchmark.loc[date])/float(benchmark.loc[dates[0]])-1)*100))
        # Requests expire across sessions and lunch/data gaps; step enforces <=3m.
        for b in accounts.values(): b['pending'].clear()
        if seq%25==0 or seq==len(dates)-1:
            saved=dict(engine_hash=engine_hash,targets=targets,dates=dates,seq=seq,accounts=accounts,marks=marks,curves=curves)
            tmp=checkpoint.with_suffix('.tmp');tmp.write_text(json.dumps(saved,allow_nan=False,separators=(',',':')),encoding='utf8');tmp.replace(checkpoint)
            print(f'Minute-only research {targets}: {seq+1}/{len(dates)} sessions',flush=True)
    results=snapshot(accounts,marks)
    for k,b in results.items():
        curve=curves[k]; navs=np.array([100_000_000]+[r['nav'] for r in curve]); b['max_drawdown_pct']=round(float((navs/np.maximum.accumulate(navs)-1).min()*100),2)
        b['benchmark_return_pct']=round(curve[-1]['index'],2)
        chosen=sorted(set(round(i*(len(curve)-1)/89) for i in range(90)))
        b['curve']=[curve[i] for i in chosen]; b['actions']=[]; b.pop('history'); b.pop('orders_next'); b.pop('observed_history_points',None)
        pd.DataFrame(accounts[k]['trades']).to_csv(ROOT/'data/minute_history'/f'minute-only-trades-{k}-v2.csv',index=False)
        pd.DataFrame(curve).to_csv(ROOT/'data/minute_history'/f'minute-only-curve-{k}-v2.csv',index=False)
    latest=json.loads((ROOT/'site/research-146.json').read_text(encoding='utf8'))
    if latest['universe']!=research['universe'] or latest['hybrid_backtest_audit']!=audit:raise ValueError('Research inputs changed during rerun')
    research=latest
    previous=research.get('minute_backtests',{}).get('Darvas',{})
    research['minute_backtests']={**research.get('minute_backtests',{}),**results}
    if len(research['minute_backtests'])!=11:raise ValueError('Need all 11 published bot results')
    research['minute_backtest_audit']={**audit,'mode':'minute_only_experimental_proxies','signal_inputs':'Completed minute OHLCV only; no daily screen. Hybrid is minute consensus, not daily selector.','risk':'14-observed-minute ATR, 5% preceding minute volume; estimated liquidity from 20 observed minutes; fees/tax/slippage; 5-session minimum hold; 7-session cooldown. Signals reset daily; no interpolation.','valuation':'Last observed continuous minute, carried forward when no observation. Ex-post 146-stock selection bias applies.'}
    if 'Darvas' in targets:
        research['minute_backtest_audit']['bot_revisions']={**latest.get('minute_backtest_audit',{}).get('bot_revisions',{}),'Darvas':dict(revision='darvas_prior_low20_v2',fixed_at=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),fix='Exit floor excludes current candle: minimum of prior 20 observed closed-minute lows.',previous_result_invalidated={k:previous.get(k) for k in ('return_pct','max_drawdown_pct','buy_count','closed_trades')},engine_sha256=engine_hash)}
        research['minute_backtests']['Darvas']['rules_revision']='darvas_prior_low20_v2'
    research['bot_timeframes']=timeframe_manifest()
    for name in ('research-146.json','dashboard.json'):
        path=ROOT/'site'/name
        obj=research if name.startswith('research') else {**json.loads(path.read_text(encoding='utf8')),**{k:research[k] for k in ('minute_backtests','minute_backtest_audit','bot_timeframes')}}
        path.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8')
    print('Minute-only study published:',targets,'updated; other bot results preserved; 146 real histories.',flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bot',choices=list(TRADERS));args=parser.parse_args();run(args.bot)
