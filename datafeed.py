"""Daily Vietnam exchange market-data adapter. No broker trading permissions."""
from __future__ import annotations
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import time
import pandas as pd
from engine import prepare

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "prices"
META_PATH = ROOT / "data" / "update_status.json"
DEFAULT_TICKERS = "FPT,HPG,VCB,MBB,TCB,ACB,MWG,VNM,SSI,PNJ,DGC,VHM"
DEFAULT_START = "2021-01-01"


def parse_symbols(value: str) -> list[str]:
    sym = [s.strip().upper() for s in value.replace(";", ",").split(",")]
    unique = list(dict.fromkeys(s for s in sym if s))
    if not unique or len(unique) > 40 or any(not s.isalnum() or len(s) > 7 for s in unique):
        raise ValueError("Chọn từ 1–40 mã hợp lệ, phân cách bằng dấu phẩy")
    return unique


def update_prices(symbols: list[str], start: str = DEFAULT_START) -> dict:
    """Full refresh prevents mixing differently back-adjusted historical prices.

    Requires an Internet connection and vnstock 5.x installed locally.
    Existing CSVs are retained when a provider call fails; never silently
    substitute generated prices for real ones.
    """
    try:
        from vnstock import Market
    except ImportError as exc:
        raise RuntimeError("Chưa cài vnstock 5. Chạy install_windows.bat hoặc pip install theo README.") from exc
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    api = Market()
    end = (datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date() + timedelta(days=1)).isoformat()
    status = {"attempted_at": datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(),
              "source": "vnstock Market() / VCI", "start": start, "end": end,
              "success": {}, "errors": {}}
    for ticker in ["VNINDEX"] + [s for s in symbols if s != "VNINDEX"]:
        try:
            asset = api.index("VNINDEX") if ticker == "VNINDEX" else api.equity(ticker)
            try:
                raw = asset.ohlcv(start=start, end=end, interval="1D", source="vci")
            except TypeError:
                raw = asset.ohlcv(start=start, end=end, interval="1D")
            cleaned = prepare(raw)
            if len(cleaned) < 30:
                raise ValueError("Quá ít nến giá (<30)")
            out = raw.copy()
            out.columns = [str(c).strip().lower() for c in out.columns]
            if "time" not in out.columns and "date" in out.columns:
                out = out.rename(columns={"date": "time"})
            output_cols = ["time", "open", "high", "low", "close", "volume"]
            csv_path = DATA_DIR / f"{ticker}.csv"
            temp = csv_path.with_suffix(".tmp")
            out[output_cols].to_csv(temp, index=False)
            temp.replace(csv_path)
            status["success"][ticker] = {"last_session": cleaned.index.max().date().isoformat(),
                                         "rows": int(len(cleaned))}
        except Exception as exc:
            status["errors"][ticker] = str(exc)[:300]
        time.sleep(0.12)
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def load_prices(symbols: list[str]):
    frames = {}
    missing = []
    for s in ["VNINDEX"] + [x for x in symbols if x != "VNINDEX"]:
        p = DATA_DIR / f"{s}.csv"
        if not p.exists():
            missing.append(s)
            continue
        try:
            frames[s] = prepare(pd.read_csv(p))
        except Exception:
            missing.append(s)
    if "VNINDEX" not in frames:
        return {}, None, missing
    index = frames.pop("VNINDEX")
    return frames, index, missing


def last_status() -> dict:
    if not META_PATH.exists():
        return {}
    try:
        return json.loads(META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
