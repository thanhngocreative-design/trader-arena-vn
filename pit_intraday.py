"""Same actual tape for monthly300 and fixed146 controls; no paper ledger writes."""
import argparse,copy,hashlib,json
import numpy as np
import pandas as pd
from engine import TRADERS,Settings,backtest
from fast_engine import CORE,build_hybrid_signals
from minute_arena import new_accounts,step,snapshot,exit_signal
from hybrid_backtest import _walk_one
from value_investing import ROOT,POLICY,quality,eligible_companies,read,write
from value_intraday import empty_accounts,value_step
from pit_universe import load_daily
from pit_context import PITContext
from pit_daily import merged_fundamentals,attach_summary
from pit_minute_data import load_minutes,wide_features
from sector_analytics import aggregate_trades

def contexts():
    config=read(ROOT/'config/research-300.json');prices,_,_=load_daily();original=read(ROOT/'config/research-universe.json')['eligible_symbols']
    raw=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv');raw['date']=pd.to_datetime(raw.date);benchmark=raw.set_index('date');benchmark[['open','high','low','close']]*=1000
    prices={s:prices[s] for s in sorted(set(config['training_symbols'])|set(original)) if s in prices}
    ctx=PITContext(prices,benchmark,config['months'],Settings(portfolio_policy='atr_v1'))
    control=copy.copy(ctx);control.static=set(original);control.allowed=np.zeros_like(ctx.allowed)
    for s in original:
        if s in control.pos:control.allowed[control.pos[s],:]=True
    control.buy={k:v.copy() for k,v in ctx.buy.items()};control.hybrid_winners={};control.hybrid_asof={}
    return {'300':ctx,'146':control},prices,config

def run_minute(ctxs,frames,coverage,config,output=None,*,initial_state=None,bot_ids=None):
    output=output or ROOT/'data/pit_results'
    output.mkdir(parents=True,exist_ok=True)
    ctx=next(iter(ctxs.values()));dates=ctx.dates[(ctx.dates>=config['start'])&(ctx.dates<=config['end'])]
    positions_in_calendar={str(d.date()):int(ctx.dates.get_loc(d)) for d in dates}
    daily={}
    for s,f in frames.items():
        if f.empty:daily[s]={};continue
        labels=f.index.normalize().to_numpy();unique,starts=np.unique(labels,return_index=True);ends=np.r_[starts[1:],len(f)]
        daily[s]={str(pd.Timestamp(d).date()):(int(a),int(b)) for d,a,b in zip(unique,starts,ends)}
    bundle=merged_fundamentals();classification=read(ROOT/'config/market-classification.json')['sectors'];reports=eligible_companies(bundle,classification)
    quality_cache={}
    def annual(s,bot,date):
        rs=reports.get(s,[]);known=tuple(i for i,r in enumerate(rs) if r['available_at']<=str(date.date()))
        key=(s,bot,date.year,known)
        if key not in quality_cache:quality_cache[key]=quality(rs,date,bot)
        return quality_cache[key]
    accounts={c:{'minute':{**new_accounts(),**empty_accounts()},'value_combo':empty_accounts()} for c in ctxs}
    if bot_ids is not None:
        accounts={c:{m:{k:b for k,b in bots.items() if k in bot_ids} for m,bots in books.items()} for c,books in accounts.items()}
    curves={c:{m:{k:[] for k in b} for m,b in books.items()} for c,books in accounts.items()};marks={};seen={};done=-1
    signature=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in ('pit_intraday.py','pit_minute_data.py','minute_arena.py','value_intraday.py','pit_context.py','replay_rules.py','engine.py','education_bots.py','portfolio.py','execution.py'))+ctx.benchmark.close.to_csv(lineterminator='\n').encode()+json.dumps(config,sort_keys=True).encode()+json.dumps({s:r.get('minute_sha256') for s,r in coverage.items()},sort_keys=True).encode()).hexdigest()
    checkpoint=output/'minute-checkpoint.json'
    if initial_state is not None:
        saved=copy.deepcopy(initial_state)
        prefix=[str(d.date()) for d in dates[:saved['seq']+1]]
        if set(saved['accounts'])!=set(ctxs):raise ValueError('Minute resume cohorts changed')
        for books in saved['curves'].values():
            for bots in books.values():
                for curve in bots.values():
                    if [r['date'] for r in curve]!=prefix:raise ValueError('Minute resume calendar changed')
        accounts=saved['accounts'];curves=saved['curves'];marks=saved['marks'];seen=saved['seen'];done=saved['seq']
        if done>len(dates)-1:raise ValueError('Minute checkpoint is ahead of the requested session')
        if done==len(dates)-1:
            # Restoring a complete, validated checkpoint is idempotent: export
            # its existing books without processing or duplicating any candle.
            write(checkpoint,dict(signature=signature,seq=done,accounts=accounts,curves=curves,marks=marks,seen=seen))
    elif checkpoint.exists():
        saved=read(checkpoint)
        if saved['signature']==signature:accounts=saved['accounts'];curves=saved['curves'];marks=saved['marks'];seen=saved['seen'];done=saved['seq'];print('Resume PIT tape after',done+1,flush=True)
    core_views={c:{k:b for k,b in books['minute'].items() if k in TRADERS} for c,books in accounts.items()}
    value_views={c:{k:b for k,b in books['minute'].items() if k in POLICY} for c,books in accounts.items()}
    no_entry={k:False for k in TRADERS}
    for seq,date in enumerate(dates):
        if seq<=done:continue
        key=str(date.date());t=positions_in_calendar[key];prev=t-1;prior_date=ctx.dates[prev]
        members={c:{s for s,i in x.pos.items() if x.allowed[i,t]} for c,x in ctxs.items()}
        held={s for books in accounts.values() for bots in books.values() for b in bots.values() for s in b['positions']}
        active=set.union(*members.values())|held
        raw={s:frames[s].iloc[slice(*daily[s][key])] for s in sorted(active) if s in daily and key in daily[s]}
        symbols,arrays=wide_features(raw);events=[]
        keys=list(TRADERS)+list(POLICY)
        any_signal=np.logical_or.reduce([arrays[k] for k in keys])
        for j,s in enumerate(symbols):
            signals=any_signal[:len(raw[s]),j]
            selected=np.ones(len(signals),dtype=bool) if s in held else np.maximum.accumulate(signals)
            events.extend((raw[s].index[i],s,j,int(i)) for i in np.flatnonzero(selected))
        gates={k:{} for k in POLICY}
        for s in active:
            if s not in ctx.pos:continue
            i=ctx.pos[s]
            for bot in POLICY:
                q=annual(s,bot,prior_date)
                if not q:continue
                c=ctx.a['close'][i,prev];ma=ctx.a['sma200'][i,prev];adv,_=ctx.execution_liquidity(i,prev)
                gates[bot][s]=dict(q,asof=str(prior_date.date()),combo=bool(c>=5000 and c<=ma*POLICY[bot]['price_anchor'] and adv>=3_000_000_000))
        def conservative_nav(bot,book,actual_marks):
            return book['cash']+sum(p['qty']*actual_marks.get(s,p['price'])*(0. if seq-seen.get(s,seq)>=20 else 1.) for s,p in book['positions'].items())
        watched=set(held)
        for ts,s,j,i in sorted(events,key=lambda e:(e[0],e[1])):
            marks[s]=float(arrays['close'][i,j]);seen[s]=seq
            # With no position, pending order or signal anywhere, this candle
            # can only update its observed quote. Preserve that quote while
            # avoiding repeated scans of every inactive account.
            if s not in watched and not any_signal[i,j]:continue
            row={k:float(v[i,j]) if k not in keys else bool(v[i,j]) for k,v in arrays.items() if k!='seconds'}
            interested=False
            for cohort,books in accounts.items():
                member=s in members[cohort]
                core=core_views[cohort];values=value_views[cohort]
                if not member and not any(s in b['positions'] or s in b['pending'] for b in books['minute'].values()) and not any(s in b['positions'] or s in b['pending'] for b in books['value_combo'].values()):continue
                interested=step(core,s,row,ts,seq,marks,entry_gates=None if member else no_entry,exit_rule=lambda k,r,p:(not member) or exit_signal(k,r,p),nav_calculator=conservative_nav) or interested
                use_gates=gates if member else {}
                if any(s in use_gates.get(k,{}) or s in b['positions'] or s in b['pending'] for k,b in values.items()):
                    value_step(values,s,row,ts,seq,marks,use_gates,nav_calculator=conservative_nav)
                if any(s in use_gates.get(k,{}) or s in b['positions'] or s in b['pending'] for k,b in books['value_combo'].items()):
                    value_step(books['value_combo'],s,row,ts,seq,marks,use_gates,combo=True,nav_calculator=conservative_nav)
                interested=interested or any(s in b['positions'] or s in b['pending'] for bots in (values,books['value_combo']) for b in bots.values())
            if interested:watched.add(s)
            else:watched.discard(s)
        for s,f in raw.items():
            if len(f):marks[s]=float(f.close.iloc[-1]);seen[s]=seq
        for cohort,books in accounts.items():
            for mode,bots in books.items():
                result=snapshot(bots,marks)
                for bot,b in result.items():
                    reserve=sum(p['qty']*marks.get(s,p['price']) for s,p in bots[bot]['positions'].items() if seq-seen.get(s,seq)>=20)
                    nav=conservative_nav(bot,bots[bot],marks)
                    curves[cohort][mode][bot].append(dict(date=key,nav=round(nav),bot=round((nav/100_000_000-1)*100,4),index=round((float(ctx.benchmark.close.loc[date])/float(ctx.benchmark.close.loc[dates[0]])-1)*100,2),valuation_reserve=round(reserve)))
                    bots[bot]['pending'].clear()
        if seq%25==0 or seq==len(dates)-1:
            write(checkpoint,dict(signature=signature,seq=seq,accounts=accounts,curves=curves,marks=marks,seen=seen))
            print('Shared PIT minute tape:',seq+1,'/',len(dates),'sessions;',list(ctxs),flush=True)
    for cohort,books in accounts.items():
        out={}
        for mode,bots in books.items():
            result=snapshot(bots,marks)
            for bot,b in result.items():
                curve=curves[cohort][mode][bot];navs=np.array([100_000_000]+[r['nav'] for r in curve]);last=curve[-1];reserve=np.array([r['valuation_reserve'] for r in curve]);unreserved=np.array([r['nav'] for r in curve])+reserve
                for h in b['holdings']:
                    age=len(dates)-1-seen.get(h['symbol'],len(dates)-1);h['quote_age_sessions']=age;h['quote_date']=str(dates[seen[h['symbol']]].date()) if h['symbol'] in seen else None
                    if age>=20:
                        p=bots[bot]['positions'][h['symbol']];h.update(value=0,pnl=round(-p['cost']),pnl_pct=-100.,valuation_reserve=round(h['qty']*marks.get(h['symbol'],p['price'])),valuation_note='Dự phòng định giá; không phải giá thị trường 0 hoặc lệnh bán')
                b.update(nav=last['nav'],return_pct=round(last['bot'],2),max_drawdown_pct=round(float((navs/np.maximum.accumulate(navs)-1).min()*100),2),benchmark_return_pct=last['index'],curve=[curve[i] for i in sorted(set(round(i*(len(curve)-1)/89) for i in range(90)))],actions=[],sector_stats=aggregate_trades(bots[bot]['trades'],classification,set(ctx.symbols)),valuation_audit=dict(final_reserve=int(reserve[-1]),maximum_reserve=int(reserve.max()),sessions_with_reserve=int((reserve>0).sum()),nav_last_quote_convention=round(unreserved[-1]),return_last_quote_pct=round((unreserved[-1]/100_000_000-1)*100,2)))
                b.pop('history');b.pop('orders_next');b.pop('observed_history_points',None)
                write(output/f'{mode}-{cohort}-{bot}-trades.json',bots[bot]['trades'])
            out[mode]=result
        write(output/f'minute-{cohort}.json',out)

def run_combo(ctxs,prices,frames,config,output=None):
    output=output or ROOT/'data/pit_results'
    output.mkdir(parents=True,exist_ok=True)
    classification=read(ROOT/'config/market-classification.json')['sectors']
    coverage=config.get('minute_input_sha256')
    if coverage is None:coverage=read(ROOT/'data/pit_results/minute-coverage.json')
    signature=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in ('fast_engine.py','hybrid_backtest.py','pit_context.py','replay_rules.py','engine.py','education_bots.py','portfolio.py','execution.py'))+next(iter(ctxs.values())).benchmark.close.to_csv(lineterminator='\n').encode()+json.dumps({k:config[k] for k in ('months','start','end','daily_input_sha256')},sort_keys=True).encode()+json.dumps(coverage,sort_keys=True).encode()).hexdigest()
    for name,ctx in ctxs.items():
        manifest=output/f'combo-{name}-inputs.json'
        if manifest.exists() and read(manifest)['signature']!=signature:raise ValueError('Combo cache inputs changed; recompute in a fresh output directory')
        write(manifest,dict(signature=signature))
        training={k:backtest(prices,ctx.benchmark,k,'2022-01-03',end_date=config['end'],settings=ctx.settings,features_cache=ctx)['curve'] for k in CORE}
        build_hybrid_signals(ctx,training);first=ctx.dates.searchsorted(config['start']);last=ctx.dates.searchsorted(config['end'],side='right')-1
        result={}
        for bot in TRADERS:
            path=output/f'combo-{name}-{bot}.json'
            if path.exists():result[bot]=read(path);continue
            r=_walk_one(ctx,bot,frames,first,last,ctx.settings);result[bot]=attach_summary(r,classification,set(ctx.symbols))
            if output!=ROOT/'data/pit_results':result[bot]['history']=[dict(date=str(d.date()),nav=round(float(row.nav))) for d,row in r['curve'].iterrows()]
            write(path,result[bot]);write(output/f'combo-{name}-{bot}-trades.json',r['trades'].astype(object).where(pd.notna(r['trades']),None).to_dict('records'))
            print('PIT combo complete',name,bot,result[bot]['return_pct'],flush=True)
        write(output/f'combo-{name}.json',result)

def run(stage,cohort=None):
    ctxs,prices,config=contexts();frames,coverage=load_minutes()
    if cohort:ctxs={cohort:ctxs[cohort]}
    if stage in ('minute','all'):run_minute(ctxs,frames,coverage,config)
    if stage in ('combo','all'):run_combo(ctxs,prices,frames,config)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['minute','combo','all'],default='all');p.add_argument('--cohort',choices=['300','146']);a=p.parse_args();run(a.stage,a.cohort)
