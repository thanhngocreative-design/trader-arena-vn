"""Verified, effective-date VN30 universe; reuses the canonical strict engines."""
import argparse,hashlib,json
from datetime import datetime
from functools import lru_cache
import pandas as pd
from value_investing import ROOT,VN,read,write,POLICY,eligible_companies,quality
from engine import Settings,TRADERS,backtest
from fast_engine import CORE,build_hybrid_signals
from pit_context import PITContext
from pit_universe import load_daily
from pit_minute_data import load_minutes
from pit_daily import merged_fundamentals,value_backtest,attach_summary
from pit_intraday import run_minute,run_combo
from sector_analytics import universe_distribution
from replay_rules import REVISION,can_fill

CONFIG=ROOT/'config/research-vn30.json'
OUTPUT=ROOT/'data/pit_results/vn30-v1'
BOTS=list(TRADERS)+list(POLICY)

def membership_digest(data=None):
    """Hash the exact membership content consistently across Git line endings."""
    return hashlib.sha256(json.dumps(read(CONFIG) if data is None else data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf8')).hexdigest()

def configuration():
    cfg=read(CONFIG);rows=cfg['months']
    if not rows or rows!=sorted(rows,key=lambda r:r['effective']):raise ValueError('Unordered VN30 events')
    for i,row in enumerate(rows):
        if len(row['members'])!=30 or len(set(row['members']))!=30:raise ValueError('VN30 must have 30 distinct members')
        if row['asof']>=row['effective'] or not row['source_url']:raise ValueError('Unverified or future VN30 notice')
        if i and rows[i-1]['effective']>=row['effective']:raise ValueError('Duplicate VN30 date')
    return cfg

def membership(cfg,day):
    known=[r for r in cfg['months'] if r['effective']<=str(day)[:10]]
    if not known:raise ValueError('VN30 membership unavailable for '+str(day))
    return set(known[-1]['members'])

def context(prices,benchmark,cfg):
    # Legal index membership, not monthly300's retrospective full-frame count.
    ctx=PITContext(prices,benchmark,cfg['months'],Settings(portfolio_policy='atr_v1'),min_history=1)
    if set(cfg['training_symbols'])-set(ctx.symbols):raise ValueError('Missing real VN30 daily history')
    return ctx

def audit_fills(cfg,prices,frames,benchmark,output=OUTPUT,cohort='vn30'):
    dates=list(benchmark.index);indices={str(d.date()):i for i,d in enumerate(dates)};counts={}
    previous={str(dates[i].date()):str(dates[i-1].date()) for i in range(1,len(dates))}
    for mode in ('daily','minute','combo'):
        for bot in BOTS:
            prefix='value_combo' if mode=='combo' and bot in POLICY else mode
            trades=read(output/f'{prefix}-{cohort}-{bot}-trades.json');inventory={};count=0
            for t in trades:
                s=t['symbol'];day=t['date'];ts=pd.Timestamp(day if mode=='daily' else t['time']);f=prices[s] if mode=='daily' else frames[s]
                if ts not in f.index:raise ValueError('VN30 fill without actual bar')
                bar=f.loc[ts]
                if bar.volume<=0 or abs(float(t['price'])-float(bar.open))>float(bar.open)*.0125+1.1:raise ValueError('Invalid VN30 fill price or volume')
                if t['qty']<=0 or t['qty']%100:raise ValueError('Invalid lot')
                if mode=='daily':
                    if t['signal_date']!=previous[day]:raise ValueError('Daily lookahead')
                elif not can_fill(t['signal_time'],t['time'],t.get('submitted_at')):raise ValueError('Invalid exact-next-minute fill')
                qty,buy_date=inventory.get(s,(0,None))
                if t['side']=='MUA':
                    if qty or s not in membership(cfg,day):raise ValueError('VN30 buy outside effective membership')
                    if bot in POLICY and not t['financial_available_at']<=t.get('quality_asof',t.get('signal_date'))<day:raise ValueError('Future annual report')
                    inventory[s]=(t['qty'],day)
                else:
                    if t['qty']>qty or indices[day]-indices[buy_date]<5:raise ValueError('Unsettled/unowned sale')
                    inventory[s]=(qty-t['qty'],buy_date)
                count+=1
            counts[mode+':'+bot]=count
    return counts

def daily(ctx,prices,cfg,classification,output=OUTPUT,options=None):
    reports=eligible_companies(merged_fundamentals(),classification)
    training={b:backtest(prices,ctx.benchmark,b,'2022-01-03',end_date=cfg['end'],settings=ctx.settings,features_cache=ctx)['curve'] for b in CORE}
    build_hybrid_signals(ctx,training);results={}
    for option in options or read(ROOT/'site/research-146.json')['backtest_options']:
        books={}
        for bot in BOTS:
            r=backtest(prices,ctx.benchmark,bot,option['start'],end_date=option['end'],settings=ctx.settings,features_cache=ctx) if bot in TRADERS else value_backtest(ctx,bot,option['start'],option['end'],reports)
            books[bot]=attach_summary(r,classification,set(cfg['eligible_symbols']))
            if option['key']=='ALL':write(output/f'daily-vn30-{bot}-trades.json',json.loads(r['trades'].to_json(orient='records',date_format='iso')))
        results[option['key']]=books;print('VN30 daily complete',option['key'],flush=True)
    result=dict(backtests=results['ALL'],backtest_periods=results);write(output/'daily-vn30.json',result);return result

def run():
    cfg=configuration();prices,_,hashes=load_daily();prices={s:prices[s] for s in cfg['training_symbols']}
    cfg['daily_input_sha256']={s:hashes[s] for s in prices}
    raw=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv');raw.date=pd.to_datetime(raw.date);benchmark=raw.set_index('date');benchmark[['open','high','low','close']]*=1000
    ctx=context(prices,benchmark,cfg);OUTPUT.mkdir(parents=True,exist_ok=True)
    signature=hashlib.sha256(CONFIG.read_bytes()+json.dumps(cfg['daily_input_sha256'],sort_keys=True).encode()+b''.join((ROOT/f).read_bytes() for f in ('vn30.py','pit_daily.py','pit_context.py','engine.py','fast_engine.py'))).hexdigest()
    manifest=OUTPUT/'daily-inputs.json'
    if manifest.exists() and read(manifest)['signature']!=signature:raise ValueError('Changed VN30 inputs; use a new output directory')
    write(manifest,dict(signature=signature));classification=read(ROOT/'config/market-classification.json')
    day=read(OUTPUT/'daily-vn30.json') if (OUTPUT/'daily-vn30.json').exists() else daily(ctx,prices,cfg,classification['sectors'])
    frames,coverage=load_minutes(cfg['eligible_symbols']);cfg['minute_input_sha256']=coverage
    run_minute({'vn30':ctx},frames,coverage,cfg,OUTPUT);run_combo({'vn30':ctx},prices,frames,cfg,OUTPUT)
    counts=audit_fills(cfg,prices,frames,benchmark)
    minute=read(OUTPUT/'minute-vn30.json');current=sorted(membership(cfg,cfg['end']))
    cohort=dict(day,minute_backtests=minute['minute'],hybrid_backtests={**read(OUTPUT/'combo-vn30.json'),**minute['value_combo']},universe=current,universe_union=cfg['eligible_symbols'])
    bundle=merged_fundamentals();reports=eligible_companies(bundle,classification['sectors'])
    first_members=membership(cfg,cfg['first_session'])
    cohort['fundamentals']=dict(source=bundle['source'],asof=bundle['asof'],requested_symbols=len(cfg['eligible_symbols']),comparable_nonfinancial_companies=sum(s in reports for s in cfg['eligible_symbols']))
    cohort['value_audit']={b:dict(quality_eligible_start=sum(quality(rs,pd.Timestamp(cfg['first_session']),b) is not None for s,rs in reports.items() if s in first_members),quality_eligible_end=sum(quality(rs,pd.Timestamp(cfg['end']),b) is not None for s,rs in reports.items() if s in current)) for b in POLICY}
    for k in ('backtests','minute_backtests','hybrid_backtests'):
        if set(cohort[k])!=set(BOTS):raise ValueError('Incomplete VN30 book')
    dates=benchmark.index[(benchmark.index>=cfg['start'])&(benchmark.index<=cfg['end'])];member_days=[]
    for d in dates:
        for s in membership(cfg,d.date()):
            key=str(d.date());has_daily=d in prices[s].index;bars=frames[s].loc[key:key+' 23:59']
            member_days.append((has_daily,len(bars)>0,key in coverage[s].get('price_mismatch_sessions',[])))
    audit=dict(symbols=len(cfg['eligible_symbols']),symbols_with_minutes=sum(len(frames[s])>0 for s in cfg['eligible_symbols']),member_days=len(member_days),member_days_with_daily=sum(r[0] for r in member_days),member_days_with_minutes=sum(r[1] for r in member_days),member_days_daily_without_minutes=sum(r[0] and not r[1] for r in member_days),member_days_quarantined=sum(r[2] for r in member_days),quality_by_symbol=coverage,no_interpolation=True)
    public=dict(revision=cfg['revision'],execution_revision=REVISION,status='complete',mode='real_market_data',generated_at=datetime.now(VN).isoformat(),start=cfg['start'],first_session=cfg['first_session'],end=cfg['end'],verified_through=cfg['verified_through'],sessions=len(dates),target=30,unique_symbols=len(cfg['eligible_symbols']),months=cfg['months'],cohort=cohort,sector_universe=universe_distribution(current,classification),minute_audit=audit,execution_audit=dict(status='all_fills_verified_against_real_bars',fills_by_book=counts,total_fills=sum(counts.values())),membership_sha256=membership_digest(),limitations=cfg['limitations'])
    write(ROOT/'site/research-vn30.json',public);print('Published VN30: 39 verified backtest accounts', {k:v for k,v in audit.items() if k!='quality_by_symbol'},flush=True)
    return public

if __name__=='__main__':run()
