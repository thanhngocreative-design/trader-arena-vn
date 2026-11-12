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


def test_six_book_comparison_uses_distinct_sources_and_handles_missing_data(tmp_path):
    node=shutil.which('node')
    if not node: pytest.skip('Node.js unavailable')
    html=SITE.read_text(encoding='utf8')
    functions='function comparisonBooks'+html.split('function comparisonBooks',1)[1].split('function renderBots()',1)[0]
    script=functions+'''
const assert=require('node:assert/strict');
const value=n=>({nav:n,return_pct:n-100,buy_count:n,closed_trades:0,max_drawdown_pct:null,history:[]});
const DATA={capital_each:100,paper_minute:{Bot:value(101)},paper:{Bot:value(102)},paper_combo:{Bot:value(103)},minute_backtests:{Bot:value(104)},backtests:{Bot:value(105)},hybrid_backtests:{Bot:value(106)},backtest_periods:{'3M':{Bot:value(999)}}};
const SHORT={Bot:'Test Bot'},safe=x=>String(x??''),n=x=>Number(x||0),money=String,pct=x=>x+'%',color=x=>x>=0?'green':'red';
let mode='paper',period='3M';const setMode=m=>mode=m;
assert.deepEqual(comparisonBooks('Bot').map(b=>b.data.nav),[101,102,103,104,105,106]);
assert.equal(comparisonMetric(DATA.paper.Bot).profit,2);
assert.equal(comparisonMetric(DATA.paper.Bot).dd,null);
assert.equal((renderBookComparison('Bot').match(/data-book=/g)||[]).length,6);
openComparisonBook('backtest');assert.equal(period,'ALL');assert.equal(mode,'backtest');
delete DATA.minute_backtests.Bot;
assert.equal(comparisonMetric(comparisonBooks('Bot')[3].data).nav,null);
assert.ok(renderBookComparison('Bot').includes('Chưa có dữ liệu'));
delete DATA.capital_each;assert.equal(comparisonMetric(DATA.paper.Bot).profit,null);
'''
    path=tmp_path/'comparison.cjs';path.write_text(script,encoding='utf8')
    result=subprocess.run([node,str(path)],capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr
