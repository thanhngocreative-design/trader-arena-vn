"""Actual continuous, positive-volume bars; no replacement of missing securities."""
import hashlib,pickle
import numpy as np
import pandas as pd
from intraday_data import normalize_minute
from value_investing import ROOT,read,write
from pit_universe import load_daily

def load_minutes():
    config=read(ROOT/'config/research-300.json');audit=read(ROOT/'data/pit_minute/audit.json');old=read(ROOT/'data/minute_history/audit.json');original=read(ROOT/'config/research-universe.json')['eligible_symbols']
    symbols=sorted(set(config['eligible_symbols'])|set(original));daily,_,_=load_daily();out=ROOT/'data/pit_results/minute-normalized';out.mkdir(exist_ok=True)
    frames={};coverage={}
    for n,s in enumerate(symbols,1):
        r=audit['symbols'].get(s)
        if not r and s in old['symbols']:r=dict(old['symbols'][s],path=f'data/minute_history/{s}.csv.gz',status='verified')
        if not r:raise ValueError('Unaudited symbol '+s)
        if r['status'] not in ('verified','no_in_window_minutes'):
            coverage[s]=dict(status=r['status'],reason=r.get('error'));continue
        source=ROOT/r['path'];digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=r['sha256']:raise ValueError('Changed minute input '+s)
        cached=out/f'{s}.pkl';meta=out/f'{s}.json';daily_digest=config['daily_input_sha256'].get(s)
        if cached.exists() and meta.exists() and read(meta).get('minute_sha256')==digest and read(meta).get('daily_sha256')==daily_digest:
            f=pd.read_pickle(cached);record=read(meta)
        else:
            raw=pd.read_csv(source)
            if raw.empty:
                f=pd.DataFrame(columns=['open','high','low','close','volume'],index=pd.DatetimeIndex([],name='time'))
                observed_daily=daily[s].loc[config['start']:config['end']]
                record=dict(status='no_in_window_trades_consistent_daily' if observed_daily.empty else 'minute_data_missing',minute_sha256=digest,daily_sha256=daily_digest,raw_bars=0,bars=0,missing_minute_with_daily=[str(x.date()) for x in observed_daily.index],price_mismatch_sessions=[])
            else:
                wire_times=pd.to_datetime(raw.time).dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None).dt.normalize()
                full_close=raw.loc[raw.volume>0].groupby(wire_times).close.last()
                comparison=full_close.to_frame('minute').join(daily[s].close.rename('daily')).dropna();ratio=comparison.minute/comparison.daily
                mismatches=ratio.index[(ratio<.92)|(ratio>1.08)]
                f=normalize_minute(raw,'vnd');zero=int((f.volume<=0).sum());f=f.loc[(f.volume>0)&~f.index.normalize().isin(mismatches)]
                observed=f.index.normalize().unique();expected=daily[s].loc[config['start']:config['end']].index
                record=dict(status='verified_with_gaps' if len(expected.difference(observed)) or len(mismatches) else 'verified',minute_sha256=digest,daily_sha256=daily_digest,raw_bars=len(raw),zero_volume_excluded=zero,bars=len(f),missing_minute_with_daily=[str(x.date()) for x in expected.difference(observed)],price_mismatch_sessions=[str(x.date()) for x in mismatches])
            f.to_pickle(cached);write(meta,record)
        frames[s]=f;coverage[s]=record
        if n%25==0:print('Verified normalized minute stocks',n,'/',len(symbols),flush=True)
    target=ROOT/'data/pit_results/minute-coverage.json'
    if not target.exists() or read(target)!=coverage:write(target,coverage)
    return frames,coverage

def wide_features(frames):
    """Same core predicates as minute_arena.features, rolling each stock column.

Rows are each stock's own observed-bar ordinal, not a filled minute grid.
Actual timestamps retain gaps and session resets. Padding never emits events.
"""
    symbols=sorted(s for s,f in frames.items() if len(f));height=max((len(frames[s]) for s in symbols),default=0)
    matrices={k:np.full((height,len(symbols)),np.nan) for k in ('open','high','low','close','volume','seconds')}
    for j,s in enumerate(symbols):
        f=frames[s]
        for k in ('open','high','low','close','volume'):matrices[k][:len(f),j]=f[k].to_numpy(dtype=float)
        matrices['seconds'][:len(f),j]=f.index.asi8/1_000_000_000
    p={k:pd.DataFrame(v,columns=symbols) for k,v in matrices.items()}
    c,h,l,v=p['close'],p['high'],p['low'],p['volume'];before=c.shift()
    hi10=h.shift().rolling(10).max();hi20=h.shift().rolling(20).max();hi30=h.shift().rolling(30).max()
    low10=l.shift().rolling(10).min();low30=l.shift().rolling(30).min()
    ma5=c.rolling(5).mean();ma10=c.rolling(10).mean();ma20=c.rolling(20).mean()
    vf=v/v.shift().rolling(20).mean();m3=c/c.shift(3)-1;m10=c/c.shift(10)-1;m20=c/c.shift(20)-1;m30=c/c.shift(30)-1
    vol=c.rolling(30).std(ddof=0)/c
    valid=(c>=5000)&((vol>=.0002)&(vol<=.12))&((c/before-1).abs()<.075)&(p['seconds'].diff().rolling(10).max()<=120)
    warm=np.arange(height)>=30
    raw={
        'Minervini':(ma5>ma10)&(ma10>ma20)&(c>hi20)&(m20>.008)&(vf>1.18),
        'ONeil':(c>hi30)&(m30>.015)&(vf>1.45)&(c>ma20),
        'Darvas':(hi30/low30-1<.095)&(c>hi20)&(c>ma20)&(vf>1.10),
        'BNF':(m20<-.014)&(m3>.003)&(c>before)&(vf>.90),
        'CIS':(m3>.0045)&(m10>.011)&(ma5>ma10)&(vf>1.28),
        'Qullamaggie':(m30>.02)&(hi10/low10-1<.025)&(c>hi10)&(vf>1.20),
        'Unger':(c>hi20)&(ma10>ma20)&(vol>.003)&(vol<.045)&(vf>1.05),
        'ThaiPham':(c>hi20)&(c>ma5)&(m10>.007)&(vf>1.55),
        'DuongChung':(c<ma20*.995)&(m3>.004)&(m20<-.012)&(vf>.85),
        'PThai':(ma10>ma20)&(m20>.012)&(vol>.004)&(vol<.05)&(c>hi10)&(vf>1.10)}
    for k,m in raw.items():p[k]=(valid&m).to_numpy()&warm[:,None]
    p['Hybrid']=sum(p[k].astype(int) for k in ('Minervini','ONeil','CIS','Qullamaggie','PThai'))>=2
    p['Buffett']=(valid&(c<=ma20*.998)&(c>before)&(vf>=.8)).to_numpy()&warm[:,None]
    p['Munger']=(valid&(c>=ma20)&(c<=ma20*1.005)&(c>ma10)&(vf>=1.)).to_numpy()&warm[:,None]
    tr=np.fmax((h-l).to_numpy(),np.fmax((h-before).abs().to_numpy(),(l-before).abs().to_numpy()))
    p['atr']=pd.DataFrame(tr,columns=symbols).rolling(14).mean();p['adv']=(c*v).rolling(20).mean()*225
    p['ma10']=ma10;p['ma20']=ma20;p['low20']=l.shift().rolling(20).min()
    return symbols,{k:x if isinstance(x,np.ndarray) else x.to_numpy() for k,x in p.items()}

if __name__=='__main__':load_minutes()
