import json,math
from pathlib import Path
import pytest
from sector_analytics import aggregate_trades,universe_distribution,attach_paper_sectors

def trade(symbol='AAA',side='MUA',qty=100,price=10000,**extra):
    return dict(symbol=symbol,side=side,qty=qty,price=price,**extra)

def test_sector_turnover_uses_buys_only_and_keeps_unknown_and_outside_symbols():
    mapping={'AAA':dict(sector='Ngân hàng',icb_code='BANK')}
    trades=[trade(gross=2_000_000),trade('ZZZ',qty=300),trade(side='BÁN',qty=50,pnl=25000)]
    result=aggregate_trades(trades,mapping,{'AAA'})
    assert result['buy_value']==5_000_000 and result['buy_fills']==2 and result['sell_fills']==1
    by={g['sector']:g for g in result['sectors']}
    assert by['Ngân hàng']['buy_share_pct']==40
    assert by['Ngân hàng']['realized_pnl']==25000
    assert by['Chưa phân loại']['buy_share_pct']==60
    assert result['outside_146_fills']==1
    assert not aggregate_trades([],mapping,{'AAA'})['sectors']
    with pytest.raises(ValueError):aggregate_trades([trade(side='BUY')],mapping,{'AAA'})

def test_universe_counts_exclude_warrants_and_delisted_from_market_reference():
    meta=dict(sectors={'A':dict(sector='Ngành 1',icb_code='1'),'B':dict(sector='Ngành 2',icb_code='2')},listing={s:dict(type=t,exchange=e) for s,t,e in [('A','STOCK','HSX'),('B','STOCK','HNX'),('C','STOCK','UPCOM'),('D','CW','HSX'),('E','STOCK','DELISTED')]})
    result=universe_distribution(['A'],meta)
    by={g['icb_code']:g for g in result}
    assert by['1']['count']==1 and by['1']['sample_share_pct']==100
    assert by['2']['count']==0 and by['2']['market_count']==1
    assert sum(g['market_count'] for g in result)==3

def test_paper_attribution_reads_full_private_ledger_not_recent_public_sample(tmp_path):
    (tmp_path/'config').mkdir();(tmp_path/'state').mkdir()
    (tmp_path/'config/market-classification.json').write_text(json.dumps({'sectors':{'AAA':{'sector':'Ngành','icb_code':'1'}}}))
    (tmp_path/'config/research-universe.json').write_text(json.dumps({'eligible_symbols':['AAA']}))
    (tmp_path/'state/paper_state.json').write_text(json.dumps({'bots':{'Bot':{'trades':[trade() for _ in range(75)]}}}))
    public={'paper':{'Bot':{'trades':[trade() for _ in range(30)]}}}
    attach_paper_sectors(public,tmp_path)
    assert public['paper']['Bot']['sector_stats']['buy_fills']==75
    assert len(public['paper']['Bot']['trades'])==30
    public['paper_minute']={'Bot':{}}
    attach_paper_sectors(public,tmp_path,{'paper_minute':{'Bot':{'trades':[trade() for _ in range(76)]}}})
    assert public['paper_minute']['Bot']['sector_stats']['buy_fills']==76

def test_published_sector_ledgers_reconcile_all_33_complete_backtests():
    root=Path(__file__).resolve().parents[1]
    data=json.loads((root/'site/sectors.json').read_text(encoding='utf8'))
    research=json.loads((root/'site/research-146.json').read_text(encoding='utf8'))
    assert sum(g['count'] for g in data['universe'])==146
    assert len({s for g in data['universe'] for s in g['symbols']})==146
    metadata=json.loads((root/'config/market-classification.json').read_text(encoding='utf8'))
    assert data['classification_asof']==metadata['asof']
    for mode,key in [('backtest','backtests'),('backtest_minute','minute_backtests'),('hybrid','hybrid_backtests')]:
        assert len(data['books'][mode])==11
        for bot,stats in data['books'][mode].items():
            expected=research[key][bot]
            assert stats['buy_fills']==expected['buy_count']
            assert stats['sell_fills']==expected['closed_trades']
            assert stats['outside_146_fills']==0
            assert sum(g['buy_fills'] for g in stats['sectors'])==expected['buy_count']
            assert sum(g['sell_fills'] for g in stats['sectors'])==expected['closed_trades']
            if stats['buy_fills']:assert abs(sum(g['buy_share_pct'] for g in stats['sectors'])-100)<.2
    assert data['expansion']['full_expansion_audit_complete'] is False
    assert all(r['minute_full_history_verified'] is False for r in data['expansion']['probes'])
