"""Synthetic unit tests only. NO fake minute prices enter the published dashboard."""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import pandas as pd
import pytest
from engine import Settings
from fast_engine import FastContext
from intraday_data import normalize_minute,load_minute
from hybrid_backtest import build_hybrid_backtests, _recent


def sample_raw(start="2026-10-20",periods=260):
    dates=pd.bdate_range(start,periods=periods)
    price=24000+np.arange(len(dates))*16
    stock=pd.DataFrame({"open":price-100,"high":price+200,
        "low":price-200,"close":price,"volume":np.full(len(dates),5_000_000)},index=dates)
    bench=pd.DataFrame({"open":1200+np.arange(len(dates))*.1,
        "high":1201+np.arange(len(dates))*.1,
        "low":1199+np.arange(len(dates))*.1,
        "close":1200+np.arange(len(dates))*.1,
        "volume":np.full(len(dates),50_000_000)},index=dates)
    return stock,bench


def minute_rows(day,base):
    start=pd.Timestamp(day)+pd.Timedelta(hours=9,minutes=15)
    data=[]
    for i in range(33):
        # Breakout first observable after 20 completed minutes.
        val=base*(1.019 if i>=20 else 1.0)
        data.append({"time":start+pd.Timedelta(minutes=i),
            "open":val,"high":val+12,"low":val-12,"close":val,
            "volume":40000 if i>=20 else 30000})
    return pd.DataFrame(data)


def fixtures():
    stock,bench=sample_raw()
    ctx=FastContext({"FPT":stock,"HPG":stock},bench)
    ctx.buy["Darvas"][:,-9:]=True
    ctx.buy["Hybrid"][:,-9:]=True
    ctx.a["atr14"][:,-10:]=1150
    minute=pd.concat([minute_rows(d.date(),float(stock.loc[d,"close"]))
                      for d in ctx.dates[-8:]],ignore_index=True)
    verified=normalize_minute(minute)
    return ctx,{"FPT":verified,"HPG":verified.copy()}


def test_minute_requires_explicit_unit_and_rejects_bad_candles():
    f=minute_rows(pd.Timestamp("2026-11-09"),25000)
    clean=normalize_minute(f)
    assert clean.index[0]==pd.Timestamp("2026-11-09T09:15:00")
    assert clean.iloc[0]["close"]==25000
    assert normalize_minute(f.assign(open=f["open"]/1000,
        high=f["high"]/1000,low=f["low"]/1000,close=f["close"]/1000),
        price_unit="thousand_vnd").iloc[0]["close"]==25000
    with pytest.raises(ValueError,match="Duplicate"):
        normalize_minute(pd.concat([f,f.iloc[:1]],ignore_index=True))
    with pytest.raises(ValueError,match="Impossible"):
        normalize_minute(f.assign(high=1))
    with pytest.raises(ValueError,match="unit"):
        normalize_minute(f,price_unit="unknown")


def test_auction_and_lunch_removed_and_not_silently_filled():
    f=minute_rows("2026-11-09",25000)
    extras=pd.DataFrame([
      {"time":"2026-11-09 09:00:00","open":25_000,"high":25_000,"low":25_000,"close":25_000,"volume":10000},
      {"time":"2026-11-09 12:00:00","open":25_000,"high":25_000,"low":25_000,"close":25_000,"volume":10000},
      {"time":"2026-11-09 14:45:00","open":25_000,"high":25_000,"low":25_000,"close":25_000,"volume":10000},
    ])
    valid=normalize_minute(pd.concat([f,extras],ignore_index=True))
    assert len(valid)==len(f)
    assert valid.index.max().hour==9


def test_missing_minute_history_never_relabelled_as_hybrid():
    stock,bench=sample_raw()
    ctx=FastContext({"FPT":stock},bench)
    values,audit=build_hybrid_backtests(ctx,{})
    assert not values and audit["status"]=="no_1m_data"
    few=normalize_minute(pd.concat([minute_rows(d.date(),float(stock.loc[d,"close"]))
                     for d in ctx.dates[-2:]],ignore_index=True))
    values,audit=build_hybrid_backtests(ctx,{"FPT":few})
    assert not values and audit["status"]=="insufficient_1m_history"


def test_no_lookahead_next_minute_fill_fees_lot_and_no_same_day_sale():
    ctx,minute=fixtures()
    results,audit=build_hybrid_backtests(ctx,minute)
    assert audit["status"]=="verified_1m_pilot"
    assert len(results)==11
    trades=results["Darvas"]["trades"]
    assert not trades.empty
    buys=trades.loc[trades["side"]=="MUA"]
    assert len(buys)>=1
    for _,x in buys.iterrows():
        assert pd.Timestamp(x["time"])>pd.Timestamp(x["signal_time"])
        assert x["fees"]>0
        assert x["qty"]%100==0
        assert x["qty"]<=2000  # 5% of preceding minute 40,000 shares
    sells=trades.loc[trades["side"]=="BÁN"]
    if not sells.empty:
        for _,x in sells.iterrows():
            assert pd.Timestamp(x["date"])>pd.Timestamp(x["buy_date"])
    assert np.isfinite(results["Darvas"]["nav"])


def test_price_mismatch_rejected_instead_of_converting_arbitrarily():
    with TemporaryDirectory() as d:
        minute=minute_rows("2026-11-09",25000)
        minute.to_csv(Path(d)/"FPT.csv",index=False)
        daily={"FPT":pd.DataFrame({"close":[45000.]},
                   index=pd.DatetimeIndex(["2026-11-09"]))}
        valid,error=load_minute(["FPT"],Path(d),daily)
        assert "FPT" not in valid
        assert "FPT" in error
        valid,error=load_minute(["FPT"],Path(d))
        assert "FPT" in valid


def test_no_future_bar_used_for_intraday_signal():
    f=normalize_minute(minute_rows("2026-11-09",25000))
    p=_recent(f)
    assert np.isnan(p.iloc[0]["high10_before"])
    assert p.iloc[20]["high10_before"]==pytest.approx(f.iloc[10:20]["high"].max())
    assert p.iloc[19]["vwap"]<=f.iloc[19]["high"]
