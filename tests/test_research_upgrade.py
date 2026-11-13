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
    assert len(TRADERS)==14 and "Hybrid" in TRADERS


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


def test_paper_fill_uses_prior_signal_cost_data_not_future_candle():
    from paper_forward import _execute
    bot={'cash':100_000_000.,'positions':{},'trades':[],
         'orders_next':[{'side':'BUY','symbol':'FPT','reason':'prior signal',
            'signal_date':'2026-11-05','vol20_prev':2_000_000,
            'atr14':1200.,'signal_close':30_000.,'value20_prev':10e9}]}
    # If the simulator were to evaluate today's completed candle, the
    # artificially tiny current ATR would incorrectly reject the fill.
    today={'FPT':pd.Series({'open':30_100.,'close':29_900.,
                           'volume':1_000_000.,'atr14':1.,'value20_prev':10e9})}
    events=_execute(bot,pd.Timestamp("2026-11-06"),350,today,Settings())
    assert len(events)==1
    assert events[0]['side']=='MUA'
    assert events[0]['qty']>=100
    assert events[0]['slippage_rate']>=Settings().slippage


def test_paper_cooldown_after_sell():
    from paper_forward import _execute
    st=Settings()
    bot={'cash':100_000_000.,'positions':{},'trades':[],
         'last_sold':{'FPT':345},
         'orders_next':[{'side':'BUY','symbol':'FPT','reason':'bounce',
             'vol20_prev':2_000_000,'atr14':1000.,
             'signal_close':30_000.,'value20_prev':20e9}]}
    now={'FPT':pd.Series({'open':30_000.,'close':30_000.,
                           'volume':2_000_000.,'value20_prev':20e9})}
    assert _execute(bot,pd.Timestamp("2026-11-06"),350,now,st)==[]
    assert not bot['positions']


def test_paper_buy_ranking_uses_relative_strength_not_raw_return():
    from paper_forward import _plans
    st=Settings()
    bot={'cash':100_000_000.,'positions':{},'orders_next':[]}
    common=dict(buy_CIS=True,atr14=1000.,close=30_000.,
                value20_prev=10e9,vol20_prev=2_000_000)
    rows={
        'AAA':pd.Series({**common,'momentum60':.45,'rs60':.01}),
        'BBB':pd.Series({**common,'momentum60':.16,'rs60':.25}),
    }
    plans=_plans(bot,'CIS',rows,{},pd.Timestamp('2026-11-06'),st)
    assert [p['symbol'] for p in plans]==['BBB','AAA']
