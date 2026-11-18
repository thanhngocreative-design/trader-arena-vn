"""One-time, pinned model upgrade: replay ONLY Elliott from retained real bars.

Existing bot accounts and ledgers are copied exactly, never reset or recomputed.
The manifest gate remains strict for ordinary daily updates. This upgrade needs
the local audited three-year minute bank, not daily candles as a substitute.
"""
import argparse,copy,hashlib,json
from datetime import datetime
import pandas as pd
from value_investing import ROOT,VN,read,write
from backtest_state import STATE,model_digest,verify_manifest,options,frozen_sources
from paper_replay import pack,unpack,START as PAPER_START,BOTS
from continuous_backtest import inputs,START,audit_ledgers
from engine import Settings,backtest
from pit_context import PITContext
from pit_daily import attach_summary
from pit_intraday import run_minute
from pit_minute_data import load_minutes
from hybrid_backtest import _walk_one
from elliott_wave import PROFILE
from bot_timeframes import timeframe_manifest
import vn30

OUT=ROOT/'data/pit_results/elliott-v1'
SPEC=ROOT/'config/elliott-migration-v1.json'
PUBLIC={'300':'research-300.json','vn30':'research-vn30.json'}
PAPERS={'300':('paper-replay.json','paper_replay.json'),'146':('paper-fixed146.json','paper_fixed146.json'),'vn30':('paper-vn30.json','paper_vn30.json')}


def guard():
    spec=read(SPEC);saved=read(STATE/'manifest.json')
    if model_digest()!=spec['new_model_sha256']:raise ValueError('Unreviewed model change; revalidate the upgrade')
    if saved['model_sha256']!=spec['previous_model_sha256']:raise ValueError('Upgrade requires the exact prior model')
    return saved


def trades(result):
    return json.loads(result['trades'].to_json(orient='records',date_format='iso'))


def compute():
    saved=guard();end,prices,benchmark,recent,cfg,fixed,official,memberships=inputs()
    if end!=saved['last_session']:raise ValueError('Finish existing daily update before adding a bot')
    dates=benchmark.index[(benchmark.index>=START)&(benchmark.index<=end)]
    verify_manifest(saved,dates,memberships,model=saved['model_sha256'])
    historical,coverage=load_minutes()
    for s,f in recent.items():
        tail=f.loc[f.index>pd.Timestamp('2026-11-12 23:59:59')]
        historical[s]=pd.concat([historical.get(s,f.iloc[:0]),tail]).sort_index()
        if historical[s].index.duplicated().any():raise ValueError('Duplicate real minute in upgrade: '+s)
    frames=historical;print('Loaded verified original minute bank',len(frames),'stocks',flush=True)
    settings=Settings(portfolio_policy='atr_v1')
    needed=set(cfg['training_symbols'])|set(fixed)|{s for r in cfg['months'] for s in r['members']}
    source={s:prices[s] for s in needed if s in prices and len(prices[s])}
    ctxs={'300':PITContext(source,benchmark,cfg['months'],settings),
          '146':PITContext(source,benchmark,cfg['months'],settings,fixed),
          'vn30':vn30.context({s:prices[s] for s in official['training_symbols']},benchmark,official)}
    classification=read(ROOT/'config/market-classification.json')['sectors']
    extension={'end':end,'model_sha256':model_digest(),'backtest':{},'paper':{},'ledgers':{},'combo_states':{},'audit':{}}
    for label,start in [('backtest',START),('paper',PAPER_START)]:
        folder=OUT/label;folder.mkdir(parents=True,exist_ok=True)
        tape=frames if label=='backtest' else {s:f.loc[f.index.normalize()>=pd.Timestamp(start)] for s,f in frames.items()}
        run_minute(ctxs,tape,coverage,{**cfg,'start':start,'end':end},folder,bot_ids=['Elliott'])
        for name,ctx in ctxs.items():
            universe=set(ctx.symbols);first=ctx.dates.searchsorted(start);last=ctx.dates.searchsorted(end,side='right')-1
            books={};ledger={}
            periods=options(end) if label=='backtest' else [dict(key='ALL',start=start,end=end)]
            daily={}
            for option in periods:
                r=backtest(prices,benchmark,'Elliott',option['start'],end_date=end,settings=ctx.settings,features_cache=ctx)
                daily[option['key']]=attach_summary(r,classification,universe)
                if option['key']=='ALL':
                    ledger['daily:Elliott']=trades(r)
                    if label=='paper':daily['ALL']['history']=[dict(date=str(d.date()),nav=round(float(row.nav))) for d,row in r['curve'].iterrows()]
            books['daily']=daily
            path=folder/f'combo-{name}-Elliott.json.gz'
            if not path.exists():
                r=_walk_one(ctx,'Elliott',tape,first,last,ctx.settings,export_state=True)
                summary=attach_summary(r,classification,universe)
                if label=='paper':summary['history']=[dict(date=str(d.date()),nav=round(float(row.nav))) for d,row in r['curve'].iterrows()]
                pack(path,dict(summary=summary,state=r['resume_state']))
            combo=unpack(path);books['combo']=combo['summary'];ledger['combo:Elliott']=combo['state']['trades']
            minute=read(folder/f'minute-{name}.json')['minute']['Elliott']
            if label=='paper':
                state=read(folder/'minute-checkpoint.json');minute['history']=[dict(date=r['date'],nav=r['nav']) for r in state['curves'][name]['minute']['Elliott']]
            books['minute']=minute;ledger['minute:Elliott']=read(folder/f'minute-{name}-Elliott-trades.json')
            if label=='paper':
                for b in [books['daily']['ALL'],books['minute'],books['combo']]:b['orders_next']=[]
            counts=audit_ledgers(name,ctx,prices,tape,ledger,memberships[name])
            extension[label][name]=books;extension['audit'][label+':'+name]=counts
            extension['ledgers'][label+':'+name]=ledger
            if label=='backtest':extension['combo_states'][name]=combo['state']
            print('Verified Elliott',label,name,{k:v.get('return_pct') for k,v in books.items() if k!='daily'},flush=True)
    write(OUT/'extension.json',extension)
    print('Elliott ready for pinned, additive publication',flush=True)


def publish():
    old=guard();extension=read(OUT/'extension.json');end=extension['end']
    regression=read(OUT/'existing-bot-regression.json')
    if regression['status']!='exact_match' or regression['daily_strategies']!=14:raise ValueError('Original-strategy differential audit missing')
    if extension['model_sha256']!=model_digest() or end!=old['last_session']:raise ValueError('Stale upgrade output')
    public={name:read(ROOT/'site'/name) for name in PUBLIC.values()}
    old_public=copy.deepcopy(public);cohorts={'300':public['research-300.json']['cohorts']['300'],'146':public['research-300.json']['cohorts']['146'],'vn30':public['research-vn30.json']['cohort']}
    for name,cohort in cohorts.items():
        b=extension['backtest'][name]
        cohort['backtests']['Elliott']=b['daily']['ALL']
        for key,summary in b['daily'].items():cohort['backtest_periods'][key]['Elliott']=summary
        cohort['minute_backtests']['Elliott']=b['minute'];cohort['hybrid_backtests']['Elliott']=b['combo']
    for name,p in public.items():
        if p['end']!=end or 'Elliott' in p['bot_ids']:raise ValueError('Unexpected publication state')
        p['bot_ids']=BOTS;p.setdefault('traders',{})['Elliott']=PROFILE;p['generated_at']=datetime.now(VN).isoformat()
        new_counts={k:v for c,counts in extension['audit'].items() if c.startswith('backtest:') for k,v in counts.items() if k.split(':')[0] in (['300','146'] if name=='research-300.json' else ['vn30'])}
        p['execution_audit']['fills_by_book'].update(new_counts);p['execution_audit']['total_fills']=sum(p['execution_audit']['fills_by_book'].values())
    ledgers=unpack(STATE/old['ledgers']);old_ledgers=copy.deepcopy(ledgers)
    minute=unpack(STATE/old['minute_state']);old_minute=copy.deepcopy(minute)
    extra=read(OUT/'backtest/minute-checkpoint.json')
    if minute['seq']!=extra['seq']:raise ValueError('Minute calendar mismatch')
    held={s for books in old_minute['accounts'].values() for bots in books.values() for b in bots.values() for s in b['positions']}
    for name in cohorts:
        minute['accounts'][name]['minute']['Elliott']=extra['accounts'][name]['minute']['Elliott']
        minute['curves'][name]['minute']['Elliott']=extra['curves'][name]['minute']['Elliott']
        ledgers[name].update(extension['ledgers']['backtest:'+name])
        for s in extra['accounts'][name]['minute']['Elliott']['positions']:
            if s in held and (old_minute['marks'].get(s)!=extra['marks'].get(s) or old_minute['seen'].get(s)!=extra['seen'].get(s)):
                raise ValueError('Shared quote differs for an existing position')
            minute['marks'][s]=extra['marks'][s];minute['seen'][s]=extra['seen'][s]
    # Demonstrate that every old account, NAV curve and trade ledger is identical.
    for name in cohorts:
        for mode,bots in old_minute['accounts'][name].items():
            for bot,b in bots.items():
                if minute['accounts'][name][mode][bot]!=b or minute['curves'][name][mode][bot]!=old_minute['curves'][name][mode][bot]:raise ValueError('Old minute account changed')
        for key,rows in old_ledgers[name].items():
            if ledgers[name][key]!=rows:raise ValueError('Old ledger changed')
    for file,p in old_public.items():
        before=p['cohorts'] if 'cohorts' in p else {'vn30':p['cohort']}
        for name,c in before.items():
            for key in ('backtests','minute_backtests','hybrid_backtests'):
                for bot,b in c[key].items():
                    if cohorts[name][key][bot]!=b:raise ValueError('Existing public account changed')
            for key,bots in c['backtest_periods'].items():
                for bot,b in bots.items():
                    if cohorts[name]['backtest_periods'][key][bot]!=b:raise ValueError('Existing daily period changed')
    paper_public={};paper_states={}
    for name,(file,state_file) in PAPERS.items():
        p=read(ROOT/'site'/file);state=read(ROOT/'state/paper_seasons'/PAPER_START/state_file)
        before_p=copy.deepcopy(p);before_state=copy.deepcopy(state)
        if p['last_session']!=end or state['last_session']!=end or 'Elliott' in p['bot_ids']:raise ValueError('Paper is not at the pinned session')
        b=extension['paper'][name]
        for mode,book,ledger_mode in [('paper',b['daily']['ALL'],'daily'),('paper_minute',b['minute'],'minute'),('paper_combo',b['combo'],'combo')]:
            p[mode]['Elliott']=book;state['ledgers'][mode+':Elliott']=extension['ledgers']['paper:'+name][ledger_mode+':Elliott']
        p['bot_ids']=BOTS;p['traders']['Elliott']=PROFILE;p['bot_timeframes']=timeframe_manifest();p['updated_at']=datetime.now(VN).isoformat()
        if 'execution_audit' in p:
            for k,v in extension['audit']['paper:'+name].items():p['execution_audit']['fills_by_book'][k.split(':',1)[1]]=v
            p['execution_audit']['total_fills']=sum(p['execution_audit']['fills_by_book'].values())
        for mode in ('paper','paper_minute','paper_combo'):
            for bot,book in before_p[mode].items():
                if p[mode][bot]!=book:raise ValueError('Existing Paper account changed')
        for key,rows in before_state['ledgers'].items():
            if state['ledgers'][key]!=rows:raise ValueError('Existing Paper ledger changed')
        paper_public[file]=p;paper_states[state_file]=state
    # New paths leave all prior immutable checkpoints available for inspection.
    prefix=f'checkpoints/{end}/{model_digest()[:12]}';manifest=copy.deepcopy(old)
    minute_path=prefix+'/minute.json.gz';ledger_path=prefix+'/ledgers.json.gz'
    pack(STATE/minute_path,minute);pack(STATE/ledger_path,ledgers)
    new_paths=[minute_path,ledger_path];manifest['combo_states']=copy.deepcopy(old['combo_states'])
    for name,state in extension['combo_states'].items():
        path=prefix+'/combo-'+name+'-Elliott.json.gz';pack(STATE/path,state);new_paths.append(path);manifest['combo_states'][name]['Elliott']=path
    manifest.update(model_sha256=model_digest(),minute_state=minute_path,ledgers=ledger_path,input_sha256=frozen_sources())
    manifest['checkpoint_sha256'].update({p:hashlib.sha256((STATE/p).read_bytes()).hexdigest() for p in new_paths})
    audit=dict(status='verified_additive_bot_upgrade',bot='Elliott',end=end,previous_model_sha256=old['model_sha256'],new_model_sha256=model_digest(),old_backtest_accounts_preserved=144,old_paper_accounts_preserved=144,new_accounts=18,real_fill_audits=extension['audit'],existing_strategy_regression=regression,prior_manifest_sha256=hashlib.sha256((STATE/'manifest.json').read_bytes()).hexdigest())
    write(STATE/'migrations/elliott-v1.json',audit)
    for name,p in public.items():write(ROOT/'site'/name,p)
    for name,p in paper_public.items():write(ROOT/'site'/name,p)
    for name,p in paper_states.items():write(ROOT/'state/paper_seasons'/PAPER_START/name,p)
    status=read(ROOT/'site/backtest-status.json');status.update(model_sha256=model_digest(),bots=BOTS,generated_at=public['research-300.json']['generated_at']);write(ROOT/'site/backtest-status.json',status)
    from replay_health import main
    main();write(STATE/'manifest.json',manifest)
    print('Published 17 bots, 306 independent accounts; original 288 unchanged',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['compute','publish']);args=parser.parse_args()
    (compute if args.stage=='compute' else publish)()
