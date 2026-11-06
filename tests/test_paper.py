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
