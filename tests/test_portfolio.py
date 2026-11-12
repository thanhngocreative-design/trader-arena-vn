from dataclasses import replace
import json
import math
from pathlib import Path
import pytest
from engine import Settings, TRADERS, backtest
from portfolio import allocation, for_bot, LIMITS
from fast_engine import FastContext
from test_engine import data

def test_limits_and_atr_risk_cash_concentration_caps():
    base=Settings()
    assert set(LIMITS)==set(TRADERS)
    assert for_bot(base,'BNF').max_positions==4
    st=for_bot(replace(base,portfolio_policy='atr_v1'),'BNF')
    assert st.max_positions==3 and base.max_positions==4
    low=allocation(st,100e6,100e6,30000,500)
    high=allocation(st,100e6,100e6,30000,2000)
    assert 0 < high < low <= 100e6/3
    assert high/30000*(2.5*2000+30000*st.fee_rate) <= 100e6*.0075+.001
    assert allocation(st,1000,100e6,30000,500)<=1000
    for bad in (0,-1,math.nan,math.inf):
        assert allocation(st,100e6,100e6,30000,bad)==0
    with pytest.raises(ValueError):
        for_bot(replace(st,risk_fraction=-.01),'BNF')

def test_fast_flexible_respects_limit_lots_cash_and_past_atr():
    # Synthetic fixture is for regression only; never published as market results.
    price,bench=data(470)
    prices={str(i):price.copy() for i in range(10)}
    st=replace(Settings(),portfolio_policy='atr_v1')
    ctx=FastContext(prices,bench,st)
    ctx.buy['BNF'][:]=True
    ctx.a['atr14'][:]=ctx.a['close']*.04
    ctx.a['vol20_prev'][:]=2_000_000
    ctx.a['value20_prev'][:]=50e9
    r=backtest(prices,bench,'BNF','2022-01-03',settings=st,features_cache=ctx)
    assert r['curve'].position_count.max()<=3
    assert r['curve'].cash.min()>=0
    assert not r['trades'].empty
    assert (r['trades']['qty']%st.lot==0).all()

def test_baseline_snapshot_keeps_original_ledger():
    root=Path(__file__).resolve().parents[1]
    baseline=json.loads((root/'state/paper_baseline.json').read_text(encoding='utf8'))
    current=json.loads((root/'state/paper_state.json').read_text(encoding='utf8'))
    if current.get('reset_id'):
        # A user-authorized season reset preserves the original ledger in its
        # immutable archive, rather than mixing it into the new competition.
        import hashlib
        archive=root/'state/paper_archive'/('before-'+current['contest_start_session'])
        saved=archive/'state__paper_state.json'
        manifest=json.loads((archive/'manifest.json').read_text(encoding='utf8'))
        assert hashlib.sha256(saved.read_bytes()).hexdigest()==manifest['sha256']['state/paper_state.json']
        for bot in current['bots'].values():
            assert all(h['date']>=current['contest_start_session'] for h in bot['history'])
            assert all(t['date']>=current['contest_start_session'] for t in bot['trades'])
        current=json.loads(saved.read_text(encoding='utf8'))
    for k,b in baseline['bots'].items():
        assert current['bots'][k]['trades'][:len(b['trades'])]==b['trades']
        assert current['bots'][k]['history'][:len(b['history'])]==b['history']
