"""Publish a fresh, fixed three-year 146-stock ATR study, preserving paper."""
import argparse,json,hashlib,time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from datafeed import load_prices
from engine import Settings,TRADERS,backtest
from fast_engine import FastContext,CORE,build_hybrid_signals
from hybrid_backtest import build_hybrid_backtests
from intraday_data import normalize_minute
from generate_dashboard import summary_backtest
from research_snapshot import apply_research_snapshot
ROOT=Path(__file__).resolve().parent
VN=ZoneInfo('Asia/Ho_Chi_Minh')
def build(daily_only=False,refresh_benchmark=False):
    u=json.loads((ROOT/'config/research-universe.json').read_text(encoding='utf8'))
    symbols=u['eligible_symbols'];assert len(symbols)==len(set(symbols))==146
    prices,original_benchmark,missing=load_prices(symbols)
    if missing:raise RuntimeError(f'Missing daily histories: {missing}')
    benchmark_path=ROOT/'data/prices/VNINDEX_research.csv'
    if refresh_benchmark or not benchmark_path.exists():
        from vn_market_data.sources.vietcap import VietcapSource
        rows=VietcapSource().get_ohlcv('VNINDEX','2021-01-01',u['end'],is_index=True)
        pd.DataFrame(rows).to_csv(benchmark_path,index=False)
    raw=pd.read_csv(benchmark_path);raw['date']=pd.to_datetime(raw.date)
    benchmark=raw.set_index('date')[['open','high','low','close','volume']].astype(float)
    benchmark[['open','high','low','close']]*=1000
    benchmark=benchmark.loc[benchmark.index<=u['end']].sort_index()
    start=pd.Timestamp(u['start']);end=pd.Timestamp(u['end']);dates=benchmark.index[(benchmark.index>=start)&(benchmark.index<=end)]
    if len(dates)!=u['calendar_sessions']:raise RuntimeError(f'Research index calendar has {len(dates)}, expected {u["calendar_sessions"]}; no artificial fill allowed')
    for sym,f in prices.items():
        f=f.loc[f.index<=end];prices[sym]=f
        check=f.reindex(dates)
        if check.isna().any().any() or (check.volume<=0).any():raise RuntimeError(f'{sym}: daily continuity no longer passes')
    settings=Settings(portfolio_policy='atr_v1');ctx=FastContext(prices,benchmark,settings)
    training_start='2022-01-03'
    reference={k:backtest(prices,benchmark,k,training_start,settings=settings,features_cache=ctx) for k in CORE}
    hybrid_info=build_hybrid_signals(ctx,{k:r['curve'] for k,r in reference.items()})
    periods={'3M':max(start,end-pd.DateOffset(months=3)),'6M':max(start,end-pd.DateOffset(months=6)),'1Y':max(start,end-pd.DateOffset(years=1)),'2Y':max(start,end-pd.DateOffset(years=2)),'ALL':start}
    by_period={}
    for label,begin in periods.items():
        by_period[label]={k:summary_backtest(backtest(prices,benchmark,k,str(begin.date()),end_date=u['end'],settings=settings,features_cache=ctx)) for k in TRADERS}
        print('New Daily research complete:',label,flush=True)
    existing=json.loads((ROOT/'site/dashboard.json').read_text(encoding='utf8'))
    meta={'revision':'continuous146_v1','start':u['start'],'end':u['end'],'daily_reference_sessions':len(dates),'universe_selection':'Survivors with complete daily trading data across the full three-year window, including uninterrupted exchange transfers. This is an intentional ex-post continuity filter, not an unbiased point-in-time universe.','policy':'atr_v1','source_daily':'DNSE/Vietcap via vn-market-data 0.4.0; benchmark Vietcap historical index','source_minute':'Vietcap public chart, actual observed ONE_MINUTE candles; no interpolation','created_at':datetime.now(VN).isoformat(),'paper_ledger_changed':False}
    minute_payload={};minute_audit={'status':'loading_146_history','symbols':0,'sessions':0,'reason':'Chưa xuất kết quả phút khi chưa tải và kiểm tra đủ 146 mã'}
    if not daily_only:
        p=ROOT/'data/minute_history';audit=json.loads((p/'audit.json').read_text(encoding='utf8'));frames={};coverage={}
        if set(audit['symbols'])!=set(symbols):raise RuntimeError('All 146 histories must be downloaded before research')
        for n,sym in enumerate(symbols,1):
            source=p/f'{sym}.csv.gz'
            if hashlib.sha256(source.read_bytes()).hexdigest()!=audit['symbols'][sym]['sha256']:raise RuntimeError(f'{sym}: history hash mismatch')
            f=normalize_minute(pd.read_csv(source),'vnd');sessions=f.index.normalize().unique();missing_days=dates.difference(sessions)
            if len(sessions)<5:raise RuntimeError(f'{sym}: insufficient actual minute history')
            observations=f.groupby(f.index.normalize()).close.last();ratios=observations/prices[sym].close.reindex(observations.index)
            if ratios.isna().any() or ((ratios<.92)|(ratios>1.08)).any():raise RuntimeError(f'{sym}: minute vs daily price mismatch')
            counts=f.groupby(f.index.normalize()).size().reindex(dates,fill_value=0)
            coverage[sym]={'bars':len(f),'sessions':len(sessions),'missing_continuous_sessions':[str(x.date()) for x in missing_days],'absent_standard_continuous_minutes':int((225-counts).clip(lower=0).sum()),'sha256':audit['symbols'][sym]['sha256']}
            frames[sym]=f
            if n%20==0:print('Validated minute histories:',n,flush=True)
        print('Starting chronological 1m backtests for 11 bots',flush=True)
        minute_results,minute_audit=build_hybrid_backtests(ctx,frames,settings)
        minute_payload={k:summary_backtest(v) for k,v in minute_results.items()}
        if len(minute_payload)!=11:raise RuntimeError('Incomplete bot results')
        minute_audit.update(status='verified_1m_146',source=meta['source_minute'],coverage_by_symbol=coverage,full_universe=True,requested_symbols=146,price_validation='Prior EOD adjustment/unit consistency checked within 8%; no interpolation',caveat='146-stock ex-post continuity universe; continuous-session observed candles only; gaps remain, next observed bar fills only within 3 minutes; no same-day sale; not actual broker executions.')
        for bot,r in minute_results.items():
            r['trades'].to_csv(ROOT/'data/minute_history'/f'trades-{bot}.csv',index=False)
            r['curve'].to_csv(ROOT/'data/minute_history'/f'curve-{bot}.csv')
        (p/'research-coverage.json').write_text(json.dumps(coverage,indent=2),encoding='utf8')
    labels={'3M':'3 tháng','6M':'6 tháng','1Y':'1 năm','2Y':'2 năm','ALL':'3 năm'}
    snapshot={'backtests':by_period['ALL'],'backtest_periods':by_period,'backtest_options':[{'key':k,'label':labels[k],'start':str(v.date()),'end':u['end']} for k,v in periods.items()],'portfolio_comparison':{},'portfolio_policy':{'revision':'atr_v1','risk_fraction':settings.risk_fraction,'atr_multiple':settings.atr_multiple},'hybrid_backtests':minute_payload,'hybrid_backtest_audit':minute_audit,'hybrid_model':hybrid_info,'universe':symbols,'universe_audit':{'candidate_count':u['original_symbols'],'tradable_history_count':146,'excluded_count':len(u['excluded_symbols']),'universe_asof':u['end'],'note':meta['universe_selection'],'skipped_examples':{s:'Thiếu phiên/ngày giao dịch trong cửa sổ 3 năm' for s in u['excluded_symbols']}},'start_date':u['start'],'research_meta':meta}
    dest=ROOT/'site/research-146.json';temp=dest.with_suffix('.tmp');temp.write_text(json.dumps(snapshot,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8');temp.replace(dest)
    payload=apply_research_snapshot(existing,dest)
    payload['warnings']=[w for w in payload.get('warnings',[]) if '167' not in w and '126' not in w]+['146 mã được chọn sau khi đã biết dữ liệu liên tục đủ 3 năm: kết quả có sai lệch chọn mẫu.','Backtest mới thay thế toàn bộ kết quả cũ; paper-forward được giữ nguyên.']
    dest=ROOT/'site/dashboard.json';temp=dest.with_suffix('.tmp');temp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8');temp.replace(dest)
    print('Published research146 snapshot. Paper payload preserved:',existing.get('paper')==payload.get('paper'),flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--daily-only',action='store_true');ap.add_argument('--refresh-benchmark',action='store_true');a=ap.parse_args();build(a.daily_only,a.refresh_benchmark)
