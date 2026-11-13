"""Seed real replay inputs from the verified bank; never synthesize OHLCV/bars."""
import hashlib,json,shutil
from datetime import datetime
import pandas as pd
from paper_replay import ROOT,START,MARKET,VN,ENDPOINT,read,write,unpack,pack

def archive_previous():
    previous='2026-11-13';archive=ROOT/'state/paper_archive'/('season-'+previous)
    files=['site/paper-replay.json','site/paper-fixed146.json','site/paper-vn30.json','state/paper_replay.json','state/paper_fixed146.json','state/paper_vn30.json']
    archive.mkdir(parents=True,exist_ok=True);manifest={}
    for name in files:
        src=ROOT/name;dest=archive/name.replace('/','__')
        if dest.exists():raw=dest.read_bytes()
        else:
            raw=src.read_bytes()
            if name.startswith('site/') and read(src)['season_start']!=previous:raise ValueError('Old paper view must be archived before changing its season')
            dest.write_bytes(raw)
        manifest[name]=hashlib.sha256(raw).hexdigest()
        if name.startswith('site/'):
            public=ROOT/'site/paper-archive'/previous/src.name;public.parent.mkdir(parents=True,exist_ok=True)
            if public.exists() and public.read_bytes()!=raw:raise ValueError('Archived public paper changed')
            if not public.exists():public.write_bytes(raw)
    target=archive/'manifest.json'
    if target.exists() and read(target)!=manifest:raise ValueError('Paper archive manifest changed')
    write(target,manifest)

def seed():
    archive_previous();base_path=MARKET/'daily-history.json.gz';base=unpack(base_path)
    digest=hashlib.sha256(base_path.read_bytes()).hexdigest();cfg=read(ROOT/'config/research-300.json')
    month=[r for r in cfg['months'] if r['effective']<=START][-1]
    if month['effective']!=START:raise ValueError('Season must begin at the frozen monthly basket effective session')
    members=sorted(month['members']);fixed=read(ROOT/'config/research-universe.json')['eligible_symbols']
    benchmark={r['date']:r for r in base['benchmark'] if START<=r['date']<=base['asof'][:10]}
    days=sorted(d for d in benchmark if not (MARKET/'sessions'/f'{d}.json.gz').exists())
    daily={day:{s:[r for r in rows if r['date']==day] for s,rows in base['prices'].items()} for day in days}
    sessions={day:dict(date=day,requested_symbols=members,source=ENDPOINT,banking_method='reused_verified_historical_bank',daily_bank_sha256=digest,banked_at=datetime.now(VN).isoformat(),minute_input_sha256={},replies={'VNINDEX':{'ONE_DAY':[benchmark[day]]}}) for day in days}
    extras={day:{} for day in days};audit=read(ROOT/'data/pit_minute/audit.json')['symbols'];old=read(ROOT/'data/minute_history/audit.json')['symbols']
    for n,s in enumerate(sorted(set(members)|set(fixed)),1):
        record=audit.get(s) or dict(old[s],path='data/minute_history/'+s+'.csv.gz',status='verified')
        if record['status'] not in ('verified','no_in_window_minutes'):raise ValueError('Unverified actual minute source '+s)
        path=ROOT/record['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Changed actual minute source '+s)
        raw=pd.read_csv(path);raw.time=pd.to_datetime(raw.time,utc=True);labels=raw.time.dt.tz_convert(VN).dt.date.astype(str)
        for day in days:
            observed=raw.loc[labels==day];rows=json.loads(observed.to_json(orient='records',date_format='iso'))
            if s in members:
                sessions[day]['replies'][s]={'ONE_DAY':daily[day].get(s,[]),'ONE_MINUTE':rows}
                sessions[day]['minute_input_sha256'][s]=record['sha256']
            else:extras[day][s]=rows
        if n%50==0:print('Verified historical paper minute sources',n,'/',len(set(members)|set(fixed)),flush=True)
    for day in days:
        if set(sessions[day]['replies'])!={'VNINDEX',*members}:raise ValueError('Incomplete actual session bank')
        pack(MARKET/'sessions'/f'{day}.json.gz',sessions[day]);pack(MARKET/'candidate-days'/f'{day}.json.gz',daily[day])
        pack(MARKET/'fixed146-sessions'/f'{day}.json.gz',dict(date=day,source=ENDPOINT,requested_symbols=sorted(extras[day]),banking_method='reused_verified_historical_bank',replies=extras[day]))
        print('Seeded actual historical completed session',day,flush=True)
    write(ROOT/'state/paper_seasons'/START/'source-provenance.json',dict(season_start=START,basket_effective=month['effective'],basket_asof=month['asof'],seeded_sessions=days,source=ENDPOINT,daily_bank_sha256=digest,no_interpolation=True,note='ONE_DAY date rows are copied from the immutable verified bank; ONE_MINUTE rows retain actual observed timestamps and raw-source SHA256. No missing bars are created. Original 2026-11-13 input files and prior-season ledgers remain untouched.'))

if __name__=='__main__':seed()
