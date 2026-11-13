"""Static mobile UI integrity checks; no browser/network access required."""
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import pytest

SITE = Path(__file__).resolve().parents[1] / "site" / "index.html"

def test_expanded_bot_chart_uses_its_own_book_and_real_recorded_nav(tmp_path):
    """Temporary account metrics only; no synthetic market output is published."""
    node=shutil.which('node')
    if not node:pytest.skip('Node.js unavailable')
    html=SITE.read_text(encoding='utf8')
    assert 'id="mainChart"' not in html
    functions='function botChartData'+html.split('function botChartData',1)[1].split('function rankExtra(',1)[0]
    script=r'''
const assert=require('node:assert/strict');
let mode='backtest',period='ALL',selected='A';
const DATA={capital_each:100000000,backtest_options:[{key:'ALL',label:'3 years'}]},SHORT={A:'Alpha',B:'Beta'},MODE_LABEL={backtest:'Day',paper:'Paper'};
const BOOKS={A:{return_pct:2,curve:[{date:'2026-11-12',bot:2,index:1}]},B:{return_pct:-3,curve:[{date:'2026-11-12',bot:-3,index:4}]}};
const part=k=>BOOKS[k],isPaper=()=>mode==='paper',studyLabel=()=> 'Fixed',safe=x=>String(x??''),pct=x=>x+'%',color=x=>x>=0?'green':'red';
'''+functions+r'''
assert.deepEqual(botChartData('B').series,BOOKS.B.curve);assert.equal(botChartData('B').showIndex,true);
assert.ok(rankChartMarkup('B').includes('id="rankChart-B"'));assert.ok(!rankChartMarkup('B').includes('rankChart-A'));
assert.ok(rankChartMarkup('B').includes('Beta Bot'));
mode='paper';BOOKS.B={return_pct:-10,curve:[],history:[{date:'2026-11-12',nav:90000000},{date:'2026-11-13',nav:null},{date:'2026-11-16',return_pct:0}]};
const chart=botChartData('B');assert.equal(chart.series.length,2);assert.ok(Math.abs(chart.series[0].bot+10)<1e-9);assert.equal(chart.series[1].bot,0);assert.equal(chart.showIndex,false);
delete DATA.capital_each;assert.equal(botChartData('B').series.length,1);
BOOKS.B.history=[];BOOKS.B.curve=[{date:'2026-11-12',bot:999,index:1}];assert.deepEqual(botChartData('B').series,[]);
assert.ok(rankChartMarkup('B').includes('Chưa có dữ liệu đã ghi nhận'));
BOOKS.B.history=[{date:'2026-11-12',nav:90000000}];BOOKS.B.curve=[{date:'2026-11-12',bot:-10,index:2}];
assert.equal(botChartData('B').showIndex,true);
'''
    path=tmp_path/'bot-chart.cjs';path.write_text(script,encoding='utf8')
    result=subprocess.run([node,str(path)],capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr


def test_cross_basket_summary_rejects_missing_results_and_unobserved_paper(tmp_path):
    """Synthetic summary metrics stay in temporary tests, never market outputs."""
    node=shutil.which('node')
    if not node:pytest.skip('Node.js unavailable')
    html=SITE.read_text(encoding='utf8')
    functions='function summaryBasketSources'+html.split('function summaryBasketSources',1)[1].split('function graph(',1)[0]
    script=r'''
const assert=require('node:assert/strict');
let mode='backtest',period='ALL',REPLAY_DATA=null,FIXED_REPLAY_DATA=null,hiddenBots={};const IDS=['A','B','C','D','E','F','G'];
const STUDY_LABELS={'300':'Monthly','146':'Fixed'},MODE_LABEL={backtest:'Day',paper:'Paper'},SHORT={};
const DATA={traders:{},backtest_options:[{key:'ALL',label:'All'}],paper_contest_start:'2026-11-13'};
const book=(ret,dd=-10)=>({return_pct:ret,max_drawdown_pct:dd,buy_count:2,closed_trades:1,history:[]});
const books=()=>Object.fromEntries(IDS.map((b,i)=>[b,book(30-i*10)]));
const PIT_DATA={cohorts:{'300':{backtest_periods:{ALL:books()}},'146':{backtest_periods:{ALL:books()}},legacy:{backtest_periods:{ALL:Object.fromEntries(IDS.map(b=>[b,book(9999)]))}}}};
const isPaper=()=>mode==='paper',safe=x=>String(x??''),pct=x=>x+'%',color=x=>x>=0?'green':'red';
'''+functions+r'''
let rank=summaryBotRanking();assert.equal(rank.sources.length,2);assert.equal(rank.rows.length,7);
assert.deepEqual(rank.rows.slice(0,3).map(r=>r.bot),['A','B','C']);
assert.deepEqual(rank.rows.slice(-3).reverse().map(r=>r.bot),['G','F','E']);
assert.equal((crossBasketSummary().match(/data-summary-bot=/g)||[]).length,6);
// Missing results cannot improve a score by silently dropping the losing basket.
PIT_DATA.cohorts['146'].backtest_periods.ALL.A.return_pct=null;
rank=summaryBotRanking();assert.equal(rank.rows.length,6);assert.equal(rank.incomplete,1);
assert.ok(!rank.rows.some(r=>r.bot==='A'));
PIT_DATA.cohorts['146'].backtest_periods.ALL.A.return_pct=30;
PIT_DATA.cohorts['300'].backtest_periods.ALL.B.return_pct=30;
PIT_DATA.cohorts['146'].backtest_periods.ALL.B.return_pct=30;
PIT_DATA.cohorts['300'].backtest_periods.ALL.A.max_drawdown_pct=null;
assert.equal(summaryBotRanking().rows[0].bot,'B');
period='3M';assert.equal(summaryBotRanking().rows.length,0);
period='ALL';for(const cohort of ['300','146'])for(const b of IDS)PIT_DATA.cohorts[cohort].backtest_periods.ALL[b].return_pct=0;
assert.ok(crossBasketSummary().includes('đồng hạng'));assert.ok(!crossBasketSummary().includes('data-summary-bot='));
mode='paper';DATA.paper=books();
REPLAY_DATA={paper:DATA.paper};FIXED_REPLAY_DATA={paper:books()};
assert.equal(summaryBotRanking().sources.length,2);assert.equal(summaryBotRanking().rows.length,0);
assert.ok(crossBasketSummary().includes('Paper đang chờ phiên replay'));
for(const b of IDS)DATA.paper[b].history=[{date:'2026-11-13',nav:100000000}];
assert.equal(summaryBotRanking().rows.length,0);
for(const b of IDS)FIXED_REPLAY_DATA.paper[b].history=[{date:'2026-11-13',nav:100000000}];
assert.equal(summaryBotRanking().rows.length,7);assert.ok(!crossBasketSummary().includes('chưa có tài khoản paper cho Rổ cố định'));
// Enabled bots alone determine ranking, missing-result counts and empty states.
hiddenBots={A:true};rank=summaryBotRanking();assert.equal(rank.rows.length,6);
assert.ok(!rank.rows.some(r=>r.bot==='A'));assert.equal(rank.rows[0].bot,'B');
assert.ok(!crossBasketSummary().includes('data-summary-bot="A"'));
hiddenBots.B=true;assert.ok(crossBasketSummary().includes('Cần ít nhất 6 bot'));
hiddenBots=Object.fromEntries(IDS.map(k=>[k,true]));
assert.ok(crossBasketSummary().includes('Chưa bật theo dõi bot nào'));
hiddenBots={};assert.equal(summaryBotRanking().rows.length,7);
'''
    path=tmp_path/'summary.cjs';path.write_text(script,encoding='utf8')
    result=subprocess.run([node,str(path)],capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr


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
const vn30=JSON.parse(fs.readFileSync(path.join(root,'research-vn30.json'),'utf8'));PIT_DATA.vn30=vn30;PIT_DATA.cohorts.vn30=vn30.cohort;PIT_DATA.sector_universes.vn30=vn30.sector_universe;
render=()=>{};const originalPaper=JSON.stringify(DATA.paper);
for(const cohort of ['300','146','vn30']){
  setStudy(cohort);assert.equal(activeStudy(),cohort);assert.equal(historicalSource(),PIT_DATA.cohorts[cohort]);
  for(const [m,key] of [['backtest','backtests'],['backtest_minute','minute_backtests'],['hybrid','hybrid_backtests']]){
    mode=m;period='ALL';assert.equal(activeKeys().length,13);
    for(const bot of IDS)assert.equal(part(bot).return_pct,PIT_DATA.cohorts[cohort][key][bot].return_pct);
  }
  const six=comparisonBooks('Buffett');assert.equal(six.length,6);
  assert.equal(six.find(b=>b.id==='backtest').data,PIT_DATA.cohorts[cohort].backtests.Buffett);
  assert.equal(six.find(b=>b.id==='paper').data,DATA.paper.Buffett);
}
const untouched=JSON.stringify(PIT_DATA);
for(const [m,key] of [['backtest','backtests'],['backtest_minute','minute_backtests'],['hybrid','hybrid_backtests']]){
  hiddenBots={};mode=m;period='ALL';const ranking=summaryBotRanking();assert.equal(ranking.rows.length,13);assert.equal(ranking.sources.length,3);
  for(const row of ranking.rows){
    const a=PIT_DATA.cohorts['300'][key][row.bot],b=PIT_DATA.cohorts['146'][key][row.bot],c=PIT_DATA.cohorts.vn30[key][row.bot];
    assert.equal(row.score,(a.return_pct+b.return_pct+c.return_pct)/3);assert.equal(row.worstDD,Math.min(a.max_drawdown_pct,b.max_drawdown_pct,c.max_drawdown_pct));
  }
  const scores=ranking.rows.map(r=>[r.bot,r.score]);study='146';hiddenBots={Minervini:true};regionFilter='VN';
  assert.deepEqual(summaryBotRanking().rows.map(r=>[r.bot,r.score]),scores.filter(r=>r[0]!=='Minervini'));
  hiddenBots={};assert.deepEqual(summaryBotRanking().rows.map(r=>[r.bot,r.score]),scores);
  const html=crossBasketSummary();assert.equal((html.match(/data-summary-bot=/g)||[]).length,6);
  assert.ok(html.includes('🧭 Tổng kết qua các rổ · '+MODE_LABEL[mode]));
  for(const row of ranking.rows)assert.deepEqual(botChartData(row.bot).series,PIT_DATA.cohorts[study][key][row.bot].curve);
  selected='Minervini';assert.ok(rankExtra('Darvas').includes('id="rankChart-Darvas"'));
}
mode='backtest';period='3M';
for(const r of summaryBotRanking().rows)assert.equal(r.score,(PIT_DATA.cohorts['300'].backtest_periods['3M'][r.bot].return_pct+PIT_DATA.cohorts['146'].backtest_periods['3M'][r.bot].return_pct+PIT_DATA.cohorts.vn30.backtest_periods['3M'][r.bot].return_pct)/3);
assert.equal(JSON.stringify(PIT_DATA),untouched);hiddenBots={};regionFilter='ALL';study='146';period='ALL';
assert.equal(JSON.stringify(DATA.paper),originalPaper);
setStudy('legacy');mode='backtest';assert.equal(activeStudy(),'146');assert.equal(part('Minervini'),PIT_DATA.cohorts['146'].backtest_periods.ALL.Minervini);
assert.ok(!studyPicker().includes("setStudy('legacy')"));assert.ok(!studyPicker().includes('Đối chứng'));
assert.ok(studyPicker().includes('Rổ cố định · 146 mã sống sót'));assert.equal(Object.keys(STUDY_LABELS).length,3);
setStudy('300');studyMonth='2023-11';assert.ok(studyPicker().includes('SJF'));
assert.ok(studyPicker().includes('2023-10-31'));assert.equal(PIT_DATA.months[0].members.length,300);
SECTOR_DATA=JSON.parse(fs.readFileSync(path.join(root,'sectors.json'),'utf8'));sectorMode='hybrid';sectorBot='Munger';renderSectors();
assert.ok(elements.sectorContent.innerHTML.includes('Độ phủ mẫu 300 mã'));
assert.equal(sectorBookStats('hybrid','Munger').buy_fills,PIT_DATA.cohorts['300'].hybrid_backtests.Munger.buy_count);
stockStudy=true;stockSymbol='SJF';PIT_STOCKS.SJF=JSON.parse(fs.readFileSync(path.join(root,'pit-stocks/SJF.json'),'utf8'));
assert.equal(stockBars().at(-1)[0],'2023-11-10');
REPLAY_DATA=JSON.parse(fs.readFileSync(path.join(root,'paper-replay.json'),'utf8'));
FIXED_REPLAY_DATA=JSON.parse(fs.readFileSync(path.join(root,'paper-fixed146.json'),'utf8'));VN30_REPLAY_DATA=JSON.parse(fs.readFileSync(path.join(root,'paper-vn30.json'),'utf8'));applyReplayData();
for(const modeId of ['paper','paper_minute','paper_combo']){
  mode=modeId;assert.equal(activeKeys().length,13);
  for(const bot of IDS)assert.equal(part(bot),REPLAY_DATA[modeId][bot]);
  assert.equal(summaryBotRanking().sources.length,3);
  if(REPLAY_DATA.status==='waiting_completed_session'){
    assert.equal(summaryBotRanking().rows.length,0);assert.ok(!crossBasketSummary().includes('data-summary-bot='));
    assert.ok(crossBasketSummary().includes('Paper đang chờ phiên replay'));
    for(const bot of IDS)assert.equal(botChartData(bot).series.length,0);
  }
}
const replayBooks=JSON.stringify(DATA.paper);
applyValueData();applyValueIntraday();assert.equal(JSON.stringify(DATA.paper),replayBooks);
assert.equal(REPLAY_DATA.execution_revision,'strict_next_candle_v1');
const monthlyBefore=JSON.stringify(REPLAY_DATA),fixedBefore=JSON.stringify(FIXED_REPLAY_DATA);
for(const cohort of ['146','vn30','300','vn30','146']){
  setStudy(cohort);const source=cohort==='vn30'?VN30_REPLAY_DATA:cohort==='146'?FIXED_REPLAY_DATA:REPLAY_DATA;
  for(const m of ['paper','paper_minute','paper_combo']){
    mode=m;for(const bot of IDS)assert.equal(part(bot),source[m][bot]);
    assert.equal(summaryBotRanking().sources.length,3);
  }
}
assert.equal(JSON.stringify(REPLAY_DATA),monthlyBefore);assert.equal(JSON.stringify(FIXED_REPLAY_DATA),fixedBefore);
const fixedList=studyPicker();assert.ok(fixedList.includes('Xem danh sách 146 mã'));
assert.equal((fixedList.match(/class="tickerbtn"/g)||[]).length,146);
assert.ok(fixedList.includes('CHP'));assert.ok(fixedList.includes('TCL'));
setStudy('vn30');studyMonth='2026-05-13';const list=studyPicker();assert.ok(list.includes('thay đổi giữa kỳ'));assert.equal((list.match(/class="tickerbtn"/g)||[]).length,30);assert.ok(list.includes(">BSR</button>"));assert.ok(!list.includes(">DGC</button>"));renderSectors();assert.ok(elements.sectorContent.innerHTML.includes('Độ phủ mẫu 30 mã'));
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
    script="const historicalSource=()=>DATA,activeStudy=()=> 'legacy',studyPicker=()=>'',studyLabel=()=> '146 mã cũ',paperSource=()=>null;\n"+functions+'''
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
    script="const historicalSource=()=>DATA,activeStudy=()=> 'legacy',studyPicker=()=>'',studyLabel=()=> '146 mã cũ',paperSource=()=>null;\n"+functions+'''
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
