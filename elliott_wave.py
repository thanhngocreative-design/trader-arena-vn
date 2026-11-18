"""Predeclared wave-3 entry proxy; confirmed pivots never backdate a signal.

Elliott's wave-2 invalidation is a theory rule. Pivot delays, retracement range,
minimum amplitude, expiry and risk exits below are Arena research assumptions.
We do not label a completed five-wave impulse using future observations.
"""
import numpy as np
import pandas as pd

SOURCE='https://www.elliottwave.com/articles/elevate-your-elliott-wave-analysis/'
PROFILE=dict(name='Elliott Wave',emoji='🌊',region='US',flag='🇺🇸',
    tag='Sóng Elliott · tìm nhịp sóng 3',
    explain='Chờ đáy–đỉnh–đáy được xác nhận, nhịp hồi 38,2–78,6% còn trên đáy đầu; mua khi giá vượt đỉnh sóng 1.',
    detail='Mô hình sóng 3 định lượng của Arena, không phải bộ đếm Elliott đầy đủ. Pivot dùng giá đóng cửa, chỉ xác nhận sau 3 nến ngày hoặc 2 nến phút; không vẽ ngược tín hiệu. Sóng 1 tối thiểu 4% ngày hoặc 0,6% phút; cấu trúc hết hạn sau 120/60 nến. Ngày + phút dùng cấu trúc ngày hôm trước và xác nhận breakout/VWAP phút. Thoát ngày khi lỗ 8% hoặc giảm 2,5 ATR từ đỉnh; phút dưới MA20 hoặc lỗ 8%. Tối đa 5 mã, vốn 100 triệu, phân bổ ATR và cùng phí/T+/luật khớp nến kế tiếp. Tham số đặt trước, chưa tối ưu theo lợi nhuận.',
    source=SOURCE,
    supported_modes=['paper_minute','paper','paper_combo','backtest_minute','backtest','hybrid'])


def entries(close,*,minute=False):
    """Series or independent stock columns; no centered rolling or future shift.

    At row t the candidate pivot is t-right, confirmed only by bars <=t.
    Replacing an extreme affects subsequent decisions only. One signal per
    confirmed 0-1-2 structure; a close below wave 0 invalidates that structure.
    """
    if isinstance(close,pd.DataFrame):
        return pd.DataFrame({k:entries(close[k],minute=minute) for k in close},index=close.index)
    right=2 if minute else 3;left=right
    amplitude=.006 if minute else .04;expiry=60 if minute else 120
    pivot=close.shift(right)
    prior=close.shift(right+1).rolling(left)
    after=close.rolling(right)
    lows=(pivot<prior.min())&(pivot<after.min())
    highs=(pivot>prior.max())&(pivot>after.max())
    events=np.flatnonzero((lows|highs).to_numpy())
    c=close.to_numpy(dtype=float);p=pivot.to_numpy(dtype=float)
    low=lows.to_numpy();out=np.zeros(len(c),dtype=bool);swings=[];used=set()
    for j,t in enumerate(events):
        kind=-1 if low[t] else 1;item=(kind,float(p[t]),int(t-right))
        if swings and swings[-1][0]==kind:
            if kind*item[1]>kind*swings[-1][1]:swings[-1]=item
        else:swings.append(item)
        swings=swings[-3:]
        if len(swings)!=3 or [x[0] for x in swings]!=[-1,1,-1]:continue
        a,b,d=swings;width=b[1]-a[1]
        if a[1]<=0 or width/a[1]<amplitude or not a[1]<d[1]<b[1]:continue
        retrace=(b[1]-d[1])/width
        if not .382<=retrace<=.786:continue
        key=tuple(x[2] for x in swings)
        if key in used:continue
        stop=min(int(events[j+1]) if j+1<len(events) else len(c),a[2]+expiry+1)
        prices=c[t:stop]
        # Once the wave-0 floor breaks, the prior count cannot reappear later.
        invalid=np.flatnonzero((prices<=a[1])|~np.isfinite(prices))
        if len(invalid):prices=prices[:invalid[0]];used.add(key)
        hits=np.flatnonzero(prices>b[1])
        if len(hits):out[t+int(hits[0])]=True;used.add(key)
    return pd.Series(out,index=close.index,name=close.name)
