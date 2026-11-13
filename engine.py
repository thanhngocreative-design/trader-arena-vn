"""Trader Arena VN — educational daily-bar paper-backtesting engine.

The strategies are rule-based approximations of *publicly described* approaches,
not reverse-engineered or authenticated trade histories of named individuals.
All transaction amounts are VND. The adapter supplies equity input prices in 1,000 VND.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict
import numpy as np
import pandas as pd

TRADERS = {
    "Minervini": {
        "name": "Mark Minervini", "emoji": "🚀",
        "tag": "Săn cổ phiếu tăng mạnh", "region": "US", "flag": "🇺🇸",
        "explain": "Chờ cổ phiếu có xu hướng dài hạn đi lên, rồi mua khi vượt đỉnh 20 phiên với khối lượng tăng.",
        "detail": "Bộ lọc Trend Template giản lược + breakout 20 phiên; chưa mô phỏng VCP, RS rank hoặc phân tích cơ bản.",
    },
    "ONeil": {
        "name": "William O’Neil", "emoji": "🔍",
        "tag": "Săn cú bứt phá", "region": "US", "flag": "🇺🇸",
        "explain": "Tìm cổ phiếu phá đỉnh 55 phiên với khối lượng lớn, khi VN-Index còn trên xu hướng trung hạn.",
        "detail": "Chỉ mô phỏng tín hiệu breakout/volume và market filter; không phải chiến thuật CAN SLIM đầy đủ.",
    },
    "Darvas": {
        "name": "Nicolas Darvas", "emoji": "📦",
        "tag": "Vượt hộp giá", "region": "US", "flag": "🇺🇸",
        "explain": "Mua cổ phiếu vượt vùng giá cao 55 phiên, rồi đi theo xu hướng và thoát khi phá hỗ trợ.",
        "detail": "Mô hình hộp Darvas xấp xỉ bằng rolling high/low, chưa tái tạo chính xác cách Darvas tự xác định hộp.",
    },
    "BNF": {
        "name": "Takashi Kotegawa (BNF)", "emoji": "🎯", "region": "JP", "flag": "🇯🇵",
        "tag": "Săn cổ phiếu bị bán quá đà",
        "explain": "Tìm cổ phiếu rơi xa dưới giá trung bình 25 phiên nhưng bắt đầu ngừng giảm, kỳ vọng một nhịp hồi ngắn.",
        "detail": "Mean reversion giản lược: lệch dưới SMA25 từ 10%, phiên đóng cửa hồi và có thanh khoản. Mốc 10% là giả thuyết cho VN, không phải ngưỡng BNF sử dụng cố định.",
        "source": "https://h9nfp.com/bnf/",
    },
    "CIS": {
        "name": "CIS", "emoji": "⚡", "region": "JP", "flag": "🇯🇵",
        "tag": "Đi theo đà tăng ngắn hạn",
        "explain": "Mua khi cổ phiếu tăng vượt vùng giá 10 phiên, hướng đi chung đang thuận lợi và nhiều người giao dịch.",
        "detail": "Trend-following proxy cho tư duy giao dịch ngắn hạn của CIS; không có bộ RSI/MACD hoặc tham số chính thức được xác thực.",
        "source": "https://diamond.jp/zai/articles/-/197112",
    },
    "Qullamaggie": {
        "name": "Kristjan Kullamägi (Qullamaggie)", "emoji": "🏄", "region": "EU", "flag": "🇸🇪",
        "tag": "Tăng mạnh rồi bứt phá tiếp",
        "explain": "Tìm cổ phiếu đã tăng mạnh, nghỉ trong biên độ tương đối hẹp rồi vượt đỉnh ngắn hạn.",
        "detail": "Proxy cho setup Breakout: momentum 60 phiên, vùng tích lũy 10 phiên, khối lượng xác nhận. Không mô phỏng điểm mua intraday hoặc Episodic Pivot.",
        "source": "https://qullamaggie.com/my-3-timeless-setups-that-have-made-me-tens-of-millions/",
    },
    "Unger": {
        "name": "Andrea Unger", "emoji": "🧠", "region": "EU", "flag": "🇮🇹",
        "tag": "Breakout có kiểm soát biến động",
        "explain": "Chỉ mua khi giá vượt đỉnh 20 phiên, thị trường đang thuận lợi và biến động không quá hỗn loạn.",
        "detail": "Mô hình thử nghiệm breakouts + ATR/volatility filter theo triết lý hệ thống; Unger chủ yếu giao dịch futures nên đây không phải chiến thuật cổ phiếu gốc.",
        "source": "https://ungeracademy.com/blog/the-trading-edge",
    },
    "ThaiPham": {
        "name": "Thái Phạm", "emoji": "🌊", "region": "VN", "flag": "🇻🇳",
        "tag": "Đọc dòng tiền theo VSA",
        "explain": "Quan sát giá đi lên cùng khối lượng mạnh sau giai đoạn tích lũy, giả định lực mua đang trở lại.",
        "detail": "Mô hình nghiên cứu VSA/Wyckoff: thân nến tăng, đóng gần đỉnh ngày, khối lượng > 1,4 lần bình quân, vượt vùng giá gần. Chỉ là proxy của học thuyết được Thái Phạm phổ biến; không phải các lệnh thật hoặc phương pháp riêng được ông xác nhận.",
        "source": "https://www.youtube.com/watch?v=r_SSPGd88mE",
    },
    "DuongChung": {
        "name": "Dương Văn Chung", "emoji": "🪃", "region": "VN", "flag": "🇻🇳",
        "tag": "Tìm nhịp hồi từ vùng giảm sâu",
        "explain": "Tìm cổ phiếu từng giảm mạnh, xuất hiện dấu hiệu ngừng rơi và bắt đầu tăng trở lại.",
        "detail": "Proxy mean-reversion theo chu kỳ: giảm tối thiểu 15% từ đỉnh 60 phiên, RSI 14 ở vùng yếu, phiên giá hồi. Ngưỡng số là giả thuyết riêng của Arena, không chứng minh ông dùng các công thức này.",
        "source": "https://www.google.com/search?q=D%C6%B0%C6%A1ng+V%C4%83n+Chung+ch%E1%BB%A9ng+kho%C3%A1n",
    },
    "PThai": {
        "name": "Phạm Nguyễn Hồng Thái (P.Thai Capital)", "emoji": "🧮", "region": "VN", "flag": "🇻🇳",
        "tag": "Định lượng theo đà và kiểm soát rủi ro",
        "explain": "Chọn cổ phiếu đang có đà tăng tốt, thanh khoản đủ lớn và biến động vừa phải khi thị trường chung tích cực.",
        "detail": "Proxy đa yếu tố kỹ thuật momentum/ATR/risk-filter, KHÔNG tái tạo mô hình V20 hay P.Thai Quant Score có thêm dữ liệu cơ bản và đánh giá point-in-time.",
        "source": "https://pthaicapital.io.vn/en/methodology",
    },
    "Hybrid": {
        "name": "Arena Hybrid · Adaptive Mix", "emoji": "🧬", "region": "MIX", "flag": "🌍",
        "tag": "Trộn các chiến thuật dẫn đầu gần đây",
        "explain": "Chọn tối đa ba mô hình đã có lợi nhuận dương trong 126 phiên trước đó, giảm điểm nếu lỗ sâu; chỉ mua khi có tín hiệu phù hợp từ nhóm được chọn.",
        "detail": "Chọn walk-forward với kết quả CHỈ đến phiên trước. Cứ 21 phiên cập nhật nhóm; cần tối thiểu 126 phiên huấn luyện. Nếu không mô hình nào đủ tốt, bot giữ tiền mặt. Đây là bot do Arena tạo, không phải chiến thuật của bất kỳ cá nhân nào.",
    },
}

@dataclass(frozen=True)
class Settings:
    initial_cash: float = 100_000_000
    fee_rate: float = 0.0015             # 0.15% each way
    sell_tax: float = 0.001              # 0.1% on gross selling value
    slippage: float = 0.0015             # conservative base per side, not a waived fee
    max_positions: int = 4
    portfolio_policy: str = 'baseline'
    risk_fraction: float = .0075
    atr_multiple: float = 2.5
    lot: int = 100
    min_average_value: float = 3_000_000_000  # liquidity gate, point-in-time
    cooldown_sessions: int = 7           # wait after sale to avoid fee churn
    minimum_hold_sessions: int = 5        # never sell before VN T+2.5 settlement
    min_price: float = 5_000.0
    min_expected_edge_cost_multiple: float = 2.5
    max_daily_participation: float = 0.005 # <=0.5% of recent daily volume


def prepare(raw: pd.DataFrame) -> pd.DataFrame:
    """OHLCV input: price in thousands VND; output price in VND."""
    if raw is None or raw.empty:
        raise ValueError("Dữ liệu OHLCV rỗng")
    df = raw.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "time" not in df.columns and "date" in df.columns:
        df = df.rename(columns={"date": "time"})
    required = {"time", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Thiếu cột {sorted(missing)}")
    df["date"] = pd.to_datetime(df["time"], errors="coerce", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None).dt.normalize()
    # CSV can instead contain date-only naive strings; those are parsed as UTC and
    # converted to 07:00 VN, still the same calendar date.
    for k in ("open", "high", "low", "close", "volume"):
        df[k] = pd.to_numeric(df[k], errors="coerce")
    df = df.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    df = df[(df["open"] > 0) & (df["close"] > 0) & (df["volume"] >= 0)]
    df = df.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    for k in ("open", "high", "low", "close"):
        df[k] *= 1000  # Vnstock quote unit: 1,000 Vietnamese dong
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def make_features(df: pd.DataFrame, benchmark: pd.DataFrame, min_average_value: float = 3_000_000_000) -> pd.DataFrame:
    p = df.copy()
    c, h, lo, v = p["close"], p["high"], p["low"], p["volume"]
    for n in (10, 20, 25, 50, 100, 150, 200):
        p[f"sma{n}"] = c.rolling(n, min_periods=n).mean()
    p["high10_prev"] = h.rolling(10, min_periods=10).max().shift(1)
    p["high20_prev"] = h.rolling(20, min_periods=20).max().shift(1)
    p["low10_prev"] = lo.rolling(10, min_periods=10).min().shift(1)
    prev_close = c.shift(1)
    true_range = pd.concat([(h-lo).abs(), (h-prev_close).abs(), (lo-prev_close).abs()],axis=1).max(axis=1)
    p["atr14"] = true_range.rolling(14, min_periods=14).mean()
    # Consolidation uses only the 10 bars BEFORE signal day, not today's high/low.
    p["range10_prev"] = p["high10_prev"] / p["low10_prev"] - 1
    p["mom5"] = c / c.shift(5) - 1
    p["close_prev1"] = c.shift(1)
    p["sma20_prev1"] = c.shift(1).rolling(20).mean().shift(1)
    p["mom20"] = c / c.shift(20) - 1
    change = c.diff()
    gain = change.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    p["rsi14"] = (100 - 100/(1+rs)).fillna(100)
    p["high60_prev"] = h.rolling(60, min_periods=60).max().shift(1)
    p["sma25"] = c.rolling(25, min_periods=25).mean()
    candle_span = (h-lo).replace(0, np.nan)
    p["close_location"] = ((c-lo)/candle_span).fillna(.5)
    p["high55_prev"] = h.rolling(55, min_periods=55).max().shift(1)
    p["low15_prev"] = lo.rolling(15, min_periods=15).min().shift(1)
    p["low252"] = lo.rolling(252, min_periods=252).min()
    p["high252"] = h.rolling(252, min_periods=252).max()
    p["vol20_prev"] = v.rolling(20, min_periods=20).mean().shift(1)
    p["value20_prev"] = (c * v).rolling(20, min_periods=20).mean().shift(1)
    p["momentum60"] = c / c.shift(60) - 1
    b_close = benchmark["close"].reindex(p.index).ffill()
    p["rs60"] = p["momentum60"] - (b_close / b_close.shift(60) - 1)
    p["range20_prev"] = h.rolling(20).max().shift(1) / lo.rolling(20).min().shift(1) - 1
    b = benchmark["close"].reindex(p.index).ffill()
    bma = b.rolling(50, min_periods=50).mean()
    p["market_ok"] = (b > bma).fillna(False)
    p["liq_ok"] = (p["value20_prev"] >= min_average_value) & (p["vol20_prev"] > 0) & (c >= 5_000)

    trend = (c > p["sma50"]) & (p["sma50"] > p["sma150"]) & (p["sma150"] > p["sma200"]) \
        & (p["sma200"] > p["sma200"].shift(21)) & (c >= p["low252"] * 1.30) \
        & (c >= p["high252"] * .75)
    p["buy_Minervini"] = trend & (c > p["high20_prev"]) & (v > p["vol20_prev"] * 1.20) \
        & (p["rs60"] > .02) & p["market_ok"]
    p["buy_ONeil"] = (c > p["sma50"]) & (c > p["high55_prev"]) \
        & (v > p["vol20_prev"] * 1.4) & (p["rs60"] > .03) \
        & (p["close_location"] > .6) & p["market_ok"]
    p["buy_Darvas"] = (c > p["sma100"]) & (c > p["high55_prev"]) \
        & (v > p["vol20_prev"] * 1.15) & (p["rs60"] > 0) \
        & (p["range20_prev"] < .40)
    # BNF proxy: oversold mean-reversion, distinct from breakout systems.
    p["buy_BNF"] = (c <= p["sma25"] * .90) & (c > c.shift(1)) \
        & (p["close_location"] > .58) & (p["rsi14"] > 26) \
        & (v > p["vol20_prev"] * .85) & (p["market_ok"] | (b > b.shift(5)))
    # CIS proxy: follow a strong short-term move instead of anticipating a reversal.
    p["buy_CIS"] = (c > p["sma10"]) & (p["sma10"] > p["sma20"]) \
        & (p["sma20"] > p["sma50"]) & (c > p["high10_prev"]) \
        & (p["rs60"] > .03) & (p["momentum60"] > .10) \
        & (v > p["vol20_prev"] * 1.2) & p["market_ok"]
    # Qullamaggie proxy: momentum continuation after a compact consolidation.
    p["buy_Qullamaggie"] = (p["momentum60"] > .25) & (p["range10_prev"] < .18) \
        & (c > p["high10_prev"]) & (c > p["sma20"]) \
        & (p["rs60"] > .08) & (v > p["vol20_prev"] * 1.25) & p["market_ok"]
    # Unger proxy: mechanical breakout gated by volatility.
    p["buy_Unger"] = (c > p["high20_prev"]) & (c > p["sma50"]) \
        & (p["atr14"] / c.shift(1) < .055) & (p["atr14"] / c.shift(1) > .009) \
        & (v > p["vol20_prev"] * 1.05) & p["market_ok"]
    # Vietnamese educational strategy proxies (not verified personal order histories).
    p["buy_ThaiPham"] = (c > p["sma25"]) & (c > p["high20_prev"]) \
        & (p["close_location"] > .78) & (v > p["vol20_prev"] * 1.4) \
        & (c > p["open"]) & p["market_ok"]
    p["buy_DuongChung"] = (c < p["high60_prev"] * .85) \
        & (p["rsi14"] > 30) & (p["rsi14"] < 49) \
        & (c > c.shift(1)) & (p["close_location"] > .6) \
        & (v > p["vol20_prev"] * .85)
    p["buy_PThai"] = (p["momentum60"] > .15) \
        & (p["rs60"] > .02) & (c > p["sma50"]) & (p["sma50"] > p["sma100"]) \
        & ((p["atr14"] / c) >= .01) & ((p["atr14"] / c) <= .055) \
        & (v > p["vol20_prev"] * .9) & p["market_ok"]
    # Hybrid's signals require other strategies' *prior* out-of-sample NAVs.
    # They are built by fast_engine after preparing the entire market context.
    p["buy_Hybrid"] = False
    for key in TRADERS:
        p[f"buy_{key}"] = (p[f"buy_{key}"] & p["liq_ok"]).fillna(False)
    return p


def stop_signal(trader: str, yesterday: pd.Series, position: dict) -> tuple[bool, str]:
    close = yesterday.get("close", np.nan)
    if pd.isna(close):
        return False, ""
    if trader == "Minervini":
        if close < position["price"] * 0.93:
            return True, "Giảm quá 7% từ giá mua"
        if close < yesterday.get("sma20", np.nan):
            return True, "Giá dưới đường trung bình 20 phiên"
    if trader == "ONeil":
        if close < position["price"] * 0.92:
            return True, "Giảm quá 8% từ giá mua"
        if close < yesterday.get("sma20", np.nan):
            return True, "Giá dưới đường trung bình 20 phiên"
    if trader == "Darvas":
        if close < position["high_water"] * 0.88:
            return True, "Giá giảm 12% so với đỉnh khi đang giữ"
        if close < yesterday.get("low15_prev", np.nan):
            return True, "Giá phá đáy 15 phiên"
    if trader == "BNF":
        if close <= position["price"] * .93:
            return True, "Hồi không thành, giảm hơn 7% từ giá mua"
        if close >= yesterday.get("sma25", np.nan) * .98:
            return True, "Giá đã hồi về gần trung bình 25 phiên"
        if close >= position["price"] * 1.06:
            return True, "Giá đã tăng 6% so với lúc mua"
    if trader == "CIS":
        if close < position["price"] * .94:
            return True, "Dừng lỗ 6%"
        # Avoid exiting on a one-day whipsaw in a rising market.
        if close < yesterday.get("sma10", np.nan) and yesterday.get("close_prev1", np.inf) < yesterday.get("sma20_prev1", -np.inf):
            return True, "Hai nhịp giảm xác nhận đà tăng suy yếu"
    if trader == "Qullamaggie":
        if close < position["price"] * .93 or close < yesterday.get("sma20", np.nan):
            return True, "Mất xu hướng 20 phiên hoặc lỗ quá 7%"
    if trader == "Unger":
        atr = yesterday.get("atr14", np.nan)
        if close < yesterday.get("sma20", np.nan):
            return True, "Giá xuống dưới trung bình 20 phiên"
        if pd.notna(atr) and close < position["high_water"] - 2.5 * atr:
            return True, "Giá giảm quá 2,5 lần biến động ATR từ đỉnh"
    if trader == "ThaiPham":
        if close < position["price"] * .93 or close < yesterday.get("sma25", np.nan):
            return True, "Dấu hiệu dòng tiền suy yếu hoặc lỗ quá 7%"
    if trader == "DuongChung":
        if close < position["price"] * .92:
            return True, "Nhịp hồi thất bại, lỗ quá 8%"
        if close >= yesterday.get("sma25", np.nan) * .98:
            return True, "Giá hồi về gần trung bình 25 phiên"
        if close >= position["price"] * 1.10:
            return True, "Chốt thử ở mức tăng 10%"
    if trader == "PThai":
        if close < position["price"] * .94 or close < yesterday.get("sma50", np.nan):
            return True, "Rủi ro xu hướng tăng hoặc lỗ quá 6%"
    if trader == "Hybrid":
        atr = yesterday.get("atr14", np.nan)
        if close < position["price"] * .92:
            return True, "Hybrid: giảm hơn 8% so với điểm mua"
        if pd.notna(atr) and close < position["high_water"] - 3 * atr:
            return True, "Hybrid: mất hơn 3 ATR từ đỉnh"
        if close < yesterday.get("sma50", np.nan):
            return True, "Hybrid: giá yếu hơn trung bình 50 phiên"
    return False, ""


def backtest(prices: Dict[str, pd.DataFrame], benchmark: pd.DataFrame,
             trader: str, start_date: str, end_date: str | None = None,
             settings: Settings | None = None, features_cache: dict | None = None) -> dict:
    settings = settings or Settings()
    if trader not in TRADERS:
        raise ValueError("Trader không được hỗ trợ")
    if not prices or benchmark is None or benchmark.empty:
        raise ValueError("Cần dữ liệu giá cổ phiếu và VN-Index")
    from portfolio import for_bot, allocation as position_budget
    settings = for_bot(settings, trader)
    if not (settings.max_positions > 0 and settings.lot > 0 and settings.initial_cash > 0):
        raise ValueError("Cài đặt vốn hoặc số lượng vị thế không hợp lệ")

    bench = benchmark.sort_index().copy()
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) if end_date else bench.index.max()
    dates = bench.index[(bench.index >= start) & (bench.index <= end)]
    if len(dates) < 1:
        raise ValueError("Khoảng mô phỏng cần ít nhất một phiên thị trường")
    # Large universes use a vectorized research engine. Existing callers
    # with plain DataFrame fixtures retain this reference implementation.
    if getattr(features_cache, "fast_context", False):
        from fast_engine import run_backtest
        return run_backtest(features_cache, trader, start_date, end_date, settings)
    features = features_cache if features_cache is not None else {
        s: make_features(frame, bench, settings.min_average_value).reindex(bench.index)
        for s, frame in prices.items() if len(frame) >= 100
    }
    if not features:
        raise ValueError("Dữ liệu cổ phiếu chưa đủ dài để tính chiến thuật")

    cash = settings.initial_cash
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    nav_rows: list[dict] = []
    actions: list[dict] = []
    for i, date in enumerate(dates):
        prior = bench.index[bench.index.get_loc(date)-1] if bench.index.get_loc(date) > 0 else None
        # At open: yesterday's complete daily candle is known, today's candle is not.
        prior_rows: dict = {}
        today_rows: dict = {}
        for s, data in features.items():
            if date in data.index:
                today_rows[s] = data.loc[date]
            if prior is not None and prior in data.index:
                prior_rows[s] = data.loc[prior]

        for s, pos in positions.items():
            if s not in prior_rows:
                continue
            row = prior_rows[s]
            if pd.notna(row["high"]):
                pos["high_water"] = max(pos["high_water"], float(row["high"]))
            exit_now, reason = stop_signal(trader, row, pos)
            if exit_now and not pos.get("exit_pending"):
                pos["exit_pending"] = reason

        # Execute sells first. Conservative T+2 settlement: earliest next *open*
        # after the T+2 afternoon, i.e. trade index >= buy_index + 3.
        for s, pos in list(positions.items()):
            if not pos.get("exit_pending") or i - pos["buy_index"] < 3:
                continue
            row = today_rows.get(s)
            if row is None or pd.isna(row["open"]) or row["volume"] <= 0:
                continue
            sell_price = float(row["open"]) * (1 - settings.slippage)
            gross = sell_price * pos["qty"]
            fees = gross * settings.fee_rate
            tax = gross * settings.sell_tax
            proceeds = gross - fees - tax
            cash += proceeds
            pnl = proceeds - pos["buy_cost"]
            trades.append({"date": date.date().isoformat(), "trader": trader, "symbol": s,
                "side": "BÁN", "qty": pos["qty"], "price": round(sell_price), "gross": round(gross),
                "fees": round(fees), "tax": round(tax), "pnl": round(pnl),
                "reason": pos["exit_pending"], "signal_date": prior.date().isoformat() if prior is not None else "",
                "buy_date": pos["date"].date().isoformat()})
            del positions[s]

        # Execute yesterday's buy signals at today's open; rank by past 60d return.
        opportunities = []
        for s, row in prior_rows.items():
            if s in positions or s not in today_rows:
                continue
            if bool(row.get(f"buy_{trader}", False)) and pd.notna(row["momentum60"]):
                opportunities.append((float(row["momentum60"]), s))
        opportunities.sort(key=lambda x: (-x[0], x[1]))
        for _score, s in opportunities:
            if len(positions) >= settings.max_positions:
                break
            row = today_rows[s]
            row_y = prior_rows[s]
            if pd.isna(row["open"]) or float(row["open"]) <= 0 or row["volume"] <= 0:
                continue
            buy_price = float(row["open"]) * (1 + settings.slippage)
            nav_open = cash + sum(
                p["qty"] * float(today_rows[z]["open"] if z in today_rows and pd.notna(today_rows[z]["open"]) else p["price"])
                for z, p in positions.items())
            allocation = position_budget(settings, cash, nav_open, buy_price, row_y["atr14"])
            max_shares = int(float(row_y["vol20_prev"]) * settings.max_daily_participation)
            max_by_budget = int(allocation / (buy_price * (1 + settings.fee_rate)))
            qty = min(max_shares, max_by_budget)
            qty = (qty // settings.lot) * settings.lot
            if qty < settings.lot:
                continue
            gross = buy_price * qty
            fee = gross * settings.fee_rate
            cost = gross + fee
            if cost > cash + 0.001:
                continue
            cash -= cost
            positions[s] = {"qty": qty, "price": buy_price, "buy_cost": cost,
                "date": date, "buy_index": i, "high_water": buy_price, "exit_pending": ""}
            trades.append({"date": date.date().isoformat(), "trader": trader, "symbol": s,
                "side": "MUA", "qty": qty, "price": round(buy_price), "gross": round(gross),
                "fees": round(fee), "tax": 0, "pnl": np.nan,
                "reason": "Tín hiệu sau đóng cửa hôm trước", "signal_date": prior.date().isoformat() if prior is not None else "",
                "buy_date": date.date().isoformat()})

        # End-of-day mark-to-market: never force-liquidate at the final close.
        invested = 0.0
        for s, p in positions.items():
            row = today_rows.get(s)
            px = float(row["close"]) if row is not None and pd.notna(row["close"]) else p["price"]
            invested += p["qty"] * px
        nav_rows.append({"date": date, "nav": cash + invested, "cash": cash, "invested": invested,
                         "position_count": len(positions)})

    curve = pd.DataFrame(nav_rows).set_index("date")
    curve["return_pct"] = (curve["nav"] / settings.initial_cash - 1) * 100
    curve["drawdown_pct"] = (curve["nav"] / curve["nav"].cummax() - 1) * 100
    bench_close = bench["close"].reindex(curve.index).ffill()
    curve["benchmark_nav"] = settings.initial_cash * bench_close / bench_close.iloc[0]
    curve["benchmark_return_pct"] = (curve["benchmark_nav"] / settings.initial_cash - 1) * 100

    trade_df = pd.DataFrame(trades)
    sold = trade_df[trade_df["side"] == "BÁN"] if not trade_df.empty else pd.DataFrame()
    total_closed = len(sold)
    wins = int((sold["pnl"] > 0).sum()) if total_closed else 0
    latest_date = curve.index[-1]
    last_prices = {s: float(features[s].loc[latest_date, "close"])
                   for s in positions if latest_date in features[s].index and pd.notna(features[s].loc[latest_date, "close"])}
    holdings = []
    for s, p in positions.items():
        last_price = last_prices.get(s, p["price"])
        market_value = p["qty"] * last_price
        profit = market_value - p["buy_cost"]
        holdings.append({"symbol": s, "qty": p["qty"], "buy_date": p["date"].date().isoformat(),
                         "buy_price": round(p["price"]), "last_price": round(last_price),
                         "value": round(market_value), "pnl": round(profit),
                         "pnl_pct": (market_value / p["buy_cost"] - 1) * 100,
                         "pending_exit": p.get("exit_pending", "")})

    for s, feat in features.items():
        if latest_date not in feat.index:
            continue
        row = feat.loc[latest_date]
        if pd.isna(row["close"]):
            continue
        if s in positions:
            exit_yes, reason = stop_signal(trader, row, positions[s])
            if positions[s].get("exit_pending"):
                actions.append({"symbol": s, "action": "CHỜ BÁN", "reason": positions[s]["exit_pending"]})
            elif exit_yes:
                actions.append({"symbol": s, "action": "THEO DÕI BÁN", "reason": reason})
            else:
                actions.append({"symbol": s, "action": "TIẾP TỤC GIỮ", "reason": "Chưa có tín hiệu thoát"})
        elif bool(row[f"buy_{trader}"]):
            actions.append({"symbol": s, "action": "TÍN HIỆU MUA", "reason": "Có tín hiệu sau đóng cửa, chưa khớp lệnh"})

    return {
        "trader": trader, "curve": curve, "trades": trade_df,
        "holdings": pd.DataFrame(holdings), "actions": pd.DataFrame(actions),
        "nav": float(curve["nav"].iloc[-1]), "cash": float(cash),
        "return_pct": float(curve["return_pct"].iloc[-1]),
        "benchmark_return_pct": float(curve["benchmark_return_pct"].iloc[-1]),
        "max_drawdown_pct": float(curve["drawdown_pct"].min()),
        "closed_trades": total_closed, "win_rate": (wins / total_closed * 100) if total_closed else None,
        "positions": len(positions), "last_date": latest_date.date().isoformat(),
        "buy_count": int((trade_df["side"] == "MUA").sum()) if not trade_df.empty else 0,
    }
