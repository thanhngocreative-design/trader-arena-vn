"""Exercise actual published books; selection never rewrites market or paper data."""
import re,shutil,subprocess
from pathlib import Path
import pytest

SITE=Path(__file__).resolve().parents[1]/'site'

def test_mix_buttons_rank_all_18_scopes_and_preserve_each_selection(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js unavailable')
    html=(SITE/'index.html').read_text(encoding='utf8')
    js=re.search(r'<script>(.*?)</script>',html,re.S)[1].rsplit('boot();',1)[0]
    script=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const storage=new Map([['arena-hidden-bots-v1',JSON.stringify({Darvas:true})]]);
global.localStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)};
const elements={};global.document={getElementById:id=>elements[id]||=({innerHTML:'',style:{},classList:{toggle(){}}}),querySelectorAll:()=>[]};
global.location={search:''};global.window={scrollTo(){}};
'''+js+r'''
const root=process.argv[2],read=f=>JSON.parse(fs.readFileSync(path.join(root,f),'utf8'));
DATA=read('dashboard.json');VALUE_DATA=read('value-investing.json');applyValueData();
VALUE_INTRADAY=read('value-intraday.json');applyValueIntraday();
PIT_DATA=read('research-300.json');PIT_DATA.vn30=read('research-vn30.json');PIT_DATA.cohorts.vn30=PIT_DATA.vn30.cohort;
REPLAY_DATA=read('paper-replay.json');FIXED_REPLAY_DATA=read('paper-fixed146.json');VN30_REPLAY_DATA=read('paper-vn30.json');applyReplayData();
IDS=Object.keys(DATA.traders);render=()=>{};
const before=JSON.stringify([PIT_DATA,REPLAY_DATA,FIXED_REPLAY_DATA,VN30_REPLAY_DATA]);
const expectedScopes={};
for(const universe of ['300','146','vn30'])for(const book of ['paper','paper_minute','paper_combo','backtest','backtest_minute','hybrid']){
  setStudy(universe);setMode(book);period='ALL';regionFilter='VN';
  const c=PIT_DATA.cohorts[universe],key={backtest:'backtests',backtest_minute:'minute_backtests',hybrid:'hybrid_backtests'}[book];
  const source=book.startsWith('paper')?paperSource()[book]:c[key];
  const expected=Object.entries(source).sort((a,b)=>b[1].nav-a[1].nav||(b[1].max_drawdown_pct??-Infinity)-(a[1].max_drawdown_pct??-Infinity)||a[0].localeCompare(b[0])).map(x=>x[0]);
  hiddenBots={};regionFilter='ALL';renderHome();
  const leaderboard=()=>[...elements.leaderboard.innerHTML.matchAll(/onclick="selectRankBot\('([^']+)'\)"/g)].map(x=>x[1]);
  assert.deepEqual(leaderboard(),expected);
  // Ranking must include hidden bots and ignore country filters.
  hiddenBots=Object.fromEntries(IDS.map(b=>[b,true]));
  assert.deepEqual(mixRanking().map(r=>r.bot),expected);
  for(const count of [2,3,4,5,6]){
    applyBestMix(count);assert.equal(regionFilter,'ALL');
    assert.deepEqual(new Set(activeKeys()),new Set(expected.slice(0,count)));
    renderHome();assert.deepEqual(leaderboard(),expected.slice(0,count));
    const total=activeKeys().reduce((sum,bot)=>sum+source[bot].nav,0);
    assert.equal(elements.totalDelta.innerHTML,mixTotalMarkup(total,count*100000000));
    assert.equal((mixControls().match(/aria-pressed="true"/g)||[]).length,1);
  }
  const scope=botSelectionScope();expectedScopes[scope]=[...activeKeys()];
  assert.deepEqual(JSON.parse(storage.get('arena-bot-selections-v2'))[scope],hiddenBots);
}
assert.equal(Object.keys(expectedScopes).length,18);
assert.ok(mixTotalMarkup(271801701,200000000).includes('+71,8 triệu'));
assert.ok(mixTotalMarkup(271801701,200000000).includes('+35,90%'));
assert.ok(mixTotalMarkup(180000000,200000000).includes('-20 triệu'));
assert.ok(mixTotalMarkup(180000000,200000000).includes('-10,00%'));
assert.ok(mixTotalMarkup(200000000,200000000).includes('0đ'));
assert.ok(mixTotalMarkup(0,0).includes('Chưa bật bot nào'));
assert.ok(studyPicker().includes('Cách chọn rổ &amp; dữ liệu'));
for(const [scope,chosen] of Object.entries(expectedScopes)){
  const [universe,book]=scope.split(':');setStudy(universe);setMode(book);
  assert.deepEqual(activeKeys(),chosen);
}
// Explicitly different two-, three- and four-bot choices survive switching.
setStudy('vn30');setMode('backtest');applyBestMix(2);const a=[...activeKeys()];
setMode('paper');applyBestMix(3);const b=[...activeKeys()];
setStudy('146');applyBestMix(4);const c=[...activeKeys()];
setStudy('vn30');assert.deepEqual(activeKeys(),b);setMode('backtest');assert.deepEqual(activeKeys(),a);
setStudy('146');setMode('paper');assert.deepEqual(activeKeys(),c);
// Reload stored selections, retaining legacy preferences as defaults only.
const saved=storage.get('arena-bot-selections-v2');botSelections=JSON.parse(saved);hiddenBots={};loadBotSelection();assert.deepEqual(activeKeys(),c);
setStudy('vn30');setMode('backtest');period='3M';
const quarter=Object.entries(PIT_DATA.cohorts.vn30.backtest_periods['3M']).sort((a,b)=>b[1].nav-a[1].nav).slice(0,2).map(x=>x[0]);
applyBestMix(2);assert.deepEqual(new Set(activeKeys()),new Set(quarter));assert.ok(mixControls().includes('3 tháng'));
setMode('paper');assert.ok(mixControls().includes('Paper ngày · mùa từ'));assert.ok(!mixControls().includes('Backtest ngày · 3 năm'));
toggleBot('Munger');const manual={...hiddenBots};setMode('paper_minute');setMode('paper');assert.deepEqual(hiddenBots,manual);
enableAllBots();assert.equal(activeKeys().length,13);
assert.equal(JSON.stringify([PIT_DATA,REPLAY_DATA,FIXED_REPLAY_DATA,VN30_REPLAY_DATA]),before);
'''
    file=tmp_path/'mix.cjs';file.write_text(script,encoding='utf8')
    result=subprocess.run([node,str(file),str(SITE)],capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr
