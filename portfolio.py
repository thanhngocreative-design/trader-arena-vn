"""Versioned research policy. ATR uses completed signal bars only."""
from dataclasses import replace
import math

# Research assumptions, not claims about the named traders' actual portfolios.
LIMITS = dict(Minervini=6, ONeil=7, Darvas=5, BNF=3, CIS=3,
              Qullamaggie=5, Unger=8, ThaiPham=6, DuongChung=4,
              PThai=8, Hybrid=6, Beginner=4, Intermediate=6, Pro=8)

def for_bot(settings, trader):
    if settings.portfolio_policy == 'baseline':
        return settings
    if settings.portfolio_policy != 'atr_v1':
        raise ValueError('Unknown portfolio policy')
    if not (0 < settings.risk_fraction <= .05 and settings.atr_multiple > 0):
        raise ValueError('Invalid risk parameters')
    return replace(settings, max_positions=LIMITS[trader])

def allocation(settings, cash, nav, price, atr):
    budget = min(cash, nav / settings.max_positions)
    if settings.portfolio_policy == 'baseline':
        return budget
    if not all(math.isfinite(float(x)) and float(x) > 0 for x in (nav, price, atr)):
        return 0.0
    # Notional cap: risk budget / ATR stop distance * entry price.
    # Fees included conservatively; lots and liquidity are capped by callers.
    risk_cap = nav * settings.risk_fraction * price / (
        settings.atr_multiple * atr + price * settings.fee_rate)
    return max(0.0, min(budget, risk_cap))
