# Monte Carlo implementation plan — not simulation results

Status: planned. No Monte Carlo probabilities or synthetic paths have been
published. Keep all observed Backtest and Paper results unchanged.

## 1. Build an audited daily return panel

For each of the six books and three baskets, export the exact saved daily NAV
of all 19 bots, including cash, open positions, recorded costs and unrealized
losses. Reconcile starting capital, ending NAV and every calendar date against
the source books. Never replace missing NAV with a price, guessed return or
forward-filled row. Use the shared verified session calendar, excluding exchange
holidays. Save source hashes, model version, cutoff and bot identifiers.

Minute and combined books also use daily NAV returns for this portfolio-risk
analysis; do not treat individual minute bars as independent profit samples.
Use independent observed bot accounts, not a hypothetical executable pooled
account. Mixing N bots starts with N times VND 100 million.

## 2. Generate joint block-bootstrap scenarios

Primary method: resample contiguous 10-session blocks of observed daily return
vectors, with replacement, into 10,000 paths for a declared 252-session horizon.
Select the SAME block indices for every bot in a scope. This preserves observed
cross-bot co-movement within each sampled day and serial behavior within blocks.
Use sensitivity runs with 5- and 20-session blocks; do not optimize block length
for an attractive outcome. Save random seed, sample length and implementation
version for exact reproduction. Generate in batches with a bounded memory budget.

Require at least 252 common observed return sessions for the primary report.
Short Paper seasons show “insufficient history” and their observed track record;
do not extrapolate a few Paper weeks into confident annual probabilities.
Bootstrap paths are hypothetical recombinations of recorded NET returns, not
real market candles or a fresh replay of orders, prices, cash and T+ settlement.
They cannot model an unseen crash or newly emerging market regime reliably.

## 3. Evaluate bots and fixed Mix groups

Report terminal NAV/return p5, p50 and p95, median and p95 maximum drawdown,
fraction of paths finishing below initial capital, fraction crossing 20%/30%
drawdown, and average terminal loss in the worst 5% of scenarios. Label every
probability as conditional on the observed sample and bootstrap assumptions.

Include each bot, All, and Mix 2–6 using the exact currently selected members.
Freeze membership before resampling; never pick the winner separately in each
simulated path. Sum constituent account NAVs at each step; do not accidentally
turn a fixed-account Mix into a daily-rebalanced equal-weight portfolio.

Historical Best Mix was selected using historical performance. Its bootstrap
report is descriptive and selection-biased. A separate evaluation must select
Mix members on training data only, freeze them for the next holdout window,
and repeat walk-forward. Do not present the in-sample Best Mix as a forecast.

## 4. Validate, then add the dashboard view

Tests must verify reconciliation against observed NAV, exact random-seed
reproduction, joint block alignment, drawdown and tail-loss calculations,
unchanged actual ledgers, frozen Mix membership and rejection of missing/short
samples. Test a small saved real sample before the full 18-scope run.

Add a separate “Monte Carlo — hypothetical scenarios” section tied to the current
book, basket and selected group. Show a percentile fan chart, terminal-outcome
distribution, risk metrics, sample dates and observation count. Explain that p5
is a scenario percentile, not a guaranteed floor or a confidence interval for
the true future return. Existing leaderboards continue to display observed results.

Optional later work: execution-cost sensitivity using recorded turnover and
incremental costs only, or full causal market-path replay. These require separate
methodology and validation; do not invent slippage, candles or fills to make the
initial NAV-bootstrap report look like an execution simulator.
