"""Live intraday research signals from completed 1-minute candles.

Every entry is a DISTINCT, explicitly experimental intraday strategy proxy,
NOT a reproduction of the named trader's trades. A bar arriving late is
stored but cannot create retroactive orders. A signal only becomes eligible
on the next real quote event; no backfilled/imaginary fills.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from math import isfinite
from statistics import mean, pstdev
from typing import Optional

from engine import TRADERS
from live.paper import LivePaper, VN, market_phase

WARMUP = 30
MAX_BAR_DELAY_SECONDS = 75


@dataclass(frozen=True)
class MinuteBar:
    symbol: str
    start_at: datetime
    received_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    resolution: str = "1"
    kind: str = "STOCK"

    def __post_init__(self):
        if self.start_at.tzinfo is None or self.received_at.tzinfo is None:
            raise ValueError("Timezone-aware bar timestamps required")
        if self.resolution != "1" or self.kind != "STOCK":
            raise ValueError("Only completed STOCK 1-minute bars are supported")
        if not all(isfinite(x) and x > 0 for x in
                   (self.open,self.high,self.low,self.close)):
            raise ValueError("Invalid bar price")
        if self.low > min(self.open,self.close) or self.high < max(self.open,self.close) or self.volume<0:
            raise ValueError("Invalid OHLCV")


def parse_closed_bar(message:dict,received_at:datetime):
    """DNSE closed-candle ('T'='bc') OHLC prices are quoted in 1000 VND."""
    if message.get("T")!="bc" or str(message.get("resolution"))!="1":
        raise ValueError("Expected closed 1-minute OHLC")
    if message.get("type")!="STOCK":
        raise ValueError("No index, derivative or synthetic candle")
    t=message.get("time")
    if not isinstance(t,(int,float)) or not t:
        raise ValueError("Invalid unix candle start timestamp")
    start=datetime.fromtimestamp(t,VN)
    symbol=str(message.get("symbol","")).upper()
    if not symbol.isalpha() or not 2<=len(symbol)<=5:
        raise ValueError("Invalid equity symbol")
    return MinuteBar(symbol=symbol,start_at=start,received_at=received_at,
        open=float(message["open"])*1000,high=float(message["high"])*1000,
        low=float(message["low"])*1000,close=float(message["close"])*1000,
        volume=int(message["volume"]))


def _signals(bars):
    """Price/volume-only minute-scale proxies, evaluated on CLOSED bars."""
    c=[float(x["close"]) for x in bars]
    h=[float(x["high"]) for x in bars]
    lo=[float(x["low"]) for x in bars]
    v=[int(x["volume"]) for x in bars]
    p=c[-1]
    avg_vol=mean(v[-21:-1])
    if avg_vol<=0 or p<5000:
        return {},{}
    hi10=max(h[-11:-1]); hi20=max(h[-21:-1]); hi30=max(h[-31:-1])
    low20=min(lo[-21:-1])
    ma5=mean(c[-5:]); ma10=mean(c[-10:]); ma20=mean(c[-20:])
    vol_factor=v[-1]/avg_vol
    mom3=p/c[-4]-1;mom5=p/c[-6]-1; mom10=p/c[-11]-1
    mom20=p/c[-21]-1; mom30=p/c[-31]-1
    span30=hi30/max(1, min(lo[-31:-1]))-1
    vol30=pstdev(c[-30:])/max(p,1)
    # A price jump in a one-minute bar can be a stale/bad feed; exclude
    # implausible movements and excessively volatile spiky securities.
    valid=.0002<=vol30<=.12 and abs(p/c[-2]-1)<.075
    # Momentum / breakouts / mean-reversion parameters are research proxies,
    # not claims about the traders' proprietary investment algorithms.
    raw={
        "Minervini": valid and ma5>ma10>ma20 and p>hi20 and mom20>.008 and vol_factor>1.18,
        "ONeil": valid and p>hi30 and mom30>.015 and vol_factor>1.45 and p>ma20,
        "Darvas": valid and span30<.095 and p>hi20 and p>ma20 and vol_factor>1.10,
        "BNF": valid and mom20<-.014 and mom3>.003 and p>c[-2] and vol_factor>.90,
        "CIS": valid and mom3>.0045 and mom10>.011 and ma5>ma10 and vol_factor>1.28,
        "Qullamaggie": valid and mom30>.02 and (hi10/min(lo[-11:-1])-1)<.025
                      and p>hi10 and vol_factor>1.20,
        "Unger": valid and p>hi20 and ma10>ma20 and .003<vol30<.045 and vol_factor>1.05,
        "ThaiPham": valid and p>hi20 and p>ma5 and mom10>.007 and vol_factor>1.55,
        "DuongChung": valid and p<ma20*.995 and mom3>.004 and mom20<-.012
                       and vol_factor>.85,
        "PThai": valid and ma10>ma20 and mom20>.012 and .004<vol30<.05 and
                 p>hi10 and vol_factor>1.10
    }
    # Arena Hybrid: consensus of 2 or more live momentum proxies.
    # Explicitly distinct from the historical 126-day walk-forward hybrid.
    raw["Hybrid"]=sum(bool(raw[k]) for k in ("Minervini","ONeil","CIS","Qullamaggie","PThai"))>=2
    metrics={"close":round(p),"vol_ratio":round(vol_factor,2),
             "mom5_pct":round(mom5*100,2),"mom20_pct":round(mom20*100,2)}
    return raw,metrics


def _exit_signal(bot, close:float, entry:float, bars) -> bool:
    if entry<=0 or len(bars)<WARMUP:
        return False
    cs=[float(x["close"]) for x in bars]
    ma10=mean(cs[-10:]); ma20=mean(cs[-20:])
    if bot in ("BNF","DuongChung"):
        return close>=entry*1.018 or close<entry*.945 or close<ma20*.97
    if bot in ("CIS","ThaiPham"):
        return close<ma10*.994 or close<entry*.93
    if bot=="Darvas":
        return close<min(float(x["low"]) for x in bars[-20:]) or close<entry*.9
    if bot in ("Unger","PThai"):
        return close<ma20*.99 or close<entry*.93
    return close<ma20*.985 or close<entry*.925


class IntradayScanner:
    def __init__(self,ledger:LivePaper):
        self.ledger=ledger
        self.bars_received=0
        self.signals_queued=0
        self.late_bars=0
        with ledger.lock,ledger.db:
            ledger.db.executescript("""
            CREATE TABLE IF NOT EXISTS minute_bars (
                symbol TEXT NOT NULL, minute TEXT NOT NULL, o REAL NOT NULL,
                h REAL NOT NULL, l REAL NOT NULL, close REAL NOT NULL,
                volume INTEGER NOT NULL, PRIMARY KEY(symbol,minute));
            CREATE INDEX IF NOT EXISTS idx_minute_bars_minute ON minute_bars(minute);
            """)

    def on_closed_bar(self,bar:MinuteBar):
        minute=bar.start_at.astimezone(VN)
        end=minute+timedelta(minutes=1)
        received=bar.received_at.astimezone(VN)
        if (minute.date()!=received.date() or
            market_phase(end,"STO")!="continuous" or
            received<end-timedelta(seconds=2)):
            return []
        age=(received-end).total_seconds()
        queued=[]
        with self.ledger.lock,self.ledger.db:
            insert=self.ledger.db.execute("""INSERT OR IGNORE INTO minute_bars
                (symbol,minute,o,h,l,close,volume) VALUES(?,?,?,?,?,?,?)""",
                (bar.symbol,minute.isoformat(),bar.open,bar.high,bar.low,
                 bar.close,bar.volume))
            if insert.rowcount==0:
                return []
            self.bars_received+=1
            # Bars from disconnected intervals can rebuild research context
            # but may not trigger a retroactive signal/fill.
            if age>MAX_BAR_DELAY_SECONDS or age< -2:
                self.late_bars+=1
                return []
            day_prefix=minute.date().isoformat()
            bars=self.ledger.db.execute("""SELECT * FROM minute_bars
                WHERE symbol=? AND substr(minute,1,10)=?
                ORDER BY minute DESC LIMIT 65""",(bar.symbol,day_prefix)).fetchall()[::-1]
            if len(bars)<WARMUP+1:
                return []
            # Require trading minutes close enough to cover a continuous
            # recent window. Reconnection holes must not generate breakouts.
            for x,y in zip(bars[-11:-1],bars[-10:]):
                if (datetime.fromisoformat(y["minute"])-
                    datetime.fromisoformat(x["minute"])).total_seconds()>120:
                    return []
            valid,metrics=_signals(bars)
            seq=int(self.ledger.get_meta("session_seq","0"))
            for bot in TRADERS:
                pos=self.ledger.db.execute(
                    "SELECT * FROM positions WHERE bot=? AND symbol=?",
                    (bot,bar.symbol)).fetchone()
                if pos:
                    if seq-int(pos["buy_seq"])<3:
                        continue  # real VN T+2.5 delivery, cannot day-trade same stock
                    should_exit=_exit_signal(bot,bar.close,float(pos["entry_price"]),bars)
                    if should_exit:
                        reason=f"1m close: {bot} intraday exit; no same-tick fill"
                        result=self.ledger.queue_signal(bot,bar.symbol,"SELL",received,reason,
                                                        source_session=day_prefix)
                        if result:queued.append(result)
                elif valid.get(bot,False):
                    reason=(f"1m closed-bar {bot} experimental proxy "
                            f"price={metrics['close']} momentum20={metrics['mom20_pct']}% "
                            f"volX={metrics['vol_ratio']}; fill only on next quote")
                    result=self.ledger.queue_signal(bot,bar.symbol,"BUY",received,reason,
                                                    source_session=day_prefix)
                    if result:queued.append(result)
            self.signals_queued+=len(queued)
        return queued

    def status(self):
        return {"closed_bars_received":self.bars_received,
                "signals_queued":self.signals_queued,"late_bars":self.late_bars,
                "warmup_minutes":WARMUP,
                "strategy_mode":"11 independent intraday research proxies",
                "feed_note":"Uses only 1-minute closed candles; no same-bar execution"}
