"""Verified historical one-minute equity candles. All stored prices are full VND.

Raw licensed data is private: do not commit data/minute/*.csv to the public repo.
Data from a free community library is NOT a license to republish its price feed.
Only HOSE-style continuous trading minutes are included; auctions are excluded.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import json
import os
import re
import pandas as pd

VN = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parent
MINUTE_DIR = ROOT / "data" / "minute"
COLUMNS = ["time", "open", "high", "low", "close", "volume"]


def normalize_minute(frame: pd.DataFrame, price_unit: str = "vnd") -> pd.DataFrame:
    if price_unit not in ("vnd", "thousand_vnd"):
        raise ValueError("Need explicit price unit: vnd or thousand_vnd")
    if frame is None or frame.empty:
        raise ValueError("No real 1-minute candles")
    f = frame.copy()
    f.columns = [str(c).strip().lower() for c in f.columns]
    if "time" not in f and "date" in f:
        f = f.rename(columns={"date": "time"})
    if any(c not in f for c in COLUMNS):
        raise ValueError("Missing OHLCV columns")
    f = f[COLUMNS].copy()
    dt = pd.to_datetime(f["time"], errors="coerce")
    if dt.isna().any():
        raise ValueError("Invalid minute timestamps")
    if dt.dt.tz is not None:
        dt = dt.dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    f["time"] = dt
    if f["time"].duplicated().any():
        raise ValueError("Duplicate minute bars cannot be used")
    for col in COLUMNS[1:]:
        f[col] = pd.to_numeric(f[col], errors="coerce")
    if f[COLUMNS[1:]].isna().any().any():
        raise ValueError("Invalid OHLCV numbers")
    if price_unit == "thousand_vnd":
        for c in ("open", "high", "low", "close"):
            f[c] *= 1000.0
    if ((f[["open","high","low","close"]] <= 0).any().any()
        or (f["volume"] < 0).any()
        or (f["high"] < f[["open","close","low"]].max(axis=1)).any()
        or (f["low"] > f[["open","close","high"]].min(axis=1)).any()):
        raise ValueError("Impossible OHLCV values")
    t = f["time"].dt.time
    from datetime import time
    trading = ((t >= time(9,15)) & (t < time(11,30))) | ((t >= time(13)) & (t < time(14,30)))
    f = f.loc[trading & (f["time"].dt.dayofweek < 5)].copy()
    f.sort_values("time", inplace=True)
    if f.empty:
        raise ValueError("No continuous-session bars; auctions not supported")
    return f.set_index("time").astype(float)


def load_minute(symbols: list[str], directory: Path = MINUTE_DIR, daily: dict | None = None):
    """Return only validated candles; do not invent missing intervals or forward fill."""
    result, errors = {}, {}
    for symbol in symbols:
        path = directory / (symbol + ".csv")
        if not path.is_file():
            continue
        try:
            f = normalize_minute(pd.read_csv(path), "vnd")
            if daily and symbol in daily:
                # Cross-provider adjusted vs raw prices can be incompatible.
                # Do not use minute prices unless they match EOD within 8%.
                ref = daily[symbol]["close"].copy()
                observations = f.groupby(f.index.normalize())["close"].last()
                both = ref.reindex(observations.index)
                ratio = observations / both
                check = both.notna()
                if check.sum() == 0 or ((ratio[check] < .92) | (ratio[check] > 1.08)).any():
                    raise ValueError("Minute/EOD price unit or adjustment mismatch")
            result[symbol] = f
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors[symbol] = str(exc)[:200]
    return result, errors


def tape_to_minute(tape: dict, required_session: str | None = None) -> pd.DataFrame:
    """Aggregate an actual provider-verified exchange trade tape to 1m OHLCV.

    This is a LOSSLESS per-minute aggregation of *existing matched prints*, not
    a historic quote API. Bars with no matched prints are missing, never padded.
    """
    if not isinstance(tape,dict) or not tape.get("trades"):
        raise ValueError("Empty verified trade tape")
    session=str(tape.get("date",""))
    parsed=pd.Timestamp(session)
    if parsed.strftime("%Y-%m-%d")!=session:
        raise ValueError("Invalid tape session date")
    if required_session and required_session!=session:
        raise ValueError("Provider tape session does not match requested date")
    trades=tape["trades"]
    output={}
    previous_acc=0
    for p in trades:
        if p.get("date")!=session:
            raise ValueError("Mixed session tape")
        vol=int(p.get("volume",0))
        acc=int(p.get("accumulated_volume",0))
        price=float(p.get("price",0))
        if vol<=0 or acc!=previous_acc+vol or price<=0:
            raise ValueError("Missing/repeated trade prints or price mismatch")
        previous_acc=acc
        ts=pd.Timestamp(session+" "+str(p.get("time","")))
        minute=ts.floor("min")
        if minute not in output:
            output[minute]=[price,price,price,price,0]
        bar=output[minute]
        bar[1]=max(bar[1],price)
        bar[2]=min(bar[2],price)
        bar[3]=price
        bar[4]+=vol
    data=pd.DataFrame([
        {"time":timestamp,"open":v[0],"high":v[1],"low":v[2],
         "close":v[3],"volume":v[4]}
        for timestamp,v in sorted(output.items())])
    return normalize_minute(data,"vnd")


def bank_trade_tapes(symbols: list[str], output: Path = MINUTE_DIR,
                     expected_session: str | None = None) -> dict:
    """Append only today's/last session true trade prints with no credentials.

    KBS trade tape does NOT support requests for past dates. This function does
    not pretend historical 1m backfill is possible. Source access can fail.
    """
    from vn_market_data import get_trade_tape
    output.mkdir(parents=True,exist_ok=True)
    now=datetime.now(VN)
    report={"source":"KBS matched prints via pinned vn-market-data v0.4.0",
            "run_at":now.isoformat(),"success":{},"skipped":{},
            "raw_prices_public":False}
    for sym in symbols:
        try:
            if not re.fullmatch(r"[A-Z]{3,5}",sym):
                raise ValueError("Unsupported ticker")
            source,tape=get_trade_tape(sym)
            if tape is None:
                raise ValueError("No verified trades returned")
            session=str(tape.get("date",""))
            if expected_session and session!=expected_session:
                raise ValueError("Trade tape belongs to "+session+", not "+expected_session)
            if session>now.date().isoformat():
                raise ValueError("Future tape session")
            # Require a late-session print to avoid banking incomplete real-time
            # snapshots. The schedule runs after close; auction prints are
            # present in the tape but excluded from continuous 1-minute bars.
            last_print=str(tape["trades"][-1]["time"]) if tape.get("trades") else ""
            if last_print<"14:25:00":
                raise ValueError("Tape incomplete: last matched print "+last_print)
            minute=tape_to_minute(tape,required_session=session)
            if len(minute)<65:
                raise ValueError("Too few matched minutes to treat as a complete session")
            path=output/(sym+".csv")
            if path.exists():
                old=normalize_minute(pd.read_csv(path),"vnd")
                prev=old.loc[old.index.normalize()==pd.Timestamp(session)]
                if not prev.empty:
                    # Avoid overwriting different results from a later provider
                    # replay or accidentally mixing data collection windows.
                    if not prev.equals(minute):
                        raise ValueError("Existing 1m bars disagree with provider; quarantined")
                    report["skipped"][sym]="Session already banked and identical"
                    continue
                combined=pd.concat([old,minute]).sort_index()
            else:
                combined=minute
            tmp=path.with_suffix(".tmp")
            combined.reset_index().to_csv(tmp,index=False)
            tmp.replace(path)
            report["success"][sym]={"date":session,"source":source,
                "bars":len(minute),"prints":len(tape["trades"])}
        except Exception as exc:
            report["skipped"][sym]=(type(exc).__name__+": "+str(exc))[:190]
    return report


def fetch_vnstock_community(symbols: list[str], start: str, end: str, output: Path = MINUTE_DIR):
    """Optional manually authorized data acquisition; vnstock v6 community, not daily CI.

    Data remains private in Actions cache / user's own environment.
    Free guest tier may have only 30 days; verified community tier up to 180 days.
    """
    from vnstock import Market
    output.mkdir(parents=True, exist_ok=True)
    results = {"source":"Vnstock v6 community 1m (VCI/KBS)",
               "requested":symbols, "success":{}, "errors":{}}
    for sym in symbols:
        try:
            if not re.fullmatch(r"[A-Z]{3,5}", sym):
                raise ValueError("Invalid stock symbol")
            raw = Market().equity(sym).ohlcv(start=start, end=end, interval="1m", source="kbs")
            if raw is None or raw.empty:
                raise ValueError("Provider returned no candles")
            norm = normalize_minute(raw, "thousand_vnd")
            # Convert back into consistent portable CSV. Do NOT upload publicly.
            path = output / (sym + ".csv")
            norm.reset_index().to_csv(path, index=False)
            results["success"][sym] = {"rows":len(norm),
                 "first":str(norm.index.min()),"last":str(norm.index.max())}
        except Exception as exc:
            results["errors"][sym] = (type(exc).__name__ + ": " + str(exc))[:250]
    return results


if __name__ == "__main__":
    ap=argparse.ArgumentParser(description="Download 1m history privately, not to GitHub")
    ap.add_argument("--symbols",default="FPT,HPG,ACB,MBB,SSI,MWG,STB,TCB")
    ap.add_argument("--start",default=(datetime.now(VN)-timedelta(days=35)).date().isoformat())
    ap.add_argument("--end",default=datetime.now(VN).date().isoformat())
    args=ap.parse_args()
    symbols=list(dict.fromkeys(x.strip().upper() for x in args.symbols.split(",") if x.strip()))
    print(json.dumps(fetch_vnstock_community(symbols,args.start,args.end),ensure_ascii=False,indent=2))
