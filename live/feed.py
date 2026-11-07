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
import secrets
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


def make_auth(api_key:str,api_secret:str,ts:int|None=None,nonce:str|None=None)->dict:
    """Official DNSE HMAC-SHA256 auth protocol; secrets never enter a URL."""
    timestamp=int(time.time()) if ts is None else int(ts)
    one_time_nonce=nonce or str(int(time.time()*1_000_000))+secrets.token_hex(4)
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
        # Always monitor some liquid names to prove the feed is truly live,
        # even on days when no strategy has a queued order.
        watch=os.getenv("LIVE_WATCH_SYMBOLS","FPT,HPG,VCB,MBB,SSI,ACB,TCB,MWG,VNM,PNJ,DGC,VHM,STB,CTG,BID,VPB")
        symbols.update(s.strip().upper() for s in watch.split(","))
        self.symbols=sorted(s for s in symbols if s.isalpha() and 2<=len(s)<=5)[:120]
        log.info("Loaded EOD plan; status %s; symbols %d",info["reason"],len(self.symbols))
        return info

    async def connect_day(self):
        """Native DNSE JSON WebSocket; no unverified pip SDK or broker endpoints."""
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
                    "name":"top_price.G1.json","symbols":self.symbols[i:i+25]}]}))
            self.connected=True
            self.last_error=""
            log.info("Authenticated to DNSE market data, watching %d symbols",len(self.symbols))

            async def beat():
                while True:
                    await asyncio.sleep(25)
                    await ws.send(json.dumps({"action":"ping",
                        "timestamp":int(time.time()*1000)}))
            heartbeat=asyncio.create_task(beat())
            try:
                while True:
                    now=now_vn()
                    if now.weekday()>4 or now.time()>time(14,38):
                        break
                    message=json.loads(await asyncio.wait_for(ws.recv(),timeout=65))
                    action=message.get("action")
                    if action=="ping":
                        await ws.send(json.dumps({"action":"pong",
                            "timestamp":message.get("timestamp")}))
                    elif action in ("error","connection_expired"):
                        raise RuntimeError("DNSE stream control: "+str(message.get("code","connection_expired"))[:50])
                    elif message.get("T")=="q":
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
                            log.debug("Rejected an invalid or stale quote")
                    # Other control/data messages cannot generate a fill.
            finally:
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
                self.connected=False

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
