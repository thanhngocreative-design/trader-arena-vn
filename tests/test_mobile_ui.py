"""Static mobile UI integrity checks; no browser/network access required."""
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import pytest

SITE = Path(__file__).resolve().parents[1] / "site" / "index.html"

def test_monthly300_controls_switch_all_historical_books_without_rewriting_paper(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js unavailable')
    html=SITE.read_text(encoding='utf8');js=re.search(r'<script>(.*?)</script>',html,re.S)[1].rsplit('boot();',1)[0]
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const elements={};global.document={getElementById:id=>elements[id]||=({innerHTML:'',style:{},classList:{toggle(){}}}),querySelectorAll:()=>[]};
global.localStorage={getItem:()=>null};global.location={search:''};global.window={scrollTo(){}};
'''+js+r'''
const root=process.argv[2];DATA=JSON.parse(fs.readFileSync(path.join(root,'dashboard.json'),'utf8'));
VALUE_DATA=JSON.parse(fs.readFileSync(path.join(root,'value-investing.json'),'utf8'));applyValueData();
VALUE_INTRADAY=JSON.parse(fs.readFileSync(path.join(root,'value-intraday.json'),'utf8'));applyValueIntraday();
PIT_DATA=JSON.parse(fs.readFileSync(path.join(root,'research-300.json'),'utf8'));IDS=Object.keys(DATA.traders);
render=()=>{};const originalPaper=JSON.stringify(DATA.paper);
for(const cohort of ['300','146']){
  setStudy(cohort);assert.equal(activeStudy(),cohort);assert.equal(historicalSource(),PIT_DATA.cohorts[cohort]);
  for(const [m,key] of [['backtest','backtests'],['backtest_minute','minute_backtests'],['hybrid','hybrid_backtests']]){
    mode=m;period='ALL';assert.equal(activeKeys().length,13);
    for(const bot of IDS)assert.equal(part(bot).return_pct,PIT_DATA.cohorts[cohort][key][bot].return_pct);
  }
  const six=comparisonBooks('Buffett');assert.equal(six.length,6);
  assert.equal(six.find(b=>b.id==='backtest').data,PIT_DATA.cohorts[cohort].backtests.Buffett);
  assert.equal(six.find(b=>b.id==='paper').data,DATA.paper.Buffett);
}
assert.equal(JSON.stringify(DATA.paper),originalPaper);
setStudy('legacy');mode='backtest';assert.equal(part('Minervini'),DATA.backtest_periods.ALL.Minervini);
setStudy('300');studyMonth='2023-11';assert.ok(studyPicker().includes('SJF'));
assert.ok(studyPicker().includes('2023-10-31'));assert.equal(PIT_DATA.months[0].members.length,300);
SECTOR_DATA=JSON.parse(fs.readFileSync(path.join(root,'sectors.json'),'utf8'));sectorMode='hybrid';sectorBot='Munger';renderSectors();
assert.ok(elements.sectorContent.innerHTML.includes('Độ phủ mẫu 300 mã'));
assert.equal(sectorBookStats('hybrid','Munger').buy_fills,PIT_DATA.cohorts['300'].hybrid_backtests.Munger.buy_count);
stockStudy=true;stockSymbol='SJF';PIT_STOCKS.SJF=JSON.parse(fs.readFileSync(path.join(root,'pit-stocks/SJF.json'),'utf8'));
assert.equal(stockBars().at(-1)[0],'2023-11-10');
REPLAY_DATA=JSON.parse(fs.readFileSync(path.join(root,'paper-replay.json'),'utf8'));applyReplayData();
for(const modeId of ['paper','paper_minute','paper_combo']){
  mode=modeId;assert.equal(activeKeys().length,13);
  for(const bot of IDS)assert.equal(part(bot),REPLAY_DATA[modeId][bot]);
}
const replayBooks=JSON.stringify(DATA.paper);
applyValueData();applyValueIntraday();assert.equal(JSON.stringify(DATA.paper),replayBooks);
assert.equal(REPLAY_DATA.execution_revision,'strict_next_candle_v1');
assert.ok(renderBookComparison('Buffett').includes('cùng quy tắc khớp nến kế tiếp'));
'''
    p=tmp_path/'pit-ui.cjs';p.write_text(script,encoding='utf8')
    result=subprocess.run([node,str(p),str(SITE.parent)],capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr

def test_all_six_value_profiles_route_to_independent_real_ledgers(tmp_path):
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
VALUE_INTRADAY=JSON.parse(fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[2]),'value-intraday.json'),'utf8'));applyValueIntraday();
assert.equal(IDS.length,13);mode='backtest_minute';
assert.equal(activeKeys().length,13);assert.equal(part('Buffett').return_pct,VALUE_DATA.minute_backtests.Buffett.return_pct);
const originalRender=render;render=()=>{};selectProfile('Buffett');assert.equal(mode,'backtest_minute');assert.equal(selected,'Buffett');
renderBots();assert.ok(elements.botDetail.innerHTML.includes('113/146'));
assert.equal(comparisonBooks('Buffett').filter(b=>b.data).length,6);
assert.ok(!elements.botDetail.innerHTML.includes('Không áp dụng'));
setMode('paper_minute');assert.equal(selected,'Buffett');assert.equal(activeKeys().length,13);
selectProfile('Munger');assert.equal(mode,'paper_minute');assert.equal(part('Munger').nav,VALUE_INTRADAY.paper_minute.Munger.nav);
for(const p of ['3M','6M','1Y','2Y','ALL']){period=p;mode='backtest';assert.equal(part('Munger').return_pct,VALUE_DATA.backtest_periods[p].Munger.return_pct);}
for(const m of ['paper_minute','paper','paper_combo','backtest_minute','backtest','hybrid']){
  mode=m;assert.equal(activeKeys().length,13);assert.ok(part('Buffett'));assert.ok(part('Munger'));
}
// A missing ledger is absent, never silently replaced by zero or daily returns.
mode='paper_minute';delete DATA.paper_minute.Munger;assert.equal(activeKeys().length,12);
renderBots();assert.ok(elements.botDetail.innerHTML.includes('Chưa tải được sổ này'));
applyValueIntraday();assert.equal(activeKeys().length,13);
// Replacing the base daily payload must retain all six overlay sources.
DATA=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));applyValueData();assert.ok(DATA.paper.Buffett&&DATA.paper_minute.Buffett);
SECTOR_DATA=JSON.parse(fs.readFileSync(process.argv[4],'utf8'));
for(const m of ['backtest_minute','backtest','hybrid','paper_minute','paper','paper_combo']){
  sectorMode=m;sectorBot='ALL';renderSectors();assert.ok(elements.sectorContent.innerHTML.includes('Tất cả 13 bot'));
}
assert.equal(sectorBookStats('backtest_minute','Buffett').buy_fills,VALUE_DATA.minute_backtests.Buffett.buy_count);
assert.equal(sectorBookStats('hybrid','Munger').buy_fills,VALUE_DATA.hybrid_backtests.Munger.buy_count);
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
    script="const historicalSource=()=>DATA,activeStudy=()=> 'legacy',studyPicker=()=>'',studyLabel=()=> '146 mã cũ';\n"+functions+'''
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
    script="const historicalSource=()=>DATA,activeStudy=()=> 'legacy',studyPicker=()=>'',studyLabel=()=> '146 mã cũ';\n"+functions+'''
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
