"""End-of-day paper using the historical engines, never future session candles.

Each run reconstructs the same season from immutable real daily/minute inputs.
It replaces a derived view, never appends a second copy of yesterday's trades.
Previously committed ledgers must match exactly before another session publishes.
"""
import argparse
import gzip
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
import time
import httpx
import pandas as pd
from value_investing import ROOT, VN, POLICY, read, write, eligible_companies
from engine import TRADERS, Settings, backtest
from fast_engine import CORE, build_hybrid_signals
from collect_pit_daily import valid_rows
from historical_minute import ENDPOINT, epoch, validate_wire
from intraday_data import normalize_minute
from pit_universe import monthly_memberships
from pit_context import PITContext
from pit_daily import attach_summary, merged_fundamentals, value_backtest
from pit_intraday import run_minute, run_combo
from replay_rules import REVISION, can_fill
from sector_analytics import universe_distribution

START = '2026-11-02'
MARKET = ROOT/'state/replay_market'
STATE = ROOT/'state/paper_seasons'/START/'paper_replay.json'
PUBLIC = ROOT/'site/paper-replay.json'
OUTPUT_BASE = ROOT/'data/pit_results/replay'/START
BOTS = list(TRADERS)+list(POLICY)


def pack(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    tmp=path.with_suffix('.tmp');tmp.write_bytes(gzip.compress(raw,mtime=0));tmp.replace(path)


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def completed_date(now):
    local=now.astimezone(VN)
    day=local.date() if local.hour>=16 else local.date()-timedelta(days=1)
    while day.weekday()>=5:day-=timedelta(days=1)
    return day.isoformat()


def frame(rows):
    if not rows:return pd.DataFrame(columns=['open','high','low','close','volume'],index=pd.DatetimeIndex([],name='date'))
    f=pd.DataFrame(rows);f['date']=pd.to_datetime(f.date)
    if f.date.duplicated().any():raise ValueError('Duplicate source dates')
    return f.loc[valid_rows(f)].set_index('date').sort_index()

def observed_minutes(raw):
    """An actual auction-only session is an empty continuous tape, not an error.

    The canonical validator still checks all raw OHLCV and duplicate timestamps;
    only its explicit no-continuous-session outcome becomes an empty frame.
    """
    try:return normalize_minute(raw,'vnd').loc[lambda f:f.volume>0]
    except ValueError as error:
        if str(error)!='No continuous-session bars; auctions not supported':raise
        return pd.DataFrame(columns=['open','high','low','close','volume'],index=pd.DatetimeIndex([],name='time'))


def fetch_session(day, symbols):
    """Bank actual wire replies before simulation. No missing-candle filling."""
    path=MARKET/'sessions'/f'{day}.json.gz'
    if path.exists():
        data=unpack(path)
        if data['requested_symbols']!=sorted(symbols):raise ValueError('Frozen session universe changed')
        return data
    replies={};upper=epoch((pd.Timestamp(day)+pd.Timedelta(days=1)).date().isoformat())
    with httpx.Client(timeout=60) as client:
        for n,s in enumerate(['VNINDEX']+sorted(symbols)):
            parts={}
            for kind,count in [('ONE_DAY',10)]+([] if s=='VNINDEX' else [('ONE_MINUTE',1000)]):
                response=client.post(ENDPOINT,json=dict(symbols=[s],timeFrame=kind,to=upper,countBack=count))
                response.raise_for_status() # stops on rate/access errors; no bypass
                wire=response.json();time.sleep(.35)
                if wire==[]:parts[kind]=[];continue
                if not isinstance(wire,list) or len(wire)!=1:raise ValueError('Unexpected source reply '+s)
                if not wire[0].get('t'):parts[kind]=[];continue
                observed=validate_wire(wire[0],s)
                observed=observed.loc[observed.time.dt.date.astype(str)==day]
                parts[kind]=json.loads(observed.to_json(orient='records',date_format='iso'))
            replies[s]=parts
            if s=='VNINDEX' and not parts['ONE_DAY']:raise ValueError('Benchmark has no completed session; no paper session invented')
            if n%50==0:print('Paper real-data banking',day,n,'/',len(symbols),flush=True)
    if not replies['VNINDEX']['ONE_DAY']:raise ValueError('Benchmark has no completed session; no paper session invented')
    data=dict(date=day,requested_symbols=sorted(symbols),source=ENDPOINT,replies=replies)
    pack(path,data);return data


def source_inputs(end, collect=True):
    base=unpack(MARKET/'daily-history.json.gz')
    cfg=read(ROOT/'config/research-300.json');months=list(cfg['months'])
    # The bank can contain later historical observations. They must not enter
    # the initial information set when a season starts earlier than its asof.
    cutoff=pd.Timestamp(START)
    prices={s:frame(rows).loc[lambda f:f.index<cutoff] for s,rows in base['prices'].items()}
    benchmark=frame(base['benchmark']).loc[lambda f:f.index<cutoff]
    calendar=pd.bdate_range(START,end)
    audits={};frames={};sessions=[]
    for date in calendar:
        day=str(date.date());prior=benchmark.index[-1]
        # Monthly ranking is made BEFORE today's source is requested. The first
        # month's membership is the already frozen November selection.
        appended=False
        if day[:7]!=str(prior.date())[:7]:
            planned=benchmark.index.append(pd.DatetimeIndex([date]))
            row=monthly_memberships(prices,planned,first=day[:7]+'-01',last=day)[0]
            frozen=[r for r in months if r['month']==day[:7]]
            if frozen:
                if frozen[-1]['effective']!=day or frozen[-1]['asof']!=str(prior.date()) or set(frozen[-1]['members'])!=set(row['members']):raise ValueError('Frozen monthly membership does not match information available before the first session')
            else:months.append(row);appended=True
        members=[r for r in months if r['effective']<=day][-1]['members']
        # All candidate daily data is collected for the NEXT monthly ranking.
        # Minute tapes are needed only for current and previously selected names
        # that could remain held; do not use minute availability for selection.
        minute_symbols=sorted(set(members)|{s for r in months if r['effective']>=START[:7]+'-01' for s in r['members']})
        session_path=MARKET/'sessions'/f'{day}.json.gz'
        if not collect and not session_path.exists():raise ValueError('Unbanked session '+day)
        try:data=fetch_session(day,minute_symbols)
        except ValueError as error:
            if 'Benchmark has no completed session' in str(error):
                if appended:months.pop()
                continue
            raise
        # Session daily updates for every catalog candidate, independently of
        # the minute universe, are frozen in a separate file.
        daily_path=MARKET/'candidate-days'/f'{day}.json.gz'
        if daily_path.exists():daily=unpack(daily_path)
        elif collect:
            daily={}
            with httpx.Client(timeout=60) as client:
                for n,s in enumerate(sorted(prices)):
                    if s in data['replies']:
                        daily[s]=data['replies'][s]['ONE_DAY'];continue
                    r=client.post(ENDPOINT,json=dict(symbols=[s],timeFrame='ONE_DAY',to=epoch((date+pd.Timedelta(days=1)).date().isoformat()),countBack=3))
                    r.raise_for_status();wire=r.json();time.sleep(.35)
                    if wire==[] or (isinstance(wire,list) and len(wire)==1 and not wire[0].get('t')):daily[s]=[];continue
                    if not isinstance(wire,list) or len(wire)!=1:raise ValueError('Invalid candidate source '+s)
                    f=validate_wire(wire[0],s);f=f.loc[f.time.dt.date.astype(str)==day]
                    daily[s]=json.loads(f.to_json(orient='records',date_format='iso'))
                    if n%200==0:print('Paper candidate daily',day,n,'/',len(prices),flush=True)
            pack(daily_path,daily)
        else:raise ValueError('Missing frozen candidate daily '+day)
        def convert(rows):
            return frame([{**r,'date':r['date'] if 'date' in r else str(pd.Timestamp(r['time']).tz_convert(VN).date())} for r in rows])
        benchmark=pd.concat([benchmark,convert(data['replies']['VNINDEX']['ONE_DAY'])])
        if date not in benchmark.index:raise ValueError('Invalid benchmark observation')
        for s,rows in daily.items():
            observed=convert(rows)
            if len(observed):prices[s]=pd.concat([prices[s],observed]).sort_index()
        day_audit={}
        for s in minute_symbols:
            raw=pd.DataFrame(data['replies'][s]['ONE_MINUTE'])
            if raw.empty:
                day_audit[s]=dict(bars=0,positive_daily=date in prices[s].index,reason='No observed minute candle; cause unconfirmed')
                continue
            raw.time=pd.to_datetime(raw.time,utc=True).dt.tz_convert(VN)
            positive=raw.loc[raw.volume>0];bad=False
            if len(positive) and date in prices[s].index:
                ratio=float(positive.close.iloc[-1])/float(prices[s].loc[date,'close']);bad=not .92<=ratio<=1.08
            normalized=observed_minutes(raw)
            if bad:normalized=normalized.iloc[:0]
            day_audit[s]=dict(bars=len(normalized),positive_daily=date in prices[s].index,price_mismatch_quarantined=bad)
            frames.setdefault(s,[]).append(normalized)
        sessions.append(day);audits[day]=day_audit
    frames={s:pd.concat(parts).sort_index() for s,parts in frames.items()}
    for s in set(cfg['eligible_symbols'])|set(frames):
        if s not in frames:frames[s]=pd.DataFrame(columns=['open','high','low','close','volume'],index=pd.DatetimeIndex([],name='time'))
    cfg=dict(cfg,start=START,end=end,months=months)
    return prices,benchmark,frames,cfg,audits,sessions


def blank():
    return dict(nav=100_000_000,cash=100_000_000,return_pct=0.,max_drawdown_pct=None,holdings=[],trades=[],history=[],curve=[],buy_count=0,closed_trades=0,win_rate=None,actions=[],orders_next=[],sector_stats=dict(sectors=[],buy_fills=0,sell_fills=0,buy_value=0,outside_146_fills=0,outside_146_buys=0))


def run(collect=True,now=None):
    now=now or datetime.now(VN);end=completed_date(now)
    payload=dict(revision='eod_replay_v1',execution_revision=REVISION,mode='real_market_data',started_at=START+'T00:00:00+07:00',season_start=START,updated_at=now.isoformat(),target=300,source=ENDPOINT,last_session=None,status='waiting_completed_session',paper_contest_start=START)
    if end<START:
        cfg=read(ROOT/'config/research-300.json');classification=read(ROOT/'config/market-classification.json')
        payload['members']=[r for r in cfg['months'] if r['effective']<=START][-1]['members']
        payload['sector_universe']=universe_distribution(payload['members'],classification)
        payload.update({m:{b:blank() for b in BOTS} for m in ('paper','paper_minute','paper_combo')})
        if not STATE.exists():
            inputs={p.relative_to(MARKET).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in MARKET.rglob('*.gz')}
            write(STATE,dict(last_session=None,execution_revision=REVISION,ledgers={},input_sha256=inputs))
        write(PUBLIC,payload);return payload
    if STATE.exists():
        previous=read(STATE)
        for path,digest in previous['input_sha256'].items():
            if hashlib.sha256(MARKET.joinpath(*Path(path.replace('\\','/')).parts).read_bytes()).hexdigest()!=digest:raise ValueError('Frozen paper input changed: '+path)
    prices,benchmark,frames,cfg,audits,sessions=source_inputs(end,collect)
    if not sessions:raise ValueError('No real completed session; keep previous published paper')
    cfg['end']=sessions[-1];settings=Settings(portfolio_policy='atr_v1')
    benchmark=benchmark.copy()
    benchmark[['open','high','low','close']]*=1000 # match historical benchmark units
    needed=set(cfg['training_symbols'])|{s for r in cfg['months'] for s in r['members']}
    prices={s:f for s,f in prices.items() if s in needed and len(f)}
    ctx=PITContext(prices,benchmark,cfg['months'],settings)
    training={k:backtest(prices,benchmark,k,'2022-01-03',end_date=cfg['end'],settings=settings,features_cache=ctx)['curve'] for k in CORE}
    build_hybrid_signals(ctx,training)
    classification=read(ROOT/'config/market-classification.json')['sectors'];reports=eligible_companies(merged_fundamentals(),classification)
    day={};ledgers={}
    def summarize(r):
        out=attach_summary(r,classification,set(ctx.symbols))
        out['history']=[dict(date=str(d.date()),nav=round(float(v.nav))) for d,v in r['curve'].iterrows()]
        out['orders_next']=[]
        return out
    for b in BOTS:
        r=backtest(prices,benchmark,b,START,end_date=cfg['end'],settings=settings,features_cache=ctx) if b in TRADERS else value_backtest(ctx,b,START,cfg['end'],reports)
        day[b]=summarize(r);ledgers['paper:'+b]=json.loads(r['trades'].to_json(orient='records',date_format='iso'))
    output=OUTPUT_BASE/cfg['end'];output.mkdir(parents=True,exist_ok=True)
    coverage={s:dict(minute_sha256=hashlib.sha256(f.to_csv().encode()).hexdigest()) for s,f in frames.items()}
    cfg['minute_input_sha256']=coverage
    run_minute({'300':ctx},frames,coverage,cfg,output)
    run_combo({'300':ctx},prices,frames,cfg,output)
    minute=read(output/'minute-300.json');combo=read(output/'combo-300.json')
    payload.update(paper=day,paper_minute=minute['minute'],paper_combo={**combo,**minute['value_combo']})
    for mode in ('paper_minute','paper_combo'):
        for b,book in payload[mode].items():
            prefix='minute' if mode=='paper_minute' else 'value_combo' if b in POLICY else 'combo'
            trades=read(output/f'{prefix}-300-{b}-trades.json');ledgers[mode+':'+b]=trades
            if prefix in ('minute','value_combo'):
                saved=read(output/'minute-checkpoint.json')
                curve=saved['curves']['300'][prefix][b]
                book['history']=[dict(date=r['date'],nav=r['nav']) for r in curve]
            book['orders_next']=[]
            for trade in trades:
                if not can_fill(trade['signal_time'],trade['time'],trade.get('submitted_at')):raise ValueError('Invalid paper fill clock')
    previous=read(STATE) if STATE.exists() else None
    if previous:
        prior_end=previous['last_session']
        for key,old in previous['ledgers'].items():
            prefix=[t for t in ledgers[key] if str(t['date'])[:10]<=prior_end]
            if prefix!=old:raise ValueError('Prior committed paper trades changed; refuse rewrite: '+key)
    payload.update(status='completed_session_replay',last_session=sessions[-1],sessions=sessions,members=[r for r in cfg['months'] if r['effective']<=sessions[-1]][-1]['members'],data_audit=audits,
        note='Replay sau phiên; chỉ thấy nến đã đóng; đúng nến kế tiếp, thiếu thì bỏ lệnh. Tài khoản liên tục từ ngày bắt đầu mùa; không cộng lại giao dịch cũ.')
    payload['sector_universe']=universe_distribution(payload['members'],read(ROOT/'config/market-classification.json'))
    inputs={p.relative_to(MARKET).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in MARKET.rglob('*.gz')}
    payload['input_sha256']=inputs
    for symbol in sorted({s for row in cfg['months'] if row['effective']>=START[:7]+'-01' for s in row['members']}):
        if symbol not in prices:continue
        observed=prices[symbol].loc[:cfg['end']].tail(780)
        bars=[[str(date.date())]+[float(row[k]) for k in ('open','high','low','close','volume')] for date,row in observed.iterrows()]
        write(ROOT/'site/replay-stocks'/f'{symbol}.json',bars)
    write(STATE,dict(last_session=sessions[-1],execution_revision=REVISION,ledgers=ledgers,input_sha256=inputs))
    write(PUBLIC,payload)
    print('Published verified EOD paper',sessions[-1],len(sessions),'sessions, 39 books',flush=True)
    return payload


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--no-collect',action='store_true');a=p.parse_args();run(not a.no_collect)
