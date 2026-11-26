"""Joint moving-block bootstrap of recorded NAV returns, not market candles."""
import math
import numpy as np

REVISION='joint_nav_bootstrap_v1'
SETTINGS=dict(paths=10000,horizon=252,blocks=[5,10,20],primary_block=10,seed=20261126,min_sessions=252)


def nav_returns(nav,capital):
    values=np.asarray(nav,dtype=np.float64)
    if values.ndim!=2 or not values.shape[0] or not values.shape[1] or not np.isfinite(values).all() or (values<0).any() or not np.isfinite(capital) or capital<=0:
        raise ValueError('Invalid observed NAV panel')
    previous=np.vstack([np.full((1,values.shape[1]),capital),values[:-1]])
    if ((previous==0)&(values!=0)).any():raise ValueError('Unexplained recovery after zero NAV; cash-flow model required')
    result=np.zeros_like(values)
    np.divide(values-previous,previous,out=result,where=previous>0)
    if not np.isfinite(result).all() or (result < -1).any():raise ValueError('Invalid recorded return')
    return result


def bootstrap_paths(returns,*,block=10,paths=10000,horizon=252,seed=20261126,batch=256,filename=None):
    r=np.asarray(returns,dtype=np.float64)
    if r.ndim!=2 or not np.isfinite(r).all() or (r < -1).any():raise ValueError('Invalid return panel')
    if not all(isinstance(x,int) and x>0 for x in (block,paths,horizon,batch)) or block>len(r):raise ValueError('Invalid bootstrap settings')
    # Generate block starts once, so changing batch size cannot change scenarios.
    starts=np.random.default_rng(seed).integers(0,len(r)-block+1,size=(paths,math.ceil(horizon/block)))
    shape=(paths,horizon+1,r.shape[1])
    out=np.memmap(filename,dtype='float64',mode='w+',shape=shape) if filename else np.empty(shape,dtype=np.float64)
    out[:,0,:]=1.
    for first in range(0,paths,batch):
        last=min(paths,first+batch)
        indices=(starts[first:last,:,None]+np.arange(block)).reshape(last-first,-1)[:,:horizon]
        growth=1+r[indices]
        np.cumprod(growth,axis=1,out=growth)
        if not np.isfinite(growth).all():raise ValueError('Scenario overflow; refusing nonfinite results')
        out[first:last,1:,:]=growth
    return out


def group_summary(wealth,indices,capital_each,*,detail=True):
    if not indices or len(set(indices))!=len(indices) or any(not isinstance(i,int) or i<0 or i>=wealth.shape[2] for i in indices):raise ValueError('Invalid fixed Mix')
    total=np.zeros(wealth.shape[:2],dtype=np.float64)
    for index in indices:total+=wealth[:,:,index]
    initial=capital_each*len(indices);total*=capital_each
    terminal=(total[:,-1]/initial-1)*100
    peaks=np.maximum.accumulate(total,axis=1)
    drawdown=(1-total/peaks).max(axis=1)*100
    quantiles=np.percentile(terminal,[5,50,95])
    metrics=dict(return_p5_pct=float(quantiles[0]),return_p50_pct=float(quantiles[1]),return_p95_pct=float(quantiles[2]),
        loss_probability_pct=float(np.mean(total[:,-1]<initial-1e-7)*100),
        dd_p50_pct=float(np.percentile(drawdown,50)),dd_p95_pct=float(np.percentile(drawdown,95)),
        dd20_probability_pct=float(np.mean(drawdown>=20-1e-10)*100),dd30_probability_pct=float(np.mean(drawdown>=30-1e-10)*100),
        worst5_return_pct=float(np.sort(terminal)[:max(1,math.ceil(len(terminal)*.05))].mean()))
    result=dict(capital=initial,metrics={k:round(v,6) for k,v in metrics.items()})
    if detail:
        q=np.percentile(total,[5,50,95],axis=0)
        result['fan']=[[i,*[round(float(q[j,i])) for j in range(3)]] for i in range(total.shape[1])]
        counts,edges=np.histogram(terminal,bins=24)
        result['histogram']=[dict(low=float(edges[i]),high=float(edges[i+1]),count=int(n)) for i,n in enumerate(counts)]
    return result
