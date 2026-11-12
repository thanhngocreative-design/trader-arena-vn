"""Publish sector attribution only after reconciling complete trade ledgers."""
import json,hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from datafeed import load_prices
from engine import TRADERS,Settings,backtest
from fast_engine import FastContext,CORE,build_hybrid_signals
from generate_dashboard import summary_backtest
from sector_analytics import aggregate_trades,universe_distribution,attach_paper_sectors
ROOT=Path(__file__).resolve().parent

def build():
    research=json.loads((ROOT/'site/research-146.json').read_text(encoding='utf8'))
    metadata=json.loads((ROOT/'config/market-classification.json').read_text(encoding='utf8'))
    symbols=research['universe'];assert len(set(symbols))==146
    prices,_,missing=load_prices(symbols)
    if missing:raise ValueError(str(missing))
    override=ROOT/'data/prices_research_vietcap/ITC.csv'
    raw=pd.read_csv(override);raw['date']=pd.to_datetime(raw.date)
    prices['ITC']=raw.set_index('date')[['open','high','low','close','volume']].astype(float)
    for sym in symbols:
        source=override if sym=='ITC' else ROOT/'data/prices'/f'{sym}.csv'
        if hashlib.sha256(source.read_bytes()).hexdigest()!=research['research_meta']['daily_input_sha256'][sym]:raise ValueError('Daily source changed: '+sym)
    bp=ROOT/'data/prices/VNINDEX_research.csv'
    if hashlib.sha256(bp.read_bytes()).hexdigest()!=research['research_meta']['benchmark_sha256']:raise ValueError('Benchmark changed')
    raw=pd.read_csv(bp);raw['date']=pd.to_datetime(raw.date)
    benchmark=raw.set_index('date')[['open','high','low','close','volume']].astype(float)
    benchmark[['open','high','low','close']]*=1000
    end=research['research_meta']['end'];start=research['research_meta']['start']
    benchmark=benchmark.loc[benchmark.index<=end]
    prices={s:f.loc[f.index<=end] for s,f in prices.items()}
    settings=Settings(portfolio_policy='atr_v1');ctx=FastContext(prices,benchmark,settings)
    reference={k:backtest(prices,benchmark,k,'2022-01-03',settings=settings,features_cache=ctx) for k in CORE}
    build_hybrid_signals(ctx,{k:r['curve'] for k,r in reference.items()})
    books={m:{} for m in ('backtest','backtest_minute','hybrid')};proof={}
    for bot in TRADERS:
        result=backtest(prices,benchmark,bot,start,end_date=end,settings=settings,features_cache=ctx)
        if summary_backtest(result)!=research['backtests'][bot]:raise ValueError('Daily replay no longer reconciles: '+bot)
        books['backtest'][bot]=aggregate_trades(result['trades'].to_dict('records'),metadata['sectors'],set(symbols))
        for mode,key in [('backtest_minute','minute_backtests'),('hybrid','hybrid_backtests')]:
            suffix='-v2' if mode=='backtest_minute' and research[key][bot].get('rules_revision')=='darvas_prior_low20_v2' else ''
            file=ROOT/'data/minute_history'/(f'minute-only-trades-{bot}{suffix}.csv' if mode=='backtest_minute' else f'trades-{bot}.csv')
            trades=pd.read_csv(file).to_dict('records')
            stats=aggregate_trades(trades,metadata['sectors'],set(symbols));expected=research[key][bot]
            if stats['buy_fills']!=expected['buy_count'] or stats['sell_fills']!=expected['closed_trades']:raise ValueError('Incomplete trade ledger: '+str(file))
            if stats['outside_146_fills']:raise ValueError('Unexpected research symbol')
            if trades and sorted(trades,key=lambda t:t.get('time',t['date']))[-1]['date']>end:raise ValueError('Future trades')
            books[mode][bot]=stats;proof[mode+':'+bot]=hashlib.sha256(file.read_bytes()).hexdigest()
        print('Full sector attribution reconciled:',bot,flush=True)
    result=dict(asof=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),classification_asof=metadata['asof'],source=metadata['source'],icb_level=metadata['icb_level'],classification_note=metadata['classification_note'],universe_count=146,market_count=metadata['active_stock_count'],exchange_counts=metadata['active_exchange_counts'],universe=universe_distribution(symbols,metadata),books=books,trade_ledger_hashes=proof,method='Executed fills only. Buy value is cumulative gross turnover, not NAV weight. Full ledgers, not recent-trade samples. Recorded rounded fill prices used when gross is absent.',period=dict(start=research['hybrid_backtest_audit']['first'],end=end),minute_rules_revision=research['minute_backtest_audit'].get('bot_revisions',{}))
    for book in books.values():
        for stats in book.values():assert not stats['outside_146_fills']
    expansion=ROOT/'site/expansion-audit.json'
    if expansion.exists():result['expansion']=json.loads(expansion.read_text(encoding='utf8'))
    (ROOT/'site/sectors.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8')
    dashboard=json.loads((ROOT/'site/dashboard.json').read_text(encoding='utf8'));attach_paper_sectors(dashboard,ROOT)
    (ROOT/'site/dashboard.json').write_text(json.dumps(dashboard,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8')
    from paper_intraday import publish
    state=json.loads((ROOT/'state/paper_intraday.json').read_text(encoding='utf8'));publish(state,state['status'])
    print('Sector dashboard ready. All 33 historical bot ledgers reconciled.',flush=True)
if __name__=='__main__':build()
