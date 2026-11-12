"""Run only the missing minute-only study; retain existing daily/combo results."""
import hashlib,json
from pathlib import Path
import pandas as pd
import numpy as np
from engine import TRADERS
from intraday_data import normalize_minute
from minute_arena import features,new_accounts,step,snapshot
from bot_timeframes import timeframe_manifest
ROOT=Path(__file__).resolve().parent

def run():
    research=json.loads((ROOT/'site/research-146.json').read_text(encoding='utf8'))
    audit=research['hybrid_backtest_audit']; frames={}; daily={}
    for sym in research['universe']:
        path=ROOT/'data/minute_history'/f'{sym}.csv.gz'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=audit['coverage_by_symbol'][sym]['sha256']: raise ValueError('Minute input changed: '+sym)
        f=normalize_minute(pd.read_csv(path),'vnd'); frames[sym]=f
        daily[sym]={str(d.date()):g for d,g in f.groupby(f.index.normalize())}
    accounts=new_accounts(); marks={}; curves={k:[] for k in TRADERS}
    dates=sorted(set(d for groups in daily.values() for d in groups)); benchmark=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv').set_index('date').close
    for seq,date in enumerate(dates):
        held={sym for b in accounts.values() for sym in b['positions']}; events=[]
        for sym in research['universe']:
            raw=daily[sym].get(date)
            if raw is None: continue
            f=features(raw)
            if sym in held: chosen=np.ones(len(f),dtype=bool)
            else:
                signal=f[list(TRADERS)].any(axis=1).to_numpy(); chosen=signal|np.r_[False,signal[:-1]]
            events.extend((ts,sym,row) for ts,row in f.loc[chosen].to_dict('index').items())
        for ts,sym,row in sorted(events,key=lambda e:(e[0],e[1])): step(accounts,sym,row,ts,seq,marks)
        # Last OBSERVED continuous minute marks, no daily price dependency.
        for sym,groups in daily.items():
            if date in groups: marks[sym]=float(groups[date].close.iloc[-1])
        values=snapshot(accounts,marks)
        for k,b in values.items(): curves[k].append(dict(date=date,nav=b['nav'],bot=b['return_pct'],index=(float(benchmark.loc[date])/float(benchmark.loc[dates[0]])-1)*100))
        # Requests expire across sessions and lunch/data gaps; step enforces <=3m.
        for b in accounts.values(): b['pending'].clear()
        if seq%25==0: print(f'Minute-only research {seq+1}/{len(dates)} sessions',flush=True)
    results=snapshot(accounts,marks)
    for k,b in results.items():
        curve=curves[k]; navs=np.array([100_000_000]+[r['nav'] for r in curve]); b['max_drawdown_pct']=round(float((navs/np.maximum.accumulate(navs)-1).min()*100),2)
        b['benchmark_return_pct']=round(curve[-1]['index'],2)
        chosen=sorted(set(round(i*(len(curve)-1)/89) for i in range(90)))
        b['curve']=[curve[i] for i in chosen]; b['actions']=[]; b.pop('history'); b.pop('orders_next')
        pd.DataFrame(accounts[k]['trades']).to_csv(ROOT/'data/minute_history'/f'minute-only-trades-{k}.csv',index=False)
        pd.DataFrame(curve).to_csv(ROOT/'data/minute_history'/f'minute-only-curve-{k}.csv',index=False)
    research['minute_backtests']=results
    research['minute_backtest_audit']={**audit,'mode':'minute_only_experimental_proxies','signal_inputs':'Completed minute OHLCV only; no daily screen. Hybrid is minute consensus, not daily selector.','risk':'14-observed-minute ATR, 5% preceding minute volume; estimated liquidity from 20 observed minutes; fees/tax/slippage; 5-session minimum hold; 7-session cooldown. Signals reset daily; no interpolation.','valuation':'Last observed continuous minute, carried forward when no observation. Ex-post 146-stock selection bias applies.'}
    research['bot_timeframes']=timeframe_manifest()
    for name in ('research-146.json','dashboard.json'):
        path=ROOT/'site'/name
        obj=research if name.startswith('research') else {**json.loads(path.read_text(encoding='utf8')),**{k:research[k] for k in ('minute_backtests','minute_backtest_audit','bot_timeframes')}}
        path.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8')
    print('Minute-only study published: 11 bots, 146 real histories.',flush=True)
if __name__=='__main__': run()
