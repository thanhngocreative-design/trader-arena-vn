"""Artificial rule fixtures stay in tests, never in published market results."""
import numpy as np
import pandas as pd
from elliott_wave import entries
from minute_arena import features
from pit_minute_data import wide_features
from portfolio import LIMITS
import pytest


def test_confirmed_wave_two_then_breakout_not_pivot_date():
    c=pd.Series([105,104,103,100,103,106,110,115,120,116,112,108,110,112,114,118,121,123,124,125],dtype=float)
    signal=entries(c)
    assert np.flatnonzero(signal).tolist()==[16]
    assert not signal.iloc[11]  # Wave-2 low is not known at its own timestamp.
    assert LIMITS['Elliott']==5
    for end in range(1,len(c)+1):
        pd.testing.assert_series_equal(entries(c.iloc[:end]),signal.iloc[:end])
    for minute in [False,True]:
        changed=c.copy();changed.iloc[15:]=[90,150,60,180,120]
        pd.testing.assert_series_equal(entries(c,minute=minute).iloc[:15],entries(changed,minute=minute).iloc[:15])
    assert not entries(c*.0).any()
    assert not entries(pd.Series([100.]*50)).any()
    # A retracement below the wave-0 floor cannot qualify as wave 2.
    broken=c.copy();broken.iloc[11]=95
    assert not entries(broken).any()


def test_minute_scalar_wide_and_independent_columns_agree():
    rng=np.random.default_rng(407)
    index=pd.date_range('2026-11-02 09:15',periods=120,freq='min')
    c=25000*np.exp(np.cumsum(rng.normal(0,.003,120)))
    f=pd.DataFrame(dict(open=c,high=c*1.002,low=c*.998,close=c,volume=100000),index=index)
    short=f.iloc[:83].copy();short['close']*=1.1;short['high']*=1.1;short['low']*=1.1;short['open']*=1.1
    symbols,arrays=wide_features({'FPT':f,'HPG':short})
    for j,s in enumerate(symbols):
        tape={'FPT':f,'HPG':short}[s]
        np.testing.assert_array_equal(arrays['Elliott'][:len(tape),j],features(tape).Elliott.to_numpy())
    frame=pd.DataFrame({'FPT':f.close,'HPG':short.close})
    for s in frame:
        pd.testing.assert_series_equal(entries(frame,minute=True)[s],entries(frame[s],minute=True))


def test_one_time_upgrade_refuses_unreviewed_models(tmp_path,monkeypatch):
    import add_elliott as upgrade
    import json
    spec=tmp_path/'upgrade.json';state=tmp_path/'state';state.mkdir()
    spec.write_text(json.dumps(dict(previous_model_sha256='old',new_model_sha256='new')))
    (state/'manifest.json').write_text(json.dumps(dict(model_sha256='old')))
    monkeypatch.setattr(upgrade,'SPEC',spec);monkeypatch.setattr(upgrade,'STATE',state)
    monkeypatch.setattr(upgrade,'model_digest',lambda:'unreviewed')
    with pytest.raises(ValueError,match='Unreviewed'):upgrade.guard()
    monkeypatch.setattr(upgrade,'model_digest',lambda:'new')
    assert upgrade.guard()['model_sha256']=='old'
    (state/'manifest.json').write_text(json.dumps(dict(model_sha256='other')))
    with pytest.raises(ValueError,match='exact prior model'):upgrade.guard()
