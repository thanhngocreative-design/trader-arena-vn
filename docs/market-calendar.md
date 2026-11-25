# Verified exchange closures in replay

The monthly collector already refused to invent a session when no real benchmark
candle existed. However, dependent baskets and continuous Backtest reconstructed
all weekdays and required a bank file for 24 November 2026. This made the first
post-holiday update fail even though 25 November's real inputs had been banked.

`config/market-closures.json` records explicit, sourced exchange closures.
`market_calendar.session_candidates` removes those dates before both collection
and reconstruction. It does not infer a holiday from missing or invalid candles.
All other weekdays retain the existing source validation and missing-bank errors.
24 November is sourced to HNX's trading-holiday notice and Vietcap's notice;
trading resumed on 25 November. No empty or fabricated candle file is created.

The calendar and its configuration are included in the strict model fingerprint.
`ops/upgrade_market_calendar.py` is a pinned one-time compatibility upgrade from
the existing model. It checks unchanged trading-source hashes, all frozen market
inputs, every account checkpoint hash, and rejects any closure that overlaps the
previously published session calendar. It updates only model metadata and saves
an audit receipt; it never resets accounts or modifies past checkpoint files.
