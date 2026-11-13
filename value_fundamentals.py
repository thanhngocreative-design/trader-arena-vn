"""Real annual statements with conservative publication/update timestamps.

Never infer filing dates. Missing fields/dates exclude a report. Revised values
are withheld until the provider's update date; original vintages are unavailable.
"""
import json,hashlib,math
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
from threading import Event
import pandas as pd
from vn_market_data.sources.vietcap import VietcapSource
from historical_minute import VN
ROOT=Path(__file__).resolve().parent
LABELS={'sales':'Net sales','profit':'Net profit/(loss) after tax','equity':"Owner's Equity",'short_debt':'Short-term borrowings','long_debt':'Long-term borrowings','cfo':'Net cash inflows/(outflows) from operating activities','capex':'Purchases of fixed assets and other long term assets'}
SECTIONS=('INCOME_STATEMENT','BALANCE_SHEET','CASH_FLOW')

def numeric(row,titles,label,prefix):
    codes=[k for k,v in titles.items() if str(v).strip().casefold()==label.casefold() and k.startswith(prefix)]
    if len(codes)!=1:return None
    value=row.get(codes[0])
    return float(value) if isinstance(value,(int,float)) and math.isfinite(value) else None

def report_available(row):
    public=row.get('publicDate')
    if not public:return None
    try:
        stamps=[pd.Timestamp(public)]
        for key in ('updateDate','createDate'):
            if row.get(key):stamps.append(pd.Timestamp(row[key]))
        stamps=[x.tz_convert(VN).tz_localize(None) if x.tzinfo else x for x in stamps]
        if any(pd.isna(x) or x.year<1990 or x.year>2100 for x in stamps):return None
        # Decisions use end-of-day facts, fills a later session. One full day
        # lag also avoids ambiguous naive provider timestamp timezones.
        return (max(stamps).normalize()+pd.Timedelta(days=1)).date().isoformat()
    except (ValueError,TypeError):return None

def parse_reports(payloads,titles):
    by=[]
    for section in SECTIONS:
        groups={}
        for r in payloads.get(section,{}).get('years',[]):
            year=r.get('yearReport');available=report_available(r)
            if year is None or r.get('lengthReport')!=5 or not available:continue
            # Keep the newest supplied version; never use its revised values
            # before its update timestamp, even if publicDate is much earlier.
            if year not in groups or available>groups[year][0]:groups[year]=(available,r)
        by.append(groups)
    reports=[]
    for year in sorted(set(by[0])&set(by[1])&set(by[2])):
        inc=by[0][year][1];bal=by[1][year][1];cf=by[2][year][1]
        values={k:numeric(inc if k in ('sales','profit') else bal if k in ('equity','short_debt','long_debt') else cf,titles,label,'isa' if k in ('sales','profit') else 'bsa' if k in ('equity','short_debt','long_debt') else 'cfa') for k,label in LABELS.items()}
        if any(v is None for v in values.values()):continue
        values.update(year=int(year),available_at=max(g[year][0] for g in by))
        reports.append(values)
    return reports

def collect(refresh=False,symbols=None,output=None,allow_missing=False):
    symbols=symbols or json.loads((ROOT/'config/research-universe.json').read_text(encoding='utf8'))['eligible_symbols']
    out=ROOT/'data/value_fundamentals';out.mkdir(parents=True,exist_ok=True)
    halt=Event()
    def one(sym):
        if halt.is_set():return sym,{'status':'halted','reports':[]}
        try:
            src=VietcapSource();payloads={};hashes={}
            for section in SECTIONS:
                path=out/f'{sym}-{section}.json'
                if refresh or not path.exists():
                    data=src._iq(f'/v1/company/{sym}/financial-statement',what=f'{sym} {section}',params={'section':section})
                    path.write_text(json.dumps(data or {},ensure_ascii=False,separators=(',',':')),encoding='utf8')
                payloads[section]=json.loads(path.read_text(encoding='utf8'));hashes[section]=hashlib.sha256(path.read_bytes()).hexdigest()
            path=out/f'{sym}-metrics.json'
            if refresh or not path.exists():path.write_text(json.dumps(src._titles(sym),ensure_ascii=False,separators=(',',':')),encoding='utf8')
            titles=json.loads(path.read_text(encoding='utf8'));hashes['metrics']=hashlib.sha256(path.read_bytes()).hexdigest()
            reports=parse_reports(payloads,titles)
            return sym,dict(status='verified' if reports else 'no_usable_dated_nonfinancial_reports',reports=reports,sha256=hashes)
        except Exception as e:
            if any(s in str(e) for s in ('403','418','429')):halt.set()
            return sym,dict(status='error',error=type(e).__name__+': '+str(e)[:240],reports=[])
    result={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for n,future in enumerate(as_completed([pool.submit(one,s) for s in symbols]),1):
            s,row=future.result();result[s]=row
            if n%10==0:print('Real dated annual statements:',n,'/',len(symbols),flush=True)
    if halt.is_set() or (not allow_missing and any(r['status'] in ('error','halted') for r in result.values())):
        raise RuntimeError('Incomplete provider refresh; retained last verified bundle, no bypass')
    bundle=dict(asof=datetime.now(VN).isoformat(),source='Vietcap IQ financial-statement + metrics',universe=symbols,companies=result,availability_rule='max(publicDate, updateDate, createDate) + 1 calendar day; no inferred filing dates; snapshots lack original vintages; missing comparable nonfinancial fields excluded')
    target=Path(output) if output else out/'verified.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(bundle,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8')
    print('Usable annual reports:',sum(bool(r['reports']) for r in result.values()),'companies',flush=True)
    return bundle
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--refresh',action='store_true');parser.add_argument('--config');parser.add_argument('--output');parser.add_argument('--allow-missing',action='store_true')
    a=parser.parse_args();symbols=json.loads(Path(a.config).read_text(encoding='utf8'))['eligible_symbols'] if a.config else None
    collect(a.refresh,symbols,a.output,a.allow_missing)
