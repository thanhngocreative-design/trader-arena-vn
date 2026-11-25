"""Exclude explicitly verified exchange closures; missing data is not a holiday."""
import json
from datetime import date
from pathlib import Path
import pandas as pd

CONFIG = Path(__file__).resolve().parent / 'config/market-closures.json'


def closed_dates(path=CONFIG):
    config = json.loads(path.read_text(encoding='utf8'))
    if config.get('revision') != 'verified_exchange_closures_v1':
        raise ValueError('Unsupported exchange calendar')
    result = set()
    for row in config['closures']:
        day = row['date']
        if date.fromisoformat(day).isoformat() != day or not row.get('reason') or not row.get('sources'):
            raise ValueError('Unverified exchange closure')
        if day in result:
            raise ValueError('Duplicate exchange closure')
        result.add(day)
    return result


def session_candidates(start, end):
    calendar = pd.bdate_range(start, end)
    closures = closed_dates()
    return calendar[~calendar.strftime('%Y-%m-%d').isin(closures)]
