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
import hmac
import hashlib
import time
from urllib.request import Request, urlopen

from live.paper import LivePaper, Book, VN, now_vn
from live.intraday import IntradayScanner, parse_closed_bar
from datafeed import PUBLIC_CANDIDATES

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


def make_auth(api_key:str,api_secret:str,ts:int|None=None,nonce:str|None=None)->dict:
    """Official DNSE HMAC-SHA256 auth protocol; secrets never enter a URL."""
    timestamp=int(time.time()) if ts is None else int(ts)
    one_time_nonce=nonce or str(time.time_ns()//1_000)
    body=f"{api_key}:{timestamp}:{one_time_nonce}".encode("utf-8")
    signature=hmac.new(api_secret.encode("utf-8"),body,hashlib.sha256).hexdigest()
    return {"action":"auth","api_key":api_key,"signature":signature,
            "timestamp":timestamp,"nonce":one_time_nonce}


def raw_quote_to_book(data:dict,received_at:datetime|None=None)->Book:
    """DNSE top_price.G1.json payload. Prices are thousand VND, quantities shares."""
    if data.get("T")!="q":
        raise ValueError("Not a quote message")
    bids=data.get("bid") or []
    offers=data.get("offer") or []
    if not bids or not offers:
        raise ValueError("Incomplete bid/ask book")
    b,a=bids[0],offers[0]
    return Book(symbol=str(data["symbol"]).upper(),market_id=str(data["marketId"]),
        board_id=str(data.get("boardId","")),
        bid=float(b["price"])*1000,ask=float(a["price"])*1000,
        bid_qty=int(b["quantity"]),ask_qty=int(a["quantity"]),
        event_at=official_time(data["time"]),
        received_at=received_at or now_vn())


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
        self.scanner=IntradayScanner(book)
        self.api_key=os.getenv("DNSE_API_KEY","")
        self.api_secret=os.getenv("DNSE_API_SECRET","")
        self.connected=False
        self.feed_connected={"quotes":False,"candles":False}
        self.last_received=""
        self.last_candle_received=""
        self.last_error=""
        self.last_plan_refresh=""
        self.symbols=[]
        self.processed_books=0
        self.fills=0
        self.task=None
        self.signal_events=0

    @property
    def configured(self):
        return bool(self.api_key and self.api_secret)

    async def load_plan(self):
        """Build research universe independent of yesterday's EOD orders."""
        now=now_vn()
        self.last_plan_refresh=now.isoformat()
        symbols=list(PUBLIC_CANDIDATES)
        # Always continue tracking owned equities and pending orders from
        # before process restart even if the candidate list changes.
        snapshot=self.book.snapshot()
        for b in snapshot["bots"].values():
            symbols.extend(p["symbol"] for p in b["positions"])
            symbols.extend(o["symbol"] for o in b["orders"] if o["status"]=="pending")
        limit=max(1,min(190,int(os.getenv("LIVE_MAX_SYMBOLS","180"))))
        self.symbols=list(dict.fromkeys(
            s.strip().upper() for s in symbols
            if s.isalpha() and 2<=len(s)<=5))[:limit]
        log.info("Intraday universe loaded: %d candidates; EOD buy plans disabled",
                 len(self.symbols))
        return {"queued":0,"symbols":len(self.symbols),
                "reason":"intraday discovery from closed 1-minute candles"}

    async def _stream(self,kind:str,channel:str):
        """Read-only feed; each socket fits within 200 symbol streams."""
        import websockets
        url="wss://ws-openapi.dnse.com.vn/v1/stream?encoding=json"
        async with websockets.connect(url,ping_interval=None,
                                       open_timeout=20,max_size=4_000_000) as ws:
            first=json.loads(await asyncio.wait_for(ws.recv(),timeout=12))
            if first.get("action")!="welcome":
                raise RuntimeError("DNSE WebSocket missing welcome")
            await ws.send(json.dumps(make_auth(self.api_key,self.api_secret)))
            reply=json.loads(await asyncio.wait_for(ws.recv(),timeout=15))
            if reply.get("action")!="auth_success":
                raise RuntimeError("DNSE WebSocket authentication was rejected")
            for i in range(0,len(self.symbols),25):
                await ws.send(json.dumps({"action":"subscribe","channels":[{
                    "name":channel,"symbols":self.symbols[i:i+25]}]}))
            self.feed_connected[kind]=True
            self.connected=all(self.feed_connected.values())
            self.last_error=""
            log.info("Authenticated DNSE %s, watching %d equities",kind,len(self.symbols))
            async def beat():
                while True:
                    await asyncio.sleep(25)
                    await ws.send(json.dumps({"action":"pong",
                        "timestamp":int(time.time()*1000)}))
            heartbeat=asyncio.create_task(beat())
            try:
                while True:
                    now=now_vn()
                    if now.weekday()>4 or now.time()>time(15,1):
                        break
                    message=json.loads(await asyncio.wait_for(ws.recv(),timeout=65))
                    action=message.get("action")
                    if action=="ping":
                        await ws.send(json.dumps({"action":"pong",
                            "timestamp":message.get("timestamp")}))
                    elif action in ("error","connection_expired"):
                        raise RuntimeError("DNSE "+kind+" stream control: "+
                                           str(message.get("code","expired"))[:50])
                    elif kind=="quotes" and message.get("T")=="q":
                        try:
                            book=raw_quote_to_book(message,now_vn())
                            result=self.book.on_quote(book)
                            if result is None:
                                continue
                            self.book.note_feed(book.received_at)
                            self.processed_books+=1
                            self.fills+=len(result)
                            self.last_received=book.received_at.isoformat()
                        except (ValueError,TypeError,KeyError,OverflowError):
                            log.debug("Ignored stale/malformed quote")
                    elif kind=="candles" and message.get("T")=="bc":
                        try:
                            bar=parse_closed_bar(message,now_vn())
                            created=self.scanner.on_closed_bar(bar)
                            self.signal_events+=len(created)
                            self.last_candle_received=bar.received_at.isoformat()
                        except (ValueError,TypeError,KeyError,OverflowError):
                            log.debug("Ignored stale/malformed closed 1m candle")
            finally:
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
                self.feed_connected[kind]=False
                self.connected=False

    async def connect_day(self):
        """Two concurrently authenticated read-only streams; no order API."""
        async with asyncio.TaskGroup() as jobs:
            jobs.create_task(self._stream("quotes","top_price.G1.json"))
            jobs.create_task(self._stream("candles","ohlc_closed.1.json"))
    
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
                if now.weekday()>4 or not(time(8,43)<=now.time()<=time(15,1)):
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
                "feed_connected":dict(self.feed_connected),
                "intraday_scanner":self.scanner.status(),
                "last_candle_received":self.last_candle_received,
                "signal_events_this_process":self.signal_events,
                "last_received":self.last_received,
                "last_plan_refresh":self.last_plan_refresh,
                "subscribed_symbols":len(self.symbols),
                "books_processed":self.processed_books,
                "fills_this_process":self.fills,
                "last_error":self.last_error if not self.configured else
                              (self.last_error if not self.connected else ""),
                "claims_realtime":bool(self.connected and self.last_received
                    and self.last_candle_received
                    and (now_vn()-official_time(self.last_received)).total_seconds()<=10
                    and (now_vn()-official_time(self.last_candle_received)).total_seconds()<=150
                    and self.scanner.bars_received>0)}
