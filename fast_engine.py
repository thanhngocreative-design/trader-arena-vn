"""Fast daily-bar research execution and causal walk-forward Hybrid signals.

All price arrays are VND, and decision data is from the prior completed bar.
Signals from date d are NEVER filled before the open of date d+1.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from engine import TRADERS, Settings, make_features, stop_signal
from execution import modeled_slippage, pass_cost_gate

CORE = tuple(k for k in TRADERS if k != "Hybrid")
KEYS = (
    "open", "high", "low", "close", "volume", "momentum60",
    "vol20_prev", "value20_prev", "atr14", "rsi14", "sma10", "sma20",
    "sma25", "sma50", "sma100", "low15_prev",
    "close_prev1", "sma20_prev1", "rs60", "market_ok",
)

class FastContext:
    fast_context = True

    def __init__(self, prices: dict, benchmark: pd.DataFrame, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.benchmark = benchmark.sort_index().copy()
        self.dates = self.benchmark.index
        self.symbols = sorted(s for s,p in prices.items() if len(p) >= 252)
        if not self.symbols:
            raise ValueError("Không có mã đủ lịch sử")
        self.pos = {s:i for i,s in enumerate(self.symbols)}
        shape=(len(self.symbols),len(self.dates))
        self.a={k:np.full(shape,np.nan,dtype=float) for k in KEYS}
        self.buy={k:np.zeros(shape,dtype=bool) for k in TRADERS}
        for i,symbol in enumerate(self.symbols):
            f=make_features(prices[symbol],self.benchmark,self.settings.min_average_value).reindex(self.dates)
            for k in KEYS:
                self.a[k][i,:]=f[k].to_numpy(dtype=float)
            for k in CORE:
                self.buy[k][i,:]=f[f"buy_{k}"].to_numpy(dtype=bool)
        self.hybrid_winners={}
        self.hybrid_asof={}
        self.build_completed=False

    def stop_row(self,i,date_pos):
        return {k:float(self.a[k][i,date_pos]) for k in KEYS}

    def candidate_indices(self,trader,signal_idx,positions,closed_at,now_idx):
        if signal_idx<0:
            return []
        mask=self.buy[trader][:,signal_idx] & np.isfinite(self.a["momentum60"][:,signal_idx])
        candidates=np.flatnonzero(mask)
        candidates=[int(i) for i in candidates
                    if i not in positions
                    and (i not in closed_at or now_idx-closed_at[i]>=self.settings.cooldown_sessions)]
        if trader in ("BNF","DuongChung"):
            candidates.sort(key=lambda i:(
                -(self.a["sma25"][i,signal_idx]/max(self.a["close"][i,signal_idx],1)-1),
                self.symbols[i]))
        elif trader=="Hybrid":
            weights=self.hybrid_winners.get(signal_idx,{})
            candidates.sort(key=lambda i:(-float(self.a["rs60"][i,signal_idx]),self.symbols[i]))
        else:
            candidates.sort(key=lambda i:(-float(self.a["rs60"][i,signal_idx]),self.symbols[i]))
        return candidates


def run_backtest(context: FastContext, trader: str, start_date: str,
                 end_date: str | None=None, settings: Settings | None=None) -> dict:
    from portfolio import for_bot, allocation as position_budget
    st=for_bot(settings or context.settings, trader)
    if trader not in TRADERS:
        raise ValueError("Trader không được hỗ trợ")
    dates=context.dates
    first=int(dates.searchsorted(pd.Timestamp(start_date),"left"))
    last=int(dates.searchsorted(pd.Timestamp(end_date),"right")-1) if end_date else len(dates)-1
    if last-first<1:
        raise ValueError("Khoảng backtest cần >=2 phiên")
    a=context.a
    cash=float(st.initial_cash)
    positions={}
    last_sold={}
    trades=[]
    curve=[]
    for t in range(first,last+1):
        prev=t-1
        # Signal generation and exit checks use only completed bars < t.
        if prev>=0:
            for i,p in positions.items():
                h=a["high"][i,prev]
                if np.isfinite(h):p["high_water"]=max(p["high_water"],float(h))
                yes,reason=stop_signal(trader,context.stop_row(i,prev),p)
                if yes and not p.get("exit_pending"):
                    p["exit_pending"]=reason

        # Sells first, with conservative T+2.5 and minimum-holding restriction.
        for i,p in list(positions.items()):
            if not p.get("exit_pending") or t-p["buy_index"]<max(3,st.minimum_hold_sessions):
                continue
            opening=a["open"][i,t]
            if not np.isfinite(opening) or opening<=0 or a["volume"][i,t]<=0:continue
            adv=a["value20_prev"][i,max(prev,0)]
            slip=modeled_slippage(st,adv,opening*p["qty"])
            px=float(opening)*(1-slip)
            gross=px*p["qty"]
            fees=gross*st.fee_rate
            tax=gross*st.sell_tax
            proceeds=gross-fees-tax
            pnl=proceeds-p["buy_cost"]
            cash+=proceeds
            trades.append({"date":dates[t].date().isoformat(),"trader":trader,
                "symbol":context.symbols[i],"side":"BÁN","qty":p["qty"],"price":round(px),
                "gross":round(gross),"fees":round(fees),"tax":round(tax),"pnl":round(pnl),
                "slippage_rate":round(slip,6),"reason":p["exit_pending"],
                "signal_date":dates[prev].date().isoformat() if prev>=0 else "",
                "buy_date":p["date"].date().isoformat()})
            del positions[i]
            last_sold[i]=t

        if prev>=0:
            candidates=context.candidate_indices(trader,prev,positions,last_sold,t)
            for i in candidates:
                if len(positions)>=st.max_positions:break
                opening=a["open"][i,t]
                if not np.isfinite(opening) or opening<=0 or a["volume"][i,t]<=0:continue
                current_nav=cash+sum(p["qty"]*(
                    float(a["open"][j,t]) if np.isfinite(a["open"][j,t]) else p["price"])
                    for j,p in positions.items())
                allocation=position_budget(st,cash,current_nav,float(opening),a["atr14"][i,prev])
                prev_row=context.stop_row(i,prev)
                if not pass_cost_gate(st,prev_row,allocation):continue
                adv=a["value20_prev"][i,prev]
                slip=modeled_slippage(st,adv,allocation)
                px=float(opening)*(1+slip)
                max_qty_volume=int(a["vol20_prev"][i,prev]*st.max_daily_participation)
                max_qty_budget=int(allocation/(px*(1+st.fee_rate)))
                qty=(min(max_qty_budget,max_qty_volume)//st.lot)*st.lot
                if qty<st.lot:continue
                # Slippage is a function of actual notional, never future volume.
                slip=modeled_slippage(st,adv,qty*float(opening))
                px=float(opening)*(1+slip)
                cost=qty*px*(1+st.fee_rate)
                if cost>cash+0.001:continue
                cash-=cost
                p={"qty":qty,"price":px,"buy_cost":cost,"date":dates[t],
                   "buy_index":t,"high_water":px,"exit_pending":""}
                positions[i]=p
                trades.append({"date":dates[t].date().isoformat(),"trader":trader,
                    "symbol":context.symbols[i],"side":"MUA","qty":qty,
                    "price":round(px),"gross":round(qty*px),"fees":round(cost-qty*px),
                    "tax":0,"pnl":np.nan,"slippage_rate":round(slip,6),
                    "reason":"Tín hiệu sau đóng cửa hôm trước; xác nhận thanh khoản/chi phí",
                    "signal_date":dates[prev].date().isoformat(),"buy_date":dates[t].date().isoformat()})

        invested=0.
        for i,p in positions.items():
            last_close=a["close"][i,t]
            px=float(last_close) if np.isfinite(last_close) and last_close>0 else p["price"]
            invested+=p["qty"]*px
        curve.append({"date":dates[t],"nav":cash+invested,"cash":cash,
                      "invested":invested,"position_count":len(positions)})

    history=pd.DataFrame(curve).set_index("date")
    history["return_pct"]=(history["nav"]/st.initial_cash-1)*100
    history["drawdown_pct"]=(history["nav"]/history["nav"].cummax()-1)*100
    benchmark_close=context.benchmark["close"].reindex(history.index).ffill()
    history["benchmark_nav"]=st.initial_cash*benchmark_close/benchmark_close.iloc[0]
    history["benchmark_return_pct"]=(history["benchmark_nav"]/st.initial_cash-1)*100
    tdf=pd.DataFrame(trades)
    sold=tdf[tdf.side=="BÁN"] if not tdf.empty else pd.DataFrame()
    nclosed=len(sold)
    holdings=[]
    for i,p in positions.items():
        cl=a["close"][i,last]
        price=float(cl) if np.isfinite(cl) else p["price"]
        value=p["qty"]*price
        holdings.append({"symbol":context.symbols[i],"qty":p["qty"],
            "buy_date":p["date"].date().isoformat(),"buy_price":round(p["price"]),
            "last_price":round(price),"value":round(value),
            "pnl":round(value-p["buy_cost"]),
            "pnl_pct":(value/p["buy_cost"]-1)*100,
            "pending_exit":p.get("exit_pending","")})
    actions=[]
    for i,symbol in enumerate(context.symbols):
        if not np.isfinite(a["close"][i,last]):continue
        row=context.stop_row(i,last)
        if i in positions:
            yes,reason=stop_signal(trader,row,positions[i])
            action=("CHỜ BÁN" if positions[i].get("exit_pending") else
                    "THEO DÕI BÁN" if yes else "TIẾP TỤC GIỮ")
            text=positions[i].get("exit_pending") or reason or "Chưa có tín hiệu thoát"
            actions.append({"symbol":symbol,"action":action,"reason":text})
        elif context.buy[trader][i,last]:
            actions.append({"symbol":symbol,"action":"TÍN HIỆU MUA",
                            "reason":"Tín hiệu sau đóng cửa, chưa khớp lệnh"})
    return {"trader":trader,"curve":history,"trades":tdf,
        "holdings":pd.DataFrame(holdings),"actions":pd.DataFrame(actions),
        "nav":float(history.nav.iloc[-1]),"cash":float(cash),
        "return_pct":float(history.return_pct.iloc[-1]),
        "benchmark_return_pct":float(history.benchmark_return_pct.iloc[-1]),
        "max_drawdown_pct":float(history.drawdown_pct.min()),
        "closed_trades":nclosed,"win_rate":(float((sold.pnl>0).sum())/nclosed*100 if nclosed else None),
        "positions":len(positions),"last_date":dates[last].date().isoformat(),
        "buy_count":int((tdf.side=="MUA").sum()) if not tdf.empty else 0}


def build_hybrid_signals(context: FastContext, base_curves: dict[str,pd.DataFrame],
                         training_bars:int=126, rebalance_bars:int=21) -> dict:
    """Causal selector: at the close of day t inspect base-bot NAVs <= t only.

    Training returns and drawdowns are computed from [t-126,t]; no return from
    t+1 or whole-window winner is used. Eligible only if the trailing realized
    return is POSITIVE. The basket stays frozen for 21 bars, avoiding churn.
    """
    if not base_curves or any(k not in base_curves for k in CORE):
        raise ValueError("Need full historical base-bot NAV curves")
    dates=context.dates
    dsize=len(dates)
    lookup={}
    for k in CORE:
        ser=base_curves[k]["nav"].reindex(dates).astype(float).ffill()
        lookup[k]=ser.to_numpy()
    current={}
    first_train=None
    for t in range(dsize):
        if t<training_bars:continue
        if first_train is None:first_train=t
        if (t-first_train)%rebalance_bars==0:
            ranking=[]
            for name in CORE:
                v=lookup[name][t-training_bars:t+1]
                if len(v)<training_bars+1 or not np.isfinite(v).all() or v[0]<=0:continue
                ret=v[-1]/v[0]-1
                peak=np.maximum.accumulate(v)
                dd=float(np.min(v/peak-1))
                score=float(ret + .35*dd)
                if ret>0 and score>0:
                    ranking.append((score,name))
            ranking.sort(key=lambda x:(-x[0],x[1]))
            top=ranking[:3]
            total=sum(score for score,_ in top)
            current={name:score/total for score,name in top} if total>0 else {}
        context.hybrid_winners[t]=dict(current)
        if not current:continue
        weights=np.zeros((len(context.symbols),),dtype=float)
        for name,w in current.items():
            weights+=context.buy[name][:,t].astype(float)*w
        # Requiring an aligned majority limits spurious lone votes.
        context.buy["Hybrid"][:,t]=(weights>=.50)&(
            context.a["rs60"][:,t]>.01)&(context.a["market_ok"][:,t]>0)&(
            context.a["close"][:,t]>context.a["sma50"][:,t])
    context.build_completed=True
    return {"training_sessions":training_bars,"rebalance_sessions":rebalance_bars,
            "leaders_latest":context.hybrid_winners.get(dsize-1,{}),
            "selection_rule":"positive last-126-session NAV and risk-adjusted ranking, with no future bars"}
