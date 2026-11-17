// HTTP fixtures are confined to these tests; no market results are generated.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import worker, {check, cutoff, latestSession, plan, API, SITE, MARKET} from './worker.mjs';

const bank = JSON.parse(gunzipSync(readFileSync(new URL('../../state/replay_market/sessions/2026-11-16.json.gz', import.meta.url))));
const rows = bank.replies.VNINDEX.ONE_DAY;
const wire = [{symbol: 'VNINDEX', t: rows.map(r => Date.parse(r.time || r.date + 'T00:00:00+07:00') / 1000), c: rows.map(r => r.close), v: rows.map(r => r.volume)}];
const now = new Date('2026-11-16T14:00:00Z');
const paper = () => ({revision: 'replay_health_v1', status: 'complete', end: '2026-11-16', bot_ids: ['test-account'], accounts: 9,
  baskets: Object.fromEntries(['300', '146', 'vn30'].map(k => [k, {end: '2026-11-16', accounts: 3, sessions: 11}]))});
const stale = () => {const p = paper();p.end = '2026-11-13';for (const b of Object.values(p.baskets)) b.end = p.end;return p;};
const backtest = end => ({status: 'complete', end});
const run = overrides => ({id: 1, head_branch: 'main', path: '.github/workflows/paper-replay.yml', status: 'completed', conclusion: 'success', run_started_at: '2026-11-16T09:00:00Z', ...overrides});
const decision = (extra = {}) => plan({paper: stale(), backtest: backtest('2026-11-13'), runs: [], target: '2026-11-16', now, ...extra});

test('VN cutoff handles midnight, before close, and weekends', () => {
  assert.equal(cutoff(new Date('2026-11-17T01:00:00Z')), '2026-11-16');
  assert.equal(cutoff(new Date('2026-11-17T17:01:00Z')), '2026-11-17');
  assert.equal(cutoff(new Date('2026-11-15T10:00:00Z')), '2026-11-13');
});
test('target comes from a retained real benchmark candle, not an invented session', () => {
  assert.equal(latestSession(wire, '2026-11-16'), '2026-11-16');
  assert.throws(() => latestSession(wire, '2026-11-13'), /No real/);
  const duplicate = structuredClone(wire);for (const key of ['t', 'c', 'v']) duplicate[0][key].push(duplicate[0][key][0]);
  assert.throws(() => latestSession(duplicate, '2026-11-16'), /Invalid/);
  assert.throws(() => latestSession([{symbol: 'VNINDEX', t: [1], c: [], v: [1]}], '2026-11-16'), /arrays/);
});
test('dispatches only the missing stage', () => {
  assert.equal(decision().action, 'dispatch_paper');
  assert.equal(decision({paper: paper()}).action, 'dispatch_backtest');
  assert.equal(decision({paper: paper(), backtest: backtest('2026-11-16')}).action, 'current');
});
test('recognizes an older run that was re-run today and an independently running Backtest', () => {
  for (const path of ['.github/workflows/paper-replay.yml', '.github/workflows/continuous-backtest.yml'])
    assert.equal(decision({runs: [run({path, status: 'in_progress', created_at: '2026-11-13T00:00:00Z'})]}).action, 'in_flight');
  assert.equal(decision({runs: [run({status: 'queued'})]}).action, 'in_flight');
});
test('cooldown and three-failure circuit breaker prevent retry storms', () => {
  assert.equal(decision({runs: [run({run_started_at: '2026-11-16T13:50:00Z', conclusion: 'failure'})]}).action, 'cooldown');
  assert.throws(() => decision({runs: [1, 2, 3].map(id => run({id, conclusion: 'failure'}))}), /Three failed/);
});
test('partial metadata and source regression never count as success', () => {
  const p = paper();p.baskets.vn30.end = '2026-11-13';
  assert.throws(() => decision({paper: p}), /disagree/);
  assert.throws(() => decision({backtest: backtest('2026-11-17')}), /older/);
  assert.throws(() => decision({runs: undefined}), /Actions/);
});

function mock({p = stale(), b = backtest('2026-11-13'), runs = [], marketStatus = 200, dispatchStatus = 204} = {}) {
  const calls = [];
  return {calls, fetcher: async (url, options = {}) => {
    calls.push({url, options});
    assert.equal(options.redirect, 'error');
    if (!url.startsWith(API)) assert.equal(options.headers?.Authorization, undefined, 'Do not send GitHub credentials to another host');
    if (url === MARKET) return Response.json(wire, {status: marketStatus});
    if (url.startsWith(SITE + 'replay-status.json')) return Response.json(p);
    if (url.startsWith(SITE + 'backtest-status.json')) return Response.json(b);
    if (url.startsWith(API + '/actions/runs?')) return Response.json({workflow_runs: runs});
    if (url.endsWith('/dispatches')) return dispatchStatus === 200 ? Response.json({workflow_run_id: 12345}) : new Response(null, {status: dispatchStatus});
    throw Error('Unexpected URL ' + url);
  }};
}
test('dry run verifies actual HTTP contract without a write', async () => {
  const m = mock();const result = await check({}, {fetcher: m.fetcher, now});
  assert.equal(result.action, 'would_dispatch_paper');
  assert.equal(m.calls.filter(c => c.url.endsWith('/dispatches')).length, 0);
});
test('live dispatch uses main and only the fixed repository with no market output mutation', async () => {
  for (const [p, workflow] of [[stale(), 'paper-replay.yml'], [paper(), 'continuous-backtest.yml']]) {
    const m = mock({p});const result = await check({DRY_RUN: 'false', GITHUB_TOKEN: 'test-only-placeholder'}, {fetcher: m.fetcher, now});
    assert.equal(result.dispatched, true);
    const writes = m.calls.filter(c => c.url.endsWith('/dispatches'));
    assert.equal(writes.length, 1);assert.equal(writes[0].url, API + '/actions/workflows/' + workflow + '/dispatches');
    assert.deepEqual(JSON.parse(writes[0].options.body), {ref: 'main'});
  }
});
test('current results and in-flight pipeline produce no dispatch', async () => {
  for (const opts of [{p: paper(), b: backtest('2026-11-16')}, {runs: [run({status: 'waiting'})]}]) {
    const m = mock(opts);await check({DRY_RUN: 'false', GITHUB_TOKEN: 'test-only-placeholder'}, {fetcher: m.fetcher, now});
    assert.equal(m.calls.filter(c => c.url.endsWith('/dispatches')).length, 0);
  }
});
test('recognizes the 2026 API dispatch receipt as well as legacy 204', async () => {
  const m = mock({dispatchStatus: 200});
  const result = await check({DRY_RUN: 'false', GITHUB_TOKEN: 'test-only-placeholder'}, {fetcher: m.fetcher, now});
  assert.equal(result.dispatched, true);assert.equal(result.run_id, 12345);
});
test('provider errors, absent credential and dispatch rejection fail visibly', async () => {
  let m = mock({marketStatus: 503});await assert.rejects(check({}, {fetcher: m.fetcher, now}), /HTTP 503/);
  m = mock();await assert.rejects(check({DRY_RUN: 'false'}, {fetcher: m.fetcher, now}), /not configured/);
  m = mock({dispatchStatus: 403});await assert.rejects(check({DRY_RUN: 'false', GITHUB_TOKEN: 'test-only-placeholder'}, {fetcher: m.fetcher, now}), /HTTP 403/);
});
test('public HTTP endpoint cannot dispatch', async () => {
  assert.equal((await worker.fetch(new Request('https://watchdog.example/', {method: 'POST'}))).status, 405);
  assert.equal((await worker.fetch(new Request('https://watchdog.example/'))).status, 200);
});
