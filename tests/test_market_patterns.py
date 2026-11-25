"""Artificial fixtures test rules only; never published as trading results."""
import numpy as np
import pandas as pd
from market_patterns import entries, wyckoff_entries, ichimoku_entries, ichimoku_lines
from minute_arena import features
from pit_minute_data import wide_features


def test_spring_requires_later_confirmation_and_permanently_invalidates_on_new_low():
    close=pd.Series([100.]*35+[100.,102.,103.,104.,105.])
    high=close+1;low=close-1;volume=pd.Series([100.]*40)
    low.iloc[35]=98;high.iloc[35]=101;volume.iloc[36:]=150
    signal=wyckoff_entries(close,high,low,volume)
    assert np.flatnonzero(signal).tolist()==[36]
    assert not signal.iloc[35]
    broken=low.copy();broken.iloc[36]=97
    assert not wyckoff_entries(close,high,broken,volume).any()
    for n in range(30,len(close)+1):
        pd.testing.assert_series_equal(wyckoff_entries(close.iloc[:n],high.iloc[:n],low.iloc[:n],volume.iloc[:n]),signal.iloc[:n])


def test_ichimoku_uses_historical_cloud_and_never_backdates_chikou():
    close=pd.Series(np.linspace(100,150,110))
    high=close+1;low=close-1
    conversion,base,a,b=ichimoku_lines(high,low)
    assert conversion.iloc[8]==(high.iloc[:9].max()+low.iloc[:9].min())/2
    signal=ichimoku_entries(close,high,low)
    assert np.flatnonzero(signal).tolist()==[77]
    for n in range(70,111):
        pd.testing.assert_series_equal(ichimoku_entries(close.iloc[:n],high.iloc[:n],low.iloc[:n]),signal.iloc[:n])


def test_wide_and_scalar_paths_agree_and_future_edits_do_not_rewrite_signals():
    rng=np.random.default_rng(9403);index=pd.date_range('2026-11-02 09:15',periods=120,freq='min')
    close=25000*np.exp(np.cumsum(rng.normal(0,.002,120)))
    frame=pd.DataFrame(dict(open=close,high=close*1.002,low=close*.998,close=close,volume=100000.),index=index)
    tapes={'FPT':frame,'HPG':frame.iloc[:95]*1.1}
    symbols,arrays=wide_features(tapes)
    for j,symbol in enumerate(symbols):
        for bot in ('Wyckoff','Ichimoku'):
            np.testing.assert_array_equal(arrays[bot][:len(tapes[symbol]),j],features(tapes[symbol])[bot].to_numpy())
    full=entries(frame.close,frame.high,frame.low,frame.volume)
    changed=frame.copy();changed.iloc[95:]*=3
    altered=entries(changed.close,changed.high,changed.low,changed.volume)
    for bot in full:
        pd.testing.assert_series_equal(full[bot].iloc[:95],altered[bot].iloc[:95])


def test_upgrade_refuses_unrequested_tapes_for_historical_holdings(tmp_path,monkeypatch):
    import pytest
    import add_market_patterns as upgrade
    from value_investing import write
    from paper_replay import pack
    monkeypatch.setattr(upgrade,'ROOT',tmp_path)
    write(tmp_path/'site/paper-replay.json',dict(sessions=['2026-11-12','2026-11-13']))
    extension=dict(ledgers={'backtest:300':{'minute:Wyckoff':[
        dict(date='2026-11-12',symbol='TEST',qty=100,side='MUA')]}})
    with pytest.raises(ValueError,match='Unrequested post-baseline'):
        upgrade.audit_extension_coverage(extension)
    # A retained source receipt can legitimately contain no observed trades.
    pack(tmp_path/'state/replay_market/pattern-sessions/2026-11-13.json.gz',
         dict(requested_symbols=['TEST'],replies={'TEST':[]}))
    result=upgrade.audit_extension_coverage(extension)
    assert result['2026-11-13']['all_have_real_collection_receipts']
