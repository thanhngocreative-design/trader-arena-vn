"""Intraday scanners: live CLOSED candles, quote-after-signal, no lookahead."""
from datetime import datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from live.paper import LivePaper,Book,VN
from live.intraday import MinuteBar,IntradayScanner,parse_closed_bar


def t(value):
    return datetime.fromisoformat(value).replace(tzinfo=VN)


def bar(n,base=t("2026-11-09T09:15:00"),big_last=False):
    start=base+timedelta(minutes=n)
    p=30000 + (n*10 if n<30 else (900 if big_last else n*10))
    return MinuteBar(symbol="FPT",start_at=start,
        received_at=start+timedelta(minutes=1,seconds=.2),
        open=p,high=p+40,low=p-40,close=p,
        volume=40000 if n==30 and big_last else 10000)


def quote(ts,symbol="FPT",bid=30900,ask=30950):
    e=t(ts)
    return Book(symbol=symbol,market_id="STO",board_id="G1",
        bid=bid,ask=ask,bid_qty=10000,ask_qty=10000,
        event_at=e,received_at=e+timedelta(milliseconds=100))


def test_closed_minute_parser_rejects_forming_candles():
    data={"T":"bc","symbol":"FPT","resolution":"1","type":"STOCK",
        "time":int(t("2026-11-09T09:15:00").timestamp()),
        "open":30.0,"high":30.2,"low":29.8,"close":30.1,"volume":"6500"}
    b=parse_closed_bar(data,t("2026-11-09T09:16:00.500"))
    assert b.close==30100 and b.volume==6500
    import pytest
    with pytest.raises(ValueError):parse_closed_bar({**data,"T":"b"},b.received_at)
    with pytest.raises(ValueError):parse_closed_bar({**data,"type":"DERIVATIVE"},b.received_at)


def test_all_bots_scanned_and_intraday_research_entries_wait_for_future_quotes():
    with TemporaryDirectory() as d:
        book=LivePaper(Path(d)/"paper.db")
        scan=IntradayScanner(book)
        for n in range(30):
            assert scan.on_closed_bar(bar(n))==[]
        queued=scan.on_closed_bar(bar(30,big_last=True))
        assert queued
        assert all(x["source"]=="INTRADAY_1M_CLOSED" for x in queued)
        assert "Hybrid" in {x["bot"] for x in queued}
        assert "Minervini" in {x["bot"] for x in queued}
        assert len(book.snapshot()["recent_fills"])==0
        assert scan.on_closed_bar(bar(30,big_last=True))==[]
        # Stale same-minute quote cannot fill a new signal.
        assert book.on_quote(quote("2026-11-09T09:45:58")) is not None
        assert not book.snapshot()["recent_fills"]
        fills=book.on_quote(quote("2026-11-09T09:46:02"))
        assert fills
        assert set(x["bot"] for x in fills).issubset(set(x["bot"] for x in queued))
        book.close()


def test_stale_bar_is_stored_but_never_fires_backdated_order():
    with TemporaryDirectory() as d:
        book=LivePaper(Path(d)/"paper.db")
        scan=IntradayScanner(book)
        for n in range(30):scan.on_closed_bar(bar(n))
        late=bar(30,big_last=True)
        delayed=MinuteBar(**{**late.__dict__,
            "received_at":late.start_at+timedelta(minutes=5)})
        assert scan.on_closed_bar(delayed)==[]
        assert scan.late_bars==1
        assert book.snapshot()["recent_fills"]==[]
        assert all(not z["orders"] for z in book.snapshot()["bots"].values())
        book.close()


def test_cash_equities_no_same_day_sale_allow_t_plus_two_afternoon():
    with TemporaryDirectory() as d:
        book=LivePaper(Path(d)/"paper.db")
        created=t("2026-11-09T09:25:00")
        assert book.queue_signal("CIS","FPT","BUY",created,"test")
        assert book.on_quote(quote("2026-11-09T09:25:03"))
        held=book.db.execute("SELECT * FROM positions WHERE bot='CIS' AND symbol='FPT'").fetchone()
        assert held
        assert book.queue_signal("CIS","FPT","SELL",t("2026-11-09T13:12:00"),"test") is None
        book.on_quote(quote("2026-11-10T09:16:02"))
        book.on_quote(quote("2026-11-11T13:01:02"))
        assert book.queue_signal("CIS","FPT","SELL",t("2026-11-11T13:02:00"),"test exit")
        sale=book.on_quote(quote("2026-11-11T13:02:02"))
        assert any(x["side"]=="SELL" for x in sale)
        book.close()


def test_bars_do_not_trigger_over_lunch_or_last_auction():
    with TemporaryDirectory() as d:
        book=LivePaper(Path(d)/"paper.db")
        scan=IntradayScanner(book)
        noon=t("2026-11-09T11:45:00")
        b=MinuteBar(symbol="FPT",start_at=noon,received_at=noon+timedelta(minutes=1),
                    open=30000,high=30050,low=29950,close=30000,volume=1000)
        assert scan.on_closed_bar(b)==[]
        book.close()
