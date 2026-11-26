"""Publish bounded cloud summaries, keeping all observed trading books immutable."""
import argparse, hashlib, json, tempfile
from datetime import datetime
from pathlib import Path
import numpy as np
from value_investing import ROOT, VN, write, read
from monte_carlo_sources import export_sources
from monte_carlo import REVISION,SETTINGS,nav_returns,bootstrap_paths,group_summary

OUTPUT=ROOT/'site/monte-carlo'
SCRATCH=ROOT/'data/pit_results/monte-carlo'


def group_specs(panel):
    bots=panel['bots'];ranking=panel['ranking'];groups={}
    for members in [[b] for b in bots]+[ranking[:n] for n in (2,3,4,5,6)]+[bots]:
        members=sorted(members);groups['|'.join(members)]=members
    return groups


def build_scope(panel,version,*,settings=SETTINGS,output=OUTPUT,scratch=SCRATCH):
    serial=json.dumps(panel,sort_keys=True,separators=(',',':'))
    source_sha=hashlib.sha256(serial.encode()).hexdigest()
    fingerprint=hashlib.sha256((source_sha+version).encode()).hexdigest()
    slug=panel['key'].replace(':','-').replace('_','-')
    file=slug+'-'+fingerprint[:16]+'.json';target=output/file
    entry=dict(file=file,fingerprint=fingerprint,source_sha256=source_sha,end=panel['dates'][-1],sessions=len(panel['dates']),
        bots=panel['bots'],model_sha256=panel['model_sha256'],period=panel['period'])
    if target.exists():
        current=read(target)
        if current.get('fingerprint')==fingerprint and current.get('revision')==REVISION:
            return {**entry,'status':current['status']}
    base=dict(revision=REVISION,fingerprint=fingerprint,source_sha256=source_sha,status='insufficient_history',
        scope=panel['key'],mode=panel['mode'],cohort=panel['cohort'],period=panel['period'],bots=panel['bots'],
        dates=dict(start=panel['dates'][0],end=panel['dates'][-1],sessions=len(panel['dates'])),
        model_sha256=panel['model_sha256'],observed_nav={b:panel['nav'][b][-1] for b in panel['bots']},
        trades=panel['trades'],settings=settings,groups={},hypothetical=True)
    # Validate even short source panels; never disguise corrupt input as short history.
    returns=nav_returns(np.column_stack([panel['nav'][b] for b in panel['bots']]),panel['capital_each'])
    if len(returns)>=settings['min_sessions']:
        groups=group_specs(panel);base['groups']={key:dict(bots=members,sensitivity={}) for key,members in groups.items()}
        scratch.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='paths-',dir=scratch) as directory:
            folder=Path(directory).resolve()
            if folder.parent!=scratch.resolve():raise ValueError('Invalid scenario scratch path')
            for block in settings['blocks']:
                filename=folder/'paths.bin'
                wealth=bootstrap_paths(returns,block=block,paths=settings['paths'],horizon=settings['horizon'],seed=settings['seed'],filename=filename)
                for key,members in groups.items():
                    summary=group_summary(wealth,[panel['bots'].index(b) for b in members],panel['capital_each'],detail=block==settings['primary_block'])
                    if block==settings['primary_block']:base['groups'][key].update(summary)
                    base['groups'][key]['sensitivity'][str(block)]=summary['metrics']
                wealth.flush();del wealth
                filename.unlink()
        base['status']='ready'
    write(target,base)
    return {**entry,'status':base['status']}


def run():
    sources=export_sources();OUTPUT.mkdir(parents=True,exist_ok=True)
    code=b''.join((ROOT/p).read_bytes().replace(b'\r\n',b'\n') for p in ('monte_carlo.py','run_monte_carlo.py'))
    version=hashlib.sha256(code+json.dumps(SETTINGS,sort_keys=True).encode()+np.__version__.encode()).hexdigest()
    scopes={}
    for key,panel in sources['panels'].items():
        scopes[key]=build_scope(panel,version)
        print('Monte Carlo',key,scopes[key]['status'],scopes[key]['sessions'],'observed sessions',flush=True)
    index=dict(revision=REVISION,version=version,end=sources['end'],model_sha256=sources['model_sha256'],
        generated_at=datetime.now(VN).isoformat(),numpy_version=np.__version__,settings=SETTINGS,scopes=scopes,hypothetical=True,
        source='Verified recorded NAV; no generated market candles or trade fills',
        selection='Fixed observed Best Mix members; descriptive in-sample selection, not a forecast')
    write(OUTPUT/'index.json',index)
    retained={x['file'] for x in scopes.values()}|{'index.json'}
    for path in OUTPUT.glob('*.json'):
        if path.resolve().parent!=OUTPUT.resolve():raise ValueError('Invalid generated output path')
        if path.name not in retained:path.unlink()
    print('Published Monte Carlo summaries; observed trading books unchanged',flush=True)


if __name__=='__main__':run()
