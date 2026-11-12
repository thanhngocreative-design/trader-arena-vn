"""Download actual Vietcap 1m candles, resumable and never interpolated."""
import argparse,json,time,hashlib
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx,pandas as pd,numpy as np
VN=ZoneInfo('Asia/Ho_Chi_Minh')
ROOT=Path(__file__).resolve().parent
ENDPOINT='https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart'
def epoch(s):return int(datetime.fromisoformat(s).replace(tzinfo=VN).timestamp())
def validate_wire(d,symbol):
    if not isinstance(d,dict) or d.get('symbol')!=symbol:raise ValueError('Unexpected symbol')
    arrays={k:d.get(k) or [] for k in 'tohlcv'}
    if not arrays['t'] or len({len(v) for v in arrays.values()})!=1:raise ValueError('Empty/mismatched candle arrays')
    f=pd.DataFrame({{'t':'time','o':'open','h':'high','l':'low','c':'close','v':'volume'}[k]:v for k,v in arrays.items()})
    f['time']=pd.to_datetime(pd.to_numeric(f.time),unit='s',utc=True).dt.tz_convert(VN)
    for k in ['open','high','low','close','volume']:f[k]=pd.to_numeric(f[k])
    if f.time.duplicated().any() or not np.isfinite(f[['open','high','low','close','volume']]).all().all():raise ValueError('Duplicate/nonfinite bars')
    if ((f[['open','high','low','close']]<=0).any().any() or (f.volume<0).any() or (f.high<f[['open','low','close']].max(axis=1)).any() or (f.low>f[['open','high','close']].min(axis=1)).any()):raise ValueError('Invalid OHLCV')
    if ((f.time.dt.second!=0)|(f.time.dt.dayofweek>=5)).any():raise ValueError('Off-minute/weekend candles')
    return f.sort_values('time')
def download(config=None,output=None):
    u=json.loads(Path(config or ROOT/'config/research-universe.json').read_text(encoding='utf8'))
    output=Path(output or ROOT/'data/minute_history');output.mkdir(parents=True,exist_ok=True)
    rawdir=output/'raw';rawdir.mkdir(exist_ok=True)
    lower=epoch(u['start']);upper=epoch((pd.Timestamp(u['end'])+pd.Timedelta(days=1)).date().isoformat())
    auditpath=output/'audit.json';audit=json.loads(auditpath.read_text()) if auditpath.exists() else {'source':ENDPOINT,'start':u['start'],'end':u['end'],'symbols':{},'no_interpolation':True}
    if (audit['start'],audit['end'])!=(u['start'],u['end']):raise ValueError('Cache window mismatch')
    with httpx.Client(timeout=40) as client:
        for n,symbol in enumerate(u['eligible_symbols'],1):
            dest=output/f'{symbol}.csv.gz'
            if symbol in audit['symbols'] and dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()==audit['symbols'][symbol]['sha256']:continue
            frames=[];cursor=upper;seen=set();pages=[]
            for page in range(60):
                path=rawdir/f'{symbol}-{cursor}.json';body={'symbols':[symbol],'timeFrame':'ONE_MINUTE','to':cursor,'countBack':20000}
                if path.exists():raw=path.read_bytes()
                else:
                    for attempt in range(3):
                        try:r=client.post(ENDPOINT,json=body);break
                        except httpx.TransportError:
                            if attempt==2:raise
                            time.sleep(2)
                    if r.status_code!=200:raise RuntimeError(f'Provider HTTP {r.status_code}; stop instead of bypassing limits')
                    raw=r.content;parsed=json.loads(raw)
                    if not isinstance(parsed,list) or len(parsed)!=1:raise RuntimeError(f'{symbol}: empty/unexpected response')
                    path.write_bytes(raw);time.sleep(1)
                j=json.loads(raw);f=validate_wire(j[0],symbol);first=int(f.time.min().timestamp());last=int(f.time.max().timestamp())
                if first in seen or last>cursor or first>=cursor:raise RuntimeError('Pagination failed')
                seen.add(first);frames.append(f);pages.append({'to':cursor,'countBack':20000,'rows':len(f),'sha256':hashlib.sha256(raw).hexdigest()})
                if first<=lower:break
                cursor=first-1
            else:raise RuntimeError('Page bound exceeded')
            f=pd.concat(frames,ignore_index=True).sort_values('time');f=f[(f.time>=pd.Timestamp(u['start'],tz=VN))&(f.time<pd.Timestamp(u['end'],tz=VN)+pd.Timedelta(days=1))]
            if f.time.duplicated().any():raise ValueError('Overlapping pages')
            tmp=dest.with_suffix('.tmp');f.to_csv(tmp,index=False,compression='gzip');tmp.replace(dest)
            audit['symbols'][symbol]={'bars':len(f),'sessions':int(f.time.dt.date.nunique()),'first':f.time.min().isoformat(),'last':f.time.max().isoformat(),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'pages':pages}
            temp=auditpath.with_suffix('.tmp');temp.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8');temp.replace(auditpath)
            print(f'{n}/{len(u["eligible_symbols"])} {symbol}: {len(f)} actual bars, {audit["symbols"][symbol]["sessions"]} sessions',flush=True)
    print('Download complete',len(audit['symbols']),flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--config');ap.add_argument('--output');a=ap.parse_args();download(a.config,a.output)
