# VN30 theo từng thời kỳ

The study uses actual effective-date membership, not today's thirty stocks held
constant backwards. `config/research-vn30.json` contains the verified membership
events, conservative known-by dates, source URLs and available source hashes.
Reserve stocks are not members. The initial January 2022 row is explicitly a
training-start snapshot of the then-existing list, not a claimed index review.

## Membership changes in the study

| Effective session | Added | Removed |
| --- | --- | --- |
| 2023-08-07, carried into the study | SHB, SSB | NVL, PDR |
| 2024-02-05 | no change | no change |
| 2024-08-05 | no change | no change |
| 2025-02-03 | LPB | POW |
| 2025-08-04 | DGC | BVH |
| 2026-02-02 | VPL | BCM |
| 2026-05-13, off-cycle | BSR | DGC |
| 2026-08-03 | MCH, TCX | PLX, TPB |

The frozen test period is 2023-11-13 through 2026-11-12, 747 benchmark sessions,
thirty members per session and 36 distinct study members. Training membership
from 2022 includes 40 distinct stocks. Warm-up indicators still require their
actual trailing observations; membership itself does not impose monthly300's
252-observation admission screen.

Sources are HOSE tables mirrored by Vietstock for 2022/2023/2024/2025; the DSC
**actual result** report corroborates the unchanged July 2024 membership and
August 5 effective date. January 2026's original HOSE table was visually
checked against [the reproduced table](https://image.vietstock.vn/2026/01/22/danh-muc-vn30-q12026.png).
July 2026's original table was also visually checked against
[this reproduction](https://image.fili.vn/2026/07/15/vn30-ky-thang-7-2026.png).
The off-cycle event is corroborated by the HOSE notice linked in the May 8 SSI
actual review and [BSR's disclosure](https://bsr.com.vn/vi/web/bsr/w/co-phieu-bsr-chinh-thuc-lot-ro-vn30-tu-13-5-2026).
Forecast portfolios were not used as final membership evidence.

## Six independent books

Run `python vn30.py` with the verified local daily/minute source bank to produce
three backtest books, all thirteen bots, and the five existing daily periods.
The result is `site/research-vn30.json`. Full trade ledgers and resumable
checkpoints stay under the ignored `data/pit_results/vn30-v1/` directory.
Changed frozen inputs require a fresh output directory; old results are not
silently resumed under a different signature.

Run the monthly source collector first, then `python paper_vn30.py` for three
independent VN30 paper books. Paper starts 2026-11-13 with 100 million VND cash
per bot/book and no inherited backtest positions. The canonical strict next
continuous candle engine, costs, share lots, settlement guard and ATR sizing
are unchanged. Absence of the required candle cancels the order. No candles,
delisting exits or results are fabricated.

The paper runner shares the immutable actual daily source bank. It banks only
any additional minute symbols in `state/replay_market/vn30-sessions/`; it never
rewrites the two existing baskets' session files. It verifies all fills and
refuses changes to previously used membership or committed trade prefixes.
A real repeat of the first session produced identical state and 39 ledgers.
The scheduled workflow now replays 117 accounts across all three universes.

## Limits

The bots trade individual stocks; they do not replicate VN30 weights. VN-Index
remains the shared performance benchmark. Each historical member-day has actual
daily data and at least one verified continuous minute, not necessarily all
225 minute slots. Provider-adjusted price and annual-statement vintage limits
remain the same as in the two existing studies. This does not establish that a
bot would have achieved the simulated prices with real orders.

Membership has been checked through 2026-11-13. A new verified notice must be
appended for future scheduled or off-cycle changes; a calendar forecast is not
accepted as a replacement membership list. Already-used paper membership and
trade records are immutable. The latest verified list continues until the next
verified effective notice is recorded.
