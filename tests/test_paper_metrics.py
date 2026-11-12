from paper_metrics import paper_metrics


def test_complete_ledger_counts_and_drawdown_survive_display_truncation():
    trades=[dict(side='MUA') for _ in range(60)]+[dict(side='BÁN',pnl=1 if i%2 else -1) for i in range(40)]
    history=[dict(nav=100_000_000),dict(nav=50_000_000)]+[dict(nav=110_000_000)]*200
    m=paper_metrics(trades,history,105_000_000)
    assert m['buy_count']==60 and m['closed_trades']==40
    assert m['win_rate']==50 and m['max_drawdown_pct']==-50
    assert m['observed_history_points']==202


def test_unstarted_paper_has_no_invented_drawdown_or_win_rate():
    m=paper_metrics([],[],100_000_000)
    assert m['buy_count']==m['closed_trades']==0
    assert m['max_drawdown_pct'] is None and m['win_rate'] is None
    assert paper_metrics([],[dict(nav=99_000_000)],98_000_000)['max_drawdown_pct']==-2
