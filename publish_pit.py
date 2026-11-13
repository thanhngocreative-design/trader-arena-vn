"""Publish only a complete real-data study; never replaces any paper ledger."""
import hashlib
from functools import lru_cache
from datetime import datetime
import pandas as pd
from value_investing import ROOT,VN,POLICY,quality,eligible_companies,read,write
from pit_daily import merged_fundamentals
from pit_universe import load_daily
from sector_analytics import universe_distribution

def audit_fills(cfg,prices,dates,baseline):
    """Check ALL ledgers, not merely the forty recent public rows."""
    @lru_cache(maxsize=4)
    def minute(symbol):return pd.read_pickle(ROOT/'data/pit_results/minute-normalized'/f'{symbol}.pkl')
    result={};date_pos={str(d.date()):i for i,d in enumerate(dates)}
    def member(s,date,cohort):
        if cohort=='146':return s in baseline
        rows=[r for r in cfg['months'] if r['effective']<=date]
        return bool(rows and s in rows[-1]['members'])
    for cohort in ('300','146'):
        for mode in ('daily','minute','combo'):
            for bot in ('Minervini','ONeil','Darvas','BNF','CIS','Qullamaggie','Unger','ThaiPham','DuongChung','PThai','Hybrid','Buffett','Munger'):
                prefix='value_combo' if mode=='combo' and bot in POLICY else mode
                path=ROOT/'data/pit_results'/f'{prefix}-{cohort}-{bot}-trades.json'
                trades=read(path);inventory={};count=0
                grouped={s:[t for t in trades if t['symbol']==s] for s in {t['symbol'] for t in trades}}
                for s,rows in grouped.items():
                    observed=prices[s] if mode=='daily' else minute(s)
                    qty=0;buy_date=None
                    for t in rows:
                        timestamp=pd.Timestamp(t['date'] if mode=='daily' else t['time'])
                        if timestamp not in observed.index:raise ValueError(f'Fill without observed source: {cohort} {mode} {bot} {s} {timestamp}')
                        actual=observed.loc[timestamp]
                        if actual.volume<=0 or abs(float(t['price'])-float(actual.open))>float(actual.open)*.0125+1.1:raise ValueError('Nontrading volume or unexplained fill price')
                        if t['qty']<=0 or t['qty']%100:raise ValueError('Invalid share lot')
                        if mode=='daily':
                            if not t['signal_date']<t['date']:raise ValueError('Same/future daily signal')
                        else:
                            age=(timestamp-pd.Timestamp(t['signal_time'])).total_seconds()
                            if not 60<=age<=180:raise ValueError('Noncausal minute execution')
                        if t['side']=='MUA':
                            if qty or not member(s,t['date'],cohort):raise ValueError('Entry outside known monthly universe or duplicate holding')
                            if bot in POLICY:
                                known=t.get('quality_asof',t.get('signal_date'))
                                if not t['financial_available_at']<=known<t['date']:raise ValueError('Future annual figures')
                            qty=t['qty'];buy_date=t['date']
                        else:
                            if t['qty']>qty or date_pos[t['date']]-date_pos[buy_date]<5:raise ValueError('Unowned or unsettled sale')
                            qty-=t['qty']
                        count+=1
                result[f'{cohort}:{mode}:{bot}']=count
    return result

def publish():
    cfg=read(ROOT/'config/research-300.json');classification=read(ROOT/'config/market-classification.json');coverage=read(ROOT/'data/pit_results/minute-coverage.json');prices,audit,_=load_daily()
    baseline=read(ROOT/'config/research-universe.json')['eligible_symbols'];bundle=merged_fundamentals();reports=eligible_companies(bundle,classification['sectors'])
    months=[r for r in cfg['months'] if r['effective']>='2023-11-01'];cohorts={};sector_universes={}
    dates=pd.DatetimeIndex(pd.to_datetime(pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv').date));dates=dates[(dates>=cfg['start'])&(dates<=cfg['end'])]
    execution_audit=audit_fills(cfg,prices,dates,baseline)
    for name,selected in [('300',cfg['eligible_symbols']),('146',baseline)]:
        day=read(ROOT/'data/pit_results'/f'daily-{name}.json');minute=read(ROOT/'data/pit_results'/f'minute-{name}.json');combo=read(ROOT/'data/pit_results'/f'combo-{name}.json')
        current=months[-1]['members'] if name=='300' else baseline
        first_members=months[0]['members'] if name=='300' else baseline
        data=dict(day,minute_backtests=minute['minute'],hybrid_backtests={**combo,**minute['value_combo']},universe=current,universe_union=selected,
            value_audit={b:dict(quality_eligible_start=sum(quality(rs,dates[0],b) is not None for s,rs in reports.items() if s in first_members),quality_eligible_end=sum(quality(rs,dates[-1],b) is not None for s,rs in reports.items() if s in current)) for b in POLICY},
            fundamentals=dict(source=bundle['source'],asof=bundle['asof'],requested_symbols=len(selected),comparable_nonfinancial_companies=sum(s in reports for s in selected)))
        for key in ('backtests','minute_backtests','hybrid_backtests'):
            if len(data[key])!=13:raise ValueError('Incomplete cohort '+name+' '+key)
            for b,r in data[key].items():
                if r['sector_stats']['buy_fills']!=r['buy_count'] or r['sector_stats']['sell_fills']!=r['closed_trades']:raise ValueError('Unreconciled full ledger '+b)
        cohorts[name]=data;sector_universes[name]=universe_distribution(current,classification)
    members={};ordered=months
    for date in dates:
        row=[r for r in ordered if r['effective']<=str(date.date())][-1];members[str(date.date())]=row['members']
    positive_daily=0;no_minute=0;mismatch=0
    absent={s:set(r.get('missing_minute_with_daily',[])) for s,r in coverage.items()};bad={s:set(r.get('price_mismatch_sessions',[])) for s,r in coverage.items()}
    for date in dates:
        key=str(date.date())
        for s in members[key]:
            if date in prices[s].index:positive_daily+=1;no_minute+=key in absent[s]
            mismatch+=key in bad[s]
    public=dict(revision='monthly300_study_v1',mode='real_market_data',status='complete',generated_at=datetime.now(VN).isoformat(),start=cfg['start'],first_session=cfg['first_session'],end=cfg['end'],sessions=len(dates),target=300,monthly_reconstitution=True,
        months=[{k:r[k] for k in ('month','effective','asof','eligible_count','members')} for r in months],union_symbols=cfg['eligible_symbols'],unique_symbols=len(cfg['eligible_symbols']),retained_delisted_in_research=cfg['retained_delisted_in_research'],catalog_candidates=cfg['catalog_candidates'],catalog_retained_delisted=cfg['catalog_retained_delisted'],candidate_status_counts=cfg['candidate_status_counts'],selection_policy=cfg['policy'],source_catalog_asof=cfg['source_catalog_asof'],
        cohorts=cohorts,sector_universes=sector_universes,execution_audit=dict(status='all_fills_verified_against_real_bars',fills_by_book=execution_audit,total_fills=sum(execution_audit.values()),checks='Every buy in known membership; every fill on positive-volume observed bar, modeled slippage bounded; next-bar timing, 100-share lots, 5-session sale guard, financial publication timing; no synthetic delisting sales'),classification_asof=classification['asof'],fundamentals_source_sha256=hashlib.sha256((ROOT/'data/pit_results/fundamentals.json').read_bytes()).hexdigest(),
        minute_audit=dict(source='Vietcap real ONE_MINUTE, observed positive-volume common continuous sessions only',quality_by_symbol=coverage,input_symbols_including_control=len(coverage),research_symbols_with_bars=sum(coverage[s].get('bars',0)>0 for s in cfg['eligible_symbols']),member_days=len(dates)*300,member_days_with_positive_daily=positive_daily,member_days_no_positive_daily=len(dates)*300-positive_daily,member_days_daily_but_no_verified_continuous_minute=no_minute,member_days_price_mismatch_quarantined=mismatch,raw_bars=sum(r.get('raw_bars',0) for r in coverage.values()),normalized_bars=sum(r.get('bars',0) for r in coverage.values()),no_in_window_trades_consistent_daily=[s for s,r in coverage.items() if r['status']=='no_in_window_trades_consistent_daily'],no_interpolation=True),
        frozen_146_snapshot_sha256=hashlib.sha256((ROOT/'site/research-146.json').read_bytes()).hexdigest(),limitations=cfg['limitations']+[
            '497 selected tickers have in-window minute bars; SJF has no in-window positive-volume daily/minute observations and remains selected in its ex-ante month. This is not replaced with another survivor.',
            'The 146 control is rerun on the same current daily/minute source, volume guards, membership-exit and stale-valuation conventions, so differences are not attributed solely to the sample by comparing unlike engines. Original 146 snapshots remain separately available.',
            'No candle/trade/exit is invented when quotes disappear. After20 market sessions without quotes, the conservative NAV reserves100% of stale exposure; last-observed-price NAV is also disclosed. A reserve is not an observed zero price, actual sale or assertion of total economic loss.',
            'Annual fundamentals are current provider versions withheld until actual publication/update+1day, not original vintages. Missing or non-comparable statements exclude only the two value-model screens; no financial values are fabricated.',
            'Paper seasons and accounts retain their existing forward-only universe/history. This study changes historical backtests, not past paper trades.'
        ])
    for symbol in sorted(set(cfg['eligible_symbols'])|set(baseline)):
        f=prices[symbol].loc[:cfg['end']].tail(780)
        bars=[[str(d.date())]+[float(row[k]) for k in ('open','high','low','close','volume')] for d,row in f.iterrows()]
        write(ROOT/'site/pit-stocks'/f'{symbol}.json',bars)
    write(ROOT/'site/research-300.json',public)
    print('Published full study: two cohorts ×13 bots ×3 backtest books; paper untouched',flush=True)

if __name__=='__main__':publish()
