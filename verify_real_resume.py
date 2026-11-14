"""Reproduce full-vs-resumed accounting using frozen REAL VN30 observations.

No market data or signals are fabricated. Ordinary synthetic engine fixtures
remain confined to tests; this audit reads the retained November 2026 bank.
"""
import argparse


def run(audit_output='data/pit_results/verified-real-resume.json'):
    import pandas as pd
    import paper_replay as p
    from paper_fixed146 import verify_inputs
    from value_investing import ROOT,read
    from pit_intraday import run_minute
    from hybrid_backtest import _walk_one
    import vn30
    state=read(ROOT/'state/paper_seasons/2026-11-02/paper_vn30.json');verify_inputs(state['input_sha256'])
    base=p.unpack(p.MARKET/'daily-history.json.gz');cfg=vn30.configuration();sessions=sorted(f.name[:10] for f in (p.MARKET/'sessions').glob('*.json.gz') if '2026-11-02'<=f.name[:10]<='2026-11-13')
    prices={s:p.frame(base['prices'][s]) for s in cfg['training_symbols']};benchmark=p.benchmark_frame(base['benchmark']);parts={s:[] for s in vn30.membership(cfg,sessions[-1])}
    for day in sessions:
     data=p.unpack(p.MARKET/'sessions'/f'{day}.json.gz')
     if day>base['asof'][:10]:
      daily=p.unpack(p.MARKET/'candidate-days'/f'{day}.json.gz')
      def convert(rows):return p.frame([{**r,'date':r.get('date') or str(pd.Timestamp(r['time']).tz_convert(p.VN).date())} for r in rows])
      benchmark=pd.concat([benchmark,convert(data['replies']['VNINDEX']['ONE_DAY'])])
      for s in prices:prices[s]=pd.concat([prices[s],convert(daily[s])]).sort_index()
     for s in parts:
      raw=pd.DataFrame(data['replies'][s]['ONE_MINUTE'])
      if raw.empty:continue
      raw.time=pd.to_datetime(raw.time,utc=True).dt.tz_convert(p.VN);tape=p.observed_minutes(raw)
      positive=raw.loc[raw.volume>0]
      if len(positive) and pd.Timestamp(day) in prices[s].index:
       ratio=float(positive.close.iloc[-1])/float(prices[s].loc[day,'close'])
       if not .92<=ratio<=1.08:tape=tape.iloc[:0]
      parts[s].append(tape)
    frames={s:pd.concat(rows).sort_index() for s,rows in parts.items() if rows};benchmark[['open','high','low','close']]*=1000
    ctx=vn30.context(prices,benchmark,cfg);settings=dict(cfg,start=sessions[0],end=sessions[-1]);output=ROOT/'data/pit_results/real-resume-check'
    run_minute({'vn30':ctx},frames,{},dict(settings,end=sessions[-2]),output/'early')
    early=read(output/'early/minute-checkpoint.json');new={s:f.loc[f.index.normalize()==pd.Timestamp(sessions[-1])] for s,f in frames.items()}
    run_minute({'vn30':ctx},new,{},settings,output/'resumed',initial_state=early)
    resumed=read(output/'resumed/minute-checkpoint.json')
    run_minute({'vn30':ctx},frames,{},settings,output/'full')
    whole=read(output/'full/minute-checkpoint.json')
    minute_accounts=len(whole['accounts']['vn30']['minute']);value_combo_accounts=len(whole['accounts']['vn30']['value_combo'])
    for key in ['accounts','curves','marks','seen','seq']:assert resumed[key]==whole[key],key
    print('REAL VN30: all 16 minute and 2 value-combo accounts match uninterrupted 10-session Paper, including every fill, NAV, cash and position',flush=True)
    first=ctx.dates.searchsorted(sessions[0]);last=ctx.dates.searchsorted(sessions[-1]);split=last-1
    combo_counts={}
    for bot in ['Beginner','DuongChung']:
     whole=_walk_one(ctx,bot,frames,first,last,ctx.settings,export_state=True)
     early=_walk_one(ctx,bot,frames,first,split,ctx.settings,export_state=True)
     resumed=_walk_one(ctx,bot,new,split+1,last,ctx.settings,initial_state=early['resume_state'],export_state=True)
     assert whole['resume_state']==resumed['resume_state'],bot
     assert len(whole['trades'])>0,bot
     combo_counts[bot]=len(whole['trades'])
     print('REAL VN30 combo resume exact:',bot,len(whole['trades']),'fills',flush=True)

    from value_investing import write
    from datetime import datetime
    from backtest_state import model_digest
    write(ROOT/audit_output,dict(status='exact_match',observed_at=datetime.now(p.VN).isoformat(),source='immutable real Vietcap ONE_MINUTE and daily observations',universe='VN30',start=sessions[0],split_after=sessions[-2],end=sessions[-1],minute_accounts=minute_accounts,value_combo_accounts=value_combo_accounts,technical_combo_fills=combo_counts,compared=['all fills','cash','positions','NAV curves','quote marks','session clocks'],model_sha256=model_digest(),input_sha256=state['input_sha256']))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--audit-output',default='data/pit_results/verified-real-resume.json')
    run(parser.parse_args().audit_output)
