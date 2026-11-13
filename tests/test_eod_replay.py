"""Synthetic engine fixtures are confined to pytest temporary directories."""
from datetime import datetime
import copy
import hashlib
import json
import pandas as pd
import pytest
import paper_replay as replay
from historical_minute import VN
from tests.test_hybrid_backtest import fixtures, sample_raw


def test_auction_only_tape_is_empty_but_invalid_candles_still_fail():
    raw=pd.DataFrame([dict(time='2026-11-02 14:45:00',open=10000,high=10000,low=10000,close=10000,volume=100)])
    assert replay.observed_minutes(raw).empty
    with pytest.raises(ValueError,match='Duplicate minute'):
        replay.observed_minutes(pd.concat([raw,raw]))
    with pytest.raises(ValueError,match='Impossible OHLCV'):
        replay.observed_minutes(raw.assign(low=12000))
    assert len(replay.observed_minutes(raw.assign(time='2026-11-02 09:30:00')))==1


def test_month_selection_cannot_see_later_rows_in_initial_daily_bank(tmp_path,monkeypatch):
    market=tmp_path/'market';market.mkdir()
    rows=[dict(date=d,open=10000,high=10000,low=10000,close=10000,volume=100) for d in ['2026-10-30','2026-11-02','2026-11-12']]
    replay.pack(market/'daily-history.json.gz',dict(prices={'FPT':rows},benchmark=rows))
    monkeypatch.setattr(replay,'MARKET',market)
    monkeypatch.setattr(replay,'START','2026-11-02')
    frozen=dict(month='2026-11',effective='2026-11-02',asof='2026-10-30',members=['FPT'])
    monkeypatch.setattr(replay,'read',lambda p:dict(months=[frozen],eligible_symbols=['FPT']))
    inspected=[]
    def selection(prices,calendar,**kwargs):
        assert prices['FPT'].index.max()==pd.Timestamp('2026-10-30')
        assert calendar[-2]==pd.Timestamp('2026-10-30')
        inspected.append(True)
        return [frozen]
    monkeypatch.setattr(replay,'monthly_memberships',selection)
    def stop(*args):raise RuntimeError('stop before requesting current-session data')
    monkeypatch.setattr(replay,'fetch_session',stop)
    with pytest.raises(RuntimeError,match='stop before'):
        replay.source_inputs('2026-11-02')
    assert inspected==[True]


def test_completed_cutoff_does_not_replay_unfinished_or_weekend_sessions():
    assert replay.completed_date(datetime(2026,11,13,15,59,tzinfo=VN))=='2026-11-12'
    assert replay.completed_date(datetime(2026,11,13,16,0,tzinfo=VN))=='2026-11-13'
    assert replay.completed_date(datetime(2026,11,15,18,0,tzinfo=VN))=='2026-11-13'


def test_published_replay_has_actual_season_scope_and_preserved_archives():
    p=replay.read(replay.PUBLIC)
    assert p['execution_revision']=='strict_next_candle_v1' and len(set(p['members']))==300
    assert all(set(p[m])==set(replay.BOTS) for m in ('paper','paper_minute','paper_combo'))
    if p['status']=='waiting_completed_session':
        assert p['last_session'] is None
        assert all(not b['trades'] and not b['history'] and b['nav']==100_000_000 for m in ('paper','paper_minute','paper_combo') for b in p[m].values())
    archive=replay.ROOT/'state/paper_archive/before-eod-replay-2026-11-13'
    for name,digest in replay.read(archive/'manifest.json').items():
        assert hashlib.sha256((archive/name.replace('/','__')).read_bytes()).hexdigest()==digest


def test_three_replay_books_are_idempotent_and_append_without_rewriting(tmp_path,monkeypatch):
    ctx,minute=fixtures();stock,benchmark=sample_raw();start=ctx.dates[-8];end=start
    config=dict(start=str(start.date()),end=str(end.date()),training_symbols=['FPT','HPG'],eligible_symbols=['FPT','HPG'],daily_input_sha256={},
        months=[dict(effective=str(ctx.dates[0].date()),asof=str((ctx.dates[0]-pd.Timedelta(days=1)).date()),members=['FPT','HPG'])])
    config['months'].append(dict(effective=str(start.replace(day=1).date()),asof=str((start.replace(day=1)-pd.Timedelta(days=1)).date()),members=['FPT','HPG']))
    (tmp_path/'config').mkdir()
    (tmp_path/'config/market-classification.json').write_text(json.dumps(replay.read(replay.ROOT/'config/market-classification.json')),encoding='utf8')
    market=tmp_path/'market';market.mkdir()
    replay.pack(market/'fixture.json.gz',dict(note='temporary synthetic source, never published'))
    for name,value in [('ROOT',tmp_path),('MARKET',market),('STATE',tmp_path/'ledger.json'),('PUBLIC',tmp_path/'public.json'),('OUTPUT_BASE',tmp_path/'o'),('START',str(start.date()))]:monkeypatch.setattr(replay,name,value)
    def inputs(until,collect):
        b=benchmark.loc[:until];prices={s:stock.loc[:until].copy() for s in ('FPT','HPG')}
        f={s:v.loc[:pd.Timestamp(until)+pd.Timedelta(days=1)].copy() for s,v in minute.items()}
        sessions=[str(d.date()) for d in b.index if d>=start]
        return prices,b,f,dict(config,end=until),{},sessions
    def context(prices,b,months,settings):
        from pit_context import PITContext
        c=PITContext(prices,b,months,settings)
        c.buy['Darvas'][:,-9:]=True;c.a['atr14'][:,-10:]=1150
        return c
    monkeypatch.setattr(replay,'source_inputs',inputs);monkeypatch.setattr(replay,'PITContext',context)
    now=datetime.combine(end.date(),datetime.min.time()).replace(hour=17,tzinfo=VN)
    first=replay.run(False,now);saved=copy.deepcopy(json.loads(replay.STATE.read_text()))
    assert len(first['paper']['Darvas']['history'])==1
    chart=json.loads((tmp_path/'site/replay-stocks/FPT.json').read_text())
    assert chart[-1][0]==str(end.date()) and chart[-1][4]==float(stock.loc[end,'close'])
    assert sum(first['paper_combo']['Darvas'][k] for k in ('buy_count','closed_trades'))>0
    again=replay.run(False,now)
    assert first==again and json.loads(replay.STATE.read_text())==saved
    later=ctx.dates[-6];replay.run(False,datetime.combine(later.date(),datetime.min.time()).replace(hour=17,tzinfo=VN))
    updated=json.loads(replay.STATE.read_text())
    for key,trades in saved['ledgers'].items():assert updated['ledgers'][key][:len(trades)]==trades
    # A changed retained source must block publication rather than alter history.
    replay.pack(market/'fixture.json.gz',dict(changed=True))
    with pytest.raises(ValueError,match='Frozen paper input changed'):replay.run(False,now)
