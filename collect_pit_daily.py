"""Bank real historical daily bars for current AND provider-retained delisted stocks."""
import json,hashlib,re,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from threading import Event
from datetime import datetime
import numpy as np
import pandas as pd
from vn_market_data.sources.vietcap import VietcapSource
from historical_minute import VN
ROOT=Path(__file__).resolve().parent
REVISION='observed_positive_volume_v2'

def valid_rows(frame):
    values=frame[['open','high','low','close','volume']].astype(float)
    return (np.isfinite(values).all(axis=1)&(values[['open','high','low','close']]>0).all(axis=1)&(values.volume>0)
            &(values.high>=values[['open','low','close']].max(axis=1))&(values.low<=values[['open','high','close']].min(axis=1)))

def run():
    meta=json.loads((ROOT/'config/market-classification.json').read_text(encoding='utf8'))
    listing={s:v for s,v in meta['listing'].items() if v['type']=='STOCK' and re.fullmatch('[A-Z0-9]{2,7}',s)}
    out=ROOT/'data/pit_daily';out.mkdir(parents=True,exist_ok=True)
    audit_path=out/'audit.json';audit=json.loads(audit_path.read_text()) if audit_path.exists() else dict(source='Vietcap real ONE_DAY candles',start='2021-01-01',end='2026-11-12',symbols={})
    halt=Event()
    def fetch(sym):
        if halt.is_set():return sym,dict(status='halted')
        dest=out/f'{sym}.json'
        try:
            if dest.exists():raw=dest.read_bytes();rows=json.loads(raw)
            else:
                rows=VietcapSource().get_ohlcv(sym,audit['start'],audit['end'])
                raw=json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode('utf8');dest.write_bytes(raw)
            if not rows:return sym,dict(status='no_history',sha256=hashlib.sha256(raw).hexdigest(),listing=listing[sym])
            f=pd.DataFrame(rows);f['date']=pd.to_datetime(f.date)
            if f.date.duplicated().any() or f.date.isna().any():raise ValueError('Duplicate/invalid dates')
            good=valid_rows(f);observed=f.loc[good]
            return sym,dict(status='verified' if len(observed) else 'no_observed_trades',validation_revision=REVISION,rows=len(f),valid_rows=len(observed),rejected_rows=int((~good).sum()),rejected_dates=[str(x.date()) for x in f.loc[~good,'date']],first=str(observed.date.min().date()) if len(observed) else None,last=str(observed.date.max().date()) if len(observed) else None,sha256=hashlib.sha256(raw).hexdigest(),listing=listing[sym])
        except Exception as e:
            msg=str(e)
            if any(x in msg for x in ('403','418','429')):halt.set()
            return sym,dict(status='error',error=type(e).__name__+': '+msg[:250],listing=listing[sym])
    wanted=[s for s in sorted(listing) if audit['symbols'].get(s,{}).get('validation_revision')!=REVISION or not (out/f'{s}.json').exists()]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for n,future in enumerate(as_completed([pool.submit(fetch,s) for s in wanted]),1):
            sym,record=future.result();audit['symbols'][sym]=record
            if n%25==0 or n==len(wanted):
                audit['updated_at']=datetime.now(VN).isoformat();tmp=audit_path.with_suffix('.tmp');tmp.write_text(json.dumps(audit,ensure_ascii=False,separators=(',',':')),encoding='utf8');tmp.replace(audit_path)
                print(f'Real daily stock histories: {len(audit["symbols"])}/{len(listing)}; last {sym}: {record["status"]}',flush=True)
    if halt.is_set():raise RuntimeError('Provider limit/access response: stopped; no bypass')
    print('Daily banking finished:',len(audit['symbols']),flush=True)
if __name__=='__main__':run()
