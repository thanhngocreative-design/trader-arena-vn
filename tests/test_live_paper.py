"""Deterministic verification of the intraday quote-paper fill contract.

These synthetic quotes are NEVER published as live market quotes.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo
from types import SimpleNamespace as Obj

from engine import Settings,TRADERS
from live.paper import LivePaper, Book, market_phase, previous_business_day, VN
from live.feed import sdk_quote_to_book

def at(date_string):
    return datetime.fromisoformat(date_string).replace(tzinfo=VN)

def q(moment,receive=None,symbol="FPT",bid=29900,ask=30000,bid_qty=10000,ask_qty=10000,market_id="STO",board="G1"):
    t=at(moment)
    return Book(symbol=symbol,market_id=market_id,bid=bid,ask=ask,
        bid_qty=bid_qty,ask_qty=ask_qty,event_at=t,
        received_at=receive or t+timedelta(milliseconds=150),board_id=board)


def make_source(today):
    prev=previous_business_day(today.date())
    return {"last_session":prev.isoformat(),"bots":{
        "Darvas":{"orders_next":[{"side":"BUY","symbol":"FPT","reason":"daily breakout"}]},
        "CIS":{"orders_next":[{"side":"BUY","symbol":"HPG","reason":"short-term momentum"}]},
    }}


def test_friday_signal_is_queued_for_monday_without_backdated_fills():
    with TemporaryDirectory() as root:
        book=LivePaper(Path(root)/"p.sqlite")
        monday=at("2026-11-09T08:50:00")
        assert book.queue_eod(make_source(monday),monday)["queued"]==2
        assert book.queue_eod(make_source(monday),monday)["queued"]==0
        snap=book.snapshot()
        assert snap["bots"]["Darvas"]["nav"]==100_000_000
        assert len(snap["bots"]["Darvas"]["orders"])==1
        assert snap["recent_fills"]==[]
        book.close()


def test_no_auction_lunch_or_stale_early_quotes_and_idempotency():
    with TemporaryDirectory() as root:
        book=LivePaper(Path(root)/"p.sqlite")
        monday=at("2026-11-09T08:50:00")
        book.queue_eod(make_source(monday),monday)
        assert book.on_quote(q("2026-11-09T09:08:00")) is None
        assert book.on_quote(q("2026-11-09T12:00:00")) is None
        outdated=q("2026-11-09T09:15:02",receive=at("2026-11-09T09:15:21"))
        assert book.on_quote(outdated) is None
        no_liquidity=q("2026-11-09T09:16:00",ask_qty=0,bid_qty=0)
        assert book.on_quote(no_liquidity) is None
        first=book.on_quote(q("2026-11-09T09:16:03",ask_qty=10000))
        assert len(first)==1
        assert first[0]["bot"]=="Darvas"
        assert first[0]["price"]>30000  # crossed spread and modeled slippage
        assert book.on_quote(q("2026-11-09T09:16:03"))==[]
        assert book.on_quote(q("2026-11-09T09:16:40"))==[]
        snap=book.snapshot()
        assert len(snap["recent_fills"])==1
        assert snap["bots"]["Darvas"]["nav"]<100_000_000 # transaction friction is not removed
        book.close()


def test_ask_bid_depth_and_price_limits_require_real_book_event():
    with TemporaryDirectory() as root:
        book=LivePaper(Path(root)/"p.sqlite")
        monday=at("2026-11-09T08:50:00")
        book.queue_eod(make_source(monday),monday)
        assert book.on_quote(q("2026-11-09T09:17:00",ask_qty=1900)) is not None
        assert book.snapshot()["recent_fills"]==[] # only 95 shares at 5% depth
        assert book.on_quote(q("2026-11-09T09:18:00",bid=29900,ask=31000)) is None # >1.8% spread
        book.close()


def test_sdk_quote_translates_kvnd_and_g1_units_to_vnd_and_shares():
    sdk=Obj(symbol="ACB",marketId="STO",boardId="G1",
        time="2026-11-09 09:18:00.100",
        bid=[Obj(price=24.55,quantity=60590)],
        offer=[Obj(price=24.6,quantity=10450)])
    b=sdk_quote_to_book(sdk)
    assert b.bid==24550 and b.ask==24600
    assert b.bid_qty==60590 and b.ask_qty==10450
    assert b.event_at.date().isoformat()=="2026-11-09"


def test_live_ledger_persists_across_restart_without_replaying_quote():
    with TemporaryDirectory() as root:
        path=Path(root)/"persist.db"
        book=LivePaper(path)
        monday=at("2026-11-09T08:50:00")
        book.queue_eod(make_source(monday),monday)
        assert len(book.on_quote(q("2026-11-09T09:17:00")))==1
        book.close()
        reopened=LivePaper(path)
        assert reopened.queue_eod(make_source(monday),monday)["queued"]==0
        assert reopened.on_quote(q("2026-11-09T09:17:00"))==[]
        assert reopened.snapshot()["bots"]["Darvas"]["positions"][0]["qty"]==500
        assert len(reopened.snapshot()["recent_fills"])==1
        reopened.close()


def test_closed_weekends_and_auction_phases():
    assert market_phase(at("2026-11-07T09:30:00"),"STO")=="closed"
    assert market_phase(at("2026-11-09T09:09:00"),"STO")=="opening_auction_or_preopen"
    assert market_phase(at("2026-11-09T14:39:00"),"STO")=="closing_auction_or_other"
    assert market_phase(at("2026-11-09T13:04:00"),"STO")=="continuous"
    assert market_phase(at("2026-11-09T10:00:00"),"DVX")=="closed"
