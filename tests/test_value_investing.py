"""Timing, real-input reconciliation and forward-only accounting invariants."""
import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
import pandas as pd
import pytest
import value_investing as v
from value_fundamentals import report_available,parse_reports

ROOT=Path(__file__).resolve().parents[1]

def reports():
    # Synthetic unit fixtures only; never used in published research.
    return [dict(year=y,available_at=f'{y+1}-04-01',equity=100.,sales=100.,profit=25.,short_debt=10.,long_debt=0.,cfo=30.,capex=-5.) for y in range(2019,2023)]

def panel():
    dates=pd.bdate_range('2023-04-03',periods=9)
    f=pd.DataFrame(dict(open=10_000.,close=10_000.,high=10_000.,low=10_000.,volume=1_000_000.,ma200=11_000.,adv=10_000_000_000.,avol=1_000_000.),index=dates)
    return dates,{'AAA':f}

def test_publication_missing_dates_and_restatements_never_backdated():
    assert report_available({}) is None
    assert report_available({'publicDate':'bad'}) is None
    assert report_available({'publicDate':'2023-03-01','updateDate':'2026-03-20T11:30:00'})=='2026-03-21'
    assert report_available({'publicDate':'2023-03-01','createDate':'2023-03-02'})=='2023-03-03'
    assert parse_reports({}, {})==[]
    r=reports();assert v.quality(r,'2023-03-31','Buffett') is None
    assert v.quality(r,'2023-04-03','Buffett') is not None
    r[-1]['available_at']='2026-04-01'
    assert v.quality(r,'2023-04-03','Buffett') is None

def test_missing_unprofitable_stale_or_nonconsecutive_reports_excluded():
    for change in ('loss','cfo','capex','debt','equity','gap'):
        r=reports()
        if change=='loss':r[-1]['profit']=-1
        if change=='cfo':r[-1]['cfo']=-1
        if change=='capex':r[-1]['capex']=-40
        if change=='debt':r[-1]['short_debt']=200
        if change=='equity':r[-1]['equity']=0
        if change=='gap':r[-2]['year']=2018
        assert v.quality(r,'2023-04-03','Buffett') is None
    assert v.quality(reports(),'2026-04-03','Buffett') is None

def test_next_session_fill_with_costs_and_expiry():
    dates,prices=panel();b=v.empty_book()
    v.plan(b,prices,{'AAA':reports()},dates[0],'Buffett')
    assert not b['trades'] and b['pending'][0]['signal_date']=='2023-04-03'
    v.execute(b,prices,dates[1],'Buffett')
    t=b['trades'][0]
    assert t['date']=='2023-04-04' and t['price']>10_000 and t['fees']>0 and t['qty']%100==0
    assert b['cash']+b['positions']['AAA']['cost']==pytest.approx(100_000_000)
    assert t['financial_available_at']<t['date']
    expired=v.empty_book();v.plan(expired,prices,{'AAA':reports()},dates[0],'Buffett')
    v.execute(expired,prices,dates[2],'Buffett')
    assert not expired['trades'] and not expired['pending']

def test_holds_without_monthly_churn_and_settlement_guard():
    dates,prices=panel();b=v.empty_book();v.plan(b,prices,{'AAA':reports()},dates[0],'Munger');v.execute(b,prices,dates[1],'Munger')
    v.plan(b,prices,{'AAA':reports()},dates[2],'Munger')
    assert not b['pending']
    order=dict(symbol='AAA',side='SELL',signal_date=str(dates[2].date()),reason='fixture',financial_available_at=None)
    b['pending']=[order];v.execute(b,prices,dates[3],'Munger');assert len(b['trades'])==1
    b['pending']=[dict(order,signal_date=str(dates[7].date()))];v.execute(b,prices,dates[8],'Munger')
    assert b['trades'][-1]['tax']>0 and not b['positions']
    assert b['cash']==pytest.approx(100_000_000+sum(t['pnl'] or 0 for t in b['trades']))

def test_published_inputs_and_all_trade_counts_reconcile():
    d=v.read(ROOT/'site/value-investing.json');bundle=v.read(ROOT/'config/value-fundamentals.json')
    assert d['fundamentals']['sha256']==hashlib.sha256((ROOT/'config/value-fundamentals.json').read_bytes()).hexdigest()
    frozen=v.read(ROOT/'site/research-146.json')
    assert d['daily_input_sha256']==frozen['research_meta']['daily_input_sha256']
    sectors=v.read(ROOT/'config/market-classification.json')['sectors']
    eligible=v.eligible_companies(bundle,sectors)
    assert len(eligible)==d['fundamentals']['comparable_nonfinancial_companies']
    assert all(sectors[s]['icb_code'] not in ('8300','8500','8700') for s in eligible)
    for books in d['backtest_periods'].values():
        for bot,r in books.items():
            assert d['traders'][bot]['supported_modes']==['paper','backtest']
            assert r['sector_stats']['buy_fills']==r['buy_count']
            assert r['sector_stats']['sell_fills']==r['closed_trades']
            assert len(r['history'])==len(r['curve']) and r['history'][0]['nav']==100_000_000
            for t in r['trades']:
                assert t['signal_date']<t['date']
                if t['side']=='MUA':assert t['financial_available_at']<=t['signal_date']

def test_paper_enrollment_never_backfills_results_or_same_open(tmp_path,monkeypatch):
    dates,prices=panel();root=tmp_path
    for directory in ('config','site','data/value_fundamentals'): (root/directory).mkdir(parents=True,exist_ok=True)
    v.write(root/'config/market-classification.json',{'sectors':{'AAA':{'icb_code':'9500','sector':'IT'}}})
    v.write(root/'config/value-fundamentals.json',{'asof':'2023-04-03','companies':{'AAA':{'reports':reports()}}})
    v.write(root/'config/value-bots.json',{'Buffett':True,'Munger':True})
    v.write(root/'site/value-investing.json',{})
    monkeypatch.setattr(v,'ROOT',root);monkeypatch.setattr(v,'inputs',lambda:(['AAA'],prices))
    # Enrollment AFTER Tuesday's open must never claim that open retrospectively.
    v.update_paper(datetime(2023,4,4,10,tzinfo=v.VN))
    initial=v.read(root/'state/value_paper.json')
    assert all(not b['trades'] and not b['history'] for b in initial['bots'].values())
    v.update_paper(datetime(2023,4,4,17,tzinfo=v.VN))
    final=v.read(root/'state/value_paper.json')
    assert all(not b['trades'] and len(b['history'])==1 for b in final['bots'].values())
    v.update_paper(datetime(2023,4,4,18,tzinfo=v.VN))
    assert v.read(root/'state/value_paper.json')==final
