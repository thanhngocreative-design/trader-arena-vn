"""One-shot historic Daily+1m research pilot for GitHub Actions.

Keeps the existing 167-candidate daily contest and paper ledger EXACTLY as-is.
Fetches real 1-minute data privately during workflow; publishes only the
aggregated bot backtest, audit and simulated fills, NOT raw minute prices.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from datafeed import parse_symbols, update_prices, load_prices
from engine import Settings, TRADERS, backtest
from fast_engine import FastContext, CORE, build_hybrid_signals
from intraday_data import MINUTE_DIR, VN, fetch_vnstock_community, load_minute
from hybrid_backtest import build_hybrid_backtests
from generate_dashboard import summary_backtest


def pilot(symbols:list[str],days:int,output_path:Path) -> dict:
    if not 7<=days<=28:
        raise ValueError("Pilot days must be 7–28 to respect guest 1m history caps")
    if not 2<=len(symbols)<=20:
        raise ValueError("Pilot supports 2–20 candidate symbols")
    today=datetime.now(VN).date()
    start=(today-timedelta(days=days)).isoformat()
    end=today.isoformat()
    feed=fetch_vnstock_community(symbols,start,end)
    status=update_prices(symbols,start="2021-01-01")
    if status["errors"]:
        raise RuntimeError("Cannot verify EOD benchmark: "+str(status["errors"]))
    good=[s for s in symbols if s in status["success"]]
    if len(good)<2:
        raise RuntimeError("Insufficient synchronized EOD candidates: "+str(status["skipped"]))
    prices,benchmark,missing=load_prices(good)
    if benchmark is None or missing:
        raise RuntimeError("EOD price files missing: "+str(missing))
    settings=Settings()
    ctx=FastContext(prices,benchmark,settings)
    warmup=max(benchmark.index.min(),__import__('pandas').Timestamp("2022-01-03"))
    reference={k:backtest(prices,benchmark,k,start_date=str(warmup.date()),
                          settings=settings,features_cache=ctx) for k in CORE}
    build_hybrid_signals(ctx,{k:v["curve"] for k,v in reference.items()})
    frames,excluded=load_minute(good,MINUTE_DIR,daily=prices)
    results,audit=build_hybrid_backtests(ctx,frames,settings)
    if not results:
        raise RuntimeError("No verified historical 1m pilot: "
                           +str(audit)+"; minute errors: "+str(feed["errors"] or excluded))
    current=json.loads(output_path.read_text(encoding="utf-8"))
    if current.get("mode")!="real_market_data" or not current.get("paper") or not current.get("backtests"):
        raise RuntimeError("Public EOD dashboard not present; refusing to overwrite daily")
    if current.get("last_session")!=benchmark.index.max().date().isoformat():
        raise RuntimeError("Pilot benchmark not synchronized with public Daily dashboard")
    audit["requested"]=symbols
    audit["source"]="Vnstock v6 community 1m; originally from provider KBS"
    audit["fetched"]=feed["success"]
    audit["minute_rejected"]=excluded
    audit["eod_rejected"]=status["skipped"]
    audit["sample_universe_only"]=True
    audit["daily_backtests_left_untouched"]=True
    current["hybrid_backtest_audit"]=audit
    current["hybrid_backtests"]={k:summary_backtest(r) for k,r in results.items()}
    current["hybrid_backtests_updated_at"]=datetime.now(VN).isoformat()
    tmp=output_path.with_suffix(".hybrid.tmp")
    tmp.write_text(json.dumps(current,ensure_ascii=False,allow_nan=False,
                              separators=(",",":"),default=str),encoding="utf-8")
    tmp.replace(output_path)
    return audit


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--symbols",default="FPT,HPG,ACB,MBB,SSI,MWG,STB,TCB,VCB,VNM,CTG,VIC")
    ap.add_argument("--days",type=int,default=21)
    ap.add_argument("--output",default=str(Path(__file__).parent/"site/dashboard.json"))
    args=ap.parse_args()
    audit=pilot(parse_symbols(args.symbols),args.days,Path(args.output))
    print("Hybrid pilot completed; real 1m coverage:",json.dumps(audit,ensure_ascii=False))
