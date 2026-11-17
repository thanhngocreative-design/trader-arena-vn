"""Publish small operational metadata from verified Paper outputs, never prices."""
import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = {'300': 'paper-replay.json', '146': 'paper-fixed146.json', 'vn30': 'paper-vn30.json'}
MODES = ('paper', 'paper_minute', 'paper_combo')


def build_status(payloads, bot_ids):
    expected = set(bot_ids)
    ends = set()
    baskets = {}
    for key, p in payloads.items():
        end = p.get('last_session')
        if p.get('status') != 'completed_session_replay' or not isinstance(end, str):
            raise ValueError('Paper is not complete: ' + key)
        date.fromisoformat(end)
        if not p.get('sessions') or p['sessions'][-1] != end:
            raise ValueError('Paper session calendar is incomplete: ' + key)
        for mode in MODES:
            if set(p.get(mode, {})) != expected:
                raise ValueError('Paper bot set is incomplete: ' + key + ':' + mode)
            for b in p[mode].values():
                history = b.get('history') or []
                if not history or history[-1].get('date') != end:
                    raise ValueError('Paper NAV is not current: ' + key + ':' + mode)
                for value in (b.get('nav'), history[-1].get('nav')):
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                        raise ValueError('Invalid observed NAV')
        ends.add(end)
        baskets[key] = {'end': end, 'sessions': len(p['sessions']), 'accounts': len(expected) * len(MODES)}
    if set(payloads) != set(FILES) or len(ends) != 1 or not expected:
        raise ValueError('All three Paper universes must finish together')
    return {'revision': 'replay_health_v1', 'status': 'complete', 'end': ends.pop(),
            'bot_ids': sorted(expected), 'accounts': len(expected) * len(MODES) * len(FILES), 'baskets': baskets}


def main():
    from engine import TRADERS
    from value_investing import POLICY
    payloads = {key: json.loads((ROOT / 'site' / name).read_text(encoding='utf8')) for key, name in FILES.items()}
    result = build_status(payloads, list(TRADERS) + list(POLICY))
    target = ROOT / 'site/replay-status.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, separators=(',', ':'), allow_nan=False), encoding='utf8')
    temporary.replace(target)
    print('Verified Paper health', result['end'], result['accounts'], 'accounts')


if __name__ == '__main__':
    main()
