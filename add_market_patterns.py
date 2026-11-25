"""Pinned additive upgrade: only two new bots, using retained verified candles.

Copy every old account exactly. Never reset or substitute daily bars for minutes.
"""
import argparse, copy, hashlib, json
from datetime import datetime
import pandas as pd
from value_investing import ROOT, VN, read, write
from backtest_state import STATE, model_digest, verify_manifest, options, frozen_sources
from paper_replay import pack, unpack, START as PAPER_START, BOTS
from continuous_backtest import inputs, START, audit_ledgers
from engine import Settings, backtest
from pit_context import PITContext
from pit_daily import attach_summary
from pit_intraday import run_minute
from pit_minute_data import load_minutes
from hybrid_backtest import _walk_one
from market_patterns import PROFILES
from bot_timeframes import timeframe_manifest
import vn30

NEW_BOTS = tuple(PROFILES)
OUT = ROOT/'data/pit_results/market-patterns-v1'
SPEC = ROOT/'config/market-patterns-migration-v1.json'
PUBLIC = ('research-300.json', 'research-vn30.json')
PAPERS = {'300':('paper-replay.json','paper_replay.json'),
          '146':('paper-fixed146.json','paper_fixed146.json'),
          'vn30':('paper-vn30.json','paper_vn30.json')}


def guard():
    spec=read(SPEC);saved=read(STATE/'manifest.json')
    if model_digest()!=spec['new_model_sha256']:raise ValueError('Unreviewed model change')
    if saved['model_sha256']!=spec['previous_model_sha256']:raise ValueError('Exact previous model required')
    return saved


def audit_extension_coverage(extension):
    """New bots can hold a former member outside today's collected baskets.

    Require a real collection receipt for those holdings after the old minute
    bank ends. An actual empty reply is allowed; an unrequested tape is not.
    """
    held=set()
    for label,ledgers in extension['ledgers'].items():
        if not label.startswith('backtest:'):continue
        for key,rows in ledgers.items():
            if key.startswith('daily:'):continue
            inventory={}
            for trade in rows:
                if trade['date']>'2026-11-12':continue
                symbol=trade['symbol'];qty=trade['qty']*(1 if trade['side']=='MUA' else -1)
                inventory[symbol]=inventory.get(symbol,0)+qty
            held.update(s for s,qty in inventory.items() if qty>0)
    monthly=read(ROOT/'site/paper-replay.json');audits={}
    for day in monthly['sessions']:
        if day<='2026-11-12':continue
        known=set()
        for folder in ('sessions','fixed146-sessions','vn30-sessions','backtest-sessions','pattern-sessions'):
            path=ROOT/'state/replay_market'/folder/(day+'.json.gz')
            if path.exists():known.update(unpack(path)['requested_symbols'])
        missing=sorted(held-known)
        if missing:raise ValueError('Unrequested post-baseline holding tapes '+day+': '+','.join(missing))
        audits[day]=dict(retained_new_bot_holdings=len(held),all_have_real_collection_receipts=True)
    return audits


def compute():
    saved=guard();end,prices,benchmark,recent,cfg,fixed,official,memberships=inputs()
    if end!=saved['last_session']:raise ValueError('Finish the current daily update first')
    dates=benchmark.index[(benchmark.index>=START)&(benchmark.index<=end)]
    verify_manifest(saved,dates,memberships,model=saved['model_sha256'])
    historical,coverage=load_minutes()
    for symbol,frame in recent.items():
        tail=frame.loc[frame.index>pd.Timestamp('2026-11-12 23:59:59')]
        historical[symbol]=pd.concat([historical.get(symbol,frame.iloc[:0]),tail]).sort_index()
        if historical[symbol].index.duplicated().any():raise ValueError('Duplicate real minute: '+symbol)
    settings=Settings(portfolio_policy='atr_v1')
    needed=set(cfg['training_symbols'])|set(fixed)|{s for row in cfg['months'] for s in row['members']}
    source={s:prices[s] for s in needed if s in prices and len(prices[s])}
    ctxs={'300':PITContext(source,benchmark,cfg['months'],settings),
          '146':PITContext(source,benchmark,cfg['months'],settings,fixed),
          'vn30':vn30.context({s:prices[s] for s in official['training_symbols']},benchmark,official)}
    sectors=read(ROOT/'config/market-classification.json')['sectors']
    result=dict(end=end,model_sha256=model_digest(),backtest={},paper={},ledgers={},combo_states={},audit={})
    for label,start in [('backtest',START),('paper',PAPER_START)]:
        folder=OUT/label;folder.mkdir(parents=True,exist_ok=True)
        tape=historical if label=='backtest' else {s:f.loc[f.index.normalize()>=pd.Timestamp(start)] for s,f in recent.items()}
        run_minute(ctxs,tape,coverage,{**cfg,'start':start,'end':end},folder,bot_ids=list(NEW_BOTS))
        minute_state=read(folder/'minute-checkpoint.json')
        for name,ctx in ctxs.items():
            universe=set(ctx.symbols);first=ctx.dates.searchsorted(start);last=ctx.dates.searchsorted(end,side='right')-1
            result[label][name]={};ledger={};result['combo_states'].setdefault(name,{})
            for bot in NEW_BOTS:
                daily={};periods=options(end) if label=='backtest' else [dict(key='ALL',start=start,end=end)]
                for option in periods:
                    r=backtest(prices,benchmark,bot,option['start'],end_date=end,settings=ctx.settings,features_cache=ctx)
                    daily[option['key']]=attach_summary(r,sectors,universe)
                    if option['key']=='ALL':
                        ledger['daily:'+bot]=json.loads(r['trades'].to_json(orient='records',date_format='iso'))
                        if label=='paper':daily['ALL']['history']=[dict(date=str(d.date()),nav=round(float(v.nav))) for d,v in r['curve'].iterrows()]
                path=folder/f'combo-{name}-{bot}.json.gz'
                if not path.exists():
                    r=_walk_one(ctx,bot,tape,first,last,ctx.settings,export_state=True)
                    summary=attach_summary(r,sectors,universe)
                    if label=='paper':summary['history']=[dict(date=str(d.date()),nav=round(float(v.nav))) for d,v in r['curve'].iterrows()]
                    pack(path,dict(summary=summary,state=r['resume_state']))
                combo=unpack(path);ledger['combo:'+bot]=combo['state']['trades']
                minute=read(folder/f'minute-{name}.json')['minute'][bot]
                if label=='paper':
                    minute['history']=[dict(date=r['date'],nav=r['nav']) for r in minute_state['curves'][name]['minute'][bot]]
                    for book in (daily['ALL'],minute,combo['summary']):book['orders_next']=[]
                ledger['minute:'+bot]=read(folder/f'minute-{name}-{bot}-trades.json')
                result[label][name][bot]=dict(daily=daily,minute=minute,combo=combo['summary'])
                if label=='backtest':result['combo_states'][name][bot]=combo['state']
                print('Computed',label,name,bot,flush=True)
            result['audit'][label+':'+name]=audit_ledgers(name,ctx,prices,tape,ledger,memberships[name])
            result['ledgers'][label+':'+name]=ledger
    write(OUT/'extension.json',result)
    print('Both bots verified on original real daily/minute inputs',flush=True)


def publish():
    old=guard();extension=read(OUT/'extension.json');end=extension['end']
    regression=read(OUT/'existing-bot-regression.json')
    if regression['status']!='exact_match' or regression['daily_strategies']!=15:raise ValueError('Existing-strategy audit missing')
    if extension['model_sha256']!=model_digest() or end!=old['last_session']:raise ValueError('Stale upgrade output')
    extension_coverage=audit_extension_coverage(extension)
    public={name:read(ROOT/'site'/name) for name in PUBLIC};before_public=copy.deepcopy(public)
    cohorts={'300':public['research-300.json']['cohorts']['300'],
             '146':public['research-300.json']['cohorts']['146'],'vn30':public['research-vn30.json']['cohort']}
    for name,cohort in cohorts.items():
        for bot,b in extension['backtest'][name].items():
            cohort['backtests'][bot]=b['daily']['ALL']
            for key,summary in b['daily'].items():cohort['backtest_periods'][key][bot]=summary
            cohort['minute_backtests'][bot]=b['minute'];cohort['hybrid_backtests'][bot]=b['combo']
    for name,p in public.items():
        if p['end']!=end or set(NEW_BOTS)&set(p['bot_ids']):raise ValueError('Unexpected publication state')
        p['bot_ids']=BOTS;p.setdefault('traders',{}).update(PROFILES);p['generated_at']=datetime.now(VN).isoformat()
        labels={'300','146'} if name=='research-300.json' else {'vn30'}
        for key,counts in extension['audit'].items():
            if key.startswith('backtest:') and key.split(':')[1] in labels:p['execution_audit']['fills_by_book'].update(counts)
        p['execution_audit']['total_fills']=sum(p['execution_audit']['fills_by_book'].values())
    ledgers=unpack(STATE/old['ledgers']);before_ledgers=copy.deepcopy(ledgers)
    minute=unpack(STATE/old['minute_state']);before_minute=copy.deepcopy(minute)
    extra=read(OUT/'backtest/minute-checkpoint.json')
    if minute['seq']!=extra['seq']:raise ValueError('Minute calendar mismatch')
    held={s for books in minute['accounts'].values() for bots in books.values() for b in bots.values() for s in b['positions']}
    for name in cohorts:
        ledgers[name].update(extension['ledgers']['backtest:'+name])
        for bot in NEW_BOTS:
            minute['accounts'][name]['minute'][bot]=extra['accounts'][name]['minute'][bot]
            minute['curves'][name]['minute'][bot]=extra['curves'][name]['minute'][bot]
            for symbol in extra['accounts'][name]['minute'][bot]['positions']:
                if symbol in held and (before_minute['marks'].get(symbol)!=extra['marks'].get(symbol) or before_minute['seen'].get(symbol)!=extra['seen'].get(symbol)):
                    raise ValueError('Shared quote differs for an existing holding')
                minute['marks'][symbol]=extra['marks'][symbol];minute['seen'][symbol]=extra['seen'][symbol]
        for mode,bots in before_minute['accounts'][name].items():
            for bot,b in bots.items():
                if minute['accounts'][name][mode][bot]!=b or minute['curves'][name][mode][bot]!=before_minute['curves'][name][mode][bot]:raise ValueError('Existing minute account changed')
        for key,rows in before_ledgers[name].items():
            if ledgers[name][key]!=rows:raise ValueError('Existing Backtest ledger changed')
    for file,p in before_public.items():
        for name,cohort in (p['cohorts'] if 'cohorts' in p else {'vn30':p['cohort']}).items():
            for mode in ('backtests','minute_backtests','hybrid_backtests'):
                for bot,b in cohort[mode].items():
                    if cohorts[name][mode][bot]!=b:raise ValueError('Existing public account changed')
            for period,bots in cohort['backtest_periods'].items():
                for bot,b in bots.items():
                    if cohorts[name]['backtest_periods'][period][bot]!=b:raise ValueError('Existing daily period changed')
    paper_public={};paper_states={}
    for name,(file,state_file) in PAPERS.items():
        p=read(ROOT/'site'/file);state=read(ROOT/'state/paper_seasons'/PAPER_START/state_file)
        before_p=copy.deepcopy(p);before_state=copy.deepcopy(state)
        if p['last_session']!=end or state['last_session']!=end or set(NEW_BOTS)&set(p['bot_ids']):raise ValueError('Paper is not at the pinned session')
        for bot,b in extension['paper'][name].items():
            for mode,book,ledger_mode in [('paper',b['daily']['ALL'],'daily'),('paper_minute',b['minute'],'minute'),('paper_combo',b['combo'],'combo')]:
                p[mode][bot]=book;state['ledgers'][mode+':'+bot]=extension['ledgers']['paper:'+name][ledger_mode+':'+bot]
        p['bot_ids']=BOTS;p['traders'].update(PROFILES);p['bot_timeframes']=timeframe_manifest();p['updated_at']=datetime.now(VN).isoformat()
        if 'execution_audit' in p:
            for key,value in extension['audit']['paper:'+name].items():p['execution_audit']['fills_by_book'][key.split(':',1)[1]]=value
            p['execution_audit']['total_fills']=sum(p['execution_audit']['fills_by_book'].values())
        for mode in ('paper','paper_minute','paper_combo'):
            for bot,b in before_p[mode].items():
                if p[mode][bot]!=b:raise ValueError('Existing Paper account changed')
        for key,rows in before_state['ledgers'].items():
            if state['ledgers'][key]!=rows:raise ValueError('Existing Paper ledger changed')
        paper_public[file]=p;paper_states[state_file]=state
    # Retain every old checkpoint; new paths hold additive accounts only.
    prefix=f'checkpoints/{end}/{model_digest()[:12]}';manifest=copy.deepcopy(old)
    minute_path=prefix+'/minute.json.gz';ledger_path=prefix+'/ledgers.json.gz'
    pack(STATE/minute_path,minute);pack(STATE/ledger_path,ledgers);paths=[minute_path,ledger_path]
    for name,bots in extension['combo_states'].items():
        for bot,state in bots.items():
            path=prefix+f'/combo-{name}-{bot}.json.gz';pack(STATE/path,state);paths.append(path);manifest['combo_states'][name][bot]=path
    manifest.update(model_sha256=model_digest(),minute_state=minute_path,ledgers=ledger_path,input_sha256=frozen_sources())
    manifest['checkpoint_sha256'].update({p:hashlib.sha256((STATE/p).read_bytes()).hexdigest() for p in paths})
    write(STATE/'migrations/market-patterns-v1.json',dict(status='verified_additive_bot_upgrade',bots=list(NEW_BOTS),end=end,
        previous_model_sha256=old['model_sha256'],new_model_sha256=model_digest(),old_backtest_accounts_preserved=153,
        old_paper_accounts_preserved=153,new_accounts=36,real_fill_audits=extension['audit'],
        post_baseline_holding_coverage=extension_coverage,existing_strategy_regression=regression))
    for file,p in public.items():write(ROOT/'site'/file,p)
    for file,p in paper_public.items():write(ROOT/'site'/file,p)
    for file,p in paper_states.items():write(ROOT/'state/paper_seasons'/PAPER_START/file,p)
    status=read(ROOT/'site/backtest-status.json');status.update(model_sha256=model_digest(),bots=BOTS,generated_at=datetime.now(VN).isoformat());write(ROOT/'site/backtest-status.json',status)
    from replay_health import main
    main();write(STATE/'manifest.json',manifest)
    print('Published 19 bots, 342 independent accounts; original 306 unchanged',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['compute','publish']);args=parser.parse_args()
    (compute if args.stage=='compute' else publish)()
