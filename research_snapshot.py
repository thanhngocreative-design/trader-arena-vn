"""Frozen verified research replaces legacy backtests without changing paper."""
import json
from pathlib import Path
from bot_timeframes import timeframe_manifest
KEYS=('backtests','backtest_periods','backtest_options','portfolio_comparison',
      'portfolio_policy','hybrid_backtests','hybrid_backtest_audit','hybrid_model',
      'universe','universe_audit','start_date','research_meta')
def apply_research_snapshot(payload,path):
    path=Path(path)
    if not path.exists():
        raise FileNotFoundError("Verified research snapshot is required; legacy results cannot be republished")
    research=json.loads(path.read_text(encoding='utf-8'))
    if research.get('research_meta',{}).get('revision')!='continuous146_v1':
        raise ValueError('Invalid research snapshot revision')
    if len(research.get('universe',[]))!=146 or len(set(research['universe']))!=146:
        raise ValueError('Research needs exactly 146 unique verified symbols')
    if not all(k in research for k in KEYS):
        raise ValueError('Incomplete research snapshot')
    if len(research.get("backtests",{}))!=11:
        raise ValueError("Research snapshot must contain 11 daily bot results")
    if research.get("hybrid_backtest_audit",{}).get("status")=="verified_1m_146" and (len(research.get("hybrid_backtests",{}))!=11 or research["hybrid_backtest_audit"].get("symbols")!=146):
        raise ValueError("Cannot label partial minute results as a full-universe study")
    return {**payload,**{k:research[k] for k in KEYS},"bot_timeframes":timeframe_manifest()}
