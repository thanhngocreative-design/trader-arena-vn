"""Causal membership and explicit non-trading valuation reserves for missing quotes."""
import numpy as np
import pandas as pd
from fast_engine import FastContext

class PITContext(FastContext):
    def __init__(self,prices,benchmark,months,settings,static=None,min_history=252):
        self.months=months;self.static=set(static) if static is not None else None
        calendar=benchmark.index
        clean={s:f.loc[f.index.intersection(calendar)].sort_index() for s,f in prices.items()}
        clean={s:f for s,f in clean.items() if len(f)>=min_history}
        super().__init__({s:f.reindex(calendar) for s,f in clean.items()},benchmark,settings)
        shape=(len(self.symbols),len(calendar));self.allowed=np.zeros(shape,dtype=bool)
        self.a['sma200']=np.full(shape,np.nan)
        self.quote=np.full(shape,np.nan);self.quote_index=np.full(shape,-1,dtype=int)
        self.known_adv=np.full(shape,np.nan);self.known_avol=np.full(shape,np.nan)
        for s,i in self.pos.items():
            f=clean[s];observed=f.reindex(calendar);has=observed.close.notna()
            self.a['sma200'][i]=observed.close.rolling(200).mean().to_numpy()
            self.quote[i]=observed.close.ffill().to_numpy()
            self.quote_index[i]=pd.Series(np.where(has,np.arange(len(calendar)),np.nan),index=calendar).ffill().fillna(-1).to_numpy(dtype=int)
            self.known_adv[i]=(f.close*f.volume).rolling(20).mean().shift().reindex(calendar).ffill().to_numpy()
            self.known_avol[i]=f.volume.rolling(20).mean().shift().reindex(calendar).ffill().to_numpy()
        if self.static is not None:
            for s in self.static:
                if s in self.pos:self.allowed[self.pos[s],:]=True
        else:
            ordered=sorted(months,key=lambda x:x['effective'])
            for j,row in enumerate(ordered):
                lo=calendar.searchsorted(row['effective']);hi=calendar.searchsorted(ordered[j+1]['effective']) if j+1<len(ordered) else len(calendar)
                for s in row['members']:
                    if s in self.pos:self.allowed[self.pos[s],lo:hi]=True

    def candidate_indices(self,trader,signal_idx,positions,closed_at,now_idx):
        return [i for i in super().candidate_indices(trader,signal_idx,positions,closed_at,now_idx) if self.allowed[i,now_idx]]

    def forced_exit(self,i,t):return not bool(self.allowed[i,t])

    def execution_liquidity(self,i,prev):
        if prev<0 or self.quote_index[i,prev]<0 or prev-self.quote_index[i,prev]>60:return np.nan,np.nan
        return float(self.known_adv[i,prev]),float(self.known_avol[i,prev])

    def mark_info(self,i,t,at_open=False,fallback=0.):
        own=float(self.a['open' if at_open else 'close'][i,t])
        if np.isfinite(own) and own>0:
            return dict(price=own,value_price=own,quote_date=str(self.dates[t].date()),age=0,reserve=False)
        prior=t-1 if at_open else t
        qidx=int(self.quote_index[i,prior]) if prior>=0 else -1
        price=float(self.quote[i,prior]) if qidx>=0 else float(fallback)
        age=t-qidx if qidx>=0 else t+1
        return dict(price=price,value_price=0. if age>=20 else price,quote_date=str(self.dates[qidx].date()) if qidx>=0 else None,age=age,reserve=age>=20)

    def mark_price(self,i,t,at_open=False,fallback=0.):return self.mark_info(i,t,at_open,fallback)['value_price']

    def reserve_value(self,i,t,qty):
        m=self.mark_info(i,t);return m['price']*qty if m['reserve'] else 0.
