"""Static mobile UI integrity checks; no browser/network access required."""
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import pytest

SITE = Path(__file__).resolve().parents[1] / "site" / "index.html"

def test_daily_only_value_profiles_route_without_fake_minute_results(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js unavailable')
    html=SITE.read_text(encoding='utf8');js=re.search(r'<script>(.*?)</script>',html,re.S)[1]
    js=js.rsplit('boot();',1)[0]
    check=r'''
const assert=require('node:assert/strict'),fs=require('node:fs');
const elements={};global.document={getElementById:id=>elements[id]||=({innerHTML:'',style:{},classList:{toggle(){}}}),querySelectorAll:()=>[]};
global.localStorage={getItem:()=>null};global.location={search:''};global.window={scrollTo(){}};
'''+js+r'''
DATA=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const intraday=JSON.parse(fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[2]),'paper-intraday.json'),'utf8'));
DATA.paper_minute=intraday.paper_minute;DATA.paper_combo=intraday.paper_combo;
VALUE_DATA=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));applyValueData();IDS=Object.keys(DATA.traders);
assert.equal(IDS.length,13);mode='backtest_minute';
assert.equal(activeKeys().length,11);assert.equal(part('Buffett'),undefined);
const originalRender=render;render=()=>{};selectProfile('Buffett');assert.equal(mode,'backtest');assert.equal(selected,'Buffett');
assert.equal(activeKeys().length,13);assert.equal(part('Buffett').return_pct,VALUE_DATA.backtests.Buffett.return_pct);
renderBots();assert.ok(elements.botDetail.innerHTML.includes('Không áp dụng — bot dài hạn chỉ theo ngày'));
assert.ok(elements.botDetail.innerHTML.includes('113/146'));
setMode('paper_minute');assert.notEqual(selected,'Buffett');assert.equal(activeKeys().length,11);
selectProfile('Munger');assert.equal(mode,'paper');assert.equal(part('Munger').nav,100000000);
assert.equal(comparisonBooks('Munger').filter(b=>b.data).length,2);
for(const p of ['3M','6M','1Y','2Y','ALL']){period=p;mode='backtest';assert.equal(part('Munger').return_pct,VALUE_DATA.backtest_periods[p].Munger.return_pct);}
// Replacing the base daily payload must not discard long-term books.
DATA=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));applyValueData();assert.ok(DATA.paper.Buffett);
SECTOR_DATA=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
sectorMode='backtest_minute';sectorBot='ALL';renderSectors();assert.ok(elements.sectorContent.innerHTML.includes('Tất cả 11 bot'));
sectorMode='backtest';renderSectors();assert.ok(elements.sectorContent.innerHTML.includes('Tất cả 13 bot'));
assert.equal(sectorBookStats('backtest','Buffett').buy_fills,VALUE_DATA.backtests.Buffett.buy_count);
'''
    path=tmp_path/'value-ui.cjs';path.write_text(check,encoding='utf8')
    result=subprocess.run([node,str(path),str(SITE.parent/'dashboard.json'),str(SITE.parent/'value-investing.json'),str(SITE.parent/'sectors.json')],capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr


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


def test_sector_filters_use_buy_turnover_and_distinguish_missing_from_empty(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js unavailable')
    html=SITE.read_text(encoding='utf8')
    functions='function sectorBookStats'+html.split('function sectorBookStats',1)[1].split('function render(){',1)[0]
    script=functions+'''
const assert=require('node:assert/strict');
const stats={outside_146_fills:0,buy_fills:4,buy_value:100,sectors:[{icb_code:'A',sector:'Ngành A',buy_fills:3,sell_fills:8,buy_value:30,realized_pnl:-10,symbols:['AAA']},{icb_code:'B',sector:'Ngành B',buy_fills:1,sell_fills:0,buy_value:70,realized_pnl:0,symbols:['BBB']}]};
let sectorMode='backtest_minute',sectorMetric='value',sectorBot='ALL',sectorRefreshError='';
const DATA={paper_contest_start:'2026-11-13',paper:{Bot:{sector_stats:{buy_fills:0,sectors:[]}}}},IDS=['Bot'],SHORT={Bot:'Bot'},MODE_LABEL={backtest_minute:'Phút',backtest:'Ngày',hybrid:'Kết hợp',paper:'Paper ngày',paper_minute:'Paper phút',paper_combo:'Paper kết hợp'};
const SECTOR_DATA={universe_count:146,icb_level:2,classification_asof:'2026-11-13',market_count:1518,universe:[{count:146,market_count:1518,sector:'Ngành A',sample_share_pct:100,market_share_pct:100,symbols:['AAA']}],period:{start:'2023-11-13',end:'2026-11-12'},books:{backtest_minute:{Bot:stats}}};
const target={innerHTML:''},$=()=>target,safe=x=>String(x??''),n=x=>Number(x||0),money=String,color=x=>x>=0?'green':'red';
const combined=combineSectorStats([stats,stats]);assert.equal(combined.buy_value,200);assert.equal(combined.buy_fills,8);
assert.equal(sectorRank(combined)[0].sector,'Ngành B');
sectorMetric='count';assert.equal(sectorRank(combined)[0].sector,'Ngành A');assert.equal(sectorShare(sectorRank(combined)[0]),75);
renderSectors();assert.ok(target.innerHTML.includes('4 lần mua'));
sectorMode='paper';renderSectors();assert.ok(target.innerHTML.includes('Chưa có lệnh mua đã khớp'));
delete DATA.paper.Bot.sector_stats;renderSectors();assert.ok(target.innerHTML.includes('Chưa đủ sổ giao dịch'));
'''
    path=tmp_path/'sector.cjs';path.write_text(script,encoding='utf8')
    result=subprocess.run([node,str(path)],capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr
