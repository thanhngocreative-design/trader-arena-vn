"""Small real-data feasibility probe, NOT a claim of full minute coverage."""
import argparse,json,hashlib,time
from pathlib import Path
from datetime import datetime
import httpx,pandas as pd,numpy as np
from vn_market_data.sources.vietcap import VietcapSource
from historical_minute import ENDPOINT,VN,validate_wire
from intraday_data import normalize_minute
ROOT=Path(__file__).resolve().parent

def run(symbols):
    metadata=json.loads((ROOT/'config/market-classification.json').read_text(encoding='utf8'))
    universe=json.loads((ROOT/'config/research-universe.json').read_text(encoding='utf8'))
    reference=pd.read_csv(ROOT/'data/prices/VNINDEX_research.csv').date
    dates=pd.DatetimeIndex(pd.to_datetime(reference));dates=dates[(dates>=universe['start'])&(dates<=universe['end'])]
    active=sorted(s for s,v in metadata['listing'].items() if v['type']=='STOCK' and v['exchange'] in ('HSX','HNX','UPCOM'))
    if not set(symbols).issubset(active):raise ValueError('Probe must use actual listed stock symbols')
    out=ROOT/'data/expansion';out.mkdir(parents=True,exist_ok=True)
    source=VietcapSource();results=[]
    with httpx.Client(timeout=30) as client:
        for sym in symbols:
            row=dict(symbol=sym,sector=metadata['sectors'].get(sym,{}).get('sector','Chưa phân loại'),daily_pass=False,minute_full_history_verified=False)
            try:
                p=out/f'{sym}-daily.json'
                if not p.exists():p.write_text(json.dumps(source.get_ohlcv(sym,universe['start'],universe['end']),ensure_ascii=False),encoding='utf8')
                f=pd.DataFrame(json.loads(p.read_text(encoding='utf8')))
                if f.empty:raise ValueError('No real daily bars')
                f['date']=pd.to_datetime(f.date);f=f.set_index('date')
                if f.index.duplicated().any():raise ValueError('Duplicate daily dates')
                f=f.reindex(dates);prices=f[['open','high','low','close']]
                valid=(np.isfinite(f).all(axis=1)&(prices>0).all(axis=1)&(f.volume>0)&(f.high>=prices.max(axis=1))&(f.low<=prices.min(axis=1)))
                row.update(daily_valid_sessions=int(valid.sum()),reference_sessions=len(dates),daily_pass=bool(valid.all()),daily_input_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                samples={}
                for name,to,expected in [('early',pd.Timestamp(universe['first_session'],tz=VN)+pd.Timedelta(days=2,hours=18),universe['first_session']),('late',pd.Timestamp(universe['end'],tz=VN)+pd.Timedelta(hours=23),universe['end'])]:
                    p=out/f'{sym}-{name}-minute.json'
                    if not p.exists():
                        response=client.post(ENDPOINT,json=dict(symbols=[sym],timeFrame='ONE_MINUTE',to=int(to.timestamp()),countBack=1000));response.raise_for_status();p.write_bytes(response.content);time.sleep(.3)
                    raw=json.loads(p.read_text(encoding='utf8'))
                    if len(raw)!=1:raise ValueError('Empty minute response')
                    bars=normalize_minute(validate_wire(raw[0],sym),'vnd');target=bars.loc[bars.index.normalize()==pd.Timestamp(expected)]
                    samples[name]=dict(expected_session=expected,observed_bars=len(target),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                row.update(minute_samples=samples,minute_endpoints_present=all(v['observed_bars']>0 for v in samples.values()))
            except Exception as e:
                row['error']=type(e).__name__+': '+str(e)[:250]
                if isinstance(e,httpx.HTTPStatusError) and e.response.status_code in (403,418,429):raise
            results.append(row);print('Expansion probe:',sym,row.get('daily_valid_sessions'),row.get('minute_endpoints_present'),row.get('error',''),flush=True)
    data=dict(asof=datetime.now(VN).isoformat(),source=metadata['source'],listed_stock_candidates=len(active),exchange_counts=metadata['active_exchange_counts'],target_min=500,target_max=600,current_verified_universe=146,additional_candidates=len(set(active)-set(universe['eligible_symbols'])),full_expansion_audit_complete=False,probed_symbols=len(results),daily_pass_count=sum(r['daily_pass'] for r in results),minute_endpoint_pass_count=sum(r.get('minute_endpoints_present',False) for r in results),probes=results,caveat='Early/late minute samples do NOT verify continuous full three-year minute history. Current listing is not point-in-time membership; 500–600 eligible symbols are not yet established.',steps=['Audit real daily history of all stock candidates against the same 747-session calendar; do not fill gaps.','Download and validate full minute history only for daily-qualified candidates, recording missing sessions and price/corporate-action mismatches.','Freeze a separate 500–600-stock study if enough pass; retain the 146-stock baseline and paper ledgers.','For a less biased market test, use point-in-time eligibility, delisted stocks where available, historical liquidity screens, corporate actions and out-of-sample validation; more symbols alone do not ensure accuracy.'])
    (ROOT/'site/expansion-audit.json').write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8')
    p=ROOT/'config/research-expansion-candidates.json';p.write_text(json.dumps(dict(asof=metadata['asof'],symbols=active,selection='Provider STOCK type on HSX/HNX/UPCOM; not yet daily/minute qualified. Not a replacement for the 146-stock universe.'),ensure_ascii=False,separators=(',',':')),encoding='utf8')
    path=ROOT/'site/sectors.json'
    if path.exists():
        data_sector=json.loads(path.read_text(encoding='utf8'));data_sector['expansion']=data;path.write_text(json.dumps(data_sector,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--symbols',default='BVH,PVI,DHG,DMC,DRC,CSM');a=p.parse_args();run(a.symbols.split(','))
