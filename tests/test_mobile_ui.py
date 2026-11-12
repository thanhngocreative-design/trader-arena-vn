"""Static mobile UI integrity checks; no browser/network access required."""
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import pytest

SITE = Path(__file__).resolve().parents[1] / "site" / "index.html"


def test_mobile_ui_controls_exist():
    html = SITE.read_text(encoding="utf-8")
    for item in ["backtestTimePicker", "backtestPeriods", "stockOverlay", "stockGraph",
                 "stockShortcuts", "toggleBot", "renderStock", "regionChips"]:
        assert item in html, f"missing UI: {item}"
    assert "localStorage" in html  # client-only tracking toggles
    assert "actions/workflows/bot-control.yml" in html  # path to authenticated cloud pause




def test_leaderboard_card_expands_inline_without_tab_navigation():
    html = SITE.read_text(encoding="utf-8")
    assert 'onclick="selectRankBot(' in html
    assert 'aria-expanded="${expandedBot===k}"' in html
    assert 'rankdetail-panel' in html
    assert 'function selectRankBot(id)' in html
    handler = html.split("function selectRankBot(id){", 1)[1].split("function openBotProfile(", 1)[0]
    assert "setPage(" not in handler
    assert "renderHome();" in handler
    assert "expandedBot===id?null:id" in handler
    assert "Xem hồ sơ đầy đủ" in html

def test_onsite_javascript_parses_under_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed on this machine")
    html=SITE.read_text(encoding="utf-8")
    scripts=re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S)
    assert len(scripts)==1
    with TemporaryDirectory() as root:
        p=Path(root)/"app.js"
        p.write_text(scripts[0],encoding="utf-8")
        result=subprocess.run([node,"--check",str(p)],capture_output=True,text=True)
        assert result.returncode==0, result.stderr

def test_failed_market_fetch_has_no_fabricated_fallback():
    html=SITE.read_text(encoding='utf-8')
    assert 'mkDemo' not in html and 'const DEMO=' not in html
    assert 'Không tải được dữ liệu thị trường thật' in html
