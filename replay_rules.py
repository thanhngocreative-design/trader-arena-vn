"""Execution clock shared by historical runs and end-of-day paper replay."""
import pandas as pd

REVISION = 'strict_next_candle_v1'


def continuous_minute(value):
    ts = pd.Timestamp(value)
    minute = ts.hour * 60 + ts.minute
    return ts.weekday() < 5 and ts.second == 0 and ts.microsecond == 0 and (
        555 <= minute < 690 or 780 <= minute < 870)


def next_minute(value):
    ts = pd.Timestamp(value)
    nxt = ts + pd.Timedelta(minutes=1)
    return nxt if continuous_minute(ts) and continuous_minute(nxt) else None


def can_fill(signal, fill, submitted=None):
    expected = next_minute(signal)
    return expected is not None and pd.Timestamp(fill) == expected and (
        submitted is None or pd.Timestamp(submitted) <= expected)
