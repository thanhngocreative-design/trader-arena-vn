"""Run dependent baskets through the session actually banked by monthly300.

The wall-clock cutoff can be ahead of the provider (or fall on a holiday).
Never request unbanked inputs or turn that cutoff into a fictional session.
Simulation engines and their immutable-ledger checks remain unchanged.
"""
import argparse
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

VN = ZoneInfo('Asia/Ho_Chi_Minh')
ROOT = Path(__file__).resolve().parent


def confirmed_clock(payload, market, now):
    from paper_replay import completed_date
    end = payload.get('last_session')
    if payload.get('status') != 'completed_session_replay' or not isinstance(end, str):
        raise ValueError('Monthly collector has no verified completed session')
    day = datetime.strptime(end, '%Y-%m-%d').date()
    if day.isoformat() != end or day.weekday() >= 5 or end > completed_date(now):
        raise ValueError('Invalid confirmed Paper cutoff')
    if not payload.get('sessions') or payload['sessions'][-1] != end:
        raise ValueError('Monthly session calendar disagrees')
    for folder in ('sessions', 'candidate-days'):
        if not (market / folder / (end + '.json.gz')).is_file():
            raise ValueError('Confirmed session has not been banked: ' + end)
    return datetime.combine(day, time(16), tzinfo=VN)


def run_stage(stage, now=None):
    import importlib
    from value_investing import read, write
    now = now or datetime.now(VN)
    monthly = read(ROOT / 'site/paper-replay.json')
    clock = confirmed_clock(monthly, ROOT / 'state/replay_market', now)
    module = importlib.import_module({'fixed146': 'paper_fixed146', 'vn30': 'paper_vn30'}[stage])
    result = module.run(now=clock)
    if result['last_session'] != monthly['last_session']:
        raise ValueError('Dependent basket disagrees with banked session')
    # The simulation clock is its source boundary; publication time is real.
    result['updated_at'] = now.isoformat()
    write(module.PUBLIC, result)
    print('Verified shared Paper cutoff', stage, result['last_session'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('fixed146', 'vn30'))
    run_stage(parser.parse_args().stage)
