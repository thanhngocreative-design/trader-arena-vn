import pandas as pd
import pytest
from vn30 import configuration,membership,context
from engine import Settings
from pit_context import PITContext
from paper_vn30 import verify_previous

def test_vn30_effective_dates_exclude_announced_future_members_and_reserves():
    c=configuration()
    for before,after,removed,added in [
        ('2025-01-24','2025-02-03',{'POW'},{'LPB'}),
        ('2025-08-01','2025-08-04',{'BVH'},{'DGC'}),
        ('2026-01-30','2026-02-02',{'BCM'},{'VPL'}),
        ('2026-05-12','2026-05-13',{'DGC'},{'BSR'}),
        ('2026-07-31','2026-08-03',{'PLX','TPB'},{'MCH','TCX'}),
    ]:
        old=membership(c,before);new=membership(c,after)
        assert old-new==removed and new-old==added
        assert len(old)==len(new)==30
    assert not membership(c,'2026-11-13')&{'VCK','BCM','GEE','VPX','PLX'}
    assert len(c['eligible_symbols'])==36
    with pytest.raises(ValueError,match='unavailable'):membership(c,'2021-01-01')

def test_vn30_training_uses_the_then_current_universe():
    c=configuration()
    assert {'NVL','PDR','KDH','PNJ'}<=membership(c,'2022-01-04')
    assert not {'SHB','SSB','MCH','TCX','VPL'}&membership(c,'2022-01-04')
    assert len(set(c['training_symbols']))==40

def test_official_membership_does_not_use_future_252_row_admission():
    # Small, temporary engine fixture; never published as market evidence.
    d=pd.bdate_range('2025-01-01',periods=300)
    f=pd.DataFrame(dict(open=10.,high=11.,low=9.,close=10.,volume=1000.),index=d)
    prices={'OLD':f,'NEW':f.tail(40)}
    rows=[dict(effective=str(d[-40].date()),members=['NEW'])]
    assert 'NEW' not in PITContext(prices,f,rows,Settings()).symbols
    c=PITContext(prices,f,rows,Settings(),min_history=1)
    assert not c.allowed[c.pos['NEW'],:-40].any()
    assert c.allowed[c.pos['NEW'],-40:].all()
    assert pd.isna(c.a['sma200'][c.pos['NEW']]).all()

def test_vn30_paper_freezes_used_membership_and_prior_trade_prefix():
    events=configuration()['months'];used=[r for r in events if r['effective']<='2026-11-13']
    old=[dict(date='2026-11-13',symbol='FPT',qty=100)]
    previous=dict(last_session='2026-11-13',membership_events=used,ledgers={'paper_minute:A':old})
    verify_previous(previous,{'paper_minute:A':old+[dict(date='2026-11-16',symbol='FPT',qty=100)]},events)
    with pytest.raises(ValueError,match='Prior VN30 paper trade'):
        verify_previous(previous,{'paper_minute:A':[dict(date='2026-11-13',symbol='FPT',qty=200)]},events)
    import copy
    changed=copy.deepcopy(events);changed[-1]['members'][0]='INVALID'
    with pytest.raises(ValueError,match='membership changed'):
        verify_previous(previous,{'paper_minute:A':old},changed)

def test_published_vn30_results_have_complete_independent_real_data_books():
    from value_investing import ROOT,read
    p=read(ROOT/'site/research-vn30.json');paper=read(ROOT/'site/paper-vn30.json');state=read(ROOT/'state/paper_vn30.json')
    assert p['minute_audit']['member_days']==747*30
    assert p['minute_audit']['member_days_with_minutes']==747*30
    assert p['execution_audit']['status']=='all_fills_verified_against_real_bars'
    assert len(p['execution_audit']['fills_by_book'])==39
    assert paper['season_start']=='2026-11-13'
    assert len(state['ledgers'])==39
    for mode in ('paper','paper_minute','paper_combo'):
        assert len(paper[mode])==13
        for bot,b in paper[mode].items():
            trades=state['ledgers'][mode+':'+bot]
            assert len(trades)==b['buy_count']+b['closed_trades']
            assert all(t['symbol'] in membership(configuration(),t['date']) for t in trades if t['side']=='MUA')
