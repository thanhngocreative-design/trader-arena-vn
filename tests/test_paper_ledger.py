"""Temporary schema fixtures are never published as market data."""
from copy import deepcopy
import pandas as pd
import pytest
from paper_ledger import preserve_trade_prefix


def records(rows):
    df=pd.DataFrame(rows)
    return df.astype(object).where(df.notna(),None).to_dict('records')


def test_first_sale_adds_nullable_columns_without_rewriting_prior_buys():
    buy=dict(date='2026-11-04',side='MUA',symbol='TEST',qty=100,price=20000,pnl=None,signal_date='2026-11-03')
    sale=dict(date='2026-11-19',side='BÁN',symbol='TEST',qty=100,price=21000,pnl=90000,buy_date='2026-11-04')
    previous=records([buy]);original=deepcopy(previous);current=records([buy,sale]);alias=current
    assert current[0]!=previous[0] and current[0]['buy_date'] is None
    result=preserve_trade_prefix(previous,current,'2026-11-18',label='combo:TEST')
    assert result is alias and current[0]==previous[0] and previous==original
    assert current[1]['buy_date']=='2026-11-04' and current[1]['pnl']==90000
    assert 'buy_date' not in current[0]
    assert preserve_trade_prefix(previous,current,'2026-11-18',label='combo:TEST')==result


@pytest.mark.parametrize('field,value',[('price',20001),('qty',200),('symbol','OTHER'),('side','BÁN'),('signal_date','2026-11-02'),('pnl',0),('reason','changed')])
def test_substantive_trade_changes_still_stop_publication(field,value):
    old=[dict(date='2026-11-04',symbol='TEST',side='MUA',qty=100,price=20000,pnl=None,signal_date='2026-11-03')]
    current=deepcopy(old);current[0][field]=value
    with pytest.raises(ValueError,match='refuse rewrite'):
        preserve_trade_prefix(old,current,'2026-11-18',label='test')


def test_missing_extra_and_reordered_history_remain_errors():
    old=[dict(date='2026-11-04',qty=100),dict(date='2026-11-05',qty=200)]
    for current in [old[:1],old+[dict(date='2026-11-06',qty=100)],list(reversed(old))]:
        with pytest.raises(ValueError):preserve_trade_prefix(old,current,'2026-11-18',label='test')
