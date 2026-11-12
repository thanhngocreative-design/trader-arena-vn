"""Regression fixtures only; no fixture data is published as market history."""
from copy import deepcopy
import numpy as np
import pandas as pd
from engine import TRADERS
from minute_arena import features,darvas_features,exit_signal,new_accounts,step
from live.intraday import _exit_signal


def broken_floor_frame():
    ts=pd.date_range('2026-11-12 09:15',periods=35,freq='min')
    f=pd.DataFrame(dict(open=20000.,high=20100.,low=19900.,close=20000.,volume=100000),index=ts)
    f.loc[ts[-1],['low','close']]=[19700.,19800.]
    return f


def test_darvas_exits_on_prior_floor_break_without_a_ten_percent_loss():
    f=broken_floor_frame();row=features(f).iloc[-1]
    assert row['close']>20000*.9
    assert row['low20']==19900 and row['close']<row['low20']
    assert exit_signal('Darvas',row,20000)
    bars=f.rename(columns={'low':'l','high':'h'}).to_dict('records')
    assert _exit_signal('Darvas',19800,20000,bars)
    # Demonstrate why the former floor could never trigger on this candle.
    assert not row['close']<f.low.rolling(20).min().iloc[-1]
    accounts={'Darvas':new_accounts()['Darvas']};marks={}
    accounts['Darvas']['positions']['FPT']=dict(qty=100,price=20000,cost=2_003_000,session=0,date='2026-11-05')
    accounts['Darvas']['cash']=97_997_000
    step(accounts,'FPT',row.to_dict(),f.index[-1],5,marks)
    assert not accounts['Darvas']['trades']
    assert accounts['Darvas']['pending']['FPT']['side']=='SELL'
    step(accounts,'FPT',row.to_dict(),f.index[-1]+pd.Timedelta(minutes=1),5,marks)
    assert accounts['Darvas']['trades'][0]['side']=='BÁN'
    assert not accounts['Darvas']['positions']


def test_current_and_future_lows_cannot_change_prior_exit_floor():
    f=broken_floor_frame();before=features(f)
    f.iloc[-1,f.columns.get_loc('low')]=100
    assert features(f).low20.iloc[-1]==before.low20.iloc[-1]
    extended=pd.concat([f,f.iloc[-1:].set_axis([f.index[-1]+pd.Timedelta(minutes=1)])])
    pd.testing.assert_frame_equal(features(extended).iloc[:-1],features(f),check_freq=False)


def test_targeted_darvas_features_equal_full_engine_features():
    rng=np.random.default_rng(42);ts=pd.date_range('2026-11-12 09:15',periods=135,freq='min')
    c=20000*np.exp(np.cumsum(rng.normal(0,.004,len(ts))))
    f=pd.DataFrame(dict(open=c,high=c*1.003,low=c*.997,close=c,volume=rng.integers(1000,100000,len(ts))),index=ts)
    full=features(f);single=darvas_features(f)
    pd.testing.assert_frame_equal(single,full[single.columns])


def test_ten_other_bots_ignore_darvas_floor_in_full_portfolio_replay():
    keys=[k for k in TRADERS if k!='Darvas']
    original={k:v for k,v in new_accounts().items() if k in keys};fixed=deepcopy(original)
    marks_old={};marks_fixed={}
    for seq,date in enumerate(pd.bdate_range('2026-11-02',periods=8)):
        for j in range(35):
            ts=date+pd.Timedelta(hours=9,minutes=15+j)
            price=20000 if seq<5 else 17500
            row=dict(open=price,high=price+100,low=price-100,close=price,volume=100000,atr=300.,adv=10e9,ma10=20000.,ma20=20000.,low20=price-100,**{k:j>=30 for k in keys})
            changed={**row,'low20':25000.}
            for sym in ('FPT','ACB'):
                step(original,sym,row,ts,seq,marks_old)
                step(fixed,sym,changed,ts,seq,marks_fixed)
    assert original==fixed
    assert all(b['trades'] for b in fixed.values())
