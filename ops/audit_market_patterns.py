"""Compare all original signals/features against the pinned pre-upgrade code."""
import subprocess, sys, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import pandas as pd
import engine, minute_arena, pit_minute_data
from education_bots import PROFILES
from market_patterns import PROFILES as NEW
from pit_universe import load_daily
from paper_replay import unpack, benchmark_frame, observed_minutes
from value_investing import read, write, VN


def run():
    spec=read(ROOT/'config/market-patterns-migration-v1.json')
    source=subprocess.check_output(['git','show',spec['baseline_commit']+':education_bots.py'],cwd=ROOT).decode('utf8')
    old=types.ModuleType('old_education_rules');exec(source,old.__dict__)
    prices,_,_=load_daily();base=unpack(ROOT/'state/replay_market/daily-history.json.gz')
    benchmark=benchmark_frame(base['benchmark'])
    old_traders=engine.TRADERS;old_signals=engine.daily_signals
    keys=[k for k in engine.TRADERS if k not in NEW]
    checked=[]
    for symbol in sorted(prices)[:64]:
        raw=prices[symbol]
        if len(raw)<252:continue
        current=engine.make_features(raw,benchmark)
        try:
            engine.TRADERS={k:old_traders[k] for k in keys};engine.daily_signals=old.daily_signals
            prior=engine.make_features(raw,benchmark)
        finally:engine.TRADERS=old_traders;engine.daily_signals=old_signals
        pd.testing.assert_frame_equal(current.loc[:,prior.columns],prior)
        for _,row in current.iloc[::31].iterrows():
            position=dict(price=float(row.close),high_water=float(row.close)*1.1)
            for bot in old.PROFILES:
                assert engine.daily_exit(bot,row,position)==old.daily_exit(bot,row,position),(symbol,bot)
        checked.append(symbol)
    bank=unpack(ROOT/'state/replay_market/sessions/2026-11-25.json.gz')
    tapes={}
    for symbol,reply in bank['replies'].items():
        if symbol=='VNINDEX' or not reply['ONE_MINUTE']:continue
        raw=pd.DataFrame(reply['ONE_MINUTE']);raw.time=pd.to_datetime(raw.time,utc=True).dt.tz_convert(VN)
        tape=observed_minutes(raw)
        if len(tape)>=80:tapes[symbol]=tape
        if len(tapes)==8:break
    for module in (minute_arena,pit_minute_data):
        fn=module.minute_signals
        try:
            if module is minute_arena:
                current={s:module.features(f) for s,f in tapes.items()};module.minute_signals=old.minute_signals
                for s,f in tapes.items():
                    prior=module.features(f);pd.testing.assert_frame_equal(current[s].loc[:,prior.columns],prior)
            else:
                symbols,current=module.wide_features(tapes);module.minute_signals=old.minute_signals
                other,prior=module.wide_features(tapes);assert symbols==other
                import numpy as np
                for key in prior:np.testing.assert_equal(current[key],prior[key])
        finally:module.minute_signals=fn
    if len(checked)<50 or len(tapes)!=8:raise ValueError('Insufficient retained real observations for regression')
    write(ROOT/'data/pit_results/market-patterns-v1/existing-bot-regression.json',dict(status='exact_match',
        baseline_commit=spec['baseline_commit'],daily_strategies=len(keys),daily_symbols=checked,
        minute_symbols=sorted(tapes),minute_source_session='2026-11-25',scalar_and_wide_minute_features_unchanged=True,
        original_daily_features_signals_and_educational_exits_unchanged=True,original_hybrid_pool_unchanged=True))
    print('Exact original-rule match:',len(keys),'strategies,',len(checked),'real daily stocks and',len(tapes),'real minute stocks')


if __name__=='__main__':run()
