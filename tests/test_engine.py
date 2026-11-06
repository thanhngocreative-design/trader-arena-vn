from datetime import date
import numpy as np
import pandas as pd
import pytest
from engine import Settings, backtest, make_features, prepare
from datafeed import parse_symbols


def data(n=420):
    idx = pd.bdate_range("2021-01-04", periods=n)
    # ~40% increase over first 300 bars: passes 252-low proximity filter.
    price = 12_000 * np.exp(.0014 * np.arange(n))
    volume = np.full(n, 2_000_000., dtype=float)
    volume[310] = 5_000_000
    volume[350] = 5_000_000
    price[312:] *= .90  # simulate drawdown / exit, holding T+2 must be respected
    df = pd.DataFrame({"open": price * 1.0001, "high": price * 1.0002,
                       "low": price * .999, "close": price, "volume":volume}, index=idx)
    bench = pd.DataFrame({"close": np.linspace(950, 1400, n)},index=idx)
    return df,bench


def test_prepare_thousand_dong_and_dates():
    raw = pd.DataFrame({"time": ["2026-10-06 07:00:00+07:00"],
        "open":[51.2],"high":[52.0],"low":[50.0],"close":[51.5],"volume":[12345]})
    df = prepare(raw)
    assert df.iloc[0]["close"] == 51_500
    assert df.index[0] == pd.Timestamp("2026-10-06")


def test_signal_is_previous_close_and_tplus3():
    price,bench = data()
    result = backtest({"FPT":price},bench,"Minervini", "2022-01-03",settings=Settings())
    log = result["trades"]
    assert not log.empty, "Synthetic uptrend should trigger a breakout"
    first_buy = log[log.side=="MUA"].iloc[0]
    signal = pd.Timestamp(first_buy["signal_date"])
    bought = pd.Timestamp(first_buy["date"])
    assert price.index.get_loc(bought) == price.index.get_loc(signal) + 1
    sells = log[log.side=="BÁN"]
    assert not sells.empty
    first_sell = sells.iloc[0]
    assert price.index.get_loc(pd.Timestamp(first_sell["date"])) >= price.index.get_loc(bought) + 3
    assert result["nav"] > 0
    assert np.isclose(result["curve"].iloc[-1]["nav"],result["nav"])


def test_no_lookahead_before_future_change():
    price,bench = data()
    earlier = backtest({"FPT":price},bench,"Darvas", "2022-01-03",end_date="2022-05-01")
    changed = price.copy()
    changed.loc[changed.index > "2022-05-01", "close"] *= 9
    changed.loc[changed.index > "2022-05-01", "high"] *= 9
    later = backtest({"FPT":changed},bench,"Darvas", "2022-01-03",end_date="2022-05-01")
    pd.testing.assert_frame_equal(earlier["curve"],later["curve"])


def test_unsupported_symbols_and_small_period():
    with pytest.raises(ValueError):
        parse_symbols("abc, *@*")
    price,bench = data()
    with pytest.raises(ValueError):
        backtest({"FPT":price},bench,"NotATrader","2022-01-03")
    with pytest.raises(ValueError):
        backtest({"FPT":price},bench,"Minervini","2020-01-01",end_date="2020-02-01")


def test_three_traders_have_valid_curves():
    price,bench = data()
    for name in ("Minervini", "ONeil", "Darvas"):
        r = backtest({"FPT":price},bench,name,"2022-01-03")
        assert r["last_date"] == bench.index[-1].date().isoformat()
        assert (r["curve"]["nav"] > 0).all()
        assert np.isfinite(r["return_pct"])
