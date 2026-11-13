"""Temporary fixtures only; no generated market data is published."""
import pytest
from paper_fixed146 import verify_previous,verify_inputs

def test_source_hash_paths_are_portable_and_still_detect_mutation(tmp_path):
    import hashlib
    folder=tmp_path/'candidate-days';folder.mkdir();file=folder/'day.gz';file.write_bytes(b'unit-test-only')
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    verify_inputs({'candidate-days\\day.gz':digest},tmp_path)
    verify_inputs({'candidate-days/day.gz':digest},tmp_path)
    file.write_bytes(b'changed fixture')
    with pytest.raises(ValueError,match='Frozen fixed146'):verify_inputs({'candidate-days/day.gz':digest},tmp_path)
    with pytest.raises(ValueError,match='Invalid frozen'):verify_inputs({'../day.gz':digest},tmp_path)

def test_fixed146_ledger_prefix_is_immutable_and_separate():
    old={'paper:A':[{'date':'2026-11-13','symbol':'FPT','qty':100}]}
    previous=dict(last_session='2026-11-13',ledgers=old)
    new={'paper:A':old['paper:A']+[{'date':'2026-11-16','symbol':'FPT','qty':100}]}
    verify_previous(previous,new)
    assert len(old['paper:A'])==1
    changed={'paper:A':[{'date':'2026-11-13','symbol':'FPT','qty':200}]}
    with pytest.raises(ValueError,match='Prior fixed146'):verify_previous(previous,changed)

def test_fixed146_does_not_enable_experimental_waiting_policy():
    import inspect,paper_fixed146
    source=inspect.getsource(paper_fixed146)
    assert 'waiting_execution' not in source
    assert paper_fixed146.REVISION=='strict_next_candle_v1'
    assert paper_fixed146.STATE.name=='paper_fixed146.json'
