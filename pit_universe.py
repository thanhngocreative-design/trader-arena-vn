"""Monthly top-300 by PREVIOUS known liquidity, including retained dead stocks.

This reduces the ex-post survivor filter. The provider's current+retained ticker
catalog is not a complete historical security master; residual coverage bias is
explicit. Never select on future returns, last-date survival or minute coverage.
"""
import hashlib,json
from pathlib import Path
import pandas as pd
from collect_pit_daily import valid_rows
from value_investing import ROOT,read,write,VN
from datetime import datetime

def monthly_memberships(prices,calendar,first='2022-01-01',last='2026-11-12',count=300):
    months=pd.period_range(first,last,freq='M');result=[]
    for month in months:
        effective=calendar[(calendar>=month.start_time)&(calendar<=month.end_time)]
        if not len(effective):continue
        cutoff=calendar[calendar<effective[0]]
        if not len(cutoff):continue
        cutoff=cutoff[-1];window=calendar[calendar<=cutoff][-60:];recent=calendar[calendar<=cutoff][-5:]
        ranking=[]
        for symbol,f in prices.items():
            known=f.loc[:cutoff]
            if len(known)<252 or not len(known.index.intersection(recent)):continue
            observed=known.loc[known.index.intersection(window)]
            if len(observed)<40:continue
            # Missing sessions add no observed turnover to the fixed 60-session
            # denominator. No candle, price or trade is synthesized.
            adv=float((observed.close*observed.volume).sum()/len(window))
            ranking.append((adv,symbol,len(observed),str(known.index[-1].date())))
        ranking.sort(key=lambda r:(-r[0],r[1]))
        result.append(dict(month=str(month),effective=str(effective[0].date()),asof=str(cutoff.date()),eligible_count=len(ranking),members=[s for _,s,_,_ in ranking[:count]],selection_facts={s:dict(observed_turnover_per_reference_session=adv,observed_sessions_in_60=n,last_observed=last_quote) for adv,s,n,last_quote in ranking[:count]}))
    return result

def load_daily(root=ROOT):
    audit=read(root/'data/pit_daily/audit.json');prices={};hashes={}
    for s,r in audit['symbols'].items():
        if r['status']!='verified':continue
        path=root/'data/pit_daily'/f'{s}.json'
        if hashlib.sha256(path.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('Changed daily source: '+s)
        f=pd.DataFrame(read(path));f['date']=pd.to_datetime(f.date);f=f.loc[valid_rows(f)].set_index('date').sort_index()
        prices[s]=f[['open','high','low','close','volume']].astype(float);hashes[s]=r['sha256']
    return prices,audit,hashes

def build():
    prices,audit,hashes=load_daily();meta=read(ROOT/'config/market-classification.json')
    if set(audit['symbols'])!={s for s,r in meta['listing'].items() if r['type']=='STOCK'}:raise ValueError('Candidate daily audit incomplete')
    benchmark=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv');calendar=pd.DatetimeIndex(pd.to_datetime(benchmark.date))
    months=monthly_memberships(prices,calendar)
    research=[r for r in months if r['effective']>='2023-11-01']
    if any(len(r['members'])!=300 for r in research):raise ValueError('Not enough real pre-period candidates for every research month')
    union=sorted({s for r in research for s in r['members']});training_union=sorted({s for r in months for s in r['members']})
    delisted=sorted(s for s in union if meta['listing'][s]['exchange']=='DELISTED')
    out=dict(revision='monthly300_past_liquidity_v1',created_at=datetime.now(VN).isoformat(),start='2023-11-12',first_session='2023-11-13',end='2026-11-12',target=300,calendar_sessions=747,
        months=months,eligible_symbols=union,training_symbols=training_union,retained_delisted_in_research=delisted,
        source=meta['source']+'; Vietcap ONE_DAY raw history',source_catalog_asof=meta['asof'],catalog_candidates=len(audit['symbols']),catalog_retained_delisted=sum(r['exchange']=='DELISTED' and r['type']=='STOCK' for r in meta['listing'].values()),
        daily_input_sha256=hashes,candidate_status_counts={k:sum(r['status']==k for r in audit['symbols'].values()) for k in sorted({r['status'] for r in audit['symbols'].values()})},
        policy='Reconstitute at first benchmark session each month using only prior sessions: >=252 positive-volume valid daily observations, >=40 of prior60 benchmark sessions observed, at least one observation in prior5 sessions; rank observed turnover/prior60 session count, descending, ticker tie-break; top300; no end-period survival/continuity condition, no future return or minute-availability filter.',
        limitations=['Current and provider-retained delisted catalog is not a complete historical security master; completely removed securities can still be missing. Reduces, does not eliminate, survivorship/data-availability bias.', 'Monthly selection uses actual observed trading history, not legal listing/suspension certificates. Missing or zero-volume/malformed candles never generate execution.', 'Source OHLCV may be back-adjusted for later corporate actions, not original historical vintages; liquidity ranking and absolute price filters can retain adjustment/availability bias. Both cohorts use the same current source and protocol; this is not a fully reconstructed point-in-time security master or total-return dataset.', 'No historical market-cap or industry labels inferred; current ICB only for descriptive attribution. Corporate-action/total-return limitations remain.'])
    write(ROOT/'config/research-300.json',out)
    print('Monthly research:300 each month;',len(union),'unique research stocks;',len(training_union),'including training;',len(delisted),'provider-retained delisted:',delisted,flush=True)
    return out

if __name__=='__main__':build()
