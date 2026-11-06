"""Shared conservative equity execution assumptions for backtest and paper replay.

Total costs are not 'optimized away': broker fee on both sides, sell-side
turnover tax, base fill slippage, plus an *extra* liquidity impact allowance.
This is a scenario model, not reconstructed level-2 bid/ask data.
"""
from __future__ import annotations
import math

def modeled_slippage(settings, average_daily_value: float, order_value: float) -> float:
    base=float(settings.slippage)
    adv=max(float(average_daily_value or 0), 1_000_000)
    order=max(float(order_value or 0), 0)
    # Cost is *never* less than the original 15bp/side baseline.
    # Low-liquidity stock or an order consuming a large share of ADV
    # receives an additional conservative penalty (up to ~100bp).
    liquidity_penalty=0.0006*max(0.0, math.sqrt(10_000_000_000/adv)-1.0)
    participation_penalty=0.025*min(0.05, order/adv)
    return min(0.0125, base+liquidity_penalty+participation_penalty)

def round_trip_cost_rate(settings, adv: float, order_value: float) -> float:
    slip=modeled_slippage(settings,adv,order_value)
    return 2*float(settings.fee_rate)+float(settings.sell_tax)+2*slip

def pass_cost_gate(settings, prev_row, order_value: float) -> bool:
    """Historical-bar ATR is a *volatility proxy*, not predicted profit."""
    atr=float(prev_row.get("atr14", float("nan")))
    close=float(prev_row.get("close", float("nan")))
    adv=float(prev_row.get("value20_prev", float("nan")))
    if not (close>0 and atr>0 and adv>0):
        return False
    swing_volatility=atr/close
    # Do not model swing trades whose recent daily ATR offers too little
    # price movement relative to costs; also reject runaway illiquidity.
    return (2.5*float(settings.min_expected_edge_cost_multiple)*0.4*
            round_trip_cost_rate(settings,adv,order_value) <= swing_volatility <= .095)
