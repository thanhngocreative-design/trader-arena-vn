import json
from pathlib import Path
from engine import TRADERS
from bot_timeframes import timeframe_manifest

def test_timeframe_categories_follow_the_active_engine_mode():
    frames=timeframe_manifest()
    for mode,description in frames.items():
        assert set(description['bots'])==set(TRADERS)
        assert sum(description['counts'].values())==11
        if mode in ('paper_minute','backtest_minute'):
            assert description['counts']['minute_only']==11
        elif mode=='paper_combo':
            assert description['counts']['daily_and_minute']==11
        elif mode=='hybrid':
            assert description['counts']['daily_and_minute']==11
            for name in ('BNF','CIS'):
                assert description['bots'][name]['category']=='daily_and_minute'
                assert description['bots'][name]['priority']=='phút'
                assert 'ngày hôm trước' in description['bots'][name]['detail']
        else:
            assert description['counts']['daily_only']==11
            assert all(b['category']=='daily_only' for b in description['bots'].values())

def test_published_timeframes_and_ui_have_mode_specific_labels():
    root=Path(__file__).resolve().parents[1]
    for name in ('dashboard.json','research-146.json'):
        data=json.loads((root/'site'/name).read_text(encoding='utf8'))
        assert data['bot_timeframes']==timeframe_manifest()
    ui=(root/'site/index.html').read_text(encoding='utf8')
    assert 'function botFrame(k)' in ui
    assert 'DATA.bot_timeframes?.[mode]' in ui
    assert 'botTimeframeOverview' not in ui
    assert 'Khung giao dịch của bot' not in ui
    assert 'frameBadge(selected)' in ui and 'frameBadge(k)' in ui
