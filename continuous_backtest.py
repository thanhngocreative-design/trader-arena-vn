"""Extend all backtest books only after the three Paper universes complete.

Bootstrap runs locally from verified retained minute candles. Daily automation
then needs only the committed daily bank, new real sessions, and model states.
Raw historical minute files are never uploaded by this module.
"""
import argparse,copy,hashlib,json
from datetime import datetime
import pandas as pd
from engine import TRADERS,Settings,backtest
from fast_engine import CORE,build_hybrid_signals
from pit_context import PITContext
from pit_intraday import run_minute
from hybrid_backtest import _walk_one
from pit_daily import attach_summary,value_backtest,merged_fundamentals
from value_investing import ROOT,VN,POLICY,read,write,eligible_companies,quality
from paper_replay import MARKET,source_inputs,pack,unpack,observed_minutes
from paper_fixed146 import add_minutes,supplemental
from backtest_state import STATE,model_digest,frozen_sources,verify_manifest,options
from sector_analytics import universe_distribution
from education_bots import PROFILES
from replay_rules import can_fill
import vn30

BOTS=list(TRADERS)+list(POLICY)
START='2023-11-12'


def used_memberships(rows,start=START,end=None):
    prior=[r for r in rows if r['effective']<=start]
    return prior[-1:]+[r for r in rows if r['effective']>start and (end is None or r['effective']<=end)]


def minute_dates(frames,end,existing=None):
    observed={s:set(days) for s,days in (existing or {}).items()}
    for s,f in frames.items():
        days=f.index.normalize().unique()
        observed.setdefault(s,set()).update(str(d.date()) for d in days if START<=str(d.date())<=end)
    return {s:sorted(days) for s,days in observed.items()}


def coverage_summary(dates,rows,prices,observed,union):
    seen={s:set(days) for s,days in observed.items()};daily=minutes=missing=0;member_days=0
    for date in dates:
        day=str(date.date());members=[r for r in rows if r['effective']<=day][-1]['members']
        for s in members:
            positive=date in prices[s].index;has_minute=day in seen.get(s,set())
            member_days+=1;daily+=positive;minutes+=has_minute;missing+=positive and not has_minute
    end=str(dates[-1].date())
    return dict(audited_through=end,member_days=member_days,member_days_with_positive_daily=daily,
        member_days_no_positive_daily=member_days-daily,member_days_with_minutes=minutes,
        member_days_daily_but_no_verified_continuous_minute=missing,
        research_symbols_with_bars=sum(bool(seen.get(s)) for s in union),
        no_in_window_trades_consistent_daily=[s for s in union if not seen.get(s) and prices[s].loc[START:end].empty],
        coverage_definition='At least one real validated continuous-minute candle per member-session; this does not mean every expected minute is present.',no_interpolation=True)


def inputs(bootstrap_end=None):
    papers=[read(ROOT/'site'/name) for name in ('paper-replay.json','paper-fixed146.json','paper-vn30.json')]
    if any(p['status']!='completed_session_replay' for p in papers) or len({p['last_session'] for p in papers})!=1:
        raise ValueError('All three Paper universes must finish on the same session first')
    end=papers[0]['last_session']
    if bootstrap_end is not None:
        if bootstrap_end>end:raise ValueError('Cannot bootstrap beyond completed Paper data')
        end=bootstrap_end
    prices,benchmark,frames,cfg,_,sessions=source_inputs(end,False)
    fixed=read(ROOT/'config/research-universe.json')['eligible_symbols']
    add_minutes(prices,frames,sessions,fixed,False)
    official=vn30.configuration()
    # Official historical VN30 is never extrapolated from today's members.
    from vn30_current import verify_current
    verify_current(official,end)
    for day in sessions:verify_current(official,day)
    prior=read(STATE/'manifest.json') if (STATE/'manifest.json').exists() else None
    retained=set()
    if prior:
        saved=unpack(STATE/prior['minute_state'])
        retained.update(s for books in saved['accounts'].values() for bots in books.values() for account in bots.values() for s in account['positions'])
        for paths in prior['combo_states'].values():
            for path in paths.values():retained.update(unpack(STATE/path)['positions'])
    since=prior['last_session'] if prior else read(ROOT/'config/research-300.json')['end']
    extra_frames={}
    for day in sessions:
        if day<=since:continue
        monthly=unpack(MARKET/'sessions'/f'{day}.json.gz')
        # Backtest may still hold a previously selected suspended stock. Bank
        # its real resumed tape as well; Paper's current members alone cannot
        # represent all historical accounts. Historical baskets are not changed.
        known=set(monthly['requested_symbols'])|set(fixed)
        required=retained|vn30.membership(official,day)
        missing=sorted(required-known)
        extra=supplemental(day,missing,True,folder='backtest-sessions')
        for s,rows in extra['replies'].items():
            raw=pd.DataFrame(rows)
            if raw.empty:continue
            raw.time=pd.to_datetime(raw.time,utc=True).dt.tz_convert(VN)
            tape=observed_minutes(raw);positive=raw.loc[raw.volume>0]
            if len(positive) and pd.Timestamp(day) in prices[s].index:
                ratio=float(positive.close.iloc[-1])/float(prices[s].loc[day,'close'])
                if not .92<=ratio<=1.08:tape=tape.iloc[:0]
            extra_frames.setdefault(s,[]).append(tape)
    for s,parts in extra_frames.items():
        frames[s]=pd.concat([frames.get(s,parts[0].iloc[:0]),*parts]).sort_index()
        if frames[s].index.duplicated().any():raise ValueError('Duplicate backtest supplemental candle')
    benchmark=benchmark.copy();benchmark[['open','high','low','close']]*=1000
    memberships={'300':cfg['months'],'146':[dict(effective='2022-01-03',asof='2021-12-31',members=fixed)],'vn30':official['months']}
    return end,prices,benchmark,frames,cfg,fixed,official,memberships


def contexts(prices,benchmark,cfg,fixed,official):
    settings=Settings(portfolio_policy='atr_v1')
    needed=set(cfg['training_symbols'])|set(fixed)|{s for row in cfg['months'] for s in row['members']}
    source={s:prices[s] for s in needed if s in prices and len(prices[s])}
    ctxs={name:PITContext(source,benchmark,cfg['months'],settings,static) for name,static in [('300',None),('146',fixed)]}
    ctxs['vn30']=vn30.context({s:prices[s] for s in official['training_symbols']},benchmark,official)
    for name,ctx in ctxs.items():
        training={b:backtest(source,benchmark,b,'2022-01-03',end_date=str(benchmark.index[-1].date()),settings=ctx.settings,features_cache=ctx)['curve'] for b in CORE}
        build_hybrid_signals(ctx,training)
        print('Prepared causal daily context',name,flush=True)
    return ctxs


def audit_ledgers(cohort,ctx,prices,frames,ledgers,memberships,after=None):
    dates={str(d.date()):i for i,d in enumerate(ctx.dates)};counts={}
    def member(symbol,day):return symbol in [r for r in memberships if r['effective']<=day][-1]['members']
    for key,trades in ledgers.items():
        mode,bot=key.split(':');inventory={}
        for trade in trades:
            s=trade['symbol'];day=trade['date'];qty,bought=inventory.get(s,(0,None))
            if trade['qty']<=0 or trade['qty']%100:raise ValueError('Invalid lot')
            if trade['side']=='MUA':
                if qty or not member(s,day):raise ValueError('Entry outside point-in-time universe')
                inventory[s]=(trade['qty'],day)
            else:
                if trade['qty']>qty or dates[day]-dates[bought]<5:raise ValueError('Unsettled or unowned sale')
                inventory[s]=(qty-trade['qty'],bought)
            if after is not None and day<=after:continue
            ts=pd.Timestamp(day if mode=='daily' else trade['time'])
            source=prices[s] if mode=='daily' else frames[s]
            if ts not in source.index or source.loc[ts,'volume']<=0:raise ValueError('Fill without a real positive-volume candle')
            opening=float(source.loc[ts,'open'])
            if abs(float(trade['price'])-opening)>opening*.0125+1.1:raise ValueError('Unverified fill price')
            if mode=='daily':
                if trade['signal_date']!=str(ctx.dates[dates[day]-1].date()):raise ValueError('Daily lookahead')
            elif not can_fill(trade['signal_time'],trade['time'],trade.get('submitted_at')):raise ValueError('Minute lookahead or deferred fill')
            if bot in POLICY and trade['side']=='MUA' and not trade['financial_available_at']<=trade.get('quality_asof',trade.get('signal_date'))<day:
                raise ValueError('Future financial report')
        counts[cohort+':'+key]=len(trades)
    return counts


def archive_baseline():
    archive=ROOT/'site/backtest-archive/2026-11-12';manifest=STATE/'baseline-manifest.json'
    if manifest.exists():
        for name,digest in read(manifest).items():
            if hashlib.sha256((archive/name).read_bytes()).hexdigest()!=digest:raise ValueError('Archived baseline changed')
        return
    records={}
    for name in ('research-300.json','research-vn30.json'):
        original=ROOT/'site'/name
        if read(original)['end']!='2026-11-12':raise ValueError('Archive baseline before extending research')
        target=archive/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(original.read_bytes());records[name]=hashlib.sha256(target.read_bytes()).hexdigest()
    write(manifest,records)


def run(bootstrap=False,bootstrap_end=None,resume_bootstrap_minute=None):
    if bootstrap_end is not None and not bootstrap:raise ValueError('A fixed bootstrap date is only valid for initial history')
    if resume_bootstrap_minute is not None and not bootstrap:raise ValueError('An unpublished bootstrap checkpoint cannot replace active account state')
    end,prices,benchmark,frames,cfg,fixed,official,memberships=inputs(bootstrap_end)
    dates=benchmark.index[(benchmark.index>=START)&(benchmark.index<=end)]
    manifest=STATE/'manifest.json';previous=read(manifest) if manifest.exists() else None
    if previous:
        verify_manifest(previous,dates,memberships)
        if previous['last_session']==end:print('No new session; all Backtests already current',end,flush=True);return
    elif not bootstrap:raise ValueError('Bootstrap the original history from the retained verified local bank first')
    historical_observations={}
    if previous:
        if previous.get('coverage_state'):historical_observations=unpack(STATE/previous['coverage_state'])
        else:
            # One-time local migration of an unpublished bootstrap. A cloud
            # update never substitutes daily bars for missing minute history.
            from pit_minute_data import load_minutes
            retained_frames,_=load_minutes()
            historical_observations=minute_dates(retained_frames,previous['last_session'])
            del retained_frames
    after=previous['last_session'] if previous else None
    if bootstrap and previous:raise ValueError('Bootstrap into a new version; do not overwrite an existing continuous ledger')
    if bootstrap:
        from pit_minute_data import load_minutes
        historical,historical_coverage=load_minutes()
        for s,f in historical.items():
            new=frames.get(s,f.iloc[:0]);new=new.loc[new.index>pd.Timestamp('2026-11-12 23:59:59')]
            frames[s]=pd.concat([f,new]).sort_index()
            if frames[s].index.duplicated().any():raise ValueError('Duplicate real candle while extending baseline')
    else:
        frames={s:f.loc[f.index.normalize()>pd.Timestamp(after)] for s,f in frames.items()}
    observations=minute_dates(frames,end,historical_observations)
    ctxs=contexts(prices,benchmark,cfg,fixed,official)
    output=ROOT/'data/pit_results/continuous'/model_digest()[:12]/end;output.mkdir(parents=True,exist_ok=True)
    config={**cfg,'start':START,'end':end}
    # The raw files were SHA-verified by load_minutes; banked session files are
    # SHA-verified by the manifest. Avoid serializing millions of old candles
    # solely to make a second, redundant cache key on every update.
    sources=frozen_sources()
    session_digest=hashlib.sha256(json.dumps(sources,sort_keys=True).encode()).hexdigest()
    coverage={s:dict(minute_sha256=hashlib.sha256((session_digest+(historical_coverage.get(s,{}).get('minute_sha256','') if bootstrap else '')).encode()).hexdigest()) for s in frames}
    initial=unpack(STATE/previous['minute_state']) if previous else None
    if resume_bootstrap_minute is not None:
        initial=read(resume_bootstrap_minute)
        if set(initial['accounts'])!=set(ctxs):raise ValueError('Wrong bootstrap checkpoint cohorts')
        for books in initial['accounts'].values():
            if set(books['minute'])!=set(BOTS) or set(books['value_combo'])!=set(POLICY):raise ValueError('Wrong bootstrap bot set')
        print('Continue unpublished bootstrap after',initial['seq']+1,'verified sessions',flush=True)
    run_minute(ctxs,frames,coverage,config,output,initial_state=initial)
    classification=read(ROOT/'config/market-classification.json');reports=eligible_companies(merged_fundamentals(),classification['sectors'])
    cohorts={};ledgers={};combo_states={};counts={};periods=options(end)
    for name,ctx in ctxs.items():
        ledgers[name]={};results={}
        for option in periods:
            results[option['key']]={}
            for bot in BOTS:
                r=backtest(prices,benchmark,bot,option['start'],end_date=end,settings=ctx.settings,features_cache=ctx) if bot in TRADERS else value_backtest(ctx,bot,option['start'],end,reports)
                results[option['key']][bot]=attach_summary(r,classification['sectors'],set(ctx.symbols))
                if option['key']=='ALL':ledgers[name]['daily:'+bot]=json.loads(r['trades'].to_json(orient='records',date_format='iso'))
        minute=read(output/f'minute-{name}.json');combo={};combo_states[name]={}
        for bot in TRADERS:
            cache=output/f'combo-state-{name}-{bot}.json.gz'
            if cache.exists():
                cached=unpack(cache);combo[bot]=cached['summary'];state=cached['state']
            else:
                state=unpack(STATE/previous['combo_states'][name][bot]) if previous else None
                first=ctx.dates.searchsorted(after,side='right') if previous else ctx.dates.searchsorted(START)
                r=_walk_one(ctx,bot,frames,first,len(ctx.dates)-1,ctx.settings,initial_state=state,export_state=True)
                combo[bot]=attach_summary(r,classification['sectors'],set(ctx.symbols));state=r['resume_state']
                pack(cache,dict(summary=combo[bot],state=state))
            combo_states[name][bot]=state;ledgers[name]['combo:'+bot]=state['trades']
            print('Computed continuous combo',name,bot,end,flush=True)
        for bot in BOTS:
            ledgers[name]['minute:'+bot]=read(output/f'minute-{name}-{bot}-trades.json')
        for bot in POLICY:ledgers[name]['combo:'+bot]=read(output/f'value_combo-{name}-{bot}-trades.json')
        if previous:
            old=unpack(STATE/previous['ledgers'])[name]
            for key,trades in old.items():
                if [t for t in ledgers[name][key] if t['date']<=after]!=trades:raise ValueError('Previously audited ledger changed')
        counts.update(audit_ledgers(name,ctx,prices,frames,ledgers[name],memberships[name],after))
        members=[r for r in memberships[name] if r['effective']<=end][-1]['members']
        cohorts[name]=dict(backtests=results['ALL'],backtest_periods=results,minute_backtests=minute['minute'],hybrid_backtests={**combo,**minute['value_combo']},universe=members,universe_union=sorted({s for r in used_memberships(memberships[name],end=end) for s in r['members']}))
        if bootstrap and end=='2026-11-12':
            baseline=read(ROOT/'site/backtest-archive/2026-11-12'/('research-vn30.json' if name=='vn30' else 'research-300.json'))
            baseline=baseline['cohort'] if name=='vn30' else baseline['cohorts'][name]
            for book in ('backtests','minute_backtests','hybrid_backtests'):
                for bot,old in baseline[book].items():
                    for metric in ('nav','cash','return_pct','max_drawdown_pct','buy_count','closed_trades'):
                        if old.get(metric)!=cohorts[name][book][bot].get(metric):raise ValueError('Original baseline changed: '+':'.join((name,book,bot,metric)))
            print('Verified all original baseline accounts unchanged:',name,flush=True)
    # Publish only after all 144 accounts reconcile and every new fill is audited.
    archive_baseline();prefix=f'checkpoints/{end}/{model_digest()[:12]}'
    minute_path=prefix+'/minute.json.gz';pack(STATE/minute_path,read(output/'minute-checkpoint.json'))
    ledger_path=prefix+'/ledgers.json.gz';pack(STATE/ledger_path,ledgers)
    coverage_path=prefix+'/minute-dates.json.gz';pack(STATE/coverage_path,observations)
    state_paths={}
    for name,states in combo_states.items():
        state_paths[name]={}
        for bot,state in states.items():
            path=f'{prefix}/combo-{name}-{bot}.json.gz';pack(STATE/path,state);state_paths[name][bot]=path
    monthly=read(ROOT/'site/research-300.json');official_public=read(ROOT/'site/research-vn30.json')
    for name,cohort in cohorts.items():
        old=monthly['cohorts'][name] if name!='vn30' else official_public['cohort']
        first_members=[r for r in memberships[name] if r['effective']<=str(dates[0].date())][-1]['members']
        cohort['value_audit']={bot:dict(quality_eligible_start=sum(s in first_members and quality(rs,dates[0],bot) is not None for s,rs in reports.items()),
            quality_eligible_end=sum(s in cohort['universe'] and quality(rs,dates[-1],bot) is not None for s,rs in reports.items())) for bot in POLICY}
        cohort['fundamentals']={**old.get('fundamentals',{}),'requested_symbols':len(cohort['universe_union']),
            'comparable_nonfinancial_companies':sum(s in reports for s in cohort['universe_union'])}
    audit=dict(status='all_fills_verified_against_real_bars',fills_by_book=counts,total_fills=sum(counts.values()),audited_through=end)
    for public in (monthly,official_public):public.update(end=end,sessions=len(dates),generated_at=datetime.now(VN).isoformat(),continuous_backtest=True,bot_ids=BOTS,backtest_options=periods,traders=PROFILES,execution_audit=audit)
    monthly['cohorts']={k:cohorts[k] for k in ('300','146')}
    monthly['months']=[r for r in cfg['months'] if r['effective']>='2023-11-01' and r['effective']<=end]
    monthly['union_symbols']=cohorts['300']['universe_union'];monthly['unique_symbols']=len(monthly['union_symbols'])
    monthly['sector_universes']={k:universe_distribution(cohorts[k]['universe'],classification) for k in ('300','146')}
    official_public['cohort']=cohorts['vn30'];official_public['sector_universe']=universe_distribution(cohorts['vn30']['universe'],classification)
    official_public['months']=used_memberships(official['months'],end=end)
    official_public['unique_symbols']=len(cohorts['vn30']['universe_union'])
    official_public['verified_through']=end
    official_public['membership_verification_basis']='Verified effective-date notices, plus retained current-member checks for each later completed session; a detected change blocks replay until its effective date is verified.'
    for public,names in [(monthly,('300','146')),(official_public,('vn30',))]:
        selected={k:v for k,v in counts.items() if k.split(':')[0] in names}
        public['execution_audit']={**audit,'fills_by_book':selected,'total_fills':sum(selected.values())}
    monthly['minute_audit']={**monthly['minute_audit'],**coverage_summary(dates,memberships['300'],prices,observations,cohorts['300']['universe_union'])}
    official_public['minute_audit']={**official_public['minute_audit'],**coverage_summary(dates,memberships['vn30'],prices,observations,cohorts['vn30']['universe_union'])}
    # Keep provenance of the original source-wide audit separate from the
    # updated, member-by-member coverage above.
    for public in (monthly,official_public):public['minute_audit']['original_source_audit_asof']='2026-11-12'
    official_public['membership_sha256']=vn30.membership_digest()
    for symbol in sorted({s for cohort in cohorts.values() for s in cohort['universe_union']}):
        observed=prices[symbol].loc[:end].tail(780)
        bars=[[str(date.date())]+[float(value) for value in row] for date,row in observed[['open','high','low','close','volume']].iterrows()]
        write(ROOT/'site/pit-stocks'/f'{symbol}.json',bars)
    write(ROOT/'site/research-300.json',monthly);write(ROOT/'site/research-vn30.json',official_public)
    write(ROOT/'site/backtest-status.json',dict(end=end,generated_at=monthly['generated_at'],model_sha256=model_digest(),bots=BOTS,status='complete'))
    state_files=[minute_path,ledger_path,coverage_path]+[path for paths in state_paths.values() for path in paths.values()]
    state_hashes={path:hashlib.sha256((STATE/path).read_bytes()).hexdigest() for path in state_files}
    write(manifest,dict(last_session=end,model_sha256=model_digest(),calendar=[str(d.date()) for d in dates],checkpoint_sha256=state_hashes,
        memberships={k:[r for r in rows if r['effective']<=end] for k,rows in memberships.items()},input_sha256=frozen_sources(),
        minute_state=minute_path,combo_states=state_paths,ledgers=ledger_path,coverage_state=coverage_path))
    print('Published all continuous Backtests through',end,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bootstrap',action='store_true');p.add_argument('--bootstrap-end');p.add_argument('--resume-bootstrap-minute');args=p.parse_args();run(args.bootstrap,args.bootstrap_end,args.resume_bootstrap_minute)
