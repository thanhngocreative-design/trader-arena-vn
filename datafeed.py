"""End-of-day Vietnam stock-market data adapter (real prices, no broker trading).

Uses vn-market-data: DNSE primary / Vietcap fallback, pinned to a public release.
Input prices are VND for equities and index points for VNINDEX. The existing
backtester expects prices in 1,000 VND, so equities are scaled down *once*
when storing CSV. No data is fabricated or extrapolated.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import time
import pandas as pd
from engine import prepare

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "prices"
META_PATH = ROOT / "data" / "update_status.json"
# Broad, fixed 2026 research candidate set.  It is NOT a historical VN100 membership list.
# Live OHLCV availability, long-enough history and point-in-time liquidity
# determine whether a candidate can actually enter an individual day's scan.
# 2026 survivors are still subject to survivorship bias in 2023 backtests.
PUBLIC_CANDIDATES = ["ACB","BID","CTG","DGC","FPT","GAS","GVR","HDB","HPG","LPB","MBB","MSN","MWG","PLX","SAB","SHB","SSB","SSI","STB","TCB","TPB","VCB","VHM","VIB","VIC","VJC","VNM","VPB","VRE","BCM","BVB","EIB","EVF","NAB","OCB","PGB","SGB","VAB","VBB","VIX","VND","VCI","HCM","FTS","BSI","CTS","ORS","AGR","APG","TVS","SHS","MBS","VDS","VFS","HSG","NKG","SMC","POM","HAH","HBC","CTD","CII","FCN","HHV","KBC","KSB","NTL","PHR","DPM","DCM","BFC","CSV","LAS","ANV","IDI","DIG","DXG","NLG","KDH","PDR","NVL","IDC","SZC","SIP","TCH","HQC","CEO","HDG","TAL","DXS","DXH","ITC","HDC","LHG","VPI","SCR","QCG","PVD","PVS","PVT","PVC","PVB","PGC","POW","NT2","REE","GEX","GEG","PC1","BSR","OIL","PVO","PVP","PPC","VSH","CHP","TMP","SJD","PNJ","DGW","PET","FRT","ELC","CMG","CTR","VGI","VTP","YEG","KDC","QNS","SBT","VHC","FMC","VNS","PAN","DBC","HAG","HNG","ACV","HVN","GMD","VSC","VOS","VTO","SCS","AST","SKG","TCL","VGC","VCG","VCS","KLB","BCG","TNG","TCM","MSH","GIL","VGT","DHC","BMP","NTP","DHA","DPG","DVP","DXP","TTA","BWE"]
DEFAULT_TICKERS = ",".join(PUBLIC_CANDIDATES)
MIN_USABLE = 70  # refuse to describe a failed broad-market scan as successful

DEFAULT_START = "2021-01-01"


def parse_symbols(value: str) -> list[str]:
    sym = [s.strip().upper() for s in value.replace(";", ",").split(",")]
    unique = list(dict.fromkeys(s for s in sym if s))
    if not unique or len(unique) > 210 or any(not s.isalnum() or len(s) > 7 for s in unique):
        raise ValueError("Chọn từ 1–210 mã hợp lệ, phân cách bằng dấu phẩy")
    return unique


def normalize_rows(rows, ticker: str) -> pd.DataFrame:
    """Normalize provider candles to the engine's documented thousand-VND unit."""
    out = pd.DataFrame(rows).copy()
    if out.empty:
        raise ValueError(f"Không có nến giá {ticker}")
    out.columns = [str(c).strip().lower() for c in out.columns]
    if "time" not in out.columns and "date" in out.columns:
        out = out.rename(columns={"date": "time"})
    columns = ["time", "open", "high", "low", "close", "volume"]
    if any(k not in out.columns for k in columns):
        raise ValueError(f"Thiếu cột OHLCV cho {ticker}: {list(out.columns)}")
    out = out[columns].copy()
    for k in columns[1:]:
        out[k] = pd.to_numeric(out[k], errors="coerce")
    if ticker != "VNINDEX":
        # vn-market-data returns FULL VND. engine.prepare() multiplies
        # by 1000 to restore VND, so CSV must hold thousands of VND.
        for k in ("open", "high", "low", "close"):
            out[k] = out[k] / 1000.0
    return out


def update_prices(symbols: list[str], start: str = DEFAULT_START) -> dict:
    try:
        from vn_market_data import get_ohlcv
    except ImportError as exc:
        raise RuntimeError("Chưa cài vn-market-data (xem requirements.txt)") from exc
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    days = max(400, (now.date() - pd.Timestamp(start).date()).days + 21)
    status = {"attempted_at": now.isoformat(), "source": "DNSE/Vietcap via vn-market-data v0.4.0",
              "start": start, "requested": len(symbols), "success": {}, "errors": {},
              "skipped": {}, "candidate_set_asof": "2026-11-06",
              "universe_note": "Research basket frozen in 2026; historic backtests may have survivorship bias."}
    for ticker in ["VNINDEX"] + [s for s in symbols if s != "VNINDEX"]:
        try:
            rows = get_ohlcv(ticker, lookback_days=days, is_index=(ticker == "VNINDEX"))
            out = normalize_rows(rows, ticker)
            clean = prepare(out)
            if len(clean) < 252:
                status["skipped"][ticker] = f"Chưa đủ 252 phiên lịch sử: {len(clean)}"
                continue
            # All tradable instruments must have a completed bar for the same
            # exchange session. Do not fill stale/suspended data forward.
            if ticker != "VNINDEX" and "VNINDEX" in status["success"]:
                last_index = status["success"]["VNINDEX"]["last_session"]
                if clean.index.max().date().isoformat() != last_index:
                    status["skipped"][ticker] = "Giá không cùng phiên VNINDEX"
                    continue
            csv_path = DATA_DIR / f"{ticker}.csv"
            temp = csv_path.with_suffix(".tmp")
            out.to_csv(temp, index=False)
            temp.replace(csv_path)
            status["success"][ticker] = {"last_session": clean.index.max().date().isoformat(),
                                         "rows": int(len(clean))}
        except Exception as exc:
            # A delisted/nonexistent or data-limited research candidate is not
            # allowed to silently become a valid data point.
            status["skipped" if ticker != "VNINDEX" else "errors"][ticker] = (
                type(exc).__name__ + ": " + str(exc))[:350]
        time.sleep(0.20)
    status["accepted"] = len(status["success"]) - int("VNINDEX" in status["success"])
    if "VNINDEX" not in status["success"]:
        status["errors"]["VNINDEX"] = "Không xác minh được VNINDEX"
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
