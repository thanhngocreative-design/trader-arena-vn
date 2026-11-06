"""Event-sourced, close-to-close simulated portfolios, *not* real executions.

On the FIRST successful after-close update, positions remain empty. That day's
signals are queued for the NEXT session. On subsequent updates, only previously
recorded signals can fill at the next open. Missing scheduled sessions are
reported as a fidelity warning because historical reconstruction is not live.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from engine import Settings, TRADERS, make_features, stop_signal
from execution import modeled_slippage, pass_cost_gate

DEFAULT_STATE = Path(__file__).resolve().parent / 'state' / 'paper_state.json'
RULES_REVISION = 2


def _now():
    return datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(timespec='seconds')


def _base_bot(settings):
    return {'cash': settings.initial_cash, 'positions': {}, 'orders_next': [], 'trades': [], 'history': []}


def _summary(bot, date, rows, settings):
    holdings=[]
    invested=0.
    for symbol, p in bot['positions'].items():
        r=rows.get(symbol)
        mark=float(r['close']) if r is not None and pd.notna(r.get('close')) else p['entry_price']
        value=mark*p['qty']; invested += value
        holdings.append({'symbol':symbol, 'qty':p['qty'], 'buy_price':round(p['entry_price']),
                         'last_price':round(mark),'value':round(value),
                         'pnl':round(value-p['entry_cost']),
                         'pnl_pct':round((value/p['entry_cost']-1)*100,2),
                         'buy_date':p['buy_date']})
    nav=bot['cash']+invested
    out={'date':str(date.date()), 'nav':round(nav), 'cash':round(bot['cash']),
         'return_pct':round((nav/settings.initial_cash-1)*100,3), 'holdings':holdings}
    return out


def _plans(bot, trader, rows, features, date, settings):
    plans=[]
    for symbol,pos in bot['positions'].items():
        r=rows.get(symbol)
        if r is None: continue
        pos['high_water']=max(pos['high_water'],float(r['high']))
        if pos.get('pending_exit'):
            plans.append({'side':'SELL','symbol':symbol,'reason':pos['pending_exit']})
        else:
            exit_yes,reason=stop_signal(trader,r,pos)
            if exit_yes:
                pos['pending_exit']=reason
                plans.append({'side':'SELL','symbol':symbol,'reason':reason})
    candidates=[]
    for symbol,r in rows.items():
        if symbol in bot['positions']: continue
        if bool(r.get(f'buy_{trader}',False)) and pd.notna(r.get('momentum60')):
            candidates.append((float(r['momentum60']),symbol))
    candidates.sort(key=lambda x:(-x[0],x[1]))
    for score,symbol in candidates:
        r=rows[symbol]
        if not pass_cost_gate(settings,r,settings.initial_cash/settings.max_positions):
            continue
        plans.append({'side':'BUY','symbol':symbol, 'reason':'Tín hiệu xác nhận thanh khoản và đủ biên độ so với chi phí',
                      'signal_date':str(date.date()),
                      'vol20_prev':float(r['vol20_prev']),
                      'atr14':float(r['atr14']),
                      'signal_close':float(r['close']),
                      'value20_prev':float(r['value20_prev']),
                      'score':round(score,4)})
    return plans


def _execute(bot, date, index_pos, rows, settings):
    orders=bot['orders_next']; bot['orders_next']=[]
    last_sold=bot.setdefault('last_sold',{})
    sells=[o for o in orders if o['side']=='SELL']
    buys=[o for o in orders if o['side']=='BUY']
    events=[]
    for o in sells:
        s=o['symbol']; pos=bot['positions'].get(s); r=rows.get(s)
        if pos is None: continue
        if index_pos < pos['buy_index']+max(3,settings.minimum_hold_sessions) or r is None or pd.isna(r['open']) or r['volume']<=0:
            # Reconsider exit after today's close; preserve pending_exit.
            continue
        slip=modeled_slippage(settings,r.get('value20_prev',0),float(r['open'])*pos['qty'])
        price=float(r['open'])*(1-slip)
        gross=pos['qty']*price; fee=gross*settings.fee_rate; tax=gross*settings.sell_tax
        proceeds=gross-fee-tax
        pnl=proceeds-pos['entry_cost']
        bot['cash'] += proceeds
        trade={'date':str(date.date()),'symbol':s,'side':'BÁN','qty':pos['qty'],
               'price':round(price),'pnl':round(pnl),'reason':o['reason'],
               'fee':round(fee),'tax':round(tax),'slippage_rate':round(slip,6)}
        bot['trades'].append(trade); events.append(trade)
        del bot['positions'][s]
        last_sold[s]=index_pos
    for o in buys:
        s=o['symbol']; r=rows.get(s)
        if s in bot['positions'] or len(bot['positions'])>=settings.max_positions: continue
        if s in last_sold and index_pos-last_sold[s]<settings.cooldown_sessions: continue
        if r is None or pd.isna(r['open']) or r['open']<=0 or r['volume']<=0: continue
        allocation_guess=bot['cash']/max(1,settings.max_positions)
        # Intraday OHLCV of this execution date is not available at the
        # opening auction. Recheck against the PREVIOUS day's queued facts only.
        signal_facts={'atr14':o.get('atr14'),'close':o.get('signal_close'),
                      'value20_prev':o.get('value20_prev')}
        if not pass_cost_gate(settings,signal_facts,allocation_guess):
            continue
        slip=modeled_slippage(settings,r.get('value20_prev',0),allocation_guess)
        price=float(r['open'])*(1+slip)
        gross_nav=bot['cash']
        for held,p in bot['positions'].items():
            held_row=rows.get(held)
            held_px=float(held_row['open']) if held_row is not None and pd.notna(held_row['open']) else p['entry_price']
            gross_nav+=held_px*p['qty']
        allocation=min(bot['cash'],gross_nav/settings.max_positions)
        max_qty_by_liquidity=int(o['vol20_prev']*settings.max_daily_participation)
        max_qty_by_budget=int(allocation/(price*(1+settings.fee_rate)))
        qty=(min(max_qty_by_liquidity,max_qty_by_budget)//settings.lot)*settings.lot
        if qty < settings.lot: continue
        slip=modeled_slippage(settings,r.get('value20_prev',0),qty*float(r['open']))
        price=float(r['open'])*(1+slip)
        cost=qty*price*(1+settings.fee_rate)
        if cost>bot['cash']+0.001:continue
        bot['cash']-=cost
        bot['positions'][s]={'qty':qty,'entry_price':price,'price':price,'entry_cost':cost,
                             'buy_index':index_pos,'buy_date':str(date.date()),
                             'high_water':price,'pending_exit':''}
        trade={'date':str(date.date()),'symbol':s,'side':'MUA','qty':qty,
               'price':round(price),'reason':o['reason'],'fee':round(cost-qty*price),'tax':0,
               'slippage_rate':round(slip,6)}
        bot['trades'].append(trade); events.append(trade)
    return events


def update_paper(prices, benchmark, state_path=DEFAULT_STATE, settings=None,
                 active_ids=None, prepared_rows=None):
    settings=settings or Settings()
    active_ids=set(TRADERS) if active_ids is None else set(active_ids)
    if not active_ids.issubset(TRADERS):
        raise ValueError("Bot bật/tắt không nằm trong danh sách")
    session=benchmark.index.max()
    full_idx=benchmark.index
    if prepared_rows is not None:
        features={}
        rows=prepared_rows
    else:
        features={s:make_features(frame,benchmark,settings.min_average_value).reindex(full_idx)
                  for s,frame in prices.items() if len(frame)>=252}
        if not features:
            raise ValueError('Dữ liệu không đủ để tính tín hiệu')
        rows={s:f.loc[session] for s,f in features.items() if session in f.index}
    if any(s not in rows or pd.isna(rows[s]['close']) for s in prices):
        raise ValueError('Dữ liệu cuối phiên thiếu cho một số cổ phiếu')
    state_path=Path(state_path); state_path.parent.mkdir(exist_ok=True,parents=True)
    if state_path.exists():
        state=json.loads(state_path.read_text(encoding='utf-8'))
        if state.get('version') != 1: raise ValueError('State version không được hỗ trợ')
    else:
        state={'version':1,'started_at':_now(),'last_session':None,
               'bots':{key:_base_bot(settings) for key in TRADERS},'warnings':[],
               'rules_revision':RULES_REVISION}
    # Upgrade a running contest in place. The original bots keep their entire
    # journal; newly introduced bot IDs start NOW with 100m virtual cash.
    added=[key for key in TRADERS if key not in state['bots']]
    for key in added:
        state['bots'][key]=_base_bot(settings)
    last=state['last_session']
    today=str(session.date())
    migrated=state.get('rules_revision') != RULES_REVISION
    if last is not None and today<=last:
        if not (added or migrated):
            return state, False
        if today != last:
            raise ValueError('State có ngày phiên mới hơn dữ liệu; không thể nâng cấp an toàn')
        for key in TRADERS:
            bot=state['bots'][key]
            # On rule migration, discard yesterday's pending signals; do not
            # retroactively create fills or delete any historical transactions.
            bot['orders_next']=_plans(bot,key,rows,features,session,settings) if key in active_ids else []
            if key in added:
                bot['started_session']=today
                summary=_summary(bot,session,rows,settings)
                bot['latest']=summary
                bot['history'].append({k:summary[k] for k in ('date','nav','cash','return_pct')})
        state['updated_at']=_now()
        state['rules_revision']=RULES_REVISION
        state['cloud_enabled']={key: key in active_ids for key in TRADERS}
        state['warnings'].append('Nâng cấp luật bot ở phiên '+today+
                                 ' mà không hồi tố lệnh giao dịch cũ.')
        tmp=state_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        tmp.replace(state_path)
        return state, True
    idx_pos=full_idx.get_loc(session)
    missed=0
    if last is not None:
        last_t=pd.Timestamp(last)
        if last_t not in full_idx:
            raise ValueError('Ngày trước trong state không còn nằm trong lịch giao dịch')
        missed=idx_pos-full_idx.get_loc(last_t)-1
        if missed>0:
            state['warnings'].append(f'Bỏ lỡ {missed} phiên giữa {last} và {today}; không tự tạo giao dịch cho các phiên đó.')
    for key in TRADERS:
        bot=state['bots'][key]
        if last is None or missed>0 or migrated or key in added or key not in active_ids:
            # Do NOT backdate orders. Disabled bots neither trade nor queue new orders.
            bot['orders_next']=[]
        else:
            _execute(bot,session,idx_pos,rows,settings)
        bot['orders_next']=_plans(bot,key,rows,features,session,settings) if key in active_ids else []
        summary=_summary(bot,session,rows,settings)
        bot['latest']=summary
        bot['history'].append({k:summary[k] for k in ('date','nav','cash','return_pct')})
        bot['history']=bot['history'][-800:]
    state['last_session']=today
    state['rules_revision']=RULES_REVISION
    state['cloud_enabled']={key: key in active_ids for key in TRADERS}
    state['updated_at']=_now()
    # Atomic write, caller should commit updated state to a persistent remote repository.
    tmp=state_path.with_suffix('.tmp')
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    tmp.replace(state_path)
    return state, True
