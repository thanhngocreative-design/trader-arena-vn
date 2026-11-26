"""Mathematical fixtures stay in tests; published scenarios use verified NAV only."""
import numpy as np
import pytest
from monte_carlo import nav_returns,bootstrap_paths,group_summary
from monte_carlo_sources import checked_panel


def test_nav_anchor_and_zero_nav_are_explicit_not_interpolated():
    r=nav_returns([[90.,100.],[0.,100.],[0.,110.]],100)
    np.testing.assert_allclose(r,[[-.1,0],[-1,0],[0,.1]])
    for bad in ([[0.],[1.]],[[np.nan]], [[-1.]]):
        with pytest.raises(ValueError):nav_returns(bad,100)


def test_joint_blocks_are_contiguous_and_batch_independent():
    r=np.column_stack([np.arange(12)/1000,np.arange(12)/1000])
    a=bootstrap_paths(r,paths=9,horizon=12,block=3,seed=91,batch=2)
    b=bootstrap_paths(r,paths=9,horizon=12,block=3,seed=91,batch=7)
    np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(a[:,:,0],a[:,:,1])
    sampled=a[:,1:,0]/a[:,:-1,0]-1
    for start in range(0,12,3):np.testing.assert_allclose(np.diff(sampled[:,start:start+3],axis=1),.001,atol=1e-14)


def test_mix_is_fixed_accounts_not_daily_rebalanced_and_drawdown_includes_start():
    paths=np.array([[[1.,1.],[1.1,.9],[1.21,.81]]])
    result=group_summary(paths,[0,1],100)
    assert result['metrics']['return_p50_pct']==1
    loss=group_summary(np.array([[[1.],[.8],[.9]]]),[0],100)
    assert loss['metrics']['dd_p95_pct']==20 and loss['metrics']['dd20_probability_pct']==100
    assert loss['metrics']['loss_probability_pct']==100
    assert sum(b['count'] for b in loss['histogram'])==1
    assert all(row[1]<=row[2]<=row[3] for row in result['fan'])
    with pytest.raises(ValueError):group_summary(paths,[-1],100)


def test_source_panel_rejects_missing_dates_and_wrong_endpoint():
    book={'BOT':dict(nav=110.,buy_count=1,closed_trades=0,max_drawdown_pct=0)}
    args=('300:paper:ALL','paper','300','ALL',book)
    with pytest.raises(ValueError,match='Missing saved'):
        checked_panel(*args,{'BOT':[dict(date='2026-11-02',nav=100.)]},['2026-11-02','2026-11-03'],'model')
    with pytest.raises(ValueError,match='reconcile'):
        checked_panel(*args,{'BOT':[dict(date='2026-11-02',nav=99.)]},['2026-11-02'],'model')


def test_small_retained_real_nav_run_and_short_history_have_no_fake_probabilities(tmp_path):
    from paper_replay import unpack
    from monte_carlo_sources import CACHE
    from run_monte_carlo import build_scope
    if not CACHE.exists():pytest.skip('Complete verified analysis NAV cache is not available')
    panel=unpack(CACHE)['panels']['300:backtest_minute:ALL']
    settings=dict(paths=128,horizon=20,blocks=[5,10,20],primary_block=10,seed=73,min_sessions=252)
    result=build_scope(panel,'test-only-small-real-run',settings=settings,output=tmp_path/'site',scratch=tmp_path/'scratch')
    import json
    saved=json.loads((tmp_path/'site'/result['file']).read_text(encoding='utf8'))
    assert saved['status']=='ready' and saved['settings']['paths']==128
    for group in saved['groups'].values():
        assert group['fan'][0][1:]==[group['capital']]*3
        assert sum(b['count'] for b in group['histogram'])==128
    short={**panel,'dates':panel['dates'][:17],'nav':{b:n[:17] for b,n in panel['nav'].items()}}
    result=build_scope(short,'test-only-short-run',settings=settings,output=tmp_path/'short',scratch=tmp_path/'scratch')
    saved=json.loads((tmp_path/'short'/result['file']).read_text(encoding='utf8'))
    assert saved['status']=='insufficient_history' and saved['groups']=={}
