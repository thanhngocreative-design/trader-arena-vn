"""Strict point-in-time, quote-driven paper fills. NO broker/order API here.

Separate competition from historical EOD simulator: a quote-tape model based
on observable DNSE G1 best bid/ask. Every fill requires a NEW, recent quote
with timestamp later than order submission. Displayed liquidity is not a
guarantee that any actual market order would execute.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import json
import math
import sqlite3
from threading import RLock

from engine import Settings, TRADERS
from execution import modeled_slippage

VN = ZoneInfo("Asia/Ho_Chi_Minh")
MARKETS = {"STO":"HOSE","STX":"HNX","UPX":"UPCOM"}
INITIAL_CASH = 100_000_000.0
MAX_QUOTE_AGE = 8.0
MAX_SPREAD = 0.018
MAX_BOOK_FRACTION = 0.05
LOT = 100


def now_vn():
    return datetime.now(VN)


def market_phase(moment: datetime, market_id: str) -> str:
    """Only continuous regular odd-free G1 matching supports this first version."""
    local = moment.astimezone(VN)
    if local.weekday() > 4 or market_id not in MARKETS:
        return "closed"
    t = local.time()
    if time(9,15) <= t < time(11,30) or time(13,0) <= t < time(14,30):
        return "continuous"
    if time(11,30) <= t < time(13,0):
        return "lunch"
    if time(9,0) <= t < time(9,15):
        return "opening_auction_or_preopen"
    if time(14,30) <= t < time(14,45):
        return "closing_auction_or_other"
    return "closed"


@dataclass(frozen=True)
class Book:
    symbol: str
    market_id: str
    bid: float
    ask: float
    bid_qty: int
    ask_qty: int
    event_at: datetime
    received_at: datetime
    board_id: str = "G1"

    def __post_init__(self):
        if self.event_at.tzinfo is None or self.received_at.tzinfo is None:
            raise ValueError("Exchange and receipt timestamps must be timezone-aware")


def previous_business_day(day: date) -> date:
    d = day - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


class LivePaper:
    def __init__(self, path: str|Path, settings:Settings|None=None):
        self.st=settings or Settings()
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path),check_same_thread=False,timeout=10)
        self.db.row_factory=sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=7000")
        self.lock=RLock()
        self._setup()

    def _setup(self):
        with self.db:
            self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS accounts(bot TEXT PRIMARY KEY, cash REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS positions(
                bot TEXT NOT NULL, symbol TEXT NOT NULL, qty INTEGER NOT NULL,
                buy_cost REAL NOT NULL, entry_price REAL NOT NULL,
                buy_seq INTEGER NOT NULL, high_water REAL NOT NULL,
                PRIMARY KEY(bot,symbol));
            CREATE TABLE IF NOT EXISTS orders(
                id TEXT PRIMARY KEY, bot TEXT NOT NULL, symbol TEXT NOT NULL,
                side TEXT NOT NULL, source_session TEXT NOT NULL,
                created_at TEXT NOT NULL, target_value REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                last_fill_minute TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS fills(
                id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
                bot TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
                quote_at TEXT NOT NULL, recorded_at TEXT NOT NULL, price REAL NOT NULL,
                qty INTEGER NOT NULL, fee REAL NOT NULL, tax REAL NOT NULL,
                slippage REAL NOT NULL, note TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS marks(symbol TEXT PRIMARY KEY,
                bid REAL NOT NULL, ask REAL NOT NULL, event_at TEXT NOT NULL);
            """)
            for bot in TRADERS:
                self.db.execute("INSERT OR IGNORE INTO accounts VALUES(?,?)",(bot,INITIAL_CASH))

    def get_meta(self,key,default=""):
        row=self.db.execute("SELECT value FROM meta WHERE key=?",(key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self,key,value):
        self.db.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))

    def queue_eod(self,source:dict,now:datetime|None=None):
        """Only yesterday's audited EOD plans. No fabricated historical fills."""
        now=now or now_vn()
        today=now.astimezone(VN).date()
        if source.get("last_session")!=previous_business_day(today).isoformat():
            return {"queued":0,"reason":"EOD state not from previous business day; market holiday or missing run"}
        accepted=0
        with self.lock,self.db:
            if self.get_meta("queued_for")==today.isoformat():
                return {"queued":0,"reason":"already queued"}
            for bot,item in source.get("bots",{}).items():
                if bot not in TRADERS:
                    continue
                for plan in item.get("orders_next",[]):
                    symbol=str(plan.get("symbol","")).upper()
                    side=plan.get("side","")
                    if not symbol.isalpha() or not (2<=len(symbol)<=5) or side not in ("BUY","SELL"):
                        continue
                    if side=="SELL" and not self.db.execute(
                            "SELECT 1 FROM positions WHERE bot=? AND symbol=?",(bot,symbol)).fetchone():
                        continue
                    oid=":".join((today.isoformat(),bot,side,symbol))
                    cur=self.db.execute("""INSERT OR IGNORE INTO orders
                        (id,bot,symbol,side,source_session,created_at,target_value,reason)
                        VALUES (?,?,?,?,?,?,?,?)""",
                        (oid,bot,symbol,side,source["last_session"],now.isoformat(),
                         INITIAL_CASH/self.st.max_positions,str(plan.get("reason",""))[:240]))
                    accepted+=cur.rowcount
            self.set_meta("queued_for",today.isoformat())
        return {"queued":accepted,"reason":"queued from EOD plans"}

    def on_quote(self,q:Book):
        now=q.received_at.astimezone(VN)
        market=q.event_at.astimezone(VN)
        age=(q.received_at-q.event_at).total_seconds()
        if (q.board_id!="G1" or market_phase(now,q.market_id)!="continuous"
            or market_phase(q.event_at,q.market_id)!="continuous"
            or now.date()!=market.date()
            or age < -.5 or age > MAX_QUOTE_AGE
            or not q.symbol.isalpha() or q.market_id not in MARKETS
            or min(q.bid,q.ask)<=0 or q.bid>q.ask
            or max(q.bid_qty,q.ask_qty)<=0
            or (q.ask/q.bid-1) > MAX_SPREAD):
            return None
        results=[]
        with self.lock,self.db:
            current_day=self.get_meta("day")
            if current_day!=now.date().isoformat():
                seq=int(self.get_meta("session_seq","0"))+1
                self.set_meta("day",now.date().isoformat())
                self.set_meta("session_seq",seq)
            seq=int(self.get_meta("session_seq","1"))
            self.db.execute("""INSERT INTO marks(symbol,bid,ask,event_at) VALUES(?,?,?,?)
                ON CONFLICT(symbol) DO UPDATE SET bid=excluded.bid,ask=excluded.ask,event_at=excluded.event_at
                WHERE excluded.event_at>marks.event_at""",
                (q.symbol,q.bid,q.ask,q.event_at.isoformat()))
            # Intraday stop-loss triggers are placed AFTER observing the quote.
            # They can be modeled only against a SUBSEQUENT quote, never at the
            # price that created the signal (no same-tick lookahead).
            for held in self.db.execute("SELECT * FROM positions WHERE symbol=?",(q.symbol,)).fetchall():
                if seq-int(held["buy_seq"])<self.st.minimum_hold_sessions:
                    continue
                self.db.execute("UPDATE positions SET high_water=MAX(high_water,?) WHERE bot=? AND symbol=?",
                                (q.bid,held["bot"],q.symbol))
                existing=self.db.execute("""SELECT 1 FROM orders WHERE bot=? AND symbol=?
                    AND side='SELL' AND status='pending'""",(held["bot"],q.symbol)).fetchone()
                if existing:continue
                stop_mult={"CIS":.94,"BNF":.93,"Darvas":.88,"Hybrid":.92}.get(held["bot"],.93)
                ref_price=float(held["high_water"]) if held["bot"]=="Darvas" else float(held["entry_price"])
                if q.bid>ref_price*stop_mult:
                    continue
                oid=":".join((now.date().isoformat(),held["bot"],"STOP",q.symbol))
                self.db.execute("""INSERT OR IGNORE INTO orders
                    (id,bot,symbol,side,source_session,created_at,target_value,reason)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (oid,held["bot"],q.symbol,"SELL",now.date().isoformat(),
                     now.isoformat(),0.0,"Intraday protective stop; not yet filled"))
            orders=self.db.execute("""SELECT * FROM orders
                WHERE symbol=? AND status='pending' ORDER BY CASE WHEN side='SELL' THEN 0 ELSE 1 END,id""",
                (q.symbol,)).fetchall()
            for o in orders:
                # Signal must be submitted BEFORE the quote's exchange timestamp.
                if q.event_at<=datetime.fromisoformat(o["created_at"]):
                    continue
                minute=q.event_at.strftime("%Y-%m-%dT%H:%M")
                if o["last_fill_minute"]==minute:
                    continue  # prevent repeatedly consuming the same order book within a minute
                held=self.db.execute("SELECT * FROM positions WHERE bot=? AND symbol=?",
                                     (o["bot"],q.symbol)).fetchone()
                if o["side"]=="SELL":
                    if not held or (seq-int(held["buy_seq"]))<self.st.minimum_hold_sessions:
                        continue
                    qty=min(int(held["qty"]),int(q.bid_qty*MAX_BOOK_FRACTION))
                    px=q.bid
                else:
                    if held:
                        self.db.execute("UPDATE orders SET status='cancelled' WHERE id=?",(o["id"],))
                        continue
                    open_pos=self.db.execute("SELECT count(*) c FROM positions WHERE bot=?",(o["bot"],)).fetchone()["c"]
                    if open_pos>=self.st.max_positions:
                        continue
                    cash=self.db.execute("SELECT cash FROM accounts WHERE bot=?",(o["bot"],)).fetchone()["cash"]
                    already=self.db.execute("SELECT COALESCE(SUM(qty*price+fee),0) v FROM fills WHERE order_id=?",(o["id"],)).fetchone()["v"]
                    remaining=min(cash,max(0,o["target_value"]-already))
                    qty=min(int(q.ask_qty*MAX_BOOK_FRACTION),
                            math.floor(remaining/(q.ask*(1+self.st.fee_rate+self.st.slippage))))
                    px=q.ask
                qty=int(qty)//LOT*LOT
                if qty<LOT:continue
                # Displayed bid/ask is an estimate, not assured fill; extra
                # liquidity/slippage allowance is added conservatively.
                advance=modeled_slippage(self.st,5_000_000_000,qty*px)
                price=px*(1+advance if o["side"]=="BUY" else 1-advance)
                fee=qty*price*self.st.fee_rate
                tax=qty*price*self.st.sell_tax if o["side"]=="SELL" else 0.
                gross=qty*price
                if o["side"]=="BUY":
                    cost=gross+fee
                    if cost>cash:continue
                    self.db.execute("UPDATE accounts SET cash=cash-? WHERE bot=?",(cost,o["bot"]))
                    self.db.execute("""INSERT INTO positions(bot,symbol,qty,buy_cost,entry_price,buy_seq,high_water)
                        VALUES(?,?,?,?,?,?,?)""",(o["bot"],q.symbol,qty,cost,price,seq,price))
                    status="filled"
                else:
                    self.db.execute("UPDATE accounts SET cash=cash+? WHERE bot=?",(gross-fee-tax,o["bot"]))
                    remaining_qty=int(held["qty"])-qty
                    if remaining_qty:
                        self.db.execute("UPDATE positions SET qty=?, buy_cost=?, high_water=? WHERE bot=? AND symbol=?",
                                        (remaining_qty,held["buy_cost"]*(remaining_qty/int(held["qty"])),
                                        held["high_water"],o["bot"],q.symbol))
                        status="pending"
                    else:
                        self.db.execute("DELETE FROM positions WHERE bot=? AND symbol=?",(o["bot"],q.symbol))
                        status="filled"
                self.db.execute("UPDATE orders SET status=?,last_fill_minute=? WHERE id=?",
                                (status,minute,o["id"]))
                self.db.execute("""INSERT INTO fills
                   (order_id,bot,symbol,side,quote_at,recorded_at,price,qty,fee,tax,slippage,note)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (o["id"],o["bot"],q.symbol,o["side"],q.event_at.isoformat(),now.isoformat(),
                     price,qty,fee,tax,advance,"SIMULATED_BBO_NOT_CONFIRMED_EXECUTION"))
                results.append({"bot":o["bot"],"symbol":q.symbol,"side":o["side"],
                                "price":round(price),"qty":qty,"quote_at":q.event_at.isoformat()})
        return results

    def snapshot(self):
        with self.lock:
            accounts=self.db.execute("SELECT bot,cash FROM accounts ORDER BY bot").fetchall()
            quotes={r["symbol"]:dict(r) for r in self.db.execute("SELECT * FROM marks")}
            statuses={}
            for item in accounts:
                b=item["bot"]
                positions=[]
                invested=0.
                for p in self.db.execute("SELECT * FROM positions WHERE bot=?",(b,)):
                    r=dict(p)
                    mark=quotes.get(p["symbol"],{})
                    bid=float(mark.get("bid",p["entry_price"]))
                    invested+=bid*p["qty"]
                    positions.append({"symbol":p["symbol"],"qty":p["qty"],
                                      "buy_price":round(p["entry_price"]),"mark_bid":round(bid),
                                      "unrealized_pnl":round(bid*p["qty"]-p["buy_cost"])})
                orders=[dict(r) for r in self.db.execute("""SELECT id,symbol,side,status,created_at
                     FROM orders WHERE bot=? ORDER BY id DESC LIMIT 20""",(b,))]
                statuses[b]={"cash":round(item["cash"]),"nav":round(item["cash"]+invested),
                             "return_pct":round((item["cash"]+invested)/INITIAL_CASH*100-100,3),
                             "positions":positions,"orders":orders}
            events=[dict(r) for r in self.db.execute("""SELECT bot,symbol,side,price,qty,quote_at,note
                FROM fills ORDER BY id DESC LIMIT 30""")]
            return {"mode":"realtime_paper","as_of":self.get_meta("last_seen"),
                    "session_day":self.get_meta("day"),"source":"DNSE WebSocket G1 best bid/ask",
                    "execution":"SIMULATED, NOT VERIFIED EXCHANGE FILLS",
                    "bots":statuses,"recent_fills":events,
                    "quotes_seen":len(quotes),
                    "last_queued_for":self.get_meta("queued_for")}

    def note_feed(self,ts:datetime):
        with self.lock,self.db:
            self.set_meta("last_seen",ts.isoformat())

    def close(self):
        with self.lock:self.db.close()
