"""Three independent VN30 paper books from the common cash-only season start."""
import hashlib,json
from datetime import datetime
import pandas as pd
from paper_replay import ROOT,VN,START,MARKET,ENDPOINT,read,write,unpack,source_inputs,completed_date,blank,observed_minutes
from paper_fixed146 import supplemental,verify_inputs
from vn30 import configuration,membership,context,BOTS,audit_fills
from pit_intraday import run_minute,run_combo
from pit_daily import attach_summary,value_backtest,merged_fundamentals
from value_investing import eligible_companies,POLICY
from engine import TRADERS,backtest
from fast_engine import CORE,build_hybrid_signals
from intraday_data import normalize_minute
from replay_rules import REVISION
from sector_analytics import universe_distribution

STATE=ROOT/'state/paper_seasons'/START/'paper_vn30.json';PUBLIC=ROOT/'site/paper-vn30.json'
OUTPUT_BASE=ROOT/'data/pit_results/replay-vn30'/START

def verify_previous(previous,ledgers,events):
    if not previous:return
    used=[r for r in events if r['effective']<=previous['last_session']]
    if previous['membership_events']!=used:raise ValueError('Previously used VN30 membership changed')
    for key,old in previous['ledgers'].items():
        if [r for r in ledgers[key] if str(r['date'])[:10]<=previous['last_session']]!=old:
            raise ValueError('Prior VN30 paper trade changed: '+key)

def run(collect=True,now=None):
    now=now or datetime.now(VN);end=completed_date(now);cfg=configuration();classification=read(ROOT/'config/market-classification.json')
    current=sorted(membership(cfg,max(START,end)))
    payload=dict(revision='eod_replay_v1',execution_revision=REVISION,cohort='vn30',target=30,mode='real_market_data',season_start=START,paper_contest_start=START,updated_at=now.isoformat(),source=ENDPOINT,members=current,sector_universe=universe_distribution(current,classification),last_session=None,status='waiting_completed_session',membership_verified_through=cfg['verified_through'])
    if end<START:
        payload.update({m:{b:blank() for b in BOTS} for m in ('paper','paper_minute','paper_combo')});write(PUBLIC,payload);return payload
    previous=read(STATE) if STATE.exists() else None
    if previous:verify_inputs(previous['input_sha256'])
    prices,benchmark,frames,_,audits,sessions=source_inputs(end,False)
    if not sessions:raise ValueError('No completed real paper session')
    end=sessions[-1];cfg={**cfg,'start':START,'end':end,'paper_cohort':'vn30'}
    union=sorted(set.union(*(membership(cfg,d) for d in sessions)))
    extra_audit={};extra={}
    for day in sessions:
        source=unpack(MARKET/'sessions'/f'{day}.json.gz');missing=sorted(set(union)-set(source['requested_symbols']))
        supplement=supplemental(day,missing,collect,folder='vn30-sessions');extra_audit[day]={}
        for s,rows in supplement['replies'].items():
            raw=pd.DataFrame(rows);f=pd.DataFrame(columns=['open','high','low','close','volume'],index=pd.DatetimeIndex([],name='time'));bad=False
            if len(raw):
                raw.time=pd.to_datetime(raw.time,utc=True).dt.tz_convert(VN);positive=raw.loc[raw.volume>0]
                if len(positive) and pd.Timestamp(day) in prices[s].index:
                    ratio=float(positive.close.iloc[-1])/float(prices[s].loc[day,'close']);bad=not .92<=ratio<=1.08
                f=observed_minutes(raw)
                if bad:f=f.iloc[:0]
            extra.setdefault(s,[]).append(f);extra_audit[day][s]=dict(bars=len(f),price_mismatch_quarantined=bad)
    for s,parts in extra.items():frames[s]=pd.concat([frames.get(s,pd.DataFrame()),*parts]).sort_index()
    frames={s:frames[s] for s in union};prices={s:prices[s] for s in cfg['training_symbols']}
    if any(f.index.duplicated().any() for f in frames.values()):raise ValueError('Duplicate VN30 source timestamps')
    cfg['daily_input_sha256']={s:hashlib.sha256(f.to_csv().encode()).hexdigest() for s,f in prices.items()}
    benchmark=benchmark.copy();benchmark[['open','high','low','close']]*=1000;ctx=context(prices,benchmark,cfg)
    training={b:backtest(prices,benchmark,b,'2022-01-03',end_date=end,settings=ctx.settings,features_cache=ctx)['curve'] for b in CORE};build_hybrid_signals(ctx,training)
    output=OUTPUT_BASE/end;output.mkdir(parents=True,exist_ok=True)
    reports=eligible_companies(merged_fundamentals(),classification['sectors']);books={};ledgers={}
    for bot in BOTS:
        r=backtest(prices,benchmark,bot,START,end_date=end,settings=ctx.settings,features_cache=ctx) if bot in TRADERS else value_backtest(ctx,bot,START,end,reports)
        b=attach_summary(r,classification['sectors'],set(union));b['history']=[dict(date=str(d.date()),nav=round(float(v.nav))) for d,v in r['curve'].iterrows()];b['orders_next']=[];books[bot]=b
        trades=json.loads(r['trades'].to_json(orient='records',date_format='iso'));ledgers['paper:'+bot]=trades;write(output/f'daily-vn30-{bot}-trades.json',trades)
    coverage={s:dict(minute_sha256=hashlib.sha256(f.to_csv().encode()).hexdigest()) for s,f in frames.items()};cfg['minute_input_sha256']=coverage
    run_minute({'vn30':ctx},frames,coverage,cfg,output);run_combo({'vn30':ctx},prices,frames,cfg,output)
    minute=read(output/'minute-vn30.json');payload.update(paper=books,paper_minute=minute['minute'],paper_combo={**read(output/'combo-vn30.json'),**minute['value_combo']})
    saved=read(output/'minute-checkpoint.json')
    for mode in ('paper_minute','paper_combo'):
        for bot,b in payload[mode].items():
            prefix='minute' if mode=='paper_minute' else 'value_combo' if bot in POLICY else 'combo'
            ledgers[mode+':'+bot]=read(output/f'{prefix}-vn30-{bot}-trades.json');b['orders_next']=[]
            if prefix in ('minute','value_combo'):b['history']=[dict(date=r['date'],nav=r['nav']) for r in saved['curves']['vn30'][prefix][bot]]
    counts=audit_fills(cfg,prices,frames,benchmark,output);verify_previous(previous,ledgers,cfg['months'])
    used_events=[r for r in cfg['months'] if r['effective']<=end]
    inputs={p.relative_to(MARKET).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in MARKET.rglob('*.gz')}
    current=sorted(membership(cfg,end));payload.update(status='completed_session_replay',last_session=end,sessions=sessions,members=current,sector_universe=universe_distribution(current,classification),membership_events=used_events,input_sha256=inputs,data_audit={d:{s:audits[d].get(s,extra_audit[d].get(s)) for s in membership(cfg,d)} for d in sessions},execution_audit=dict(status='all_fills_verified_against_real_bars',fills_by_book=counts,total_fills=sum(counts.values())),note='VN30 theo ngày hiệu lực công bố; 39 tài khoản riêng cùng vốn tiền mặt đầu mùa. Replay khớp đúng nến kế tiếp; thiếu thì hủy lệnh.')
    for s in union:
        f=prices[s].loc[:end].tail(780);write(ROOT/'site/replay-stocks'/f'{s}.json',[[str(d.date())]+[float(r[k]) for k in ('open','high','low','close','volume')] for d,r in f.iterrows()])
    write(STATE,dict(last_session=end,execution_revision=REVISION,cohort='vn30',membership_events=used_events,ledgers=ledgers,input_sha256=inputs));write(PUBLIC,payload)
    print('Published verified VN30 paper',end,'39 independent accounts',flush=True);return payload

if __name__=='__main__':run()
