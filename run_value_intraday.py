"""Replay only the two value adaptations against verified real 146 histories."""
import hashlib,json
from datetime import datetime
import numpy as np
import pandas as pd
from intraday_data import normalize_minute
from minute_arena import snapshot
from sector_analytics import aggregate_trades
from value_investing import ROOT,VN,POLICY,PROFILES,read,write,inputs,eligible_companies
from value_intraday import REVISION,empty_accounts,minute_features,gates_for_date,value_step

def run():
    base=read(ROOT/'site/research-146.json');public=read(ROOT/'site/value-investing.json')
    symbols,prices=inputs();bundle=read(ROOT/'config/value-fundamentals.json')
    classification=read(ROOT/'config/market-classification.json')['sectors'];reports=eligible_companies(bundle,classification)
    benchmark=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv');benchmark['date']=pd.to_datetime(benchmark.date);benchmark=benchmark.set_index('date').close
    all_dates=benchmark.index;dates=all_dates[(all_dates>=base['research_meta']['start'])&(all_dates<=base['research_meta']['end'])]
    if len(dates)!=747:raise ValueError('Expected actual original 747-session calendar')
    gates={};signal_dates={}
    for date in dates:
        previous=all_dates[all_dates<date][-1];key=str(date.date());signal_dates[key]=str(previous.date())
        gates[key]=gates_for_date(reports,prices,previous)
    needed={s for g in gates.values() for b in g.values() for s in b}
    daily={};hashes={}
    for n,s in enumerate(symbols,1):
        path=ROOT/'data/minute_history'/f'{s}.csv.gz';digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=base['hybrid_backtest_audit']['coverage_by_symbol'][s]['sha256']:raise ValueError('Changed real minute source: '+s)
        hashes[s]=digest
        if s in needed:
            f=normalize_minute(pd.read_csv(path),'vnd')
            daily[s]={str(d.date()):g for d,g in f.groupby(f.index.normalize())}
        if n%20==0:print('Verified minute source',n,'/146',flush=True)
    code_hash=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in ('value_intraday.py','minute_arena.py','run_value_intraday.py','value_investing.py','config/value-fundamentals.json'))+json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    accounts={m:empty_accounts() for m in ('minute','combo')};curves={m:{k:[] for k in POLICY} for m in accounts};marks={};done=-1
    checkpoint=ROOT/'data/value_fundamentals/intraday-checkpoint.json'
    if checkpoint.exists():
        saved=read(checkpoint)
        if saved['code_hash']==code_hash:
            accounts=saved['accounts'];curves=saved['curves'];marks=saved['marks'];done=saved['seq'];print('Resuming session',done+1,flush=True)
    for seq,date in enumerate(dates):
        if seq<=done:continue
        key=str(date.date());g=gates[key];events=[]
        held={s for bots in accounts.values() for b in bots.values() for s in b['positions']}
        active=held|{s for b in g.values() for s in b}
        for s in sorted(active):
            raw=daily.get(s,{}).get(key)
            if raw is None:continue
            f=minute_features(raw)
            # A new entry can create a holding DURING this session. Include
            # every later bar too, so its exits/marks cannot disappear merely
            # because an entry predicate stopped being true.
            signal=f[list(POLICY)].any(axis=1).to_numpy()
            chosen=np.ones(len(f),dtype=bool) if s in held else np.maximum.accumulate(signal)
            events.extend((ts,s,row) for ts,row in f.loc[chosen].to_dict('index').items())
        for ts,s,row in sorted(events,key=lambda e:(e[0],e[1])):
            for mode,bots in accounts.items():value_step(bots,s,row,ts,seq,marks,g,combo=mode=='combo')
        # Actual last observed continuous minute; carry forward only for marks,
        # never synthesize a signal or fill into a missing minute/session.
        for s,groups in daily.items():
            raw=groups.get(key)
            if raw is not None:marks[s]=float(raw.close.iloc[-1])
        for mode,bots in accounts.items():
            values=snapshot(bots,marks)
            for bot,b in values.items():curves[mode][bot].append(dict(date=key,nav=b['nav'],bot=b['return_pct'],index=round((float(benchmark.loc[date])/float(benchmark.loc[dates[0]])-1)*100,2)))
            for b in bots.values():b['pending'].clear()
        if seq%25==0 or seq==len(dates)-1:
            write(checkpoint,dict(code_hash=code_hash,seq=seq,accounts=accounts,curves=curves,marks=marks))
            print('Two value bots, minute + combo:',seq+1,'/747 sessions',flush=True)
    results={}
    for mode,bots in accounts.items():
        result=snapshot(bots,marks)
        for bot,b in result.items():
            for t in bots[bot]['trades']:
                age=(pd.Timestamp(t['time'])-pd.Timestamp(t['signal_time'])).total_seconds()
                if not 60<=age<=180 or pd.Timestamp(t['submitted_at'])>pd.Timestamp(t['time']):raise ValueError('Noncausal fill')
                if t['side']=='MUA' and not t['financial_available_at']<=t['quality_asof']<t['date']:raise ValueError('Future annual financials')
            curve=curves[mode][bot];navs=np.array([100_000_000]+[r['nav'] for r in curve])
            b.update(max_drawdown_pct=round(float((navs/np.maximum.accumulate(navs)-1).min()*100),2),benchmark_return_pct=curve[-1]['index'],curve=curve,actions=[],rules_revision=REVISION,sector_stats=aggregate_trades(bots[bot]['trades'],classification,symbols))
            b.pop('history');b.pop('orders_next');b.pop('observed_history_points',None)
            write(ROOT/'data/value_fundamentals'/f'{mode}-trades-{bot}.json',bots[bot]['trades'])
            print(mode,bot,b['return_pct'],b['max_drawdown_pct'],b['buy_count']+b['closed_trades'],flush=True)
        results['minute_backtests' if mode=='minute' else 'hybrid_backtests']=result
    # Preserve the independently published daily results/paper books byte values.
    public=read(ROOT/'site/value-investing.json');public.update(results,traders=PROFILES)
    public['intraday_backtest_audit']=dict(revision=REVISION,generated_at=datetime.now(VN).isoformat(),first=str(dates[0].date()),last=str(dates[-1].date()),sessions=len(dates),requested_symbols=146,quality_eligible_symbols_ever=len(needed),minute_source='Vietcap observed ONE_MINUTE; same 146 input hashes as original verified study',input_sha256=hashes,engine_sha256=code_hash,fundamentals_sha256=hashlib.sha256((ROOT/'config/value-fundamentals.json').read_bytes()).hexdigest(),financial_timing='Annual quality available by prior benchmark session EOD; revisions withheld until actual update/publication + 1 day',gaps='No interpolation; next observed fill only 60–180 seconds after signal; requests expire across sessions',valuation='Last observed continuous minute; carries only for NAV when no new observation',scope='Minute uses annual quality + minute price/volume only. Combo adds prior-day MA200/price and liquidity; both are experimental adaptations, not actual Buffett/Munger methods.')
    public['intraday_policy']=dict(revision=REVISION,minute_entry={'Buffett':'Close ≤ 0.998×MA20 and > prior close, volume ≥0.8×prior20 mean','Munger':'MA20 ≤ close ≤1.005×MA20, close >MA10, volume ≥prior20 mean'},minute_exit={'Buffett':'Close <0.985×MA20 or <0.925×entry, or annual quality fails','Munger':'Close <0.99×MA20 or <0.94×entry, or annual quality fails'},warmup=30,price_floor=5000,max_gap_seconds=180,minimum_hold_sessions=5,cooldown_sessions=7,positions={'Buffett':6,'Munger':4},sizing='NAV/max_positions, 100-share lots, at most 5% of preceding minute volume; same fees/tax/slippage model; no ATR sizing in these two adaptations',combo='Same minute entries/exits, additionally prior completed session close ≤ daily price_anchor×MA200 and trailing20 turnover ≥3bn VND; no current-day closing data')
    write(ROOT/'site/value-investing.json',public)

if __name__=='__main__':run()
