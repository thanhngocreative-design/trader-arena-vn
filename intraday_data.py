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
