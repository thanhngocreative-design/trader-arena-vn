"""Paper statistics from the complete ledger, never the UI's recent-trade list."""
import math


def paper_metrics(trades,history,current_nav,initial_cash=100_000_000):
    buys=sum(t['side']=='MUA' for t in trades)
    sells=[t for t in trades if t['side']=='BÁN']
    drawdown=None
    if history:
        peak=float(initial_cash); worst=0.
        for nav in [float(h['nav']) for h in history]+[float(current_nav)]:
            if not math.isfinite(nav) or nav<0: raise ValueError('Invalid observed paper NAV')
            peak=max(peak,nav)
            worst=min(worst,(nav/peak-1)*100)
        drawdown=round(worst,2)
    return dict(buy_count=buys,closed_trades=len(sells),
        win_rate=round(sum(t['pnl']>0 for t in sells)/len(sells)*100,1) if sells else None,
        max_drawdown_pct=drawdown,observed_history_points=len(history))
