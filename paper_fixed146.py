"""Independent fixed-146 paper accounts, sharing verified inputs and strict engines."""
import hashlib,json,time
from pathlib import PurePosixPath
from datetime import datetime
import httpx
import pandas as pd
from paper_replay import (ROOT,VN,START,MARKET,ENDPOINT,epoch,validate_wire,normalize_minute,
    read,write,pack,unpack,source_inputs,completed_date,blank,BOTS,Settings,PITContext,
    backtest,CORE,build_hybrid_signals,eligible_companies,merged_fundamentals,value_backtest,
    TRADERS,POLICY,attach_summary,run_minute,run_combo,can_fill,REVISION,universe_distribution)

STATE=ROOT/'state/paper_fixed146.json'
PUBLIC=ROOT/'site/paper-fixed146.json'

def supplemental(day,symbols,collect=True,folder='fixed146-sessions'):
    """Never rewrite the already banked monthly-session source to add names."""
    path=MARKET/folder/f'{day}.json.gz'
    if path.exists():
        data=unpack(path)
        if data['requested_symbols']!=sorted(symbols):raise ValueError('Frozen supplemental universe changed')
        return data
    if not collect and symbols:raise ValueError('Missing real fixed146 minute input '+day)
    replies={}
    if symbols:
        with httpx.Client(timeout=60) as client:
            for s in sorted(symbols):
                r=client.post(ENDPOINT,json=dict(symbols=[s],timeFrame='ONE_MINUTE',
                    to=epoch((pd.Timestamp(day)+pd.Timedelta(days=1)).date().isoformat()),countBack=1000))
                r.raise_for_status();wire=r.json();time.sleep(.35)
                if wire==[] or isinstance(wire,list) and len(wire)==1 and not wire[0].get('t'):
                    replies[s]=[];continue
                if not isinstance(wire,list) or len(wire)!=1:raise ValueError('Unexpected source '+s)
                f=validate_wire(wire[0],s);f=f.loc[f.time.dt.date.astype(str)==day]
                replies[s]=json.loads(f.to_json(orient='records',date_format='iso'))
    data=dict(date=day,source=ENDPOINT,requested_symbols=sorted(symbols),replies=replies)
    pack(path,data);return data

def add_minutes(prices,frames,sessions,fixed,collect=True):
    extra={};audit={}
    for day in sessions:
        monthly=unpack(MARKET/'sessions'/f'{day}.json.gz')
        missing=sorted(set(fixed)-set(monthly['requested_symbols']))
        data=supplemental(day,missing,collect);audit[day]={}
        for s,rows in data['replies'].items():
            f=pd.DataFrame(columns=['open','high','low','close','volume'],index=pd.DatetimeIndex([],name='time'))
            bad=False;raw=pd.DataFrame(rows);date=pd.Timestamp(day)
            if len(raw):
                raw.time=pd.to_datetime(raw.time,utc=True).dt.tz_convert(VN)
                positive=raw.loc[raw.volume>0]
                if len(positive) and date in prices[s].index:
                    ratio=float(positive.close.iloc[-1])/float(prices[s].loc[date,'close']);bad=not .92<=ratio<=1.08
                f=normalize_minute(raw,'vnd');f=f.loc[f.volume>0]
                if bad:f=f.iloc[:0]
            extra.setdefault(s,[]).append(f)
            audit[day][s]=dict(bars=len(f),price_mismatch_quarantined=bad,positive_daily=date in prices[s].index)
    for s,parts in extra.items():
        frames[s]=pd.concat([frames[s],*parts]).sort_index() if s in frames else pd.concat(parts).sort_index()
        if frames[s].index.duplicated().any():raise ValueError('Duplicate supplemental minute '+s)
    return audit

def verify_previous(previous,ledgers):
    if not previous:return
    for key,old in previous['ledgers'].items():
        prefix=[t for t in ledgers[key] if str(t['date'])[:10]<=previous['last_session']]
        if prefix!=old:raise ValueError('Prior fixed146 paper trades changed: '+key)

def verify_inputs(inputs,market=MARKET):
    for path,digest in inputs.items():
        relative=PurePosixPath(path.replace('\\','/'))
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid frozen input path')
        if hashlib.sha256(market.joinpath(*relative.parts).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen fixed146 source changed: '+path)

def run(collect=True,now=None):
    now=now or datetime.now(VN);end=completed_date(now)
    fixed=read(ROOT/'config/research-universe.json')['eligible_symbols']
    if len(fixed)!=146 or len(set(fixed))!=146:raise ValueError('Invalid fixed146 source membership')
    classification=read(ROOT/'config/market-classification.json')
    payload=dict(revision='eod_replay_v1',execution_revision=REVISION,cohort='146',target=146,
        mode='real_market_data',season_start=START,paper_contest_start=START,updated_at=now.isoformat(),
        source=ENDPOINT,members=fixed,sector_universe=universe_distribution(fixed,classification),last_session=None,status='waiting_completed_session')
    if end<START:
        payload.update({m:{b:blank() for b in BOTS} for m in ('paper','paper_minute','paper_combo')})
        write(PUBLIC,payload);return payload
    previous=read(STATE) if STATE.exists() else None
    if previous:
        if previous['members']!=fixed:raise ValueError('Fixed146 membership changed during paper season')
        verify_inputs(previous['input_sha256'])
    # The monthly collector must finish first. Reuse its immutable candidate days;
    # only missing fixed-universe minute tapes are requested here.
    prices,benchmark,frames,cfg,audits,sessions=source_inputs(end,False)
    if not sessions:raise ValueError('No real completed paper session')
    extra_audit=add_minutes(prices,frames,sessions,fixed,collect)
    cfg={**cfg,'end':sessions[-1],'paper_cohort':'146'};benchmark=benchmark.copy();benchmark[['open','high','low','close']]*=1000
    needed=set(cfg['training_symbols'])|set(fixed)|{s for row in cfg['months'] for s in row['members']}
    prices={s:f for s,f in prices.items() if s in needed and len(f)}
    ctx=PITContext(prices,benchmark,cfg['months'],Settings(portfolio_policy='atr_v1'),static=fixed)
    if set(fixed)-set(ctx.pos):raise ValueError('Missing fixed146 daily histories')
    training={k:backtest(prices,benchmark,k,'2022-01-03',end_date=cfg['end'],settings=ctx.settings,features_cache=ctx)['curve'] for k in CORE}
    build_hybrid_signals(ctx,training)
    reports=eligible_companies(merged_fundamentals(),classification['sectors']);day={};ledgers={}
    for bot in BOTS:
        r=backtest(prices,benchmark,bot,START,end_date=cfg['end'],settings=ctx.settings,features_cache=ctx) if bot in TRADERS else value_backtest(ctx,bot,START,cfg['end'],reports)
        book=attach_summary(r,classification['sectors'],set(fixed));book['history']=[dict(date=str(d.date()),nav=round(float(v.nav))) for d,v in r['curve'].iterrows()];book['orders_next']=[]
        day[bot]=book;ledgers['paper:'+bot]=json.loads(r['trades'].to_json(orient='records',date_format='iso'))
    output=ROOT/'data/pit_results/replay-fixed146'/cfg['end'];output.mkdir(parents=True,exist_ok=True)
    coverage={s:dict(minute_sha256=hashlib.sha256(f.to_csv().encode()).hexdigest()) for s,f in frames.items()};cfg['minute_input_sha256']=coverage
    run_minute({'146':ctx},frames,coverage,cfg,output);run_combo({'146':ctx},prices,frames,cfg,output)
    minute=read(output/'minute-146.json');payload.update(paper=day,paper_minute=minute['minute'],paper_combo={**read(output/'combo-146.json'),**minute['value_combo']})
    saved=read(output/'minute-checkpoint.json')
    for mode in ('paper_minute','paper_combo'):
        for bot,book in payload[mode].items():
            prefix='minute' if mode=='paper_minute' else 'value_combo' if bot in POLICY else 'combo'
            trades=read(output/f'{prefix}-146-{bot}-trades.json');ledgers[mode+':'+bot]=trades
            if prefix in ('minute','value_combo'):book['history']=[dict(date=r['date'],nav=r['nav']) for r in saved['curves']['146'][prefix][bot]]
            book['orders_next']=[]
            for t in trades:
                if not can_fill(t['signal_time'],t['time'],t.get('submitted_at')):raise ValueError('Invalid fixed146 paper clock')
    verify_previous(previous,ledgers)
    payload.update(status='completed_session_replay',last_session=sessions[-1],sessions=sessions,data_audit=audits,supplemental_data_audit=extra_audit,
        note='Rổ cố định 146 mã sống sót; tài khoản riêng từ 13/11/2026. Replay cuối ngày, khớp đúng nến kế tiếp; thiếu thì hủy lệnh.')
    inputs={p.relative_to(MARKET).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in MARKET.rglob('*.gz')};payload['input_sha256']=inputs
    for s in fixed:
        f=prices[s].loc[:cfg['end']].tail(780)
        write(ROOT/'site/replay-stocks'/f'{s}.json',[[str(d.date())]+[float(r[k]) for k in ('open','high','low','close','volume')] for d,r in f.iterrows()])
    write(STATE,dict(last_session=sessions[-1],execution_revision=REVISION,cohort='146',members=fixed,ledgers=ledgers,input_sha256=inputs));write(PUBLIC,payload)
    print('Published verified fixed146 paper',sessions[-1],'39 independent accounts',flush=True)
    return payload

if __name__=='__main__':run()
