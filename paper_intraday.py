"""Forward-only public-Vietcap minute paper; never replays history into orders.

Poller can warm indicators from old bars, but orders require a fresh completed
bar received after enrollment. Each fill requires an already saved request
whose submission precedes the observed fill bar start. This is bar-based
paper, not a bid/ask execution service. No broker credentials or orders.
"""
import argparse,json,time
from pathlib import Path
from datetime import datetime,timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import httpx,pandas as pd
from historical_minute import ENDPOINT,VN,validate_wire
from intraday_data import normalize_minute
from minute_arena import features,new_accounts,step,snapshot
from hybrid_backtest import _recent,_minute_entry_mask,_eligible_daily
from engine import TRADERS
import value_intraday as value_models
ROOT=Path(__file__).resolve().parent

def atomic(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,allow_nan=False,separators=(',',':')),encoding='utf8'); tmp.replace(path)

def export_gates(context,index,path=None):
    atomic(Path(path or ROOT/'state/paper_daily_gates.json'),dict(date=str(context.dates[index].date()),bots={k:[s for s in context.symbols if _eligible_daily(context,k,context.pos[s],index)] for k in TRADERS}))

def eligible_bar(ts,received,enrolled,watermark=None):
    ts=pd.Timestamp(ts); received=pd.Timestamp(received); enrolled=pd.Timestamp(enrolled)
    end=ts+pd.Timedelta(minutes=1)
    return (ts>=enrolled and ts.date()==received.date() and 0<=(received-end).total_seconds()<=75 and (watermark is None or ts>pd.Timestamp(watermark)))

def publish(state,status,errors=None):
    state['status']=status; state['updated_at']=datetime.now(VN).isoformat()
    # Newly created requests cannot fill any bar that has already started
    # while a polling batch or its durable write was in progress. Rounding
    # conservatively to AFTER the next minute boundary also covers disk I/O.
    not_before=pd.Timestamp.now(tz=VN).tz_localize(None).ceil('min')+pd.Timedelta(seconds=1)
    for mode in ('paper_minute','paper_combo'):
        for b in state[mode].values():
            for req in b['pending'].values():
                if not req.get('persisted'):
                    req['submitted']=max(pd.Timestamp(req['submitted']),not_before).isoformat()
                    req['persisted']=True
    public={k:state[k] for k in ('started_at','updated_at','status','last_observed_at','sessions','symbols_observed','combo_gate_date','combo_gate_valid')}
    public['errors']=(errors or [])[:8]
    public['provider_verified_at']=state.get('provider_verified_at')
    public['strategy_revisions']={'Darvas':'darvas_prior_low20_v2'}
    for key in ('contest_start_session','reset_id','reset_at'):
        if key in state: public[key]=state[key]
    public['note']='Paper theo nến đã đóng; khớp ảo ở nến tương lai sau khi lệnh đã được lưu, có phí/T+ và giới hạn khối lượng. Không phải khớp broker. Không chạy bù quá khứ. GitHub Actions có thể khởi động trễ; khoảng gián đoạn được bỏ qua.'
    for mode in ('paper_minute','paper_combo'): public[mode]=snapshot(state[mode],state['marks'])
    from sector_analytics import attach_paper_sectors
    attach_paper_sectors(public,ROOT,{mode:state[mode] for mode in ('paper_minute','paper_combo')})
    atomic(ROOT/'state/paper_intraday.json',state); atomic(ROOT/'site/paper-intraday.json',public)

def run(minutes=0):
    path=ROOT/'state/paper_intraday.json'; now=datetime.now(VN)
    state=json.loads(path.read_text(encoding='utf8')) if path.exists() else dict(started_at=now.isoformat(),last_observed_at=None,sessions=[],symbols_observed=[],marks={},watermarks={},paper_minute=new_accounts(),paper_combo=new_accounts())
    value_state=value_models.load_state(ROOT,now)
    universe=json.loads((ROOT/'config/research-universe.json').read_text(encoding='utf8'))['eligible_symbols']
    end=time.monotonic()+minutes*60
    lock=Lock(); last_request=[0.]
    def fetch(sym):
        with lock:
            delay=.3-(time.monotonic()-last_request[0])
            if delay>0: time.sleep(delay)
            last_request[0]=time.monotonic()
        with httpx.Client(timeout=18) as client:
            r=client.post(ENDPOINT,json=dict(symbols=[sym],timeFrame='ONE_MINUTE',to=int(datetime.now(VN).timestamp()),countBack=75)); r.raise_for_status()
        data=r.json()
        if len(data)!=1: raise ValueError(sym+': empty provider response')
        return sym,validate_wire(data[0],sym),datetime.now(VN)
    while True:
        now=datetime.now(VN); errors=[]; fresh=0
        value_fresh=0
        value_controls=json.loads((ROOT/'config/value-bots.json').read_text(encoding='utf8'))
        value_active={mode:{k:b for k,b in value_state[mode].items() if value_controls.get(k,True)} for mode in value_models.MODES}
        for mode in value_models.MODES:
            for k,b in value_state[mode].items():
                if not value_controls.get(k,True):b['pending'].clear()
        value_gate_path=ROOT/'state/value_daily_gates.json'
        value_gates=json.loads(value_gate_path.read_text(encoding='utf8')) if value_gate_path.exists() else {}
        value_gate_day=pd.Timestamp(value_gates.get('date','1970-01-01')).date()
        value_gate_valid=timedelta(0)<now.date()-value_gate_day<=timedelta(days=5)
        value_state.update(gate_date=value_gates.get('date'),gate_valid=value_gate_valid)
        if not value_gate_valid:
            for mode in value_models.MODES:
                for b in value_state[mode].values():b['pending'].clear()
        controls=json.loads((ROOT/'config/bots.json').read_text(encoding='utf8'))
        active={mode:{k:b for k,b in state[mode].items() if controls.get(k,True)} for mode in ('paper_minute','paper_combo')}
        for mode in active:
            for k,b in state[mode].items():
                if not controls.get(k,True): b['pending'].clear()
        # Outside common continuous windows, a single verification sample is
        # fetched. It cannot create orders; last_observed_at stays null/stale.
        market=now.weekday()<5 and ('09:16'<=now.strftime('%H:%M')<='11:31' or '13:01'<=now.strftime('%H:%M')<='14:31')
        symbols=universe if market else universe[:1]
        gp=ROOT/'state/paper_daily_gates.json'
        gates=json.loads(gp.read_text(encoding='utf8')) if gp.exists() else {}
        gate_day=pd.Timestamp(gates.get('date','1970-01-01')).date()
        valid_gates=timedelta(0)<now.date()-gate_day<=timedelta(days=5)
        def guarded(sym):
            try:return fetch(sym)
            except Exception as e:return sym,None,type(e).__name__+': '+str(e)[:180]
        with ThreadPoolExecutor(max_workers=4) as pool:
            observations=list(pool.map(guarded,symbols))
        source_ok=any(raw is not None for _,raw,_ in observations)
        if source_ok:
            state['provider_verified_at']=datetime.now(VN).isoformat()
            value_state['provider_verified_at']=state['provider_verified_at']
        events=[]
        for sym,raw,received in observations:
            if raw is None: errors.append(sym+': '+received); continue
            f=normalize_minute(raw,'vnd'); local=pd.Timestamp(received).tz_localize(None)
            f=f[(f.index.normalize()==local.normalize())&(f.index+pd.Timedelta(minutes=1)<=local)]
            if f.empty: continue
            ff=features(f); combo=_recent(f); value_rows=value_models.minute_features(f).to_dict('index')
            masks={k:_minute_entry_mask(k,combo) for k in TRADERS}
            for ts,row in ff.to_dict('index').items():
                aware=ts.tz_localize(VN)
                if not eligible_bar(aware,datetime.now(VN),state['started_at'],state['watermarks'].get(sym)):continue
                j=f.index.get_loc(ts)
                entries={k:valid_gates and sym in gates.get('bots',{}).get(k,[]) and bool(masks[k][j]) for k in TRADERS}
                events.append((ts,sym,row,entries,received,value_rows[ts]))
        # Shared cash is processed in bar-time order, never API/symbol order.
        for ts,sym,row,entries,received,value_row in sorted(events,key=lambda e:(e[0],e[1])):
            day=str(ts.date())
            if day not in state['sessions']:state['sessions'].append(day)
            seq=state['sessions'].index(day)
            submitted=pd.Timestamp.now(tz=VN).tz_localize(None)
            step(active['paper_minute'],sym,row,ts,seq,state['marks'],submitted_at=submitted)
            if valid_gates: step(active['paper_combo'],sym,row,ts,seq,state['marks'],submitted_at=submitted,entry_gates=entries)
            if value_gate_valid and eligible_bar(ts.tz_localize(VN),datetime.now(VN),value_state['started_at'],value_state['watermarks'].get(sym)):
                if day not in value_state['sessions']:value_state['sessions'].append(day)
                value_seq=value_state['sessions'].index(day)
                for mode,bots in value_active.items():
                    value_models.value_step(bots,sym,value_row,ts,value_seq,value_state['marks'],value_gates.get('bots',{}),combo=mode=='paper_combo',submitted_at=pd.Timestamp.now(tz=VN).tz_localize(None))
                value_state['watermarks'][sym]=ts.tz_localize(VN).isoformat()
                value_state['last_observed_at']=max(value_state.get('last_observed_at') or '',received.isoformat())
                if sym not in value_state['symbols_observed']:value_state['symbols_observed'].append(sym)
                value_fresh+=1
            state['watermarks'][sym]=ts.tz_localize(VN).isoformat()
            state['last_observed_at']=max(state.get('last_observed_at') or '',received.isoformat())
            if sym not in state['symbols_observed']:state['symbols_observed'].append(sym)
            fresh+=1
        # Freshness/status are explicit; no invented observations or daily NAV.
        status='scheduled_start' if pd.Timestamp(now)<pd.Timestamp(state['started_at']) else 'observing_fresh_minutes' if fresh else ('waiting_fresh_minutes' if market else 'market_closed')
        state['combo_gate_date']=gates.get('date'); state['combo_gate_valid']=valid_gates
        if fresh:
            values={m:snapshot(state[m],state['marks']) for m in ('paper_minute','paper_combo')}
            for mode,bots in values.items():
                for k,b in bots.items():
                    point=dict(date=state['last_observed_at'],nav=b['nav'],return_pct=b['return_pct'])
                    state[mode][k]['history'].append(point)
        if value_fresh:
            for mode in value_models.MODES:
                for k,b in snapshot(value_state[mode],value_state['marks']).items():
                    value_state[mode][k]['history'].append(dict(date=value_state['last_observed_at'],nav=b['nav'],return_pct=b['return_pct']))
        value_status='observing_fresh_minutes' if value_fresh else ('waiting_fresh_minutes' if market else 'market_closed')
        value_models.publish(value_state,value_status,errors,ROOT)
        publish(state,status,errors)
        print(status,'fresh bars',fresh,'errors',len(errors),flush=True)
        if minutes<=0 and not source_ok:
            raise RuntimeError('No verified response from the real minute provider; see recorded errors')
        if minutes<=0 or time.monotonic()>=end or now.strftime('%H:%M')>='14:35':break
        time.sleep(min(45,max(0,end-time.monotonic())))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=int,default=0);a=p.parse_args();run(a.minutes)
