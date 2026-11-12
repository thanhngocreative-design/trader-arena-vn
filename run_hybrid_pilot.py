"""One-shot historic Daily+1m research pilot for GitHub Actions.

Keeps the existing 167-candidate daily contest and paper ledger EXACTLY as-is.
Fetches real 1-minute data privately during workflow; publishes only the
aggregated bot backtest, audit and simulated fills, NOT raw minute prices.
"""
from __future__ import annotations
import argparse
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from datafeed import parse_symbols, update_prices, load_prices
from engine import Settings, TRADERS, backtest
from fast_engine import FastContext, CORE, build_hybrid_signals
from intraday_data import MINUTE_DIR, VN, bank_trade_tapes, load_minute, normalize_minute
from hybrid_backtest import build_hybrid_backtests
from generate_dashboard import summary_backtest


def pilot(symbols:list[str],output_path:Path,bank_only:bool=False) -> dict:
    banked=bank_trade_tapes(symbols,output=MINUTE_DIR)
    all_sessions=set()
    for sym in symbols:
        path=MINUTE_DIR / (sym+".csv")
        if path.exists():
            try:
                frame=normalize_minute(pd.read_csv(path))
                all_sessions.update(frame.index.normalize())
            except (ValueError,TypeError,OSError):
                pass
    info={"banking":"in_progress","banked":banked["success"],
          "skipped":banked["skipped"],"available_sessions":len(all_sessions),
          "provider":banked["source"],"dashboard_updated":False}
    if bank_only or len(all_sessions)<5:
        return info
    # Fetch previous-day history independently of the ongoing daily contest.
    status=update_prices(symbols,start="2021-01-01")
    if status["errors"]:
        return {**info,"reason":"EOD benchmark unavailable: "+str(status["errors"])}
    good=[s for s in symbols if s in status["success"]]
    if len(good)<2:
        return {**info,"reason":"Not enough EOD candidate histories"}
    prices,benchmark,missing=load_prices(good)
    if benchmark is None or missing:
        return {**info,"reason":"Some EOD inputs were unavailable"}
    settings=Settings()
    ctx=FastContext(prices,benchmark,settings)
    warmup=max(benchmark.index.min(),pd.Timestamp("2022-01-03"))
    reference={k:backtest(prices,benchmark,k,start_date=str(warmup.date()),
                          settings=settings,features_cache=ctx) for k in CORE}
    build_hybrid_signals(ctx,{k:v["curve"] for k,v in reference.items()})
    frames,excluded=load_minute(good,MINUTE_DIR,daily=prices)
    results,audit=build_hybrid_backtests(ctx,frames,settings)
    if not results:
        return {**info,"reason":"Minute EOD integrity checks did not pass",
                "audited":audit,"rejected":excluded}
    current=json.loads(output_path.read_text(encoding="utf-8"))
    if current.get("mode")!="real_market_data" or not current.get("paper") or not current.get("backtests"):
        return {**info,"reason":"Refusing to replace missing Daily public dashboard"}
    if current.get("last_session")!=benchmark.index.max().date().isoformat():
        return {**info,"reason":"Public daily dashboard not synchronized with pilot EOD"}
    audit["requested"]=symbols
    audit["source"]="KBS matched-trade tape banked using vn-market-data v0.4.0"
    audit["banked_at"]=datetime.now(VN).isoformat()
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
    return {**info,"banking":"published","audited":audit,"dashboard_updated":True}


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--symbols",default="FPT,HPG,ACB,MBB,SSI,MWG,STB,TCB")
    ap.add_argument("--output",default=str(Path(__file__).parent/"site/dashboard.json"))
    ap.add_argument("--status-path",default="")
    ap.add_argument("--bank-only",action="store_true")
    args=ap.parse_args()
    audit=pilot(parse_symbols(args.symbols),Path(args.output),args.bank_only)
    # Metadata is public; raw licensed 1-minute candles are NOT.
    coverage={
        "status":"verified_1m_pilot" if audit.get("dashboard_updated") else "banking",
        "session_count":int(audit.get("available_sessions",0)),
        "required_sessions":5,
        "symbols_banked_last_run":sorted(audit.get("banked",{})),
        "last_banked_session":max((x.get("date","") for x in audit.get("banked",{}).values()),default=""),
        "last_checked_at":datetime.now(VN).isoformat(),
        "feed":"KBS matched-trade tape, sampled once after market",
        "paper_only":True,
        "note":"Missing historical sessions cannot be retroactively invented. Do not compare 8-stock hybrid pilot to full Daily universe."
    }
    output_dir=Path(args.output).parent
    output_dir.mkdir(parents=True,exist_ok=True)
    coverage_file=output_dir/"hybrid-coverage.json"
    temporary=coverage_file.with_suffix(".tmp")
    temporary.write_text(json.dumps(coverage,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(coverage_file)
    print("HYBRID BANKING REPORT:",json.dumps(audit,ensure_ascii=False,default=str))
    if args.status_path:
        Path(args.status_path).write_text(json.dumps(audit,ensure_ascii=False,default=str),encoding="utf-8")
