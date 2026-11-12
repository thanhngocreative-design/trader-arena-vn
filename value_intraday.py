"""Explicit experimental minute/combo adaptations of annual-quality models.

No assertion that Buffett or Munger trade this way. Shared causal bar execution,
separate accounts from both their daily books and the original eleven bots.
"""
from datetime import datetime
from pathlib import Path
import json
import numpy as np
import pandas as pd
from engine import Settings
from minute_arena import step,snapshot
from sector_analytics import aggregate_trades
from value_investing import ROOT,VN,POLICY,quality,eligible_companies,read,write

MODES=('paper_minute','paper_combo')
SETTINGS={k:Settings(max_positions=p['positions'],portfolio_policy='baseline') for k,p in POLICY.items()}
REVISION='value_intraday_v1'

def empty_accounts():
    return {k:dict(cash=100_000_000.,positions={},pending={},closed={},trades=[],history=[]) for k in POLICY}

def minute_features(f):
    c=f.close;v=f.volume;before=c.shift();p=f.copy()
    ma10=c.rolling(10).mean();ma20=c.rolling(20).mean();vf=v/v.shift().rolling(20).mean()
    valid=(c>=5000)&(c.rolling(30).std(ddof=0)/c).between(.0002,.12)&((c/before-1).abs()<.075)&(f.index.to_series().diff().dt.total_seconds().rolling(10).max()<=120)&(np.arange(len(f))>=30)
    # Price anchors use completed minute prices only, not daily OHLCV.
    p['Buffett']=(valid&(c<=ma20*.998)&(c>before)&(vf>=.8)).fillna(False)
    p['Munger']=(valid&(c>=ma20)&(c<=ma20*1.005)&(c>ma10)&(vf>=1.)).fillna(False)
    p['atr']=pd.concat([f.high-f.low,(f.high-before).abs(),(f.low-before).abs()],axis=1).max(axis=1).rolling(14).mean()
    p['adv']=(c*v).rolling(20).mean()*225;p['ma20']=ma20;p['ma10']=ma10
    return p

def exit_rule(bot,row,entry):
    # Forced exit on a failed/expired annual screen is also settlement-limited.
    if not row.get('quality_'+bot,False):return True
    if bot=='Buffett':return row['close']<row['ma20']*.985 or row['close']<entry*.925
    return row['close']<row['ma20']*.99 or row['close']<entry*.94

def gates_for_date(reports,prices,date):
    date=pd.Timestamp(date);out={k:{} for k in POLICY}
    for bot in POLICY:
        for sym,rs in reports.items():
            q=quality(rs,date,bot)
            if not q:continue
            combo=False
            if sym in prices and date in prices[sym].index:
                r=prices[sym].loc[date]
                combo=bool(r.adv>=3_000_000_000 and r.close>=5000 and r.close<=r.ma200*POLICY[bot]['price_anchor'])
            out[bot][sym]=dict(q,combo=combo,asof=str(date.date()))
    return out

def export_gates(bundle,prices,symbols,date,root=ROOT):
    classification=read(root/'config/market-classification.json')['sectors']
    reports=eligible_companies(bundle,classification)
    obj=dict(revision=REVISION,date=str(pd.Timestamp(date).date()),source_asof=bundle['asof'],published_at=datetime.now(VN).isoformat(),bots=gates_for_date(reports,prices,date))
    write(root/'state/value_daily_gates.json',obj)
    return obj

def value_step(accounts,symbol,row,ts,session,marks,gates,combo=False,submitted_at=None):
    row=dict(row);entry={}
    for bot in accounts:
        q=gates.get(bot,{}).get(symbol);row['quality_'+bot]=bool(q)
        entry[bot]=bool(q and row.get(bot,False) and (not combo or q['combo']))
    prior={k:b['pending'].get(symbol) for k,b in accounts.items()}
    lengths={k:len(b['trades']) for k,b in accounts.items()}
    before={k:(b['cash'],dict(b['positions'].get(symbol,{}))) for k,b in accounts.items()}
    step(accounts,symbol,row,ts,session,marks,submitted_at=submitted_at,entry_gates=entry,bot_settings=SETTINGS,exit_rule=exit_rule)
    for bot,b in accounts.items():
        req=b['pending'].get(symbol)
        if req:
            q=gates.get(bot,{}).get(symbol)
            req.update(symbol=symbol,financial_available_at=q['available_at'] if q else None,quality_asof=q['asof'] if q else None)
        if len(b['trades'])>lengths[bot]:
            trade=b['trades'][-1];cash,position=before[bot];settings=SETTINGS[bot]
            net=b['cash']-cash
            gross=-net/(1+settings.fee_rate) if trade['side']=='MUA' else net/(1-settings.fee_rate-settings.sell_tax)
            trade.update(price=gross/trade['qty'],gross=gross,fees=gross*settings.fee_rate,tax=0. if trade['side']=='MUA' else gross*settings.sell_tax)
            if trade['side']=='BÁN':trade['pnl']=net-position['cost']*trade['qty']/position['qty']
            for key in ('financial_available_at','quality_asof'):
                trade[key]=(prior[bot] or {}).get(key)
            trade['rules_revision']=REVISION

def load_state(root=ROOT,now=None):
    path=root/'state/value_intraday.json'
    if path.exists():return read(path)
    return dict(revision=REVISION,started_at=(now or datetime.now(VN)).isoformat(),last_observed_at=None,sessions=[],symbols_observed=[],marks={},watermarks={},paper_minute=empty_accounts(),paper_combo=empty_accounts())

def publish(state,status,errors=None,root=ROOT):
    now=datetime.now(VN);not_before=pd.Timestamp(now).tz_localize(None).ceil('min')+pd.Timedelta(seconds=1)
    for mode in MODES:
        for b in state[mode].values():
            for req in b['pending'].values():
                if not req.get('persisted'):
                    req['submitted']=max(pd.Timestamp(req['submitted']),not_before).isoformat();req['persisted']=True
    state.update(updated_at=now.isoformat(),status=status)
    public={k:state.get(k) for k in ('revision','started_at','updated_at','status','last_observed_at','sessions','symbols_observed','gate_date','gate_valid','provider_verified_at')}
    classification=read(root/'config/market-classification.json')['sectors'];symbols=read(root/'config/research-universe.json')['eligible_symbols']
    for mode in MODES:
        public[mode]=snapshot(state[mode],state['marks'])
        for bot,b in public[mode].items():
            b['paper_started_at']=state['started_at'];b['sector_stats']=aggregate_trades(state[mode][bot]['trades'],classification,symbols)
    public['errors']=(errors or [])[:8]
    public['note']='Biến thể phút thử nghiệm, không phải cách Buffett/Munger thực sự giao dịch. Bộ lọc tài chính biết từ phiên trước; combo thêm giá/MA200 và thanh khoản ngày trước. Lệnh chỉ khớp nến tương lai sau khi đã lưu; không chạy bù quá khứ.'
    write(root/'state/value_intraday.json',state);write(root/'site/value-intraday.json',public)
    return public
