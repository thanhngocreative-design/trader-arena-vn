# Portfolio policy atr_v1

The active research now uses only the 146-stock continuous three-year universe;
see README_RESEARCH146.md. Old public backtests and comparison snapshots were
removed at the user's request. The original paper journal is preserved in
state/paper_baseline.json and the running ledger remains state/paper_state.json.

Research position limits (not claims about the real traders' portfolios):
Minervini 6, ONeil 7, Darvas 5, BNF 3, CIS 3, Qullamaggie 5, Unger 8,
ThaiPham 6, DuongChung 4, PThai 8, Hybrid 6.

Entry notional is capped by available cash, NAV / the bot's position limit,
and NAV * 0.0075 / (2.5 * completed prior-day ATR + entry fee per share)
times entry price. Lot size, historical liquidity, fees and slippage caps
still apply. Missing/invalid ATR rejects an entry. Existing strategy exit
rules remain in force. This ATR distance is a sizing proxy, not a guaranteed
loss cap; gaps, missing liquidity and T+ holding restrictions can exceed it.

The paper contest continues without rewriting past trades or NAV. Its full
ledger is retained. Research results and paper results are separate accounts.
