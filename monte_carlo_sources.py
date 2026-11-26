"""Read complete recorded NAV; reconstruct daily NAV with exact book checks.

Analysis only. Never writes trading ledgers, prices, model files or checkpoints.
"""
import hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from value_investing import ROOT, read, write, eligible_companies
from paper_replay import unpack, pack
from backtest_state import STATE, model_digest, verify_manifest

CACHE=ROOT/'state/monte_carlo/nav-source.json.gz'
MODES=('paper','paper_minute','paper_combo','backtest','backtest_minute','hybrid')
CAPITAL=100_000_000


def normalized_history(rows, *, expected_dates=None):
    result=[];seen=set()
    for row in rows:
        day=pd.Timestamp(row['date']).date().isoformat();nav=float(row['nav'])
        if day in seen or not np.isfinite(nav) or nav<0:raise ValueError('Invalid or duplicate saved NAV')
        seen.add(day);result.append([day,nav])
    if not result or [r[0] for r in result]!=sorted(seen):raise ValueError('Unordered/empty saved NAV')
    if expected_dates is not None and [r[0] for r in result]!=expected_dates:raise ValueError('Missing saved NAV session; no interpolation')
    return result


def checked_panel(key, mode, cohort, period, books, histories, dates, model):
    bots=sorted(books)
    if set(histories)!=set(bots):raise ValueError('Incomplete NAV bot set')
    navs={}
    for bot in bots:
        rows=normalized_history(histories[bot],expected_dates=dates)
        if abs(rows[-1][1]-float(books[bot]['nav']))>1.01:raise ValueError('NAV does not reconcile: '+key+':'+bot)
        navs[bot]=[r[1] for r in rows]
        # Check every retained public chart point as well as the endpoint.
        actual=dict(rows)
        for row in books[bot].get('history' if mode.startswith('paper') else 'curve',[]):
            day=(pd.to_datetime(row['date'],format='%d/%m/%y') if '/' in str(row['date']) else pd.Timestamp(row['date'])).date().isoformat()
            if day not in actual or abs(float(row['nav'])-actual[day])>1.01:raise ValueError('Saved chart differs: '+key+':'+bot)
    ranking=sorted(bots,key=lambda b:(-float(books[b]['nav']),
        -float(books[b]['max_drawdown_pct']) if books[b].get('max_drawdown_pct') is not None else float('inf'),b.casefold()))
    return dict(key=key,mode=mode,cohort=cohort,period=period,dates=dates,bots=bots,nav=navs,
        capital_each=CAPITAL,ranking=ranking,model_sha256=model,
        trades={b:int(books[b].get('buy_count') or 0)+int(books[b].get('closed_trades') or 0) for b in bots})


def export_sources():
    saved=read(STATE/'manifest.json');model=model_digest()
    verify_manifest(saved,pd.to_datetime(saved['calendar']),saved['memberships'])
    monthly=read(ROOT/'site/research-300.json');vn=read(ROOT/'site/research-vn30.json')
    papers={c:read(ROOT/'site'/f) for c,f in [('300','paper-replay.json'),('146','paper-fixed146.json'),('vn30','paper-vn30.json')]}
    if {p['last_session'] for p in papers.values()}!={saved['last_session']} or monthly['end']!=saved['last_session'] or vn['end']!=saved['last_session']:
        raise ValueError('Wait for all verified Paper and Backtest books to finish together')
    source_identity=dict(model=model,end=saved['last_session'],checkpoints=saved['checkpoint_sha256'],inputs=saved['input_sha256'],
        exporter=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest())
    fingerprint=hashlib.sha256(json.dumps(source_identity,sort_keys=True).encode()).hexdigest()
    if CACHE.exists():
        cache=unpack(CACHE)
        if cache.get('fingerprint')==fingerprint:return cache
    cohorts={**monthly['cohorts'],'vn30':vn['cohort']};panels={};dates=saved['calendar']
    minute=unpack(STATE/saved['minute_state'])
    for cohort,public in cohorts.items():
        for mode in ('backtest_minute','hybrid'):
            books=public['minute_backtests' if mode=='backtest_minute' else 'hybrid_backtests'];histories={}
            for bot in books:
                if mode=='backtest_minute':rows=minute['curves'][cohort]['minute'][bot]
                elif bot in minute['curves'][cohort]['value_combo']:rows=minute['curves'][cohort]['value_combo'][bot]
                else:rows=unpack(STATE/saved['combo_states'][cohort][bot])['history']
                histories[bot]=rows
            key=f'{cohort}:{mode}:ALL';panels[key]=checked_panel(key,mode,cohort,'ALL',books,histories,dates,model)
        for mode in ('paper','paper_minute','paper_combo'):
            p=papers[cohort];key=f'{cohort}:{mode}:ALL'
            panels[key]=checked_panel(key,mode,cohort,'ALL',p[mode],{b:x['history'] for b,x in p[mode].items()},p['sessions'],model)
    # Public charts are downsampled; regenerate complete daily curves and verify
    # all original ALL trades and every published curve/endpoint before using them.
    from continuous_backtest import inputs,contexts
    from engine import TRADERS,backtest
    from pit_daily import merged_fundamentals,value_backtest
    from paper_ledger import preserve_trade_prefix
    end,prices,benchmark,_,cfg,fixed,official,_=inputs()
    ctxs=contexts(prices,benchmark,cfg,fixed,official)
    reports=eligible_companies(merged_fundamentals(),read(ROOT/'config/market-classification.json')['sectors'])
    old_ledgers=unpack(STATE/saved['ledgers'])
    for cohort,ctx in ctxs.items():
        public=cohorts[cohort]
        for option in monthly['backtest_options']:
            period=option['key'];books=public['backtest_periods'][period];histories={};calendar=None
            for bot in books:
                r=backtest(prices,benchmark,bot,option['start'],end_date=end,settings=ctx.settings,features_cache=ctx) if bot in TRADERS else value_backtest(ctx,bot,option['start'],end,reports)
                rows=[dict(date=str(d.date()),nav=float(v.nav)) for d,v in r['curve'].iterrows()]
                if calendar is None:calendar=[row['date'] for row in rows]
                histories[bot]=rows
                if period=='ALL':
                    trades=json.loads(r['trades'].to_json(orient='records',date_format='iso'))
                    preserve_trade_prefix(old_ledgers[cohort]['daily:'+bot],trades,end,label='Monte Carlo source:'+cohort+':'+bot)
            key=f'{cohort}:backtest:{period}';panels[key]=checked_panel(key,'backtest',cohort,period,books,histories,calendar,model)
            print('Verified complete daily NAV source',key,len(calendar),'sessions',flush=True)
    result=dict(revision='monte_nav_v1',fingerprint=fingerprint,model_sha256=model,end=end,panels=panels)
    pack(CACHE,result)
    return result


if __name__=='__main__':
    result=export_sources();print('Verified full NAV panels:',len(result['panels']),result['end'],flush=True)
