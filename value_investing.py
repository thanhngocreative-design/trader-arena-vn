"""Two educational, daily-only quality-company models; no fabricated fundamentals.

Separate from the eleven frozen Arena strategies. Parameters are research
assumptions, not Buffett/Munger's actual rules. MA200 is a price anchor, NOT
intrinsic value. Annual statement revisions are gated by actual update dates.
"""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from engine import Settings
from execution import modeled_slippage
from sector_analytics import aggregate_trades

ROOT=Path(__file__).resolve().parent
VN=ZoneInfo('Asia/Ho_Chi_Minh')
POLICY={'Buffett':dict(positions=6,roe=.15,debt=1.,margin=.08,price_anchor=.95),
        'Munger':dict(positions=4,roe=.20,debt=.6,margin=.12,price_anchor=1.15)}
PROFILES={k:dict(name='Warren Buffett' if k=='Buffett' else 'Charlie Munger',
    emoji='🌳' if k=='Buffett' else '💎',region='US',flag='🇺🇸',supported_modes=['paper','backtest'],
    tag='Doanh nghiệp tốt, chờ giá giảm' if k=='Buffett' else 'Chất lượng cao, danh mục tập trung',
    explain='Đọc báo cáo năm đã công bố, ưu tiên lợi nhuận và dòng tiền bền vững; xét mua mỗi tháng, giữ khi chất lượng còn tốt.',
    detail=f"Mô hình học hỏi tư duy, không phải công thức hay lệnh thật của {k}. Ba năm lãi, CFO và FCF dương; ROE bình quân ≥{p['roe']:.0%}, biên lãi ≥{p['margin']:.0%}, nợ vay/vốn chủ ≤{p['debt']}; tối đa {p['positions']} mã. Giá mua ≤{p['price_anchor']} × MA200 chỉ là mốc giá tham chiếu, KHÔNG phải định giá nội tại. Chỉ doanh nghiệp phi tài chính có số liệu phù hợp. Chỉ giao dịch ngày; không dùng ATR để cắt lỗ.",
    source='https://www.berkshirehathaway.com/letters/1989.html') for k,p in POLICY.items()}

def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8');tmp.replace(path)

def quality(reports,date,bot):
    """Only supplied annual versions available on decision day; no inferred dates."""
    known=sorted((r for r in reports if r['available_at']<=str(pd.Timestamp(date).date()) and r['year']<pd.Timestamp(date).year),key=lambda r:r['year'])
    if len(known)<4:return None
    years=known[-4:]
    if [r['year'] for r in years]!=list(range(years[-1]['year']-3,years[-1]['year']+1)):return None
    if years[-1]['year']<pd.Timestamp(date).year-2:return None
    if any(r['equity']<=0 or r['sales']<=0 for r in years):return None
    recent=years[1:];p=POLICY[bot]
    if any(r['profit']<=0 or r['cfo']<=0 or r['cfo']-abs(r['capex'])<=0 or r['short_debt']<0 or r['long_debt']<0 for r in recent):return None
    roes=[r['profit']/((r['equity']+prev['equity'])/2) for prev,r in zip(years,recent)]
    roe=float(np.mean(roes));margin=min(r['profit']/r['sales'] for r in recent)
    debt=(recent[-1]['short_debt']+recent[-1]['long_debt'])/recent[-1]['equity']
    conversion=sum(r['cfo'] for r in recent)/sum(r['profit'] for r in recent)
    if roe<p['roe'] or margin<p['margin'] or debt>p['debt'] or conversion<.8:return None
    return dict(roe=roe,margin=margin,debt=debt,score=roe+margin-debt*.05,
                fiscal_year=recent[-1]['year'],available_at=max(r['available_at'] for r in years))

def eligible_companies(bundle,classification):
    # Current industry labels are an explicit additional sample limitation.
    return {s:r['reports'] for s,r in bundle['companies'].items()
            if classification.get(s,{}).get('icb_code') not in ('8300','8500','8700')
            and s in classification and r.get('reports')}

def features(prices):
    result={}
    for s,f in prices.items():
        f=f.sort_index().copy();f['ma200']=f.close.rolling(200).mean()
        f['adv']=(f.close*f.volume).rolling(20).mean();f['avol']=f.volume.rolling(20).mean()
        result[s]=f
    return result

def empty_book():return dict(cash=100_000_000.,positions={},trades=[],history=[],pending=[],last_session=None,last_review=None)

def mark(book,prices,date):
    holdings=[]
    for s,p in book['positions'].items():
        available=prices[s].loc[:date]
        if available.empty:raise ValueError('No observed mark for '+s)
        price=float(available.iloc[-1].close);value=price*p['qty'];pnl=value-p['cost']
        holdings.append(dict(symbol=s,qty=p['qty'],buy_date=p['buy_date'],buy_price=p['cost']/p['qty'],last_price=price,value=round(value),pnl=round(pnl),pnl_pct=100*pnl/p['cost']))
    return book['cash']+sum(h['value'] for h in holdings),holdings

def execute(book,prices,date,bot):
    """One-session orders only. Missing next candle expires, never stale fill."""
    settings=Settings();orders=book['pending'];book['pending']=[]
    for order in orders:
        s=order['symbol'];f=prices[s];signal=pd.Timestamp(order['signal_date'])
        next_dates=f.index[f.index>signal]
        if not len(next_dates) or next_dates[0]!=date:continue
        row=f.loc[date];prev=f.loc[signal]
        if not (row.volume>0 and row.open>0):continue
        nav,_=mark(book,prices,signal)
        budget=min(book['cash'],nav/POLICY[bot]['positions'])
        if order['side']=='BUY':
            if s in book['positions'] or len(book['positions'])>=POLICY[bot]['positions']:continue
            slip=modeled_slippage(settings,float(prev.adv),budget);price=float(row.open)*(1+slip)
            qty=int(min(budget/(price*(1+settings.fee_rate)),float(prev.avol)*.005)//100)*100
            if qty<=0:continue
            gross=qty*price;fees=gross*settings.fee_rate;tax=0.;pnl=None
            book['cash']-=gross+fees
            book['positions'][s]=dict(qty=qty,cost=gross+fees,buy_date=str(date.date()))
        else:
            p=book['positions'].get(s)
            if not p or len(f.loc[p['buy_date']:signal])<5:continue
            # Cap exits too; partial fills retain proportional cost basis.
            qty=min(p['qty'],int(float(prev.avol)*.005//100)*100)
            if qty<=0:continue
            slip=modeled_slippage(settings,float(prev.adv),qty*float(row.open));price=float(row.open)*(1-slip)
            gross=qty*price;fees=gross*settings.fee_rate;tax=gross*settings.sell_tax
            cost=p['cost']*qty/p['qty'];pnl=gross-fees-tax-cost;book['cash']+=gross-fees-tax
            p['cost']-=cost;p['qty']-=qty
            if p['qty']==0:del book['positions'][s]
        book['trades'].append(dict(date=str(date.date()),symbol=s,trader=bot,side='MUA' if order['side']=='BUY' else 'BÁN',qty=qty,price=price,gross=gross,fees=fees,tax=tax,pnl=pnl,signal_date=str(signal.date()),reason=order['reason'],financial_available_at=order['financial_available_at']))
    if book['cash']<-.01:raise ValueError('Negative cash')

def plan(book,prices,reports,date,bot,force=False):
    month=str(date.date())[:7]
    if not force and book['last_review']==month:return
    book['last_review']=month;orders=[];rank=[]
    for s,rs in reports.items():
        if s not in prices or date not in prices[s].index:continue
        q=quality(rs,date,bot);row=prices[s].loc[date]
        if s in book['positions']:
            if not q:orders.append(dict(symbol=s,side='SELL',reason='Chất lượng báo cáo năm không còn đạt bộ lọc hoặc báo cáo quá cũ',financial_available_at=None))
        elif q and row.adv>=3_000_000_000 and row.close>=5000 and row.close<=row.ma200*POLICY[bot]['price_anchor']:
            rank.append((q['score'],s,q))
    # Existing companies are held, not churned to chase a higher score.
    free=POLICY[bot]['positions']-len(book['positions'])
    for _,s,q in sorted(rank,key=lambda x:(-x[0],x[1]))[:max(0,free)]:
        orders.append(dict(symbol=s,side='BUY',reason='Chất lượng 3 năm đạt bộ lọc; giá trong giới hạn MA200 tham chiếu',financial_available_at=q['available_at']))
    book['pending']=[dict(o,signal_date=str(date.date())) for o in orders]

def session(book,prices,reports,date,bot,trade=True):
    if trade:execute(book,prices,date,bot)
    else:book['pending']=[]
    nav,_=mark(book,prices,date)
    book['history'].append(dict(date=str(date.date()),nav=round(nav),return_pct=round(100*(nav/100_000_000-1),4)))
    book['last_session']=str(date.date())
    if trade:plan(book,prices,reports,date,bot)

def summary(book,prices,date,classification,symbols,benchmark=None):
    nav,holdings=mark(book,prices,date);h=book['history'];sells=[t for t in book['trades'] if t['side']=='BÁN']
    values=np.array([100_000_000]+[r['nav'] for r in h],dtype=float)
    dd=float(np.min(values/np.maximum.accumulate(values)-1))*100 if h else None
    stats=aggregate_trades(book['trades'],classification,symbols)
    out=dict(nav=round(nav),cash=round(book['cash']),return_pct=round(100*(nav/100_000_000-1),2),max_drawdown_pct=None if dd is None else round(dd,2),buy_count=sum(t['side']=='MUA' for t in book['trades']),closed_trades=len(sells),win_rate=round(100*sum(t['pnl']>0 for t in sells)/len(sells),1) if sells else None,holdings=holdings,trades=list(reversed(book['trades'][-40:])),orders_next=book['pending'],actions=[],history=h,sector_stats=stats,observed_history_points=len(h),paper_started_at=book.get('enrolled_at'))
    curve=[]
    for r in h:
        idx=0 if benchmark is None else 100*(float(benchmark.loc[r['date'],'close'])/float(benchmark.loc[h[0]['date'],'close'])-1)
        curve.append(dict(date=pd.Timestamp(r['date']).strftime('%d/%m/%y'),nav=r['nav'],bot=r['return_pct'],index=round(idx,2)))
    out['curve']=curve
    return out

def inputs():
    from datafeed import load_prices
    symbols=read(ROOT/'config/research-universe.json')['eligible_symbols']
    prices,_,missing=load_prices(symbols)
    if missing:raise RuntimeError('Missing real daily data: '+str(missing))
    override=ROOT/'data/prices_research_vietcap/ITC.csv'
    if override.exists():
        f=pd.read_csv(override);f['date']=pd.to_datetime(f.date);prices['ITC']=f.set_index('date')[['open','high','low','close','volume']].astype(float)
    return symbols,features(prices)

def build_backtests():
    symbols,prices=inputs();f=ROOT/'config/value-fundamentals.json';bundle=read(f)
    classification=read(ROOT/'config/market-classification.json')['sectors'];reports=eligible_companies(bundle,classification)
    base=read(ROOT/'site/research-146.json');b=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv');b['date']=pd.to_datetime(b.date);b=b.set_index('date')
    results={};audit={}
    for option in base['backtest_options']:
        dates=b.index[(b.index>=option['start'])&(b.index<=option['end'])];results[option['key']]={}
        for bot in POLICY:
            book=empty_book()
            for date in dates:session(book,prices,reports,date,bot)
            result=summary(book,prices,dates[-1],classification,symbols,b)
            result['benchmark_return_pct']=round(100*(float(b.loc[dates[-1],'close'])/float(b.loc[dates[0],'close'])-1),2)
            results[option['key']][bot]=result
            write(ROOT/'data/value_fundamentals'/f'trades-{option["key"]}-{bot}.json',book['trades'])
            if option['key']=='ALL':
                audit[bot]=dict(quality_eligible_start=sum(quality(rs,dates[0],bot) is not None for rs in reports.values()),quality_eligible_end=sum(quality(rs,dates[-1],bot) is not None for rs in reports.values()),trade_count=len(book['trades']))
            print(option['key'],bot,result['return_pct'],result['max_drawdown_pct'],len(book['trades']),flush=True)
    public=dict(revision='value_quality_v1',mode='real_market_data',generated_at=datetime.now(VN).isoformat(),traders=PROFILES,backtests=results['ALL'],backtest_periods=results,policy=POLICY,audit=audit,
        fundamentals=dict(source=bundle['source'],asof=bundle['asof'],sha256=hashlib.sha256(f.read_bytes()).hexdigest(),comparable_nonfinancial_companies=len(reports),requested_symbols=len(symbols),availability_rule=bundle['availability_rule']),
        limitations=['Bộ 146 mã được chọn sau khi biết dữ liệu liên tục: còn sai lệch chọn mã sống sót.', 'Báo cáo hiện tại không phải kho phiên bản gốc. Mỗi giá trị chỉ dùng sau ngày công bố/cập nhật muộn nhất cộng 1 ngày; báo cáo bị sửa khiến lịch sử có thể thiếu cơ hội.', 'Loại ngành ngân hàng, bảo hiểm, dịch vụ tài chính theo ICB hiện tại vì bộ lọc nợ/CFO không tương đương; phân ngành chưa theo từng thời điểm.', 'MA200 là mốc giá tương đối, không phải định giá nội tại hay đo lường lợi thế cạnh tranh. Không mô phỏng đánh giá quản trị định tính.', 'Giá theo nguồn OHLCV đang dùng của Arena; chưa tái dựng đầy đủ cổ tức tiền mặt/quyền và giá chưa điều chỉnh. Chưa phải mô hình tổng lợi nhuận của nhà đầu tư dài hạn.', 'Ngưỡng cố định do Arena đặt trước khi chạy, không phải công thức được Buffett/Munger xác nhận. Xét mỗi tháng, khớp phiên sau, phí/trượt giá/thuế và giới hạn thanh khoản.'])
    public['daily_input_sha256']={s:hashlib.sha256((ROOT/'data/prices_research_vietcap/ITC.csv' if s=='ITC' else ROOT/'data/prices'/f'{s}.csv').read_bytes()).hexdigest() for s in symbols}
    dest=ROOT/'site/value-investing.json'
    if dest.exists():
        old=read(dest)
        for k in ('paper','paper_started_at','paper_last_session'): 
            if k in old:public[k]=old[k]
    write(dest,public)

def update_paper(now=None):
    now=now or datetime.now(VN);symbols,prices=inputs();classification=read(ROOT/'config/market-classification.json')['sectors']
    latest=ROOT/'data/value_fundamentals/verified.json';bundle=read(latest if latest.exists() else ROOT/'config/value-fundamentals.json')
    reports=eligible_companies(bundle,classification);dest=ROOT/'state/value_paper.json'
    state=read(dest) if dest.exists() else dict(enrolled_at=now.isoformat(),bots={k:dict(empty_book(),enrolled_at=now.isoformat()) for k in POLICY})
    public=read(ROOT/'site/value-investing.json');day=pd.Timestamp(now.date())
    # Never mark an unfinished session as EOD. Require the entire 146 panel.
    common=None
    for f in prices.values():common=f.index if common is None else common.intersection(f.index)
    dates=common[(common<day)|((common==day)&(now.hour>=16))]
    if not len(dates):raise RuntimeError('No completed common market session')
    date=dates[-1]
    controls=read(ROOT/'config/value-bots.json')
    for bot,book in state['bots'].items():
        if not controls.get(bot,True):book['pending']=[]
        if book['last_session']:
            for d in dates[dates>pd.Timestamp(book['last_session'])]:
                # Forward-only: only durable pre-open intentions can be filled.
                opened=datetime.combine(d.date(),datetime.min.time(),VN).replace(hour=9)
                registered=datetime.fromisoformat(book.get('orders_recorded_at',state['enrolled_at']))
                execute(book,prices,d,bot) if registered<opened else book.update(pending=[])
                session(book,prices,reports,d,bot,trade=False)
            # New intentions are based on latest completed EOD, persisted now.
            # If the next session has already opened, let that order expire.
        if controls.get(bot,True) and (not book['last_session'] or book.get('planned_session')!=str(date.date())):
            plan(book,prices,reports,date,bot,force=not book['last_session'])
            book['planned_session']=str(date.date());book['orders_recorded_at']=now.isoformat()
        book['last_session']=str(date.date())
    write(dest,state)
    public['paper']={k:summary(book,prices,date,classification,symbols) for k,book in state['bots'].items()}
    public['paper_started_at']=state['enrolled_at'];public['paper_last_session']=str(date.date())
    public['cloud_enabled']=controls
    public['paper_fundamentals_asof']=bundle['asof'];write(ROOT/'site/value-investing.json',public)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backtest',action='store_true');p.add_argument('--paper',action='store_true');a=p.parse_args()
    if a.backtest:build_backtests()
    if a.paper:update_paper()
