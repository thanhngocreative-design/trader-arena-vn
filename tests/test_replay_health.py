"""Operational freshness checks read real outputs without generating market data."""
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from engine import TRADERS
from value_investing import POLICY
from replay_health import FILES, build_status

ROOT = Path(__file__).resolve().parents[1]


def payloads():
    return {k: json.loads((ROOT / 'site' / name).read_text(encoding='utf8')) for k, name in FILES.items()}


def test_health_covers_all_observed_accounts_without_rewriting_results():
    books = payloads()
    before = copy.deepcopy(books)
    status = build_status(books, list(TRADERS) + list(POLICY))
    assert status['accounts'] == 9 * (len(TRADERS) + len(POLICY))
    assert status['end'] == books['300']['last_session']
    assert books == before


@pytest.mark.parametrize('case', ['missing_bot', 'missing_basket', 'stale_history', 'bad_nav', 'incomplete'])
def test_health_refuses_partial_or_invalid_outputs(case):
    books = payloads()
    if case == 'missing_bot':
        del books['vn30']['paper']['Darvas']
    elif case == 'missing_basket':
        del books['146']
    elif case == 'stale_history':
        books['146']['paper']['Darvas']['history'].pop()
    elif case == 'bad_nav':
        books['300']['paper']['Darvas']['nav'] = float('nan')
    else:
        books['vn30']['status'] = 'waiting_completed_session'
    with pytest.raises(ValueError):
        build_status(books, list(TRADERS) + list(POLICY))


def test_cloud_watchdog_decisions_and_authenticated_dispatch_contract():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    result = subprocess.run([node, '--test', str(ROOT / 'ops/cloud-watchdog/worker.test.mjs')],
                            capture_output=True, text=True, encoding='utf8')
    assert result.returncode == 0, result.stdout + result.stderr
