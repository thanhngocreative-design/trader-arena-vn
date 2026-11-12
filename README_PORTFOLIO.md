# Portfolio policy atr_v1

The frozen pre-upgrade files are in `site/baseline-v1/`, copied from commit
`aebf31761b06f7d3def27556afdd2d6267d63f1e`. Never regenerate these files.
The existing paper ledger continues in place without rewriting historical fills
or NAVs. Revision 4 clears pending entries and queues new decisions after the
migration session; existing holdings are not forcibly liquidated to meet a cap.

Limits (research assumptions, not the real traders' portfolios):
Minervini 6, ONeil 7, Darvas 5, BNF 3, CIS 3, Qullamaggie 5, Unger 8,
ThaiPham 6, DuongChung 4, PThai 8, Hybrid 6.

For each entry, notional is capped by cash, NAV / the bot's position limit,
and NAV * 0.0075 / (2.5 * prior completed daily ATR + entry fee per share)
times entry price. Lot size, fees, slippage and historical liquidity limits
still apply. Missing or invalid ATR rejects the entry. The ATR distance is a
sizing proxy; existing strategy exit rules remain in force, and gaps/T+ holding
restrictions can produce losses larger than the assumed risk budget.

The dashboard Backtest page compares baseline 4/equal allocation with atr_v1
for five identical daily windows, universes and cost assumptions. Total order
count includes buys and sells; drawdown is signed peak-to-trough NAV change.
Each policy trains its own causal Hybrid selector from its own past core NAVs.
Frozen original backtests remain downloadable independently of fresh reruns.
This is a joint policy comparison, not attribution of gains to ATR alone.

Only the existing real DNSE/Vietcap data adapter produces published results.
Regression tests may use synthetic fixtures, which never enter the dashboard.
The Daily+1m pilot and realtime account remain independent; daily comparisons
are never advertised as minute or live performance.

Daily workflow tests, refreshes real market data, computes both policies and
publishes GitHub Pages. Missing/invalid data stops publication. The policy does
not remove the existing 2026-survivor universe bias or corporate-action limits.
