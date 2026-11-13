"""Temporary synthetic fixtures only; no fabricated market data is published."""
import pandas as pd
import pytest
from replay_rules import next_minute, can_fill
from minute_arena import step, new_accounts
from tests.test_minute_arena import row


@pytest.mark.parametrize('signal,fill,expected',[
    ('10:00','10:01',True),('10:00','10:02',False),
    ('11:29','13:00',False),('14:29','14:30',False),
    ('11:28','11:29',True),('13:00','13:01',True)])
def test_exact_continuous_clock(signal,fill,expected):
    assert can_fill('2026-11-12 '+signal,'2026-11-12 '+fill)==expected


def test_missing_fill_expires_but_later_candle_can_form_new_signal():
    a=new_accounts();marks={};ts=pd.Timestamp('2026-11-12 10:00')
    step(a,'FPT',row(),ts,0,marks)
    step(a,'FPT',row(),ts+pd.Timedelta(minutes=2),0,marks)
    assert not a['Minervini']['trades']
    assert a['Minervini']['pending']['FPT']['signal'].endswith('10:02:00')
    step(a,'FPT',row(False),ts+pd.Timedelta(minutes=3),0,marks)
    assert len(a['Minervini']['trades'])==1
    assert a['Minervini']['trades'][0]['signal_time'].endswith('10:02:00')


def test_combo_decisions_do_not_peek_at_next_observed_timestamp():
    from tests.test_hybrid_backtest import fixtures
    from hybrid_backtest import _walk_one
    ctx,frames=fixtures();first=len(ctx.dates)-8;last=len(ctx.dates)-1
    baseline=_walk_one(ctx,'Darvas',frames,first,last,ctx.settings)
    for _,trade in baseline['trades'].iterrows():
        assert can_fill(trade.signal_time,trade.time)
    buy=baseline['trades'].query("side == 'MUA'").iloc[0]
    altered={s:f.drop(pd.Timestamp(buy.time),errors='ignore') for s,f in frames.items()}
    changed=_walk_one(ctx,'Darvas',altered,first,last,ctx.settings)
    assert not any(t['signal_time']==buy.signal_time for t in changed['trades'].to_dict('records'))
