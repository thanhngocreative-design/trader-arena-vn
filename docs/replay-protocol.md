# Monthly universe and six-book execution protocol

Revision: `strict_next_candle_v1`. Thirteen bots each have three historical
backtests and three independent EOD paper replay accounts.

## Universe

At the first actual benchmark session of each month, select the 300 highest
observed-turnover stocks using only earlier sessions. Require 252 prior valid
positive-volume daily observations, at least 40 of the last 60 benchmark
sessions observed, and at least one observation in the last five sessions.
Rank the sum of observed close × volume divided by 60 reference sessions;
ticker order breaks ties. Do not filter on subsequent survival, returns,
continuous trading over the whole study, or minute availability.

The historical study covers 747 sessions from 2023-11-13 through 2026-11-12,
37 monthly selections and 498 distinct names. 497 have in-window minute
observations. SJF has no in-window positive-volume trades and stays in its
original ex-ante selection; no replacement survivor is substituted.

Names outside current membership cannot enter. Existing positions can only
exit on real observed trading candles with settlement and liquidity guards.
The monthly universe exit rule is a model policy, not advance knowledge of
delisting. No sale, cash recovery, zero market price or corporate action is
invented for a disappeared security. After 20 missing-quote benchmark sessions,
the existing conservative NAV reserve remains separate from actual last price.

## Shared execution

* Minute signal uses a completed candle labeled t. Its order can fill only at
  the real positive-volume open of t+1 minute, in the same continuous session.
  If that candle is absent, invalid or quarantined, the old request expires.
  A later observed candle can create its own fresh request.
* Common modeled windows are 09:15–11:29 and 13:00–14:29 Vietnam time. Auctions
  and breaks are excluded. No order bridges lunch, session end or overnight.
* Daily signals use a completed daily candle and may execute at the next
  benchmark session's real positive-volume open. If the stock has no valid
  candle in that session, no fill occurs. A later daily observation can lead
  to a fresh decision; persistent exit intent is reevaluated with facts known
  before each session.
* Combined bots use the previous completed day's screen and completed minute
  signals, followed by the exact next-minute fill. There is no current day's
  final high, low, close or volume in intraday entry decisions.
* Lot sizes, per-bot position caps, ATR risk sizing for the 11 technical bots,
  NAV allocations for Buffett/Munger, fees, tax, liquidity caps, cooldown and
  five-session minimum sale holding guard remain in force. Buffett/Munger
  minute variants are experimental adaptations, not their actual strategies.

## Paper operation and recovery

Paper replay starts 2026-11-13, with 100 million VND per bot per independent
book. Old forward journals are retained byte-for-byte under
`state/paper_archive/before-eod-replay-2026-11-13/` and are no longer advanced.
They are not added to the new replay accounts. The original 146 and previous
300 historical results also remain in the archive/Git history.

`paper-replay.yml` runs at 16:47 and retries at 18:47 Vietnam weekdays. Before
16:00 it cannot consume the current day's candles. An observed benchmark daily
candle is required; a weekday alone does not manufacture a trading session.
Wire requests are bounded and stop on provider access/rate errors.

Daily candidate data is collected for the frozen 1,757-name source catalog
so future monthly ranking does not depend on current 300 membership. Minute
data covers current and previously selected paper-season names, including
potential retained holdings. New IPOs absent from that frozen catalog require
an audited catalog update; this limitation is not silently hidden.

The actual baseline daily histories and each collected session are compressed
and retained in `state/replay_market/`, outside the public dashboard. Source
hashes protect previously committed inputs. Positive-volume minute/daily
price disagreement beyond the existing 8% band quarantines that session.
An absent minute is not automatically described as provider data loss: it can
also mean no trade or a suspension. No gap is filled with made-up OHLCV.

The season is deterministically reconstructed with the same engines as the
backtest, with cash and holdings carried forward. All prior committed trade
prefixes must match exactly before publishing. Retrying the same completed
session replaces a derived view and cannot double-count trades. If validation
fails, the prior published account stays in use; a recovery artifact retains
banked source inputs. Annual statements use the frozen real dated statement
bundle; updated statements need versioned ingestion without rewriting earlier
paper decisions. No unavailable financial numbers are filled in.

Paper performance is only published after a completed session is collected
and verified. An account awaiting its first session displays initialized capital
and no recorded results; it does not reuse a historical backtest as paper.

Source security-master coverage, revised annual statements, adjusted OHLCV and
current ICB labels still impose the limitations described in research-300.md.
This reduces survivor selection bias; it does not establish a perfect original
historical security master or guarantee executable broker prices.
