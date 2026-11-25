import json
import pandas as pd
import pytest
from market_calendar import session_candidates, closed_dates


def test_official_holiday_between_real_sessions_does_not_require_a_fake_candle():
    days = session_candidates('2026-11-20', '2026-11-26').strftime('%Y-%m-%d').tolist()
    assert days == ['2026-11-20', '2026-11-23', '2026-11-25', '2026-11-26']
    # Dates without an explicit closure remain candidates, even without a bank file.
    assert '2026-11-26' in days
    pd.testing.assert_index_equal(session_candidates('2026-11-02', '2026-11-23'),
                                  pd.bdate_range('2026-11-02', '2026-11-23'))


def test_calendar_requires_evidence_and_refuses_duplicate_dates(tmp_path):
    path = tmp_path / 'calendar.json'
    row = dict(date='2026-11-24', reason='test-only calendar fixture', sources=['https://example.test/notice'])
    for rows in ([dict(row, sources=[])], [row, row]):
        path.write_text(json.dumps(dict(revision='verified_exchange_closures_v1', closures=rows)))
        with pytest.raises(ValueError):
            closed_dates(path)


def test_calendar_upgrade_keeps_state_guards_and_rejects_published_session_removal(tmp_path, monkeypatch):
    import hashlib
    from ops import upgrade_market_calendar as upgrade
    from value_investing import write, read
    state = tmp_path / 'state'
    state.mkdir()
    (tmp_path / 'config').mkdir()
    (tmp_path / 'site').mkdir()
    protected = tmp_path / 'strategy.py'
    protected.write_bytes(b'unchanged strategy fixture')
    spec = dict(previous_model_sha256='old', new_model_sha256='new', scope='calendar only',
                unchanged_source_sha256={'strategy.py': hashlib.sha256(protected.read_bytes()).hexdigest()})
    write(tmp_path / 'config/market-calendar-compat-v1.json', spec)
    saved = dict(model_sha256='old', calendar=['2026-11-23'], memberships={},
                 last_session='2026-11-23', checkpoint_sha256={'checkpoint': 'retained-hash'})
    write(state / 'manifest.json', saved)
    write(tmp_path / 'site/backtest-status.json', dict(model_sha256='old', end='2026-11-23'))
    monkeypatch.setattr(upgrade, 'ROOT', tmp_path)
    monkeypatch.setattr(upgrade, 'STATE', state)
    monkeypatch.setattr(upgrade, 'model_digest', lambda: 'unreviewed')
    with pytest.raises(ValueError, match='Unreviewed'):
        upgrade.run()
    monkeypatch.setattr(upgrade, 'model_digest', lambda: 'new')
    monkeypatch.setattr(upgrade, 'closed_dates', lambda: {'2026-11-23'})
    with pytest.raises(ValueError, match='published trading session'):
        upgrade.run()
    monkeypatch.setattr(upgrade, 'closed_dates', lambda: {'2026-11-24'})
    protected.write_bytes(b'changed strategy fixture')
    with pytest.raises(ValueError, match='Trading source changed'):
        upgrade.run()
    protected.write_bytes(b'unchanged strategy fixture')
    calls = []
    monkeypatch.setattr(upgrade, 'verify_manifest', lambda *a, **kw: calls.append(kw))
    upgrade.run()
    after = read(state / 'manifest.json')
    assert after == {**saved, 'model_sha256': 'new'}
    assert calls == [{'model': 'old'}]
    assert read(state / 'migrations/market-calendar-v1.json')['checkpoint_sha256'] == saved['checkpoint_sha256']
