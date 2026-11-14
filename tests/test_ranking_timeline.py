"""Replay rankings from the actual published NAV observations, never interpolated prices."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[1] / 'site'


def test_timeline_matches_real_books_and_handles_ties_and_missing_observations(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    html = (SITE / 'index.html').read_text(encoding='utf8')
    assert 'id="racePanel"' in html and 'ontoggle="renderRace()"' in html
    assert 'id="racePage"' not in html and 'id="nav-race"' not in html
    js = re.search(r'<script>(.*?)</script>', html, re.S)[1].rsplit('boot();', 1)[0]
    script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
global.localStorage={getItem:()=>null,setItem(){}};
const elements={};global.document={visibilityState:'visible',getElementById:id=>elements[id]||=({innerHTML:'',textContent:'',value:0,open:id==='racePanel',style:{},setAttribute(k,v){this[k]=v},classList:{toggle(){}}}),querySelectorAll:()=>[]};
global.location={search:''};global.window={scrollTo(){}};
'''+js+r'''
const root=process.argv[2],read=f=>JSON.parse(fs.readFileSync(path.join(root,f),'utf8'));
DATA=read('dashboard.json');VALUE_DATA=read('value-investing.json');applyValueData();
VALUE_INTRADAY=read('value-intraday.json');applyValueIntraday();
PIT_DATA=read('research-300.json');PIT_DATA.vn30=read('research-vn30.json');PIT_DATA.cohorts.vn30=PIT_DATA.vn30.cohort;
REPLAY_DATA=read('paper-replay.json');FIXED_REPLAY_DATA=read('paper-fixed146.json');VN30_REPLAY_DATA=read('paper-vn30.json');applyReplayData();
IDS=Object.keys(DATA.traders);render=()=>{};page='home';
const unchanged=JSON.stringify([PIT_DATA,REPLAY_DATA,FIXED_REPLAY_DATA,VN30_REPLAY_DATA]);
let changes=0;
for(const universe of ['300','146','vn30'])for(const book of Object.keys(MODE_LABEL)){
  setStudy(universe);setMode(book);period='ALL';enableAllBots();raceDate=null;
  const data=raceHistory();assert.equal(data.bots.length,16);assert.deepEqual(data.omitted,[]);
  assert.equal(data.dates.length,isPaper()?10:90);assert.equal(data.dates.at(-1),'2026-11-13');
  for(let i=0;i<data.dates.length;i++){
    const date=data.dates[i],expected=IDS.map(bot=>{
      const b=part(bot),row=(isPaper()?b.history:b.curve).find(row=>raceISO(row.date)===date);
      return {bot,nav:row.nav};
    }).sort((a,b)=>b.nav-a.nav||a.bot.localeCompare(b.bot));
    assert.deepEqual(data.frames[i].map(({bot,nav})=>({bot,nav})),expected);
    for(const row of data.frames[i])assert.equal(row.rank,1+expected.filter(other=>other.nav>row.nav).length);
    if(i&&data.frames[i][0].bot!==data.frames[i-1][0].bot)changes++;
  }
  renderRace();seekRace(0);assert.equal(elements.raceDate.textContent,raceShortDate(data.dates[0]));
  assert.ok(!elements.raceGraph.innerHTML.includes('NaN'));
  seekRace(9999);assert.equal(raceDate,'2026-11-13');assert.equal(elements.raceNext.disabled,true);
  assert.equal((elements.raceRows.innerHTML.match(/data-race-bot=/g)||[]).length,16);
  applyBestMix(6);renderRace();assert.equal(raceData.bots.length,6);
  assert.deepEqual(new Set(raceData.bots),new Set(activeKeys()));
  seekRace(1);const chosen=raceDate;renderRace();assert.equal(raceDate,chosen);
  hiddenBots=Object.fromEntries(IDS.map(bot=>[bot,true]));mixChoice={kind:'manual'};
  renderRace();assert.equal(raceData.dates.length,0);assert.ok(elements.raceContent.innerHTML.includes('Chưa có mốc NAV chung'));
}
assert.ok(changes>0,'Actual recorded history includes changes of leader');
assert.equal(JSON.stringify([PIT_DATA,REPLAY_DATA,FIXED_REPLAY_DATA,VN30_REPLAY_DATA]),unchanged);
assert.equal(raceISO('13/11/26'),'2026-11-13');assert.equal(raceISO('31/02/26'),null);assert.equal(raceISO('2026-02-30'),null);
// Temporary NAV-only edge cases are not published market observations.
mode='backtest';study='legacy';period='ALL';IDS=['A','B'];hiddenBots={};
DATA={traders:{},backtests:Object.fromEntries(IDS.map(bot=>[bot,{curve:bot==='A'?[{date:'2026-01-01',nav:100},{date:'2026-01-02',nav:110},{date:'2026-01-03',nav:120}]:[{date:'2026-01-01',nav:100},{date:'2026-01-03',nav:130}]}]))};
let sparse=raceHistory();assert.deepEqual(sparse.dates,['2026-01-01','2026-01-03']);
assert.deepEqual(sparse.frames[0].map(row=>row.rank),[1,1]);
raceData=sparse;assert.ok(raceLeaderText(0).startsWith('Đồng hạng'));assert.ok(raceLeaderText(1).startsWith('Vươn lên dẫn đầu: B'));
for(const bot of IDS)DATA.backtests[bot]={curve:[{date:'2026-01-01',nav:100},{date:'2026-01-01',nav:999},{date:'2026-01-02',nav:null},{date:'2026-01-03',nav:-10}]};
assert.deepEqual(raceHistory().dates,[]);

'''
    target = tmp_path / 'timeline.cjs'
    target.write_text(script, encoding='utf8')
    result = subprocess.run([node, str(target), str(SITE)], capture_output=True, text=True, encoding='utf8')
    assert result.returncode == 0, result.stderr
