"""Regression tests for broad VN equity research and causal Hybrid selection."""
import numpy as np
import pandas as pd
from engine import Settings, TRADERS, backtest
from execution import modeled_slippage, round_trip_cost_rate, pass_cost_gate
from fast_engine import CORE, FastContext, build_hybrid_signals
from datafeed import DEFAULT_TICKERS, parse_symbols
from test_engine import data


def test_universe_is_broad_but_does_not_invent_prices():
    universe=parse_symbols(DEFAULT_TICKERS)
    assert 120 <= len(universe) <= 210
    assert len(set(universe)) == len(universe)
    assert {"FPT","HPG","VCB","MWG","PNJ","SSI"}.issubset(universe)
    assert len(TRADERS)==11 and "Hybrid" in TRADERS


def test_cost_is_real_and_gets_worse_for_illiquid_orders():
    st=Settings()
    liquid=modeled_slippage(st,90_000_000_000,25_000_000)
    illiquid=modeled_slippage(st,1_500_000_000,25_000_000)
    assert liquid >= .0015
    assert illiquid > liquid
    assert round_trip_cost_rate(st,90_000_000_000,25_000_000)>=.007
    assert st.minimum_hold_sessions >= 3 and st.cooldown_sessions >= 5
    assert st.max_daily_participation <= .005
    assert pass_cost_gate(st,dict(atr14=800,close=10000,value20_prev=10e9),25e6)
    assert not pass_cost_gate(st,dict(atr14=10,close=10000,value20_prev=1e9),25e6)


def test_fast_core_matches_next_open_and_respects_tplus():
    price,bench=data(470)
    ctx=FastContext({"FPT":price},bench)
    r=backtest({"FPT":price},bench,"Minervini","2022-01-03",
               settings=ctx.settings,features_cache=ctx)
    assert r["nav"]>0 and np.isfinite(r["nav"])
    buys=r["trades"]
    if not buys.empty:
        for t in buys.to_dict("records"):
            if t["side"]=="MUA":
                signal=pd.Timestamp(t["signal_date"])
                fill=pd.Timestamp(t["date"])
                assert ctx.dates.get_loc(fill)==ctx.dates.get_loc(signal)+1
        first_buy={}
        for t in buys.to_dict("records"):
            if t["side"]=="MUA":first_buy[t["symbol"]]=t["date"]
            if t["side"]=="BÁN":
                assert ctx.dates.get_loc(pd.Timestamp(t["date"]))-ctx.dates.get_loc(pd.Timestamp(first_buy[t["symbol"]]))>=ctx.settings.minimum_hold_sessions


def test_hybrid_selection_does_not_peek_ahead():
    price,bench=data(470)
    ctx=FastContext({"FPT":price},bench)
    idx=ctx.dates
    base={}
    for i,k in enumerate(CORE):
        nav=100e6*(1+(0.001 if k=="Darvas" else -.0001)*np.arange(len(idx)))
        base[k]=pd.DataFrame({"nav":nav},index=idx)
    selection=build_hybrid_signals(ctx,base,training_bars=55,rebalance_bars=10)
    assert "Darvas" in selection["leaders_latest"]
    cutoff=len(idx)-70
    # Corrupt ONLY the future training NAVs and ensure all prior selections
    # and prior Hybrid buy signals stay bitwise identical.
    mutated={k:v.copy() for k,v in base.items()}
    mutated["CIS"].iloc[cutoff+1:,0] *= 70
    ctx2=FastContext({"FPT":price},bench)
    build_hybrid_signals(ctx2,mutated,training_bars=55,rebalance_bars=10)
    for t in range(55,cutoff+1):
        assert ctx.hybrid_winners[t]==ctx2.hybrid_winners[t]
    np.testing.assert_array_equal(ctx.buy["Hybrid"][:,:cutoff+1],ctx2.buy["Hybrid"][:,:cutoff+1])


def test_hybrid_cash_when_nobody_makes_positive_trailing_return():
    price,bench=data(370)
    ctx=FastContext({"FPT":price},bench)
    base={k:pd.DataFrame({"nav":100e6*(1-.0002*np.arange(len(ctx.dates)))},
                         index=ctx.dates) for k in CORE}
    build_hybrid_signals(ctx,base,training_bars=42,rebalance_bars=7)
    assert not ctx.buy["Hybrid"].any()
    assert ctx.hybrid_winners[len(ctx.dates)-1]=={}
