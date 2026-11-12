import json
import pytest
from pathlib import Path
from research_snapshot import KEYS,apply_research_snapshot
from historical_minute import validate_wire

def snapshot():
    r={k:{} for k in KEYS}
    r['universe']=[f'T{i}' for i in range(146)]
    r['backtests']={str(i):{'return_pct':i} for i in range(11)}
    r['research_meta']={'revision':'continuous146_v1'}
    r['hybrid_backtest_audit']={'status':'loading_146_history'}
    return r

def test_snapshot_replaces_old_results_and_preserves_paper(tmp_path):
    old={'paper':{'bot':{'trades':[{'qty':100}]}},'backtests':{'old':1},'portfolio_comparison':{'old':1}}
    r=snapshot();p=tmp_path/'research.json';p.write_text(json.dumps(r))
    new=apply_research_snapshot(old,p)
    assert new['paper']==old['paper']
    assert new['backtests']==r['backtests'] and new['portfolio_comparison']=={}
    assert old['backtests']=={'old':1}
    with pytest.raises(FileNotFoundError):apply_research_snapshot(old,tmp_path/'missing.json')
    r['hybrid_backtest_audit']={'status':'verified_1m_146','symbols':8}
    p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='partial'):apply_research_snapshot(old,p)

def test_actual_wire_candles_reject_duplicates_wrong_symbol_or_bad_prices():
    # Minimal synthetic validation fixture, never published as market data.
    d={'symbol':'FPT','t':[1794449700],'o':[30000],'h':[30100],'l':[29900],'c':[30050],'v':[1000]}
    assert len(validate_wire(d,'FPT'))==1
    with pytest.raises(ValueError,match='symbol'):validate_wire(d,'HPG')
    with pytest.raises(ValueError,match='OHLCV'):validate_wire({**d,'h':[1]},'FPT')
    doubled={k:v*2 if isinstance(v,list) else v for k,v in d.items()}
    with pytest.raises(ValueError,match='Duplicate'):validate_wire(doubled,'FPT')
