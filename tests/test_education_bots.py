"""Educational rule fixtures, kept out of published simulation results."""
import numpy as np
import pandas as pd
from education_bots import PROFILES,daily_signals,daily_exit
from engine import TRADERS,make_features
from fast_engine import CORE,FastContext
from portfolio import LIMITS
from tests.test_hybrid_backtest import sample_raw


def test_educational_signals_use_past_only_and_leave_original_hybrid_pool_fixed():
    stock,benchmark=sample_raw(periods=310)
    baseline=make_features(stock,benchmark)
    changed=stock.copy();changed.iloc[290:]*=2
    altered=make_features(changed,benchmark)
    for bot in PROFILES:
        pd.testing.assert_series_equal(baseline['buy_'+bot].iloc[:290],altered['buy_'+bot].iloc[:290])
        assert bot in TRADERS and bot not in CORE
    assert len(CORE)==10 and LIMITS['Beginner']==4 and LIMITS['Intermediate']==6 and LIMITS['Pro']==8
    ctx=FastContext({'FPT':stock},benchmark)
    for bot in PROFILES:np.testing.assert_array_equal(ctx.buy[bot][0],baseline['buy_'+bot])


def test_levels_have_distinct_predeclared_filters_and_exits():
    p=pd.DataFrame(dict(close=[110.,110.],volume=[150.,150.],sma20=[90.,105.],sma50=[100.,100.],
        sma100=[90.,90.],sma200=[80.,80.],high20_prev=[100.,100.],high55_prev=[100.,100.],
        vol20_prev=[100.,100.],rs60=[.06,.06],atr14=[2.,2.],market_ok=[True,True]))
    signals=daily_signals(p)
    assert signals['Beginner'].tolist()==[False,True]
    assert signals['Intermediate'].tolist()==[True,True] and signals['Pro'].tolist()==[True,True]
    p['market_ok']=False
    assert not daily_signals(p)['Intermediate'].any() and not daily_signals(p)['Pro'].any()
    position=dict(price=100.,high_water=110.)
    for bot in PROFILES:assert daily_exit(bot,dict(close=80.,sma20=95.,sma50=100.,atr14=2.),position)
