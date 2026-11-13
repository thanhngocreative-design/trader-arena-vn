"""Minute-only experimental proxies and shared causal bar-paper ledger.

No daily price feature enters this engine. T+ holding is a session-count rule.
Fills are modeled from a later observed open, not actual broker executions.
"""
from copy import deepcopy
import math
import pandas as pd
from engine import Settings, TRADERS
from portfolio import for_bot, allocation
from execution import modeled_slippage
from paper_metrics import paper_metrics
BOT_SETTINGS={k:for_bot(Settings(portfolio_policy='atr_v1'),k) for k in TRADERS}


def features(f):
    c=f.close; h=f.high; l=f.low; v=f.volume
    p=f.copy(); before=c.shift()
    hi10=h.shift().rolling(10).max(); hi20=h.shift().rolling(20).max(); hi30=h.shift().rolling(30).max()
    low10=l.shift().rolling(10).min(); low30=l.shift().rolling(30).min()
    ma5=c.rolling(5).mean(); ma10=c.rolling(10).mean(); ma20=c.rolling(20).mean()
    vf=v/v.shift().rolling(20).mean(); m3=c/c.shift(3)-1; m10=c/c.shift(10)-1
    m20=c/c.shift(20)-1; m30=c/c.shift(30)-1; vol=c.rolling(30).std(ddof=0)/c
    valid=(c>=5000)&vol.between(.0002,.12)&((c/before-1).abs()<.075)&(f.index.to_series().diff().dt.total_seconds().rolling(10).max()<=120)
    raw={
      'Minervini':(ma5>ma10)&(ma10>ma20)&(c>hi20)&(m20>.008)&(vf>1.18),
      'ONeil':(c>hi30)&(m30>.015)&(vf>1.45)&(c>ma20),
      'Darvas':(hi30/low30-1<.095)&(c>hi20)&(c>ma20)&(vf>1.10),
      'BNF':(m20<-.014)&(m3>.003)&(c>before)&(vf>.90),
      'CIS':(m3>.0045)&(m10>.011)&(ma5>ma10)&(vf>1.28),
      'Qullamaggie':(m30>.02)&(hi10/low10-1<.025)&(c>hi10)&(vf>1.20),
      'Unger':(c>hi20)&(ma10>ma20)&(vol>.003)&(vol<.045)&(vf>1.05),
      'ThaiPham':(c>hi20)&(c>ma5)&(m10>.007)&(vf>1.55),
      'DuongChung':(c<ma20*.995)&(m3>.004)&(m20<-.012)&(vf>.85),
      'PThai':(ma10>ma20)&(m20>.012)&(vol>.004)&(vol<.05)&(c>hi10)&(vf>1.10)}
    for k,mask in raw.items(): p[k]=(valid&mask&(pd.Series(range(len(f)),index=f.index)>=30)).fillna(False)
    p['Hybrid']=p[['Minervini','ONeil','CIS','Qullamaggie','PThai']].sum(axis=1)>=2
    p['atr']=pd.concat([h-l,(h-before).abs(),(l-before).abs()],axis=1).max(axis=1).rolling(14).mean()
    p['adv']=(c*v).rolling(20).mean()*225
    p['ma10']=ma10; p['ma20']=ma20; p['low20']=l.shift(1).rolling(20).min()
    return p


def darvas_features(f):
    """Same Darvas features, without calculating ten unused entry proxies."""
    c=f.close;h=f.high;l=f.low;v=f.volume;before=c.shift()
    p=f.copy()
    hi20=h.shift().rolling(20).max(); hi30=h.shift().rolling(30).max()
    low30=l.shift().rolling(30).min(); ma20=c.rolling(20).mean()
    valid=(c>=5000)&(c.rolling(30).std(ddof=0)/c).between(.0002,.12)&((c/before-1).abs()<.075)&(f.index.to_series().diff().dt.total_seconds().rolling(10).max()<=120)
    p['Darvas']=(valid&(hi30/low30-1<.095)&(c>hi20)&(c>ma20)&(v/v.shift().rolling(20).mean()>1.10)&(pd.Series(range(len(f)),index=f.index)>=30)).fillna(False)
    p['atr']=pd.concat([h-l,(h-before).abs(),(l-before).abs()],axis=1).max(axis=1).rolling(14).mean()
    p['adv']=(c*v).rolling(20).mean()*225
    p['ma10']=c.rolling(10).mean();p['ma20']=ma20
    # The current bar may BREAK the prior floor; it cannot define that floor.
    p['low20']=l.shift(1).rolling(20).min()
    return p


def exit_signal(bot,row,entry):
    c=row['close']; ma10=row['ma10']; ma20=row['ma20']
    if bot in ('BNF','DuongChung'): return c>=entry*1.018 or c<entry*.945 or c<ma20*.97
    if bot in ('CIS','ThaiPham'): return c<ma10*.994 or c<entry*.93
    if bot=='Darvas': return c<row['low20'] or c<entry*.9
    if bot in ('Unger','PThai'): return c<ma20*.99 or c<entry*.93
    return c<ma20*.985 or c<entry*.925


def new_accounts():
    return {k:dict(cash=100_000_000.,positions={},pending={},closed={},trades=[],history=[]) for k in TRADERS}


def step(accounts,symbol,row,ts,session,marks,*,submitted_at=None,entry_gates=None,bot_settings=None,exit_rule=None,nav_calculator=None):
    """A request must exist before its fill bar START. Never same-bar fills.

    Paper supplies actual receipt time; history supplies the signal bar end.
    Minute volume participation uses only the preceding observed signal bar.
    """
    if float(row['volume'])<=0:return
    ts=pd.Timestamp(ts); marks[symbol]=float(row['close'])
    for bot,b in accounts.items():
        p=b['positions'].get(symbol)
        gate=bool(row.get(bot,False)) if entry_gates is None else bool(entry_gates.get(bot,False))
        if not p and symbol not in b['pending'] and not gate: continue
        s=(bot_settings or BOT_SETTINGS)[bot]
        req=b['pending'].pop(symbol,None)
        if req:
            age=(ts-pd.Timestamp(req['signal'])).total_seconds()
            if 0<=age<=180 and pd.Timestamp(req['submitted'])>ts:
                b['pending'][symbol]=req
                continue
            if pd.Timestamp(req['submitted'])<=ts and 60<=age<=180:
                px=float(row['open']); qty=req['qty']
                slip=modeled_slippage(s,req['adv'],qty*px)
                if req['side']=='BUY' and not p and len(b['positions'])<s.max_positions:
                    px*=1+slip
                    qty=min(qty,int(min(req['budget'],b['cash'])/(px*(1+s.fee_rate)))//100*100)
                    if qty>=100:
                        cost=qty*px*(1+s.fee_rate); b['cash']-=cost
                        b['positions'][symbol]=dict(qty=qty,price=px,cost=cost,session=session,date=str(ts.date()))
                        b['trades'].append(dict(date=str(ts.date()),time=ts.isoformat(),signal_time=req['signal'],submitted_at=req['submitted'],symbol=symbol,side='MUA',qty=qty,price=round(px),fees=round(qty*px*s.fee_rate),pnl=None))
                elif req['side']=='SELL' and p and session-p['session']>=max(3,s.minimum_hold_sessions):
                    qty=min(qty,p['qty']); px*=1-slip
                    cost=p['cost']*qty/p['qty']; gross=qty*px; pnl=gross*(1-s.fee_rate-s.sell_tax)-cost
                    b['cash']+=gross*(1-s.fee_rate-s.sell_tax)
                    b['trades'].append(dict(date=str(ts.date()),time=ts.isoformat(),signal_time=req['signal'],submitted_at=req['submitted'],symbol=symbol,side='BÁN',qty=qty,price=round(px),fees=round(gross*s.fee_rate),tax=round(gross*s.sell_tax),pnl=round(pnl)))
                    p['qty']-=qty; p['cost']-=cost
                    if not p['qty']: del b['positions'][symbol]; b['closed'][symbol]=session
        p=b['positions'].get(symbol)
        cap=int(float(row['volume'])*.05)//100*100
        adv=float(row['adv']); atr=float(row['atr'])
        if cap<100 or not math.isfinite(adv) or adv<=0: continue
        if p:
            if session-p['session']<max(3,s.minimum_hold_sessions) or not (exit_rule or exit_signal)(bot,row,p['price']): continue
            req=dict(side='SELL',qty=min(cap,p['qty']))
        else:
            if not gate or len(b['positions'])>=s.max_positions or session-b['closed'].get(symbol,-999)<s.cooldown_sessions: continue
            nav=nav_calculator(bot,b,marks) if nav_calculator else b['cash']+sum(x['qty']*marks.get(k,x['price']) for k,x in b['positions'].items())
            budget=allocation(s,b['cash'],nav,float(row['close']),atr)
            qty=min(cap,int(budget/(float(row['close'])*(1+s.fee_rate)))//100*100)
            if qty<100: continue
            req=dict(side='BUY',qty=qty,budget=budget)
        req.update(signal=ts.isoformat(),submitted=pd.Timestamp(submitted_at or ts+pd.Timedelta(minutes=1)).isoformat(),adv=adv)
        b['pending'][symbol]=req


def snapshot(accounts,marks):
    result={}
    for bot,b in accounts.items():
        holds=[]
        for sym,p in b['positions'].items():
            px=marks.get(sym,p['price']); value=p['qty']*px
            holds.append(dict(symbol=sym,qty=p['qty'],buy_date=p['date'],buy_price=round(p['price']),last_price=round(px),value=round(value),pnl=round(value-p['cost']),pnl_pct=(value/p['cost']-1)*100))
        nav=b['cash']+sum(h['value'] for h in holds)
        result[bot]=dict(nav=round(nav),cash=round(b['cash']),return_pct=round((nav/100_000_000-1)*100,2),holdings=holds,trades=list(reversed(b['trades'][-40:])),history=deepcopy(b['history']),orders_next=list(b['pending'].values()),**paper_metrics(b['trades'],b['history'],nav))
    return result
