# Research 146 stocks, 13 November 2023 to 12 November 2026

The user-selected universe is frozen in config/research-universe.json. Each
of its 146 stocks has valid daily OHLCV and positive trading volume on all 747
reference sessions. An exchange transfer is allowed if the data stays continuous.
The continuity condition uses knowledge of the whole window and therefore has
survivorship/selection bias. It is not an unbiased point-in-time stock universe.

The research benchmark is fetched from Vietcap, not interpolated. It includes
12 August 2024, which was absent from the prior cached DNSE VNINDEX series.
Daily warm-up prices before November 2023 train indicators and the causal
Hybrid selector; reported performance starts in the selected research window.

Run:

    python historical_minute.py
    python run_research_146.py --refresh-benchmark

All source prices stay in ignored data/ directories. Publication contains only
simulated statistics, a limited trade journal, coverage counts and source hashes.
Downloads are resumable. Invalid prices, symbol/unit mismatches, non-progressing
pagination or provider errors stop the run. Missing observed bars are never
filled. A stock may have a valid daily bar yet lack continuous-minute bars on
some days; those gaps are disclosed per stock, not converted into artificial
trades. The model still values held positions using actual daily closes.

ATR policy atr_v1 applies to the new study. The old public backtests and
baseline-v1 research files are removed at the user's request. The live paper
ledger and its original paper-only baseline remain intact. Daily refreshes
apply the verified site/research-146.json snapshot so the old backtest universe
cannot silently reappear. The older 8-stock banking workflow cannot overwrite
the 146-stock research. This snapshot remains explicitly historical as of
12 November 2026, even if the paper contest later advances to a new session.

The simulator uses completed prior daily data plus completed minute signals,
next-observed-bar opening fills within three minutes, 100-share lots, a 5% cap
of preceding minute volume, past daily participation limits, fees, sell tax,
slippage, cooldown and a conservative minimum holding period. Stops are not
promises of execution. Missing liquidity and gaps can cause larger losses than
the ATR sizing proxy. Published trades are simulations, not actual broker fills.

ITC daily inputs are fetched from Vietcap because the cached DNSE daily series
differed from the actual Vietcap minute/session close on 28 August, 3 September
and 4 September 2026. No prices are manually rescaled to fit; the source daily
candles are preserved and their hash is disclosed in research metadata.
