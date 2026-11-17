// Cloud-only operational watchdog. Never calculates or edits trading results.
export const REPO = 'thanhngocreative-design/trader-arena-vn';
export const API = `https://api.github.com/repos/${REPO}`;
export const SITE = 'https://thanhngocreative-design.github.io/trader-arena-vn/';
export const MARKET = 'https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart';
const PATHS = new Set(['.github/workflows/paper-replay.yml', '.github/workflows/continuous-backtest.yml']);
const ACTIVE = new Set(['queued', 'in_progress', 'waiting', 'requested', 'pending']);

export function cutoff(now) {
  const local = new Date(now.getTime() + 7 * 3600000);
  if (local.getUTCHours() < 16) local.setUTCDate(local.getUTCDate() - 1);
  while ([0, 6].includes(local.getUTCDay())) local.setUTCDate(local.getUTCDate() - 1);
  return local.toISOString().slice(0, 10);
}

export function latestSession(wire, end) {
  if (!Array.isArray(wire) || wire.length !== 1 || wire[0].symbol !== 'VNINDEX') throw Error('Invalid benchmark response');
  const {t, c, v} = wire[0];
  if (![t, c, v].every(Array.isArray) || !t.length || t.length !== c.length || t.length !== v.length) throw Error('Invalid benchmark arrays');
  const observed = [], seen = new Set();
  // Vietcap also encodes numeric arrays as strings; match the canonical loader's numeric conversion.
  const number = value => typeof value === 'number' || (typeof value === 'string' && value.trim() !== '') ? Number(value) : NaN;
  for (let i = 0; i < t.length; i++) {
    const stamp = number(t[i]), close = number(c[i]), volume = number(v[i]);
    if (![stamp, close, volume].every(Number.isFinite) || !Number.isInteger(stamp) || stamp <= 0 || seen.has(stamp) || close <= 0 || volume < 0) throw Error('Invalid benchmark candle');
    seen.add(stamp);
    const local = new Date(stamp * 1000 + 7 * 3600000), day = local.toISOString().slice(0, 10);
    if (day <= end && ![0, 6].includes(local.getUTCDay()) && volume > 0) observed.push(day);
  }
  if (!observed.length) throw Error('No real completed benchmark session observed');
  return observed.sort().at(-1);
}

function paperEnd(p) {
  if (p?.revision !== 'replay_health_v1' || p.status !== 'complete' || !Array.isArray(p.bot_ids) || !p.bot_ids.length || new Set(p.bot_ids).size !== p.bot_ids.length) throw Error('Invalid Paper health');
  if (Object.keys(p.baskets || {}).sort().join(',') !== '146,300,vn30' || !/^\d{4}-\d{2}-\d{2}$/.test(p.end)) throw Error('Incomplete Paper health');
  if (p.accounts !== p.bot_ids.length * 9 || Object.values(p.baskets).some(b => b.end !== p.end || b.accounts !== p.bot_ids.length * 3 || b.sessions < 1)) throw Error('Paper baskets disagree');
  return p.end;
}

export function plan({paper, backtest, runs, target, now, verifyTarget}) {
  const p = paperEnd(paper);
  if (backtest?.status !== 'complete' || !/^\d{4}-\d{2}-\d{2}$/.test(backtest.end) || !Array.isArray(backtest.bots)) throw Error('Invalid Backtest health');
  if (p > target || backtest.end > target) throw Error('Provider observation is older than published results');
  const sameBots = [...backtest.bots].sort().join('\0') === [...paper.bot_ids].sort().join('\0');
  const current = p === target && backtest.end === target && sameBots;
  // Owner-operated commissioning only: rerun real, already-current books for this
  // exact observed session. Never invent a stale session to test dispatch access.
  const verify = current && verifyTarget === target;
  if (current && !verify) return {action: 'current', target};
  if (!Array.isArray(runs)) throw Error('Invalid Actions response');
  const relevant = runs.filter(r => r.head_branch === 'main' && PATHS.has(r.path));
  const active = relevant.find(r => ACTIVE.has(r.status));
  if (active) return {action: 'in_flight', target, run_id: active.id};
  const recent = relevant.filter(r => {
    const started = Date.parse(r.run_started_at || r.created_at);
    return Number.isFinite(started) && now.getTime() - started < 30 * 60000;
  });
  if (recent.length) return {action: 'cooldown', target};
  const today = relevant.filter(r => String(r.run_started_at || r.created_at).slice(0, 10) === now.toISOString().slice(0, 10));
  if (today.filter(r => r.conclusion === 'failure').length >= 3) throw Error('Three failed pipeline runs; inspection required');
  return {action: !verify && p === target ? 'dispatch_backtest' : 'dispatch_paper', target,
    ...(verify ? {verification: true} : {})};
}

async function json(fetcher, url, options = {}) {
  // Workers does not implement redirect:error. Reject 3xx below without ever
  // following a Location header (especially with a GitHub Authorization header).
  const response = await fetcher(url, {...options, redirect: 'manual', signal: AbortSignal.timeout(20000)});
  if (!response.ok) throw Error(`HTTP ${response.status} reading ${new URL(url).hostname}`);
  return response.json();
}

export async function check(env, {fetcher = fetch, now = new Date()} = {}) {
  const end = cutoff(now), until = Date.parse(end + 'T00:00:00+07:00') / 1000 + 86400;
  const wire = await json(fetcher, MARKET, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({symbols: ['VNINDEX'], timeFrame: 'ONE_DAY', to: until, countBack: 5})});
  const target = latestSession(wire, end), suffix = '?watchdog=' + now.getTime();
  const [paper, backtest] = await Promise.all(['replay-status.json', 'backtest-status.json'].map(name => json(fetcher, SITE + name + suffix, {headers: {'Cache-Control': 'no-cache'}})));
  const headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'trader-arena-cloud-watchdog', 'X-GitHub-Api-Version': '2026-03-10'};
  if (env.GITHUB_TOKEN) headers.Authorization = 'Bearer ' + env.GITHUB_TOKEN;
  // Consult main-branch Actions before dispatching, including old runs re-run today.
  const actions = await json(fetcher, API + '/actions/runs?branch=main&per_page=100', {headers});
  const result = {...plan({paper, backtest, runs: actions.workflow_runs, target, now, verifyTarget: env.VERIFY_DISPATCH_TARGET}), observed_cutoff: end};
  if (!result.action.startsWith('dispatch_')) return result;
  if (env.DRY_RUN !== 'false') return {...result, action: 'would_' + result.action};
  if (!env.GITHUB_TOKEN) throw Error('GitHub Actions token is not configured');
  const workflow = result.action === 'dispatch_paper' ? 'paper-replay.yml' : 'continuous-backtest.yml';
  const response = await fetcher(API + '/actions/workflows/' + workflow + '/dispatches', {
    method: 'POST', headers: {...headers, 'Content-Type': 'application/json'},
    body: JSON.stringify({ref: 'main'}), redirect: 'manual', signal: AbortSignal.timeout(20000)
  });
  if (![200, 204].includes(response.status)) throw Error('GitHub dispatch failed: HTTP ' + response.status);
  if (response.status === 200) {
    const receipt = await response.json();
    if (!Number.isInteger(receipt.workflow_run_id) || receipt.workflow_run_id <= 0) throw Error('GitHub accepted dispatch but returned an invalid run receipt');
    return {...result, dispatched: true, run_id: receipt.workflow_run_id};
  }
  return {...result, dispatched: true};
}

export default {
  async scheduled(_event, env) {
    const result = await check(env);
    console.log(JSON.stringify(result));
  },
  async fetch(request) {
    if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method not allowed', {status: 405});
    return Response.json({service: 'trader-arena-cloud-watchdog', version: 1, http: 'read-only; execution requires a scheduled event'});
  }
};
