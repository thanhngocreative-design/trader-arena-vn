from datetime import datetime
import pytest
from historical_minute import VN
import vn30_current as m


def test_current_check_is_banked_once_and_never_backfills_unknown_history(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'CHECKS',tmp_path)
    members=['X'+str(i) for i in range(30)]
    cfg=dict(verified_through='2026-11-13',months=[dict(effective='2026-08-03',members=members)])
    now=datetime(2026,11,16,17,tzinfo=VN);calls=[]
    def fetch():calls.append(1);return members
    assert m.verify_current(cfg,'2026-11-16',now=now,fetch=fetch)=='2026-11-16'
    m.verify_current(cfg,'2026-11-16',now=now,fetch=fetch)
    assert calls==[1]
    with pytest.raises(ValueError,match='historical VN30'):
        m.verify_current(cfg,'2026-11-17',now=datetime(2026,11,18,17,tzinfo=VN),fetch=fetch)
    with pytest.raises(ValueError,match='VN30 changed'):
        m.verify_current(cfg,'2026-11-18',now=datetime(2026,11,18,17,tzinfo=VN),fetch=lambda:members[:-1]+['DIFFERENT'])
