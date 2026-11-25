# Wyckoff and Ichimoku research hypotheses

These are predeclared Arena models, not authenticated personal trade histories.
References: [Wyckoff methodology](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial)
and [Ichimoku construction](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/ichimoku-cloud).

Wyckoff uses a spring proxy. Calculate support/resistance from the preceding
30 observed bars, excluding the signal bar. Require a range no wider than 25%
for daily bars or 4% for minutes. A spring penetrates support by at most 3% daily
or 0.8% minute, closes back above support and within resistance, and has volume
at least 0.8 times the previous 20-bar average. During the next 10 daily or 20
minute observations, enter once after closing above the spring high with volume
over 1.2 times the previous average. A new low below the spring low permanently
invalidates that structure. This does not label every Wyckoff accumulation phase.

Ichimoku uses high/low midpoints over 9, 26 and 52 bars. The cloud at time t is
Senkou A/B calculated 26 bars earlier. Require price above both boundaries,
Tenkan above Kijun, price above its close 26 bars earlier, and currently computed
Senkou A above B. Signal only on transition into this regime. Do not shift a
future close backward to obtain Chikou confirmation. Minimum cloud warm-up is
78 observed bars. Minute variants are experimental adaptations, calculated
only from observed minutes of each actual session.

Both use the existing next-bar execution, lot sizes, fees, taxes, slippage,
participation limits, settlement, missing-bar cancellation and ATR allocation.
Wyckoff permits five holdings; Ichimoku permits six. Daily Wyckoff exits at an
8% entry loss or 2.5 ATR below high-water; daily Ichimoku exits below Kijun or at
an 8% entry loss. Minute exits use MA20 or an 8% loss. Combined books use the
previous completed daily signal and the existing minute confirmation/risk rules.
No parameter was selected by maximizing the new bots' backtest returns.

The additive migration computes only these two bots from the original verified
three-year minute bank and subsequent immutable sessions, for all three baskets.
Each gets its own VND 100 million account. Existing 153 Paper and 153 Backtest
accounts, trade ledgers, curves, daily comparison windows and checkpoint files
must remain unchanged. Backfilled Paper history is retrospective simulation.
The original ten-strategy Arena Hybrid candidate pool remains unchanged.
