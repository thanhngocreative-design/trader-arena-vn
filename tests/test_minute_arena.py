import pandas as pd
import numpy as np
from minute_arena import features,new_accounts,step
from live.intraday import _signals
from paper_intraday import eligible_bar


def test_vector_minute_signals_match_existing_scalar_proxies_and_are_causal():
    rng=np.random.default_rng(21); index=pd.date_range('2026-11-12 09:15',periods=120,freq='min')
    c=25000*np.exp(np.cumsum(rng.normal(0,.004,120)))
    f=pd.DataFrame(dict(open=c,high=c*1.002,low=c*.998,close=c,volume=rng.integers(10000,200000,120)),index=index)
    vector=features(f)
    for j in range(30,len(f)):
        bars=f.iloc[:j+1].rename(columns={'high':'h','low':'l'}).to_dict('records')
        scalar,_=_signals(bars)
        assert all(bool(vector.iloc[j][k])==bool(v) for k,v in scalar.items())
    changed=f.copy();changed.iloc[65:]=changed.iloc[65:]*2
    pd.testing.assert_frame_equal(features(changed).iloc[:65],vector.iloc[:65])


def row(signal=True):
    return dict(open=20000.,close=20000.,high=20100.,low=19900.,volume=100000,atr=200.,adv=10_000_000_000.,ma10=20000.,ma20=20000.,low20=19900.,Minervini=signal)


def test_future_fill_fee_liquidity_and_no_same_day_sale():
    accounts=new_accounts();marks={};ts=pd.Timestamp('2026-11-12 10:00')
    step(accounts,'FPT',row(),ts,0,marks)
    b=accounts['Minervini'];assert not b['trades'] and b['pending']
    step(accounts,'FPT',row(False),ts+pd.Timedelta(minutes=1),0,marks)
    assert len(b['trades'])==1 and b['trades'][0]['side']=='MUA'
    assert b['cash']<100_000_000-b['positions']['FPT']['qty']*20000
    assert b['positions']['FPT']['qty']<=5000
    stop=row(False);stop['close']=10000
    step(accounts,'FPT',stop,ts+pd.Timedelta(minutes=2),0,marks)
    assert not b['pending'] # T+ even if a minute stop fires
    step(accounts,'FPT',stop,ts+pd.Timedelta(minutes=3),5,marks)
    step(accounts,'FPT',stop,ts+pd.Timedelta(minutes=4),5,marks)
    assert b['trades'][-1]['side']=='BÁN'


def test_paper_receipt_time_cannot_fill_an_already_started_bar_or_bridge_gap():
    a=new_accounts();marks={};ts=pd.Timestamp('2026-11-12 10:00')
    step(a,'FPT',row(),ts,0,marks,submitted_at=ts+pd.Timedelta(seconds=65))
    step(a,'FPT',row(False),ts+pd.Timedelta(minutes=1),0,marks)
    assert not a['Minervini']['trades']
    step(a,'FPT',row(False),ts+pd.Timedelta(minutes=2),0,marks)
    assert a['Minervini']['trades'][0]['time'].endswith('10:02:00')
    a=new_accounts();marks={}
    step(a,'FPT',row(),ts+pd.Timedelta(minutes=2),0,marks)
    step(a,'FPT',row(False),ts+pd.Timedelta(minutes=6),0,marks)
    assert not a['Minervini']['trades']


def test_paper_rejects_old_future_before_enrollment_and_duplicate_bars():
    ts=pd.Timestamp('2026-11-12 10:00',tz='Asia/Ho_Chi_Minh')
    assert eligible_bar(ts,ts+pd.Timedelta(seconds=65),ts-pd.Timedelta(minutes=1))
    assert not eligible_bar(ts,ts+pd.Timedelta(minutes=4),ts-pd.Timedelta(minutes=1))
    assert not eligible_bar(ts,ts+pd.Timedelta(seconds=65),ts+pd.Timedelta(seconds=1))
    assert not eligible_bar(ts,ts+pd.Timedelta(seconds=30),ts-pd.Timedelta(minutes=1))
    assert not eligible_bar(ts,ts+pd.Timedelta(seconds=65),ts-pd.Timedelta(minutes=1),ts)


def test_forward_worker_orders_shared_cash_by_bar_time_not_provider_order(tmp_path,monkeypatch):
    """Synthetic wire fixture stays in temporary test files, never published."""
    import json
    from datetime import datetime
    import paper_intraday as worker
    from historical_minute import VN
    (tmp_path/'config').mkdir();(tmp_path/'state').mkdir()
    (tmp_path/'config/research-universe.json').write_text(json.dumps({'eligible_symbols':['ACB','FPT']}))
    (tmp_path/'config/bots.json').write_text('{}')
    state=dict(started_at='2026-11-12T09:15:00+07:00',last_observed_at=None,sessions=['2026-11-12'],symbols_observed=[],marks={},watermarks={'FPT':'2026-11-12T09:59:00+07:00','ACB':'2026-11-12T09:59:00+07:00'},paper_minute=new_accounts(),paper_combo=new_accounts())
    b=state['paper_minute']['Minervini']
    for sym,signal,submitted in [('FPT','09:58','09:59:05'),('ACB','09:59','10:00:05')]:
        b['pending'][sym]=dict(side='BUY',qty=5000,budget=100_000_000,signal='2026-11-12T'+signal,submitted='2026-11-12T'+submitted,adv=10_000_000_000,persisted=True)
    (tmp_path/'state/paper_intraday.json').write_text(json.dumps(state))
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None): return datetime(2026,11,12,10,2,5,tzinfo=VN)
    class Reply:
        def __init__(self,sym): self.sym=sym
        def raise_for_status(self): pass
        def json(self):
            times=pd.date_range('2026-11-12 09:15',end='2026-11-12 '+('10:01' if self.sym=='ACB' else '10:00'),freq='min',tz=VN)
            return [dict(symbol=self.sym,t=[int(x.timestamp()) for x in times],o=[20000]*len(times),h=[20000]*len(times),l=[20000]*len(times),c=[20000]*len(times),v=[100000]*len(times))]
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,json):return Reply(json['symbols'][0])
    monkeypatch.setattr(worker,'ROOT',tmp_path);monkeypatch.setattr(worker,'datetime',Clock)
    monkeypatch.setattr(worker.httpx,'Client',Client)
    worker.run()
    actual=json.loads((tmp_path/'state/paper_intraday.json').read_text())
    buys=actual['paper_minute']['Minervini']['trades']
    assert len(buys)==1 and buys[0]['symbol']=='FPT'
    assert not actual['paper_combo']['Minervini']['trades']
    assert len(actual['paper_minute']['Minervini']['history'])==1
    assert actual['last_observed_at']=='2026-11-12T10:02:05+07:00'
