"""Temporary engine fixtures; never published as market observations."""
import json
import pandas as pd
import pytest
import numpy as np
from hybrid_backtest import _walk_one
from tests.test_hybrid_backtest import fixtures


def test_combo_resume_matches_uninterrupted_cash_fills_curve_and_holdings():
    ctx,tape=fixtures();first=len(ctx.dates)-8;split=first+3;last=len(ctx.dates)-1
    whole=_walk_one(ctx,'Darvas',tape,first,last,ctx.settings,export_state=True)
    early=_walk_one(ctx,'Darvas',tape,first,split,ctx.settings,export_state=True)
    saved=json.loads(json.dumps(early['resume_state'],allow_nan=False))
    assert saved['positions'], 'Exercise an open position across the restart'
    # A resumed engine only receives newly banked minute candles.
    future={s:f.loc[f.index>=ctx.dates[split+1]] for s,f in tape.items()}
    resumed=_walk_one(ctx,'Darvas',future,split+1,last,ctx.settings,initial_state=saved,export_state=True)
    pd.testing.assert_frame_equal(whole['curve'],resumed['curve'])
    pd.testing.assert_frame_equal(whole['trades'],resumed['trades'])
    pd.testing.assert_frame_equal(whole['holdings'],resumed['holdings'])
    assert whole['cash']==resumed['cash']
    assert whole['resume_state']==resumed['resume_state']
    with pytest.raises(ValueError,match='next benchmark'):
        _walk_one(ctx,'Darvas',future,split+2,last,ctx.settings,initial_state=saved)


def test_minute_resume_matches_full_run_with_only_new_session_tapes(tmp_path,monkeypatch):
    import pit_intraday
    from pit_intraday import run_minute
    from value_investing import read
    ctx,tape=fixtures();first=len(ctx.dates)-8;split=first+3
    ctx.allowed=np.ones_like(ctx.buy['Darvas']);ctx.a['sma200']=ctx.a['sma100'].copy()
    ctx.execution_liquidity=lambda i,t:(float(ctx.a['value20_prev'][i,t]),float(ctx.a['vol20_prev'][i,t]))
    canonical=pit_intraday.wide_features
    def forced_entry(frames):
        symbols,arrays=canonical(frames)
        arrays['Darvas'][25:]=True
        return symbols,arrays
    monkeypatch.setattr(pit_intraday,'wide_features',forced_entry)
    cfg=dict(start=str(ctx.dates[first].date()),end=str(ctx.dates[-1].date()))
    partial={**cfg,'end':str(ctx.dates[split].date())}
    run_minute({'test':ctx},tape,{},cfg,tmp_path/'full')
    run_minute({'test':ctx},tape,{},partial,tmp_path/'partial')
    state=read(tmp_path/'partial/minute-checkpoint.json')
    assert state['accounts']['test']['minute']['Darvas']['positions']
    new_tape={s:f.loc[f.index>=ctx.dates[split+1]] for s,f in tape.items()}
    run_minute({'test':ctx},new_tape,{},cfg,tmp_path/'resumed',initial_state=state)
    full=read(tmp_path/'full/minute-checkpoint.json');resumed=read(tmp_path/'resumed/minute-checkpoint.json')
    for key in ('accounts','curves','marks','seen','seq'):assert full[key]==resumed[key]
    assert read(tmp_path/'full/minute-test.json')==read(tmp_path/'resumed/minute-test.json')
    run_minute({'test':ctx},{}, {},cfg,tmp_path/'complete',initial_state=full)
    assert read(tmp_path/'complete/minute-test.json')==read(tmp_path/'full/minute-test.json')
    state['curves']['test']['minute']['Darvas'][0]['date']='1999-01-01'
    with pytest.raises(ValueError,match='calendar changed'):
        run_minute({'test':ctx},new_tape,{},cfg,tmp_path/'bad',initial_state=state)


def test_manifest_allows_new_dates_but_rejects_rewritten_source_membership_and_models(tmp_path):
    from copy import deepcopy
    import hashlib
    from backtest_state import verify_manifest,options
    raw=tmp_path/'source.gz';raw.write_bytes(b'unit fixture only')
    rows={'300':[dict(effective='2026-11-02',members=['FPT'])]}
    saved=dict(last_session='2026-11-12',model_sha256='model',calendar=['2026-11-12'],
        memberships=rows,input_sha256={'source.gz':hashlib.sha256(raw.read_bytes()).hexdigest()})
    dates=pd.to_datetime(['2026-11-12','2026-11-13'])
    verify_manifest(saved,dates,rows,market=tmp_path,model='model')
    with pytest.raises(ValueError,match='Strategy changed'):
        verify_manifest(saved,dates,rows,market=tmp_path,model='changed')
    changed=deepcopy(rows);changed['300'][0]['members']=['HPG']
    with pytest.raises(ValueError,match='membership changed'):
        verify_manifest(saved,dates,changed,market=tmp_path,model='model')
    raw.write_bytes(b'changed')
    with pytest.raises(ValueError,match='market input changed'):
        verify_manifest(saved,dates,rows,market=tmp_path,model='model')
    periods=options('2026-11-13')
    assert periods[0]['start']=='2026-08-13' and periods[-1]['start']=='2023-11-12'
    assert all(p['end']=='2026-11-13' for p in periods)
