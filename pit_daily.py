"""Daily point-in-time study, original 11 engines plus two annual-quality models."""
import numpy as np
import pandas as pd
from engine import TRADERS,Settings,backtest
from fast_engine import CORE,build_hybrid_signals
from execution import modeled_slippage
from value_investing import ROOT,POLICY,quality,eligible_companies,read,write
from pit_universe import load_daily
from pit_context import PITContext
from generate_dashboard import summary_backtest
from sector_analytics import aggregate_trades

def merged_fundamentals():
    bundle=read(ROOT/'config/value-fundamentals-300.json');old=read(ROOT/'config/value-fundamentals.json')
    bundle['companies']={**old['companies'],**bundle['companies']}
    return bundle

def attach_summary(result,classification,symbols):
    out=summary_backtest(result);out['sector_stats']=aggregate_trades(result['trades'].to_dict('records'),classification,symbols)
    history=result['curve'];reserve=history.get('valuation_reserve',pd.Series(0.,index=history.index))
    last=out['nav'];gap=float(reserve.iloc[-1]);unreserved=history.nav+reserve
    out['valuation_audit']=dict(policy='After 20 benchmark sessions with no observed quote, reserve 100% of stale marked value for NAV only; no zero market candle, sale or cash receipt is fabricated. Quotes resuming reverse the reserve.',final_reserve=round(gap),maximum_reserve=round(float(reserve.max())),sessions_with_reserve=int((reserve>0).sum()),nav_last_quote_convention=round(last+gap),return_last_quote_pct=round(((last+gap)/100_000_000-1)*100,2),max_drawdown_last_quote_pct=round(float((unreserved/unreserved.cummax()-1).min()*100),2))
    return out

def value_backtest(ctx,bot,start,end,reports):
    st=Settings(max_positions=POLICY[bot]['positions']);first=ctx.dates.searchsorted(start);last=ctx.dates.searchsorted(end,side='right')-1
    cash=100_000_000.;positions={};pending=[];trades=[];history=[];review=None
    def nav(t,at_open=False):return cash+sum(p['qty']*ctx.mark_price(i,t,at_open=at_open,fallback=p['price']) for i,p in positions.items())
    for t in range(first,last+1):
        prev=t-1;date=ctx.dates[t];date_str=str(date.date())
        for i,p in list(positions.items()):
            if ctx.forced_exit(i,t):p['exit_pending']='Ra khỏi danh mục tháng đã biết trước phiên'
            if not p.get('exit_pending') or t-p['buy_index']<5:continue
            opening=ctx.a['open'][i,t];adv,avol=ctx.execution_liquidity(i,prev)
            if not np.isfinite(opening) or not np.isfinite(adv) or not np.isfinite(avol) or ctx.a['volume'][i,t]<=0:continue
            qty=min(p['qty'],int(avol*.005)//100*100)
            if qty<100:continue
            px=float(opening)*(1-modeled_slippage(st,adv,qty*opening));gross=px*qty;fee=gross*st.fee_rate;tax=gross*st.sell_tax
            portion=p['buy_cost'] if qty==p['qty'] else p['buy_cost']*qty/p['qty'];pnl=gross-fee-tax-portion
            cash+=gross-fee-tax
            trades.append(dict(date=date_str,symbol=ctx.symbols[i],trader=bot,side='BÁN',qty=qty,price=px,gross=gross,fees=fee,tax=tax,pnl=pnl,reason=p['exit_pending'],signal_date=str(ctx.dates[prev].date())))
            p['qty']-=qty;p['buy_cost']-=portion
            if not p['qty']:del positions[i]
        for i,q,signal in pending:
            if i in positions or len(positions)>=st.max_positions or not ctx.allowed[i,t] or signal!=prev:continue
            opening=ctx.a['open'][i,t];adv,avol=ctx.execution_liquidity(i,prev)
            if not np.isfinite(opening) or not np.isfinite(adv) or not np.isfinite(avol) or ctx.a['volume'][i,t]<=0:continue
            budget=min(cash,nav(prev)/st.max_positions);px=float(opening)*(1+modeled_slippage(st,adv,budget))
            qty=int(min(budget/(px*(1+st.fee_rate)),avol*.005)//100)*100
            if qty<100:continue
            gross=qty*px;fee=gross*st.fee_rate;cash-=gross+fee
            positions[i]=dict(qty=qty,buy_cost=gross+fee,price=px,buy_index=t,date=date_str,exit_pending='')
            trades.append(dict(date=date_str,symbol=ctx.symbols[i],trader=bot,side='MUA',qty=qty,price=px,gross=gross,fees=fee,tax=0.,pnl=np.nan,signal_date=str(ctx.dates[signal].date()),financial_available_at=q['available_at']))
        pending=[]
        reserve=sum(ctx.reserve_value(i,t,p['qty']) for i,p in positions.items())
        history.append(dict(date=date,nav=nav(t),cash=cash,position_count=len(positions),valuation_reserve=reserve))
        month=date_str[:7]
        if month!=review:
            review=month;rank=[]
            for symbol,rs in reports.items():
                if symbol not in ctx.pos:continue
                i=ctx.pos[symbol];q=quality(rs,date,bot)
                if i in positions:
                    if not q:positions[i]['exit_pending']='Chất lượng báo cáo năm không còn đạt hoặc quá cũ'
                elif ctx.allowed[i,t] and q:
                    c=ctx.a['close'][i,t];ma=ctx.a['sma200'][i,t];adv,_=ctx.execution_liquidity(i,t)
                    if c>=5000 and c<=ma*POLICY[bot]['price_anchor'] and adv>=3_000_000_000:rank.append((q['score'],symbol,i,q))
            rank.sort(key=lambda x:(-x[0],x[1]));pending=[(i,q,t) for _,_,i,q in rank[:max(0,st.max_positions-len(positions))]]
    h=pd.DataFrame(history).set_index('date');h['return_pct']=(h.nav/100_000_000-1)*100;h['drawdown_pct']=(h.nav/h.nav.cummax()-1)*100
    b=ctx.benchmark.close.reindex(h.index);h['benchmark_return_pct']=(b/b.iloc[0]-1)*100
    holdings=[]
    for i,p in positions.items():
        m=ctx.mark_info(i,last,fallback=p['price']);value=m['value_price']*p['qty'];pnl=value-p['buy_cost']
        holdings.append(dict(symbol=ctx.symbols[i],qty=p['qty'],buy_date=p['date'],buy_price=p['price'],last_price=m['price'],value=round(value),pnl=round(pnl),pnl_pct=pnl/p['buy_cost']*100,quote_date=m['quote_date'],quote_age_sessions=m['age'],valuation_reserve=round((m['price']-m['value_price'])*p['qty']),valuation_note='Dự phòng định giá khi thiếu giá; không phải lệnh bán hay giá thị trường 0' if m['reserve'] else 'Giá quan sát'))
    td=pd.DataFrame(trades);sells=td[td.side=='BÁN'] if len(td) else td
    return dict(curve=h,trades=td,holdings=pd.DataFrame(holdings),actions=pd.DataFrame(),nav=float(h.nav.iloc[-1]),cash=cash,return_pct=float(h.return_pct.iloc[-1]),benchmark_return_pct=float(h.benchmark_return_pct.iloc[-1]),max_drawdown_pct=float(h.drawdown_pct.min()),closed_trades=len(sells),buy_count=sum(r['side']=='MUA' for r in trades),win_rate=100*float((sells.pnl>0).sum())/len(sells) if len(sells) else None)

def run(target=None):
    config=read(ROOT/'config/research-300.json');all_prices,audit,hashes=load_daily();classification=read(ROOT/'config/market-classification.json')['sectors']
    original=read(ROOT/'config/research-universe.json')['eligible_symbols'];bundle=merged_fundamentals();reports=eligible_companies(bundle,classification)
    raw=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv');raw['date']=pd.to_datetime(raw.date);benchmark=raw.set_index('date');benchmark[['open','high','low','close']]*=1000
    source={s:all_prices[s] for s in sorted(set(config['training_symbols'])|set(original)) if s in all_prices}
    settings=Settings(portfolio_policy='atr_v1');cohorts={}
    periods=read(ROOT/'site/research-146.json')['backtest_options']
    for name,static in [('300',None),('146',original)]:
        if target and name!=target:continue
        ctx=PITContext(source,benchmark,config['months'],settings,static)
        training={k:backtest(source,benchmark,k,'2022-01-03',end_date=config['end'],settings=settings,features_cache=ctx)['curve'] for k in CORE}
        build_hybrid_signals(ctx,training);results={}
        for option in periods:
            label=option['key'];results[label]={}
            for bot in list(TRADERS)+list(POLICY):
                result=backtest(source,benchmark,bot,option['start'],end_date=option['end'],settings=settings,features_cache=ctx) if bot in TRADERS else value_backtest(ctx,bot,option['start'],option['end'],reports)
                results[label][bot]=attach_summary(result,classification,set(ctx.symbols))
                if label=='ALL':write(ROOT/'data/pit_results'/f'daily-{name}-{bot}-trades.json',result['trades'].astype(object).where(pd.notna(result['trades']),None).to_dict('records'))
            print('PIT daily cohort',name,label,'13 bots complete',flush=True)
        cohorts[name]=dict(backtests=results['ALL'],backtest_periods=results)
        write(ROOT/'data/pit_results'/f'daily-{name}.json',cohorts[name])
    return cohorts

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--cohort',choices=['300','146']);run(p.parse_args().cohort)
