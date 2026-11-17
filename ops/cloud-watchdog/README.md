# Independent cloud replay watchdog

Deployment status: **prepared; not activated until Cloudflare authentication,
the repository-limited secret, and a real cloud invocation have been verified**.
Do not describe GitHub's daily schedule as fixed merely because manual replay works.

Cloudflare Cron checks at 16:55, 17:25, 18:55 and 20:25 on weekdays, Vietnam time.
It observes actual positive-close/positive-volume VN-Index daily candles from
the same Vietcap endpoint as the simulation. Holidays do not become invented
sessions. If the provider is stale, the log's `target` can precede `observed_cutoff`;
this is not proof that the exchange was closed.

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
   the default read-only mode:

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
or logged. Dry-run is the default; absent credentials cannot silently activate
writes. Configuring this Worker does not weaken the simulation's candle, causal
execution, accounting or checkpoint verification.

## Validation

```powershell
python replay_health.py
python -m pytest -q tests/test_replay_health.py
node ops/cloud-watchdog/probe.mjs
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
