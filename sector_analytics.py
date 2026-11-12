"""ICB sector counts and complete-ledger trade attribution, never guessed labels."""
import math
from pathlib import Path
import json

UNKNOWN='Chưa phân loại'

def aggregate_trades(trades,classification,research_symbols):
    groups={};outside=0;outside_buys=0
    for t in trades:
        side=t.get('side')
        if side not in ('MUA','BÁN'):raise ValueError('Unexpected executed trade side')
        sym=t['symbol'];meta=classification.get(sym,{})
        code=meta.get('icb_code') or 'UNKNOWN';name=meta.get('sector') or UNKNOWN
        g=groups.setdefault(code,dict(icb_code=code,sector=name,buy_fills=0,sell_fills=0,buy_value=0.,sell_value=0.,realized_pnl=0.,symbols=set()))
        qty=float(t['qty']);price=float(t['price']);gross=t.get('gross')
        value=float(gross) if gross is not None and math.isfinite(float(gross)) else qty*price
        if not all(math.isfinite(x) and x>0 for x in (qty,price,value)):raise ValueError('Invalid executed value')
        g['symbols'].add(sym)
        if sym not in research_symbols:
            outside+=1;outside_buys+=side=='MUA'
        if side=='MUA':g['buy_fills']+=1;g['buy_value']+=value
        else:
            pnl=float(t['pnl'])
            if not math.isfinite(pnl):raise ValueError('Missing realized PNL')
            g['sell_fills']+=1;g['sell_value']+=value;g['realized_pnl']+=pnl
    total_buys=sum(g['buy_fills'] for g in groups.values());total_value=sum(g['buy_value'] for g in groups.values())
    result=[]
    for g in groups.values():
        g['symbols']=sorted(g['symbols']);g['unique_symbols']=len(g['symbols'])
        g['buy_share_pct']=round(100*g['buy_value']/total_value,2) if total_value else 0
        g['buy_fill_share_pct']=round(100*g['buy_fills']/total_buys,2) if total_buys else 0
        for key in ('buy_value','sell_value','realized_pnl'):g[key]=round(g[key])
        result.append(g)
    result.sort(key=lambda g:(-g['buy_value'],g['sector']))
    return dict(sectors=result,buy_fills=total_buys,sell_fills=sum(g['sell_fills'] for g in result),buy_value=round(total_value),outside_146_fills=outside,outside_146_buys=outside_buys)

def universe_distribution(symbols,metadata):
    sector_map=metadata['sectors'];listing=metadata['listing']
    active={s for s,v in listing.items() if v['type']=='STOCK' and v['exchange'] in ('HSX','HOSE','HNX','UPCOM')}
    groups={}
    for sym in sorted(active|set(symbols)):
        info=sector_map.get(sym,{});code=info.get('icb_code') or 'UNKNOWN'
        g=groups.setdefault(code,dict(icb_code=code,sector=info.get('sector') or UNKNOWN,symbols=[],market_count=0))
        if sym in active:g['market_count']+=1
        if sym in symbols:g['symbols'].append(sym)
    for g in groups.values():
        g['count']=len(g['symbols']);g['sample_share_pct']=round(g['count']/len(symbols)*100,2)
        g['market_share_pct']=round(g['market_count']/len(active)*100,2)
    return sorted(groups.values(),key=lambda g:(-g['count'],g['sector']))

def attach_paper_sectors(public,root,current_books=None):
    """Stats use complete private state, not public recent 30/40 trade lists."""
    root=Path(root);meta_path=root/'config/market-classification.json'
    if not meta_path.exists():return public
    meta=json.loads(meta_path.read_text(encoding='utf8'))
    u=set(json.loads((root/'config/research-universe.json').read_text(encoding='utf8'))['eligible_symbols'])
    for mode,path in [('paper','state/paper_state.json'),('paper_minute','state/paper_intraday.json'),('paper_combo','state/paper_intraday.json')]:
        state_path=root/path
        if mode not in public:continue
        if current_books and mode in current_books:
            bots=current_books[mode]
        else:
            if not state_path.exists():continue
            state=json.loads(state_path.read_text(encoding='utf8'));bots=state['bots'] if mode=='paper' else state[mode]
        for bot,ledger in bots.items():
            if bot in public[mode]:public[mode][bot]['sector_stats']=aggregate_trades(ledger['trades'],meta['sectors'],u)
    return public
