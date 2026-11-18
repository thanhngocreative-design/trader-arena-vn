# Elliott Wave: Arena wave-3 hypothesis

Reference: [Elliott Wave International's formation rules](https://www.elliottwave.com/articles/elevate-your-elliott-wave-analysis/). A second wave cannot retrace beyond the beginning of the first. A complete five-wave impulse has additional constraints, including wave 3 not being the shortest motive wave. This bot enters a *candidate* third wave, so it cannot verify a completed future impulse when buying. It is a numerical research proxy, not an authoritative Elliott wave count or a claim of predictive accuracy.

Predeclared Arena assumptions:

- Use closing-price pivots, with three observations on each side for daily bars, two for minute bars. The pivot becomes observable only after the right-hand confirmation bars close. Never assign a trade signal to the earlier pivot date.
- Look for confirmed low–high–low. The first rise must be at least 4% daily, 0.6% minute. The second low must remain above the first and retrace 38.2–78.6% of the first rise.
- Signal once on a subsequent observed close above the first high. Invalidate on a break of the initial low; expire 120 daily or 60 minute observations after the first low. Same-side pivot replacement changes subsequent decisions only. Parameters are fixed before calculating results, with no profit-based search.
- Daily mode uses completed daily bars and the existing next-session execution engine. Minute mode uses each session's own minute bars and existing validity/warm-up gates. Combined mode uses the previous completed daily signal plus the shared minute breakout/VWAP confirmation. A previous-day signal expires if no eligible minute confirms during that session.
- Each account starts with VND 100 million; at most five holdings. Use the existing ATR allocation, liquidity gates, participation limits, 100-share lots, fees, taxes, slippage, settlement and strict next-bar execution. Missing required minute bars never become invented fills.
- Daily exits: 8% below entry or 2.5 daily ATR below the high-water mark. Minute exits: below MA20 or 8% below entry. Combined exits also retain the shared daily-risk/minute-confirmation engine. The theoretical wave floor is an entry-structure invalidation, not a promise that an executable stop fills at that price.

## Adding the accounts without resetting existing bots

`add_elliott.py` is an explicit one-time migration. It accepts only the pinned previous and new model hashes in `config/elliott-migration-v1.json`. Ordinary continuous updates still reject incompatible model state.

Compute all Elliott books using the original audited daily/minute bank and later immutable session observations. Use each basket's existing effective-date membership. Audit every fill against an actual positive-volume bar, causal signal time, membership, lot and settlement rules. Compute only the new bot; copy all existing public accounts, daily windows, minute account states, curves and ledgers exactly. Save new checkpoint paths and retain the previous checkpoints. The migration refuses a change to any existing account or ledger. Persist the upgrade receipt under `state/backtest_continuous/migrations/elliott-v1.json`.

There are then 17 bots × 3 baskets × 6 modes = 306 independent virtual accounts. Paper has 153; Backtest has 153, plus separately restarted daily comparison windows. Daily automation replays all 17 bots for Paper, then resumes the 17-bot Backtest checkpoint. The original Arena Hybrid candidate pool remains the original ten strategies.
