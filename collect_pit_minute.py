"""Resumable real minute banking; selection never depends on data availability."""
import hashlib,json,time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
from threading import Lock,Event
import httpx,pandas as pd
from historical_minute import ENDPOINT,VN,epoch,validate_wire
from value_investing import ROOT,read,write

def run():
    config=read(ROOT/'config/research-300.json');symbols=config['eligible_symbols']
    old=read(ROOT/'data/minute_history/audit.json');out=ROOT/'data/pit_minute';out.mkdir(exist_ok=True)
    rawdir=out/'raw';rawdir.mkdir(exist_ok=True);ap=out/'audit.json'
    audit=read(ap) if ap.exists() else dict(source=ENDPOINT,start=config['start'],end=config['end'],symbols={})
    lower=epoch(config['start']);upper=epoch((pd.Timestamp(config['end'])+pd.Timedelta(days=1)).date().isoformat())
    lock=Lock();last=[0.];halt=Event()
    def request(client,body):
        with lock:
            pause=.35-(time.monotonic()-last[0])
            if pause>0:time.sleep(pause)
            if halt.is_set():raise RuntimeError('Stopped after provider access/rate response')
            last[0]=time.monotonic()
        r=client.post(ENDPOINT,json=body)
        if r.status_code in (403,418,429):halt.set()
        r.raise_for_status();return r.content
    def one(sym):
        dest=out/f'{sym}.csv.gz'
        if sym in old['symbols']:
            p=ROOT/'data/minute_history'/f'{sym}.csv.gz';record=old['symbols'][sym]
            if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256']:
                return sym,dict(status='verified',path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=record['sha256'],bars=record['bars'],sessions=record['sessions'],first=record['first'],last=record['last'],reused_baseline=True)
        try:
            cursor=upper;frames=[];pages=[];seen=set();exhausted=False
            with httpx.Client(timeout=40) as client:
                for page in range(60):
                    path=rawdir/f'{sym}-{cursor}.json'
                    if path.exists():raw=path.read_bytes()
                    else:
                        for attempt in range(3):
                            try:raw=request(client,dict(symbols=[sym],timeFrame='ONE_MINUTE',to=cursor,countBack=20000));break
                            except httpx.TransportError:
                                if attempt==2:raise
                                time.sleep(2)
                        path.write_bytes(raw)
                    j=json.loads(raw);pages.append(dict(to=cursor,sha256=hashlib.sha256(raw).hexdigest()))
                    if j==[] or (isinstance(j,list) and len(j)==1 and j[0].get('symbol')==sym and not j[0].get('t')):
                        exhausted=True;break
                    if not isinstance(j,list) or len(j)!=1:raise ValueError('Unexpected minute payload')
                    f=validate_wire(j[0],sym);first=int(f.time.min().timestamp());last_ts=int(f.time.max().timestamp())
                    if first in seen or last_ts>cursor or first>=cursor:raise ValueError('Nonprogressing/invalid pagination')
                    seen.add(first);frames.append(f);pages[-1]['rows']=len(f)
                    if first<=lower:break
                    cursor=first-1
                else:raise ValueError('Bounded page limit exceeded')
            if not frames:return sym,dict(status='no_minute_history',pages=pages,exhausted=exhausted)
            f=pd.concat(frames,ignore_index=True).sort_values('time');f=f[(f.time>=pd.Timestamp(config['start'],tz=VN))&(f.time<pd.Timestamp(config['end'],tz=VN)+pd.Timedelta(days=1))]
            if f.time.duplicated().any():raise ValueError('Overlapping minute pages')
            tmp=dest.with_suffix('.tmp');f.to_csv(tmp,index=False,compression='gzip');tmp.replace(dest)
            return sym,dict(status='verified' if len(f) else 'no_in_window_minutes',path=str(dest.relative_to(ROOT)).replace('\\','/'),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),bars=len(f),sessions=int(f.time.dt.date.nunique()),first=f.time.min().isoformat() if len(f) else None,last=f.time.max().isoformat() if len(f) else None,pages=pages,exhausted=exhausted)
        except Exception as e:return sym,dict(status='error',error=type(e).__name__+': '+str(e)[:240])
    wanted=[]
    for s in symbols:
        r=audit['symbols'].get(s,{})
        if r.get('status')=='verified' and (ROOT/r['path']).exists() and hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256']:continue
        wanted.append(s)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(one,s) for s in wanted]):
            s,r=future.result();audit['symbols'][s]=r;audit['updated_at']=datetime.now(VN).isoformat();write(ap,audit)
            print('Real PIT minute',len(audit['symbols']),'/',len(symbols),s,r['status'],r.get('bars',''),r.get('error',''),flush=True)
    if halt.is_set():raise RuntimeError('Stopped on provider rate/access response; no bypass')
    return audit

if __name__=='__main__':run()
