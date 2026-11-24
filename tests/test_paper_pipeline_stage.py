from datetime import datetime
import pytest
from paper_pipeline_stage import confirmed_clock, VN


def test_dependent_baskets_use_confirmed_session_not_stale_provider_wall_clock(tmp_path):
    p = dict(status='completed_session_replay', last_session='2026-11-23', sessions=['2026-11-23'])
    now = datetime(2026, 11, 24, 22, tzinfo=VN)
    for folder in ('sessions', 'candidate-days'):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / '2026-11-23.json.gz').touch()
    assert confirmed_clock(p, tmp_path, now) == datetime(2026, 11, 23, 16, tzinfo=VN)
    for bad in [dict(p, status='waiting'), dict(p, last_session='2026-11-25'),
                dict(p, last_session='2026-11-22'), dict(p, sessions=[]), dict(p, last_session=None)]:
        with pytest.raises(ValueError):
            confirmed_clock(bad, tmp_path, now)
    (tmp_path / 'sessions/2026-11-23.json.gz').unlink()
    with pytest.raises(ValueError, match='not been banked'):
        confirmed_clock(p, tmp_path, now)
