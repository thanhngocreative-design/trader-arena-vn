# Independent cloud replay watchdog

Deployment status (2026-11-18 Vietnam): **active and verified end to end**.
Cloudflare's native scheduled handler began at 02:43:34, observed real session
2026-11-17, and received GitHub's successful dispatch receipt at 02:43:39 for
[run 44161675845](https://github.com/thanhngocreative-design/trader-arena-vn/actions/runs/44161675845).
The matching GitHub run is a workflow_dispatch on main at commit 39d64b3.
Paper replay, its required Backtest job, and both Pages deployments succeeded.
The cloud decision log records action=dispatch_paper, dispatched=true,
verification=true and the same run_id; this was not a local CLI dispatch.

The bounded commissioning cron was removed immediately after dispatch, within
its 15-minute window. The commissioning flag is back to `disabled`. Reloading
settings confirmed DRY_RUN=false, the encrypted GITHUB_TOKEN, and only the two
normal weekday expressions. No always-on personal computer is needed.

The first commissioning attempt exposed Workers' unsupported redirect:error
mode. Requests now use manual redirect handling and reject non-success statuses
without following Location headers or forwarding credentials. A native workerd
regression test exercises current-book checks, dispatch receipts, read-only health
and redirect rejection with isolated HTTP contract fixtures and a retained real
benchmark candle. Test fixtures never become published trading results.

Comparison of baseline 39d64b3 with published commit eaa1b1b verified all 144 Paper
accounts and all 144 Backtest trade ledgers unchanged when replaying the same
session. Paper source hashes, session calendars, and the simulation model hash
also remain unchanged. The latest completed market session is 2026-11-17.

Worker: https://trader-arena-cloud-watchdog.thanhngo-creative.workers.dev/
The public endpoint responds correctly; this alone does not verify scheduled execution.
The production `/health` endpoint subsequently returned
`{"action":"current","target":"2026-11-17","observed_cutoff":"2026-11-17"}`.
This verifies real provider, published metadata and authenticated GitHub reads
from Cloudflare after the fix. It does not prove a scheduled dispatch succeeds.
`/health` always overrides DRY_RUN=true and disables commissioning; it never
dispatches even with production credentials. Successful replies are cached for
five minutes under a normalized key, and errors are uncached HTTP 503 responses.
The published Paper and Backtest health both report session 2026-11-17.

Cloudflare Cron checks at 16:55, 17:25, 18:55 and 20:25 on weekdays, Vietnam time.
It observes actual positive-close/positive-volume VN-Index daily candles from
the same Vietcap endpoint as the simulation. Holidays do not become invented
sessions. Since 24 November, `target` is the completed-weekday refresh boundary;
`market_observed` separately records the latest real candle returned to the Worker.
A stale probe no longer declares yesterday's outputs current. It requests the
normal collector, which still refuses to invent a session without actual candles.
Dependent Paper baskets use the monthly collector's confirmed, banked session,
so an unavailable current session does not cause an unbanked-input error.
Cooldown, in-flight detection and the three-failure circuit breaker remain active.

The Worker reads the published compact Paper and Backtest metadata. It skips
current results, queued/running pipelines, and recent attempts. If Paper is
behind, it dispatches `paper-replay.yml` on `main`, including its required
Backtest job. If only Backtest is behind, it dispatches `continuous-backtest.yml`.
Three recent failures stop automatic retries and require inspection. Source or
API errors fail visibly in Cloudflare logs; they never generate trading results.

## Credentials and activation

1. Use the account owner's Cloudflare Workers Free account. No paid plan, domain,
   billing upgrade, local always-on computer or market archive upload is needed.
2. Create a fine-grained GitHub token limited to **this repository only**, with
   **Actions: read and write**. No repository Contents write permission is needed.
   The owner must approve this new access. Set an appropriate expiration and
   arrange rotation before expiry. Never put the token in chat, Git, screenshots
   or configuration files.
3. Authenticate the official Wrangler CLI with the owner's Cloudflare account.
   From the repository root, install the pinned project version and deploy in
   the mode recorded in wrangler.toml (currently production; set DRY_RUN=true
   explicitly when commissioning a separate installation):

   ```powershell
   npm ci --prefix ops/cloud-watchdog
   npm --prefix ops/cloud-watchdog run deploy
   ```

   The owner enters the GitHub token directly into Cloudflare's secret UI, or a
   documented hidden secret prompt. Its binding name is `GITHUB_TOKEN`. The secret
   is sent only to Cloudflare and then used only with api.github.com for this repo.
4. Verify a scheduled invocation in Cloudflare logs. Confirm the real latest
   observed session and that an already-running GitHub pipeline is skipped.
5. Set `DRY_RUN = "false"` and redeploy only after the secret and behavior are
   verified. Exercise the GitHub dispatch through the cloud runner, then verify
   the resulting run and its published session. A deployment URL alone is not
   proof of unattended execution. Leave the production weekday schedule enabled.

The public HTTP endpoint is read-only and cannot dispatch workflows. A cloud
scheduled event is the only execution entry point. The token is never returned
or logged. Dry-run is the code default; absent credentials cannot silently activate
writes. Configuring this Worker does not weaken the simulation's candle, causal
execution, accounting or checkpoint verification.

For an explicitly approved commissioning test when all books are current, set
`VERIFY_DISPATCH_TARGET` to the exact real observed session date. This requests
an idempotent Paper replay on main, with the usual active-run, 30-minute cooldown,
three-failure and DRY_RUN guards. It does not replace any source or health data.
Immediately disable this flag after the verified dispatch. The deployed value
is currently `disabled`; it is deliberately absent from the normal config.

Validation after activation: all 128 repository tests passed with
`python -m pytest -q tests`; the cloud watchdog's 15 Node tests and its native
workerd runtime test passed; GitHub CI
run 44158620879 passed for commit 39d64b3, including native runtime tests. The
cloud-triggered Paper and Backtest jobs also passed their own 128-test checks.
Bare local pytest also discovers tests
in the ignored upstream skill installation clone; those unrelated Bash-based
tests fail on this Windows machine where Bash is unavailable. The clean GitHub
checkout does not include that ignored installation clone.

## Validation

```powershell
python replay_health.py
python -m pytest -q tests/test_replay_health.py
node ops/cloud-watchdog/probe.mjs
npm --prefix ops/cloud-watchdog run test:runtime
```

The last command reads live public endpoints without any credential or write.
GitHub can rate-limit this unauthenticated probe; the deployed Worker uses the
repository-limited token for GitHub requests. A rate-limit error is not a passed
end-to-end check and must not be hidden by an invented API response.
The health publisher refuses missing bots, old NAV points and incomplete baskets.
HTTP contract fixtures are test-only and never become market or performance data.

References: [Cloudflare Cron](https://developers.cloudflare.com/workers/configuration/cron-triggers/),
[Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/),
[GitHub workflow dispatch permissions and responses](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).
