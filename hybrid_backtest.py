"""Walk-forward Daily + 1m hybrid backtest, entirely separate from EOD contest.

Historical equities only: no same-day sell after buying. Signals at completed
minute t can only fill at the open of subsequent OBSERVED continuous-session bar
t+1; no bar highs/lows or next bar volumes are used in signal decisions.
Daily signals are from the previous completed session, never the session being
executed. Minute price values are full VND per share.

Trade sizes: 100-share lots, prior completed day liquidity, cap of 5% of
last observed 1-minute matched volume, fees/tax and dynamic slippage.
No interpolation for missing bars. No fake minute history or backfilled fills.
"""
from __future__ import annotations
from datetime import timedelta
import numpy as np
import pandas as pd
from engine import Settings, TRADERS, stop_signal
from fast_engine import FastContext
from execution import modeled_slippage, pass_cost_gate

MINUTE_VOLUME_PARTICIPATION = .05
MINUTE_MAX_GAP = timedelta(minutes=3)
MIN_BARS_FOR_SIGNAL = 20
SHORT_TERM = {"BNF","CIS"}
RECOVERY = {"BNF","DuongChung"}
MIN_DAYS_FOR_REPORT = 5


def _recent(f: pd.DataFrame) -> pd.DataFrame:
    """Causal, completed-minute features; no current-day closing values."""
    c=f["close"]
    v=f["volume"]
    p=f.copy()
    p["vwap"]=(c*v).cumsum()/v.cumsum().replace(0,np.nan)
    p["ma5"]=c.rolling(5,min_periods=5).mean()
    p["high10_before"]=f["high"].rolling(10,min_periods=10).max().shift(1)
    p["low10_before"]=f["low"].rolling(10,min_periods=10).min().shift(1)
    p["high20_before"]=f["high"].rolling(20,min_periods=20).max().shift(1)
    p["volume_mean10_before"]=v.rolling(10,min_periods=10).mean().shift(1)
    p["close_before"]=c.shift(1)
    return p


def _eligible_daily(context:FastContext,bot:str,i:int,prev:int) -> bool:
    if prev < 0:
        return False
    a=context.a
    def val(k):
        return float(a[k][i,prev])
    if not np.isfinite(val("value20_prev")) or val("value20_prev")<context.settings.min_average_value:
        return False
    if bot=="BNF":
        return (np.isfinite(val("sma25")) and np.isfinite(val("close"))
                and val("close") <= val("sma25")*.97
                and val("rsi14")<53 and val("volume")>0)
    if bot=="CIS":
        return (val("sma10")>val("sma20")>val("sma50")
                and val("rs60")>0 and val("momentum60")>0
                and bool(context.buy["CIS"][i,prev]) or
                (val("sma10")>val("sma20")>val("sma50")
                 and val("rs60")>0 and val("momentum60")>.05
                 and val("value20_prev")>=context.settings.min_average_value))
    return bool(context.buy[bot][i,prev])


def _minute_enter(bot:str,now,prior,day_bar_index:int) -> bool:
    if day_bar_index < MIN_BARS_FOR_SIGNAL:
        return False
    if not all(np.isfinite(float(now[k])) for k in ("close","vwap","ma5","close_before","high10_before")):
        return False
    price=float(now["close"])
    if bot=="BNF":
        # First recovery from intraday dip; avoid buying a falling minute.
        return (price>float(now["ma5"]) and price>float(now["close_before"])
                and price>=float(now["vwap"])*.995
                and float(now["volume"])>=float(now["volume_mean10_before"])*.6)
    if bot=="DuongChung":
        return price>float(now["ma5"]) and price>float(now["vwap"]) and price>float(now["close_before"])
    if bot=="CIS":
        return (price>float(now["high20_before"]) and price>float(now["vwap"])
                and float(now["volume"])>float(now["volume_mean10_before"])*1.15)
    # Swing bots use daily screen and minute confirmation; do not look at day's
    # final close or high to decide the minute entry.
    return (price>float(now["high10_before"]) and price>float(now["vwap"])
            and float(now["volume"])>float(now["volume_mean10_before"])*.8)


def _walk_one(context: FastContext, bot:str, candles:dict[str,pd.DataFrame],
              first:int, last:int, settings:Settings):
    cash=float(settings.initial_cash)
    positions:dict[int,dict]={}
    closed_at:dict[int,int]={}
    trades=[]
    history=[]
    eligible_dates=0
    minute_bars=0
    observed_symbols=set()
    symbols=context.symbols
    inv=context.pos
    a=context.a
    for t in range(first,last+1):
        date=context.dates[t]
        day=date.date()
        prev=t-1
        day_rows={}
        for sym,f in candles.items():
            if sym not in inv:
                continue
            rows=f.loc[f.index.normalize()==date]
            if rows.empty:
                continue
            day_rows[sym]=_recent(rows)
            observed_symbols.add(sym)
            minute_bars+=len(rows)
        if day_rows:
            eligible_dates+=1
        # Full previous daily candle is already observable at the start of t.
        for i,p in positions.items():
            if prev>=0 and np.isfinite(a["high"][i,prev]):
                p["high_water"]=max(float(p["high_water"]),float(a["high"][i,prev]))
            if prev>=0:
                yes,reason=stop_signal(bot,context.stop_row(i,prev),p)
                if yes:p["exit_pending"]=reason

        # One shared chronological tape for all symbols: no symbol is allowed
        # to consume cash based on a later minute before another symbol's
        # earlier-minute signal has been evaluated.
        rows_by_sym={sym:rows.reset_index().to_dict("records") for sym,rows in day_rows.items()}
        events=sorted((bars[j]["time"],sym,j)
                      for sym,bars in rows_by_sym.items() for j in range(len(bars)))
        pending={}  # sym -> fill request made strictly at a prior observed minute
        for ts,sym,j in events:
            values=rows_by_sym[sym]
            row=values[j]
            i=inv[sym]
            daily_prev=context.stop_row(i,prev) if prev>=0 else {}
            # First fill the request that was created at a prior completed
            # minute (using this observed bar OPEN, not a future close/high).
            req=pending.pop(sym,None)
            if req and req["fill_at"]==ts:
                px0=float(row["open"])
                if req["side"]=="SELL":
                    p=positions.get(i)
                    if p and t-p["buy_index"]>=max(3,settings.minimum_hold_sessions):
                        qty=min(p["qty"],req["max_qty"])
                        qty=(qty//settings.lot)*settings.lot
                        if qty>=settings.lot:
                            adv=float(a["value20_prev"][i,prev])
                            slip=modeled_slippage(settings,adv,qty*px0)
                            price=px0*(1-slip)
                            gross=qty*price
                            fee=gross*settings.fee_rate
                            tax=gross*settings.sell_tax
                            portion=p["buy_cost"]*qty/p["qty"]
                            cash+=gross-fee-tax
                            pnl=gross-fee-tax-portion
                            trades.append({"date":day.isoformat(),"time":ts.isoformat(),
                                "signal_time":req["signal_time"].isoformat(),"trader":bot,
                                "symbol":sym,"side":"BÁN","qty":qty,"price":round(price),
                                "gross":round(gross),"fees":round(fee),"tax":round(tax),
                                "pnl":round(pnl),"slippage_rate":round(slip,6),
                                "reason":req["reason"],"buy_date":p["date"].date().isoformat()})
                            p["qty"]-=qty
                            p["buy_cost"]-=portion
                            if p["qty"]<=0:
                                del positions[i]
                                closed_at[i]=t
                elif req["side"]=="BUY" and i not in positions:
                    if len(positions)<settings.max_positions and (
                        i not in closed_at or t-closed_at[i]>=settings.cooldown_sessions
                    ):
                        budget=min(cash,req["allocation"])
                        adv=float(a["value20_prev"][i,prev])
                        slip=modeled_slippage(settings,adv,budget)
                        projected=px0*(1+slip)
                        qty_budget=(int(budget/(projected*(1+settings.fee_rate)))//settings.lot)*settings.lot
                        qty=min(req["max_qty"],qty_budget)
                        if qty>=settings.lot:
                            slip=modeled_slippage(settings,adv,qty*px0)
                            price=px0*(1+slip)
                            cost=qty*price*(1+settings.fee_rate)
                            if cost<=cash and cost<=budget*1.001:
                                cash-=cost
                                positions[i]={"qty":qty,"price":price,"buy_cost":cost,
                                    "date":date,"buy_index":t,"high_water":price,
                                    "exit_pending":""}
                                trades.append({"date":day.isoformat(),"time":ts.isoformat(),
                                    "signal_time":req["signal_time"].isoformat(),
                                    "signal_date":context.dates[prev].date().isoformat(),
                                    "trader":bot,"symbol":sym,"side":"MUA","qty":qty,
                                    "price":round(price),"gross":round(qty*price),
                                    "fees":round(cost-qty*price),"tax":0,"pnl":np.nan,
                                    "slippage_rate":round(slip,6),
                                    "reason":"Previous Daily screen + completed 1m signal; next-bar open fill"})
            # Now evaluate current completed minute. The order can only fill
            # on the next OBSERVED continuous bar, never this same minute.
            if j==len(values)-1 or int(row["volume"])<=0:
                continue
            next_ts=values[j+1]["time"]
            if next_ts-ts>MINUTE_MAX_GAP:
                continue
            max_minute=(int(row["volume"]*MINUTE_VOLUME_PARTICIPATION)//settings.lot)*settings.lot
            if max_minute<settings.lot:
                continue
            p=positions.get(i)
            if p is not None:
                if t-p["buy_index"]<max(3,settings.minimum_hold_sessions):
                    continue
                if not p.get("exit_pending"):
                    entry=float(p["price"])
                    stop={"BNF":.94,"CIS":.94,"Darvas":.88}.get(bot,.93)
                    trigger=float(row["close"]) < max(entry*stop,
                                float(p["high_water"])*.88 if bot=="Darvas" else 0)
                    if trigger:
                        p["exit_pending"]="Stop phát sinh từ nến phút đã đóng"
                p["high_water"]=max(float(p["high_water"]),float(row["high"]))
                if p.get("exit_pending"):
                    pending[sym]={"side":"SELL","max_qty":max_minute,"fill_at":next_ts,
                                  "signal_time":ts,"reason":p["exit_pending"]}
                continue
            if len(positions)>=settings.max_positions or (
                i in closed_at and t-closed_at[i]<settings.cooldown_sessions
            ):
                continue
            if not _eligible_daily(context,bot,i,prev):
                continue
            if not _minute_enter(bot,row,None,j):
                continue
            # Budget uses yesterday's observable closes for holdings; today's
            # future EOD prices are never visible to this calculation.
            current_nav=cash+sum(
                h["qty"]*float(a["close"][k,prev]) if prev>=0 and np.isfinite(a["close"][k,prev])
                else h["qty"]*h["price"] for k,h in positions.items())
            budget=min(cash,current_nav/max(1,settings.max_positions))
            if not pass_cost_gate(settings,daily_prev,budget):
                continue
            prev_volume=float(a["vol20_prev"][i,prev])
            if not np.isfinite(prev_volume):
                continue
            daily_cap=(int(prev_volume*settings.max_daily_participation)//settings.lot)*settings.lot
            qty_cap=min(max_minute,daily_cap)
            if qty_cap<settings.lot:continue
            pending[sym]={"side":"BUY","max_qty":qty_cap,"allocation":budget,
                          "fill_at":next_ts,"signal_time":ts}
        invested=0.
        for i,p in positions.items():
            # EOD marks do not generate same-day execution signals.
            close=a["close"][i,t]
            invested+=p["qty"]*(float(close) if np.isfinite(close) else p["price"])
        history.append({"date":date,"nav":cash+invested,"cash":cash,
                        "invested":invested,"position_count":len(positions)})
    curve=pd.DataFrame(history).set_index("date")
    curve["return_pct"]=(curve.nav/settings.initial_cash-1)*100
    curve["drawdown_pct"]=(curve.nav/curve.nav.cummax()-1)*100
    benchmark=context.benchmark["close"].reindex(curve.index).ffill()
    curve["benchmark_return_pct"]=(benchmark/benchmark.iloc[0]-1)*100
    tdf=pd.DataFrame(trades)
    sells=tdf[tdf.side=="BÁN"] if not tdf.empty else pd.DataFrame()
    holdings=[]
    for i,p in positions.items():
        sym=symbols[i]
        cl=a["close"][i,last]
        price=float(cl) if np.isfinite(cl) else p["price"]
        value=price*p["qty"]
        holdings.append({"symbol":sym,"qty":p["qty"],"buy_date":p["date"].date().isoformat(),
                         "buy_price":round(p["price"]),"last_price":round(price),
                         "value":round(value),"pnl":round(value-p["buy_cost"]),
                         "pnl_pct":100*(value/p["buy_cost"]-1),
                         "pending_exit":p.get("exit_pending","")})
    return {"trader":bot,"curve":curve,"trades":tdf,
        "holdings":pd.DataFrame(holdings),"actions":pd.DataFrame([]),
        "nav":float(curve.nav.iloc[-1]),"cash":cash,
        "return_pct":float(curve.return_pct.iloc[-1]),
        "benchmark_return_pct":float(curve.benchmark_return_pct.iloc[-1]),
        "max_drawdown_pct":float(curve.drawdown_pct.min()),
        "closed_trades":len(sells),
        "win_rate":(float((sells.pnl>0).sum())/len(sells)*100 if len(sells) else None),
        "buy_count":int((tdf.side=="MUA").sum()) if not tdf.empty else 0,
        "minute_bars_observed":minute_bars,"sessions_with_data":eligible_dates,
        "observed_symbols":sorted(observed_symbols)}


def build_hybrid_backtests(context:FastContext,minute:dict[str,pd.DataFrame],
                           settings:Settings|None=None):
    """Return (bot results, provenance). Never substitutes daily bars as minutes."""
    settings=settings or context.settings
    if not minute:
        return {},{"status":"no_1m_data","symbols":0,"sessions":0,
                   "reason":"Không có nến 1 phút thật; chỉ xem backtest Daily"}
    all_dates=set()
    for sym,frame in minute.items():
        if sym in context.pos:
            all_dates.update(frame.index.normalize())
    valid_dates=context.dates.intersection(pd.DatetimeIndex(sorted(all_dates)))
    if len(valid_dates)<MIN_DAYS_FOR_REPORT:
        return {},{"status":"insufficient_1m_history",
                   "symbols":len(minute),"sessions":len(valid_dates),
                   "reason":"Cần ít nhất 5 phiên có dữ liệu phút thật"}
    first=int(context.dates.get_loc(valid_dates.min()))
    last=int(context.dates.get_loc(valid_dates.max()))
    results={key:_walk_one(context,key,minute,first,last,settings) for key in TRADERS}
    audit={"status":"verified_1m_pilot","symbols":len(minute),
           "sessions":len(valid_dates),"first":valid_dates.min().date().isoformat(),
           "last":valid_dates.max().date().isoformat(),
           "symbols_list":sorted(minute),
           "mode":"daily_screen_plus_minute_decision_next_bar_fill",
           "minute_price_unit":"VND","min_hold_sessions":settings.minimum_hold_sessions,
           "caveat":"Chỉ áp dụng các mã có dữ liệu phút; không phải toàn bộ 167 mã. Nến ngày/các sự kiện quyền có thể không đồng nhất. Không cho phép mua và bán cùng ngày."}
    return results,audit
