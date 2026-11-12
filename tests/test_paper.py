from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
from test_engine import data
from paper_forward import update_paper


def test_paper_first_run_is_empty_then_idempotent():
    prices,index=data(420)
    with TemporaryDirectory() as root:
        state_path=Path(root)/'state.json'
        initial, changed=update_paper({'FPT': prices.iloc[:330]},index.iloc[:330],state_path)
        assert changed
        assert initial['bots']['Minervini']['cash']==100_000_000
        assert initial['bots']['Minervini']['trades']==[]
        assert all(not b['positions'] for b in initial['bots'].values())
        duplicate, changed=update_paper({'FPT': prices.iloc[:330]},index.iloc[:330],state_path)
        assert not changed
        assert duplicate==initial
        next_day, changed=update_paper({'FPT': prices.iloc[:331]},index.iloc[:331],state_path)
        assert changed
        assert len(next_day['bots']['Minervini']['history'])==2


def test_missed_days_never_fabricate_fills():
    prices,index=data(420)
    with TemporaryDirectory() as root:
        path=Path(root)/'state.json'
        update_paper({'FPT':prices.iloc[:330]},index.iloc[:330],path)
        s,changed=update_paper({'FPT':prices.iloc[:336]},index.iloc[:336],path)
        assert changed
        assert any('Bỏ lỡ' in w for w in s['warnings'])
        assert s['bots']['Minervini']['trades']==[]


def test_new_season_prepares_only_before_start_and_records_history_on_start(tmp_path):
    import json
    from engine import Settings,TRADERS
    from paper_forward import _base_bot,RULES_REVISION
    prices,index=data(420)
    path=tmp_path/'season.json'
    start=str(index.index[330].date())
    path.write_text(json.dumps(dict(version=1,started_at=start+'T00:00:00+07:00',contest_start_session=start,last_session=None,bots={k:_base_bot(Settings()) for k in TRADERS},warnings=[],rules_revision=RULES_REVISION)))
    before,_=update_paper({'FPT':prices.iloc[:330]},index.iloc[:330],path)
    for b in before['bots'].values():
        assert b['cash']==100_000_000
        assert not b['positions'] and not b['trades'] and not b['history']
        assert b['latest']['nav']==100_000_000
    again,_=update_paper({'FPT':prices.iloc[:330]},index.iloc[:330],path)
    assert all(not b['history'] for b in again['bots'].values())
    on_start,_=update_paper({'FPT':prices.iloc[:331]},index.iloc[:331],path)
    assert all([x['date'] for x in b['history']]==[start] for b in on_start['bots'].values())
    assert all(all(t['date']>=start for t in b['trades']) for b in on_start['bots'].values())
