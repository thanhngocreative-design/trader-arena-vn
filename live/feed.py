"""Cloud-only read-only DNSE market feed bridge for live paper simulation.

This file NEVER imports the DNSE REST trading client and NEVER sends orders.
Public EOD plans are used to pre-register intents; live G1 quote updates
are only used to model hypothetical fills later in time.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo
import json
import logging
import os
from urllib.request import Request, urlopen

from live.paper import LivePaper, Book, VN, now_vn

log=logging.getLogger(__name__)
STATE_URL=os.getenv(
    "LIVE_PLANS_URL",
    "https://raw.githubusercontent.com/thanhngocreative-design/trader-arena-vn/main/state/paper_state.json"
)
ALLOWED_STATE_URL_PREFIX="https://raw.githubusercontent.com/thanhngocreative-design/trader-arena-vn/"

def official_time(value):
    """DNSE SDK Quote.time may be a local string, ISO string, or unix timestamp."""
    if isinstance(value,datetime):
        return value.replace(tzinfo=VN) if value.tzinfo is None else value.astimezone(VN)
    if isinstance(value,(int,float)):
        return datetime.fromtimestamp(value,VN)
    if not value:
        raise ValueError("DNSE quote missing exchange timestamp")
    if isinstance(value,dict):
        if "Seconds" in value:
            return datetime.fromtimestamp(float(value["Seconds"])+float(value.get("Nanos",0))/1e9,VN)
        raise ValueError("Unknown timestamp object")
    text=str(value).strip()
    try:
        parsed=datetime.fromisoformat(text.replace("Z","+00:00"))
    except ValueError:
        parsed=datetime.strptime(text,"%Y-%m-%d %H:%M:%S.%f") if "." in text else datetime.strptime(text,"%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=VN) if parsed.tzinfo is None else parsed.astimezone(VN)


def sdk_quote_to_book(q) -> Book:
    # Market data examples return prices in THOUSANDS of VND per share.
    # DNSE quotes.quantity is in SHARES (not board lots).
    bids=getattr(q,"bid",None) or []
    asks=getattr(q,"offer",None) or []
    if not bids or not asks:
        raise ValueError("Missing two-sided order book")
    bid,ask=bids[0],asks[0]
    return Book(symbol=str(q.symbol).upper(), market_id=str(q.marketId),
        board_id=str(q.boardId),
        bid=float(bid.price)*1000,ask=float(ask.price)*1000,
        bid_qty=int(bid.quantity),ask_qty=int(ask.quantity),
        event_at=official_time(q.time),received_at=now_vn())


def fetch_eod_source():
    if not STATE_URL.startswith(ALLOWED_STATE_URL_PREFIX):
        raise RuntimeError("LIVE_PLANS_URL must point to the approved public repo")
    request=Request(STATE_URL+"?t="+str(int(now_vn().timestamp())),
                    headers={"User-Agent":"TraderArenaVN-PaperOnly/1.0"})
    with urlopen(request,timeout=12) as r:
        if r.status!=200:
            raise RuntimeError("EOD plan unavailable")
        raw=r.read(2_000_001)
        if len(raw)>2_000_000:
            raise RuntimeError("Unreasonably large EOD state")
        data=json.loads(raw.decode("utf-8"))
        if not isinstance(data,dict) or not isinstance(data.get("bots"),dict):
            raise RuntimeError("Invalid EOD plan")
        return data


class DNSEMarketWorker:
    def __init__(self,book:LivePaper):
        self.book=book
        self.api_key=os.getenv("DNSE_API_KEY","")
        self.api_secret=os.getenv("DNSE_API_SECRET","")
        self.connected=False
        self.last_received=""
        self.last_error=""
        self.last_plan_refresh=""
        self.symbols=[]
        self.processed_books=0
        self.fills=0
        self.task=None

    @property
    def configured(self):
        return bool(self.api_key and self.api_secret)

    async def load_plan(self):
        now=now_vn()
        source=await asyncio.to_thread(fetch_eod_source)
        info=self.book.queue_eod(source,now)
        self.last_plan_refresh=now.isoformat()
        snapshot=self.book.snapshot()
        symbols=set()
        for b in snapshot["bots"].values():
            symbols.update(p["symbol"] for p in b["positions"])
            symbols.update(o["symbol"] for o in b["orders"] if o["status"]=="pending")
        self.symbols=sorted(s for s in symbols if s.isalpha() and 2<=len(s)<=5)
        log.info("Loaded EOD plan; status %s; symbols %d",info["reason"],len(self.symbols))
        return info

    async def connect_day(self):
        # Import only the official WebSocket market-data client.
        from dnse import TradingClient
        client=TradingClient(api_key=self.api_key,api_secret=self.api_secret,
                             base_url="wss://ws-openapi.dnse.com.vn",
                             encoding="json",auto_reconnect=True)
        def on_quote(q):
            try:
                book=sdk_quote_to_book(q)
                results=self.book.on_quote(book)
                if results is None:
                    return  # stale, auction or invalid quote; not live evidence
                self.book.note_feed(book.received_at)
                self.processed_books+=1
                self.fills+=len(results)
                self.last_received=book.received_at.isoformat()
            except (ValueError,TypeError,AttributeError) as exc:
                # Market may send one-sided or malformed books. Do not fill.
                log.debug("Ignored quote: %s",type(exc).__name__)
            except Exception:
                log.exception("Failed to process quote safely")
        try:
            await client.connect()
            for i in range(0,len(self.symbols),30):
                await client.subscribe_quotes(self.symbols[i:i+30],on_quote=on_quote,
                                               encoding="json",board_id="G1")
            self.connected=True
            self.last_error=""
            log.info("Subscribed to %s live quotes, G1",len(self.symbols))
            while True:
                now=now_vn()
                if now.weekday()>4 or now.time()>time(14,38):break
                await asyncio.sleep(5)
        finally:
            self.connected=False
            try:
                await client.disconnect()
            except Exception:
                log.exception("DNSE WebSocket disconnect error")

    async def run(self):
        while True:
            now=now_vn()
            try:
                # Provider can be disconnected on quiet days; do not report live
                # if no valid quote was received. Calendar holidays simply produce no fills.
                if not self.configured:
                    self.last_error="DNSE credentials not configured"
                    await asyncio.sleep(60)
                    continue
                if now.weekday()>4 or not(time(8,43)<=now.time()<=time(14,38)):
                    await asyncio.sleep(30)
                    continue
                if now.time()<time(9,10):
                    await self.load_plan()
                    await asyncio.sleep(45)
                    continue
                if self.last_plan_refresh[:10]!=now.date().isoformat():
                    await self.load_plan()
                if not self.symbols:
                    await asyncio.sleep(45)
                    continue
                await self.connect_day()
                await asyncio.sleep(20)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected=False
                self.last_error=type(exc).__name__+": "+str(exc)[:140]
                log.warning("Market feed unavailable (%s), no simulated fills",type(exc).__name__)
                await asyncio.sleep(15)

    def status(self):
        return {"configured":self.configured,"connected":self.connected,
                "last_received":self.last_received,
                "last_plan_refresh":self.last_plan_refresh,
                "subscribed_symbols":len(self.symbols),
                "books_processed":self.processed_books,
                "fills_this_process":self.fills,
                "last_error":self.last_error if not self.configured else
                              (self.last_error if not self.connected else ""),
                "claims_realtime":bool(self.connected and self.last_received and
                    (now_vn()-official_time(self.last_received)).total_seconds()<=10)}
