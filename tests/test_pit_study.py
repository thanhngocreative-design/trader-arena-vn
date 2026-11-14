"""Selection/valuation causality and parity; fixtures are never published."""
import numpy as np
import pandas as pd
import pytest
from pit_universe import monthly_memberships
from collect_pit_daily import valid_rows
from pit_minute_data import wide_features
from minute_arena import features,new_accounts,step
from value_intraday import minute_features
from pit_context import PITContext
from engine import Settings,TRADERS
from value_investing import ROOT,read

def prices(index,price=10_000,volume=100_000):
    return pd.DataFrame(dict(open=price,high=price,low=price,close=price,volume=volume),index=index)

def test_monthly_selection_ignores_future_survival_and_return():
    calendar=pd.bdate_range('2021-01-01','2024-01-31')
    a=prices(calendar,volume=200_000);b=prices(calendar,volume=300_000);c=prices(calendar,volume=100_000)
    full={'AAA':a,'BBB':b,'CCC':c}
    before=monthly_memberships(full,calendar,'2023-01-01','2023-03-31',2)
    # The highest prior liquidity company can disappear after January. It must
    # still be selected in January; no full-window continuity/survival filter.
    changed={'AAA':a.copy(),'BBB':b.loc[:'2023-01-09'].copy(),'CCC':c.copy()}
    changed['CCC'].loc['2023-01-02':,'close']*=100
    after=monthly_memberships(changed,calendar,'2023-01-01','2023-03-31',2)
    assert before[0]==after[0] and before[0]['members']==['BBB','AAA']
    assert 'BBB' not in after[-1]['members']
    assert all(r['asof']<r['effective'] for r in after)

def test_new_listing_needs_only_prior_history_not_future_history():
    calendar=pd.bdate_range('2021-01-01','2024-12-31')
    f={'OLD':prices(calendar),'NEW':prices(calendar[calendar>='2023-01-02'],volume=300_000)}
    months=monthly_memberships(f,calendar,'2023-02-01','2024-03-31',2)
    assert 'NEW' not in months[0]['members'] and 'NEW' in months[-1]['members']

def test_zero_volume_and_bad_rows_quarantined_not_whole_stock():
    f=prices(pd.bdate_range('2023-01-02',periods=5)).reset_index(names='date')
    f.loc[1,'volume']=0;f.loc[2,'low']=20_000
    assert valid_rows(f).tolist()==[True,False,False,True,True]

def test_wide_features_equal_original_core_and_value_features_with_gaps():
    rng=np.random.default_rng(937);times=pd.date_range('2023-01-03 09:15',periods=160,freq='min')
    raw={}
    for j,s in enumerate(('AAA','BBB','CCC')):
        index=times.delete(np.arange(j+10,70,11));c=20_000+np.cumsum(rng.normal(0,60,len(index)))
        f=pd.DataFrame(dict(open=c,high=c+30,low=c-30,close=c,volume=rng.integers(5000,100_000,len(index))),index=index)
        raw[s]=f
    symbols,wide=wide_features(raw)
    for j,s in enumerate(symbols):
        expected=features(raw[s]);value=minute_features(raw[s]);n=len(expected)
        for k in TRADERS:np.testing.assert_array_equal(wide[k][:n,j],expected[k].to_numpy())
        for k in ('Buffett','Munger'):np.testing.assert_array_equal(wide[k][:n,j],value[k].to_numpy())
        for k in ('atr','adv','ma10','ma20','low20'):np.testing.assert_allclose(wide[k][:n,j],expected[k].to_numpy(),rtol=1e-12,equal_nan=True)
        for k in TRADERS:assert not wide[k][n:,j].any()

def test_stale_reserve_is_not_market_price_or_trade():
    calendar=pd.bdate_range('2021-01-04',periods=400);f=prices(calendar[:330]);benchmark=prices(calendar)
    ctx=PITContext({'AAA':f},benchmark,[],Settings(),static=['AAA']);i=ctx.pos['AAA']
    before=ctx.mark_info(i,340);after=ctx.mark_info(i,350)
    assert before['value_price']==10_000 and before['price']==10_000
    assert after['value_price']==0 and after['price']==10_000 and after['quote_date']==str(calendar[329].date())
    assert ctx.reserve_value(i,350,100)==1_000_000
    assert np.isnan(ctx.a['close'][i,350])  # no fabricated zero candle

def test_pending_minute_order_cannot_fill_zero_volume_candle():
    a=new_accounts();b=a['Darvas'];t=pd.Timestamp('2023-01-03 10:00')
    b['pending']['AAA']=dict(side='BUY',qty=100,budget=10_000_000,signal=(t-pd.Timedelta(minutes=1)).isoformat(),submitted=t.isoformat(),adv=10_000_000_000)
    row=dict(open=10_000.,close=10_000.,volume=0.,adv=10_000_000_000.,atr=100.,ma10=10_000.,ma20=10_000.,low20=9500.)
    step(a,'AAA',row,t,0,{})
    assert not b['trades'] and b['cash']==100_000_000

def test_published_months_real_tickers_full_ledgers_and_source_snapshots():
    import hashlib
    p=read(ROOT/'site/research-300.json');cfg=read(ROOT/'config/research-300.json');meta=read(ROOT/'config/market-classification.json')
    assert p['status']=='complete' and p['mode']=='real_market_data' and p['sessions']>=747
    assert p['execution_revision']=='strict_next_candle_v1'
    assert len(p['months'])>=37 and p['unique_symbols']==len(set(p['union_symbols']))
    assert set(cfg['eligible_symbols'])<=set(p['union_symbols'])
    for month in p['months']:
        assert len(month['members'])==len(set(month['members']))==300 and month['asof']<month['effective']
        assert all(meta['listing'][s]['type']=='STOCK' for s in month['members'])
    assert len(p['retained_delisted_in_research'])==11
    assert 497<=p['minute_audit']['research_symbols_with_bars']<=p['unique_symbols']
    baseline=ROOT/'site/backtest-archive/2026-11-12/research-300.json'
    original=read(baseline) if baseline.exists() else p
    assert original['minute_audit']['no_in_window_trades_consistent_daily']==['SJF']
    assert set(p['union_symbols'])=={s for row in p['months'] for s in row['members']}
    assert p['execution_audit']['status']=='all_fills_verified_against_real_bars'
    count=0
    for name,cohort in p['cohorts'].items():
        for mode,key in [('daily','backtests'),('minute','minute_backtests'),('combo','hybrid_backtests')]:
            assert len(cohort[key])==len(p.get('bot_ids',range(13)))
            for bot,r in cohort[key].items():
                assert r['sector_stats']['buy_fills']==r['buy_count'] and r['sector_stats']['sell_fills']==r['closed_trades']
                n=r['buy_count']+r['closed_trades'];assert n==p['execution_audit']['fills_by_book'][f'{name}:{mode}:{bot}'];count+=n
    assert p['execution_audit']['total_fills']==count
    assert p['frozen_146_snapshot_sha256']==hashlib.sha256((ROOT/'site/research-146.json').read_bytes()).hexdigest()
