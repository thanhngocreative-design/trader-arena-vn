"""Causal minute/combo adapters; synthetic fixtures never leave temporary tests."""
from copy import deepcopy
from datetime import datetime
import pandas as pd
import pytest
import value_intraday as m
from minute_arena import new_accounts
from engine import TRADERS
from value_investing import ROOT,read

def bar(**overrides):
    return dict(dict(open=20_000.,close=20_000.,volume=100_000.,adv=10_000_000_000.,atr=200.,ma20=20_000.,ma10=20_000.,Buffett=True,Munger=True),**overrides)

def gates(combo=True):
    return {k:{'AAA':dict(available_at='2023-03-01',asof='2023-04-03',combo=combo)} for k in m.POLICY}

def test_quality_gates_are_required_and_combo_adds_prior_daily_gate():
    ts=pd.Timestamp('2023-04-04 10:00');marks={}
    a=m.empty_accounts();m.value_step(a,'AAA',bar(),ts,0,marks,{})
    assert all(not b['pending'] for b in a.values())
    minute=m.empty_accounts();combo=m.empty_accounts()
    m.value_step(minute,'AAA',bar(),ts,0,{},gates(False))
    m.value_step(combo,'AAA',bar(),ts,0,{},gates(False),combo=True)
    assert all(b['pending'] for b in minute.values())
    assert all(not b['pending'] for b in combo.values())
    assert set(new_accounts())==set(TRADERS) and len(new_accounts())==11

def test_future_bar_only_and_actual_money_reconciles_with_partial_exit():
    a=m.empty_accounts();marks={};t=pd.Timestamp('2023-04-04 10:00')
    m.value_step(a,'AAA',bar(),t,0,marks,gates(),submitted_at=t+pd.Timedelta(seconds=90))
    m.value_step(a,'AAA',bar(Buffett=False,Munger=False),t+pd.Timedelta(minutes=1),0,marks,gates())
    assert all(not b['trades'] for b in a.values())
    m.value_step(a,'AAA',bar(Buffett=False,Munger=False),t+pd.Timedelta(minutes=2),0,marks,gates())
    for k,b in a.items():
        trade=b['trades'][0]
        assert trade['side']=='MUA' and trade['quality_asof']=='2023-04-03'
        assert trade['financial_available_at']<trade['quality_asof']<trade['date']
        assert trade['price']>20_000 and trade['gross']==pytest.approx(trade['qty']*trade['price'])
        assert b['cash']+trade['gross']+trade['fees']==pytest.approx(100_000_000)
    # Failed quality cannot sell before settlement. Once settled, a later bar
    # fills the exit, including tax; cap can force a partial sale.
    before=deepcopy(a)
    m.value_step(a,'AAA',bar(Buffett=False,Munger=False),t+pd.Timedelta(minutes=3),1,marks,{})
    assert all(not b['pending'] for b in a.values())
    m.value_step(a,'AAA',bar(Buffett=False,Munger=False,volume=4000.),t+pd.Timedelta(minutes=4),5,marks,{})
    m.value_step(a,'AAA',bar(Buffett=False,Munger=False),t+pd.Timedelta(minutes=5),5,marks,{})
    for k,b in a.items():
        sell=b['trades'][-1];old=before[k]['positions']['AAA']
        assert sell['side']=='BÁN' and sell['qty']==200 and sell['tax']>0
        assert b['cash']-before[k]['cash']==pytest.approx(sell['gross']-sell['fees']-sell['tax'])
        assert sell['pnl']==pytest.approx(sell['gross']-sell['fees']-sell['tax']-old['cost']*sell['qty']/old['qty'])

def test_minute_indicators_never_see_future_bars():
    dates=pd.date_range('2023-04-04 09:15',periods=80,freq='min')
    c=pd.Series([20_000+(i%9)*10 for i in range(80)],index=dates)
    raw=pd.DataFrame(dict(open=c,high=c+20,low=c-20,close=c,volume=100_000),index=dates)
    before=m.minute_features(raw);changed=raw.copy();changed.loc[dates[55]:,'close']*=1.5
    after=m.minute_features(changed)
    pd.testing.assert_frame_equal(before.loc[:dates[54]],after.loc[:dates[54]])

def test_value_paper_publication_retains_empty_real_accounts_no_backfill(tmp_path):
    (tmp_path/'config').mkdir();(tmp_path/'site').mkdir()
    from value_investing import write
    write(tmp_path/'config/market-classification.json',{'sectors':{}})
    write(tmp_path/'config/research-universe.json',{'eligible_symbols':['AAA']})
    state=m.load_state(tmp_path,datetime(2023,4,4,10,tzinfo=m.VN))
    pub=m.publish(state,'market_closed',root=tmp_path)
    assert pub['last_observed_at'] is None and not pub['sessions']
    for mode in m.MODES:
        for b in pub[mode].values():
            assert b['nav']==100_000_000 and not b['trades'] and not b['history']
            assert b['max_drawdown_pct'] is None
    assert m.load_state(tmp_path)['started_at']==state['started_at']

def test_full_real_minute_results_have_separate_sources_and_reconcile_counts():
    v=read(ROOT/'site/value-investing.json');base=read(ROOT/'site/research-146.json');audit=v['intraday_backtest_audit']
    assert audit['sessions']==747 and audit['requested_symbols']==146
    assert audit['input_sha256']=={s:r['sha256'] for s,r in base['hybrid_backtest_audit']['coverage_by_symbol'].items()}
    for key in ('minute_backtests','hybrid_backtests'):
        assert set(v[key])=={'Buffett','Munger'}
        for r in v[key].values():
            assert len(r['curve'])==747
            assert r['buy_count']==r['sector_stats']['buy_fills']
            assert r['closed_trades']==r['sector_stats']['sell_fills']
            assert r['rules_revision']==m.REVISION
            for t in r['trades']:
                assert 60<=(pd.Timestamp(t['time'])-pd.Timestamp(t['signal_time'])).total_seconds()<=180
                if t['side']=='MUA':assert t['financial_available_at']<=t['quality_asof']<t['date']
