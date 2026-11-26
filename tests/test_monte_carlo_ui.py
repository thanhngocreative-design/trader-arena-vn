"""Exercise the real page script against saved real books and scenario summaries."""
import re, shutil, subprocess
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_monte_navigation_preserves_selection_and_all_live_scope_groups(tmp_path):
    node=shutil.which('node')
    if not node:pytest.skip('Node.js unavailable')
    html=(ROOT/'site/index.html').read_text(encoding='utf8')
    assert 'id="montePage"' in html and 'id="nav-monte"' in html
    assert 'Xem Monte Carlo của nhóm này' in html
    script=re.search(r'<script>(.*?)</script>',html,re.S)[1].rsplit('boot();',1)[0]
    fixture=r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
global.localStorage={getItem:()=>null,setItem(){}};
const elements={};global.document={getElementById:id=>elements[id]||=({innerHTML:'',style:{},classList:{toggle(){}},setAttribute(){}}),querySelectorAll:()=>[]};
global.window={scrollTo(){}};global.location={search:''};
'''+script+r'''
const root=process.argv[2],read=f=>JSON.parse(fs.readFileSync(path.join(root,f),'utf8'));
DATA=read('dashboard.json');VALUE_DATA=read('value-investing.json');applyValueData();VALUE_INTRADAY=read('value-intraday.json');applyValueIntraday();
PIT_DATA=read('research-300.json');PIT_DATA.vn30=read('research-vn30.json');PIT_DATA.cohorts.vn30=PIT_DATA.vn30.cohort;
REPLAY_DATA=read('paper-replay.json');FIXED_REPLAY_DATA=read('paper-fixed146.json');VN30_REPLAY_DATA=read('paper-vn30.json');applyReplayData();IDS=Object.keys(DATA.traders);
monteIndex=read('monte-carlo/index.json');monteStatus={paper:read('replay-status.json'),backtest:read('backtest-status.json')};
for(const [key,entry] of Object.entries(monteIndex.scopes))monteCache[key]=read('monte-carlo/'+entry.file);
const actualRender=render;render=()=>{};mode='backtest';study='300';period='ALL';mixChoice={kind:'best',count:4};selectBestBots(4);
let before=JSON.stringify({mode,study,period,mixChoice,hiddenBots});setPage('monte');assert.equal(JSON.stringify({mode,study,period,mixChoice,hiddenBots}),before);setPage('home');assert.equal(JSON.stringify({mode,study,period,mixChoice,hiddenBots}),before);
page='monte';
for(const book of Object.keys(MODE_LABEL))for(const basket of ['300','146','vn30']){
 mode=book;study=basket;period='ALL';applyReplayData();
 const key=monteScope();monteChecked=key;monteCheckedAt=Date.now();
 for(const size of [2,3,4,5,6,19]){
  mixChoice=size===19?{kind:'all'}:{kind:'best',count:size};if(size===19)hiddenBots={};else selectBestBots(size);
  const selected=activeKeys(),data=monteCache[key];assert.equal(selected.length,size);
  before=JSON.stringify({mode,study,period,mixChoice,hiddenBots});renderMonteCarlo();assert.equal(JSON.stringify({mode,study,period,mixChoice,hiddenBots}),before);
  if(isPaper()){assert.ok(elements.monteContent.innerHTML.includes('Chưa đủ lịch sử'));assert.ok(!elements.monteContent.innerHTML.includes('Kịch bản kết thúc lỗ'));}
  else {assert.ok(data.groups[monteGroupKey(selected)],key+' preset mismatch');assert.ok(elements.monteContent.innerHTML.includes('Kịch bản kết thúc lỗ'));}
 }
}
mode='backtest';study='300';period='3M';applyReplayData();mixChoice={kind:'all'};hiddenBots={};monteChecked=monteScope();monteCheckedAt=Date.now();renderMonteCarlo();assert.ok(elements.monteContent.innerHTML.includes('Chưa đủ lịch sử'));assert.ok(!elements.monteContent.innerHTML.includes('Kịch bản kết thúc lỗ'));
period='ALL';monteChecked=monteScope();monteCheckedAt=Date.now();selectMonteBot('Wyckoff');assert.deepEqual(activeKeys(),['Wyckoff']);renderMonteCarlo();assert.ok(elements.monteContent.innerHTML.includes('Kịch bản kết thúc lỗ'));
let pair;const groups=monteCache[monteScope()].groups;for(let i=0;i<IDS.length&&!pair;i++)for(let j=i+1;j<IDS.length&&!pair;j++)if(!groups[monteGroupKey([IDS[i],IDS[j]])])pair=[IDS[i],IDS[j]];
hiddenBots=Object.fromEntries(IDS.map(k=>[k,!pair.includes(k)]));mixChoice={kind:'manual'};renderMonteCarlo();assert.ok(elements.monteContent.innerHTML.includes('Nhóm này chưa có mô phỏng cloud'));assert.ok(!elements.monteContent.innerHTML.includes('Kịch bản kết thúc lỗ'));
hiddenBots={};const all=monteCache[monteScope()].groups[monteGroupKey(activeKeys())],savedProbability=all.metrics.loss_probability_pct;all.metrics.loss_probability_pct=101;renderMonteCarlo();assert.ok(elements.monteContent.innerHTML.includes('chưa đủ kiểm chứng'));assert.ok(!elements.monteContent.innerHTML.includes('Kịch bản kết thúc lỗ'));all.metrics.loss_probability_pct=savedProbability;
hiddenBots={};monteStatus.backtest={...monteStatus.backtest,end:'2099-01-01'};renderMonteCarlo();assert.ok(!elements.monteContent.innerHTML.includes('Kịch bản kết thúc lỗ'));assert.ok(elements.monteContent.innerHTML.includes('Chờ kết quả Monte Carlo cập nhật'));
'''
    output=tmp_path/'monte-ui.cjs';output.write_text(fixture,encoding='utf8')
    result=subprocess.run([node,str(output),str(ROOT/'site')],capture_output=True,text=True,encoding='utf8')
    assert result.returncode==0,result.stderr
