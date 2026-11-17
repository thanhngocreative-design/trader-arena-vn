// Isolated HTTP contract fixtures only. Nothing here writes market/paper results.
// Run in the actual workerd runtime, whose Request API differs from Node's.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {gunzipSync} from 'node:zlib';
import {Miniflare, convertV4MiniflareOptions} from 'miniflare';

test('workerd accepts every upstream request and rejects redirects without forwarding credentials', async () => {
  const root = fileURLToPath(new URL('.', import.meta.url));
  const bank = JSON.parse(gunzipSync(readFileSync(new URL('../../state/replay_market/sessions/2026-11-16.json.gz', import.meta.url))));
  const rows = bank.replies.VNINDEX.ONE_DAY;
  const wire = [{symbol: 'VNINDEX', t: rows.map(r => Date.parse(r.time || r.date + 'T00:00:00+07:00') / 1000), c: rows.map(r => r.close), v: rows.map(r => r.volume)}];
  const harness = `
    import {check, health, API, SITE, MARKET} from './worker.mjs';
    export default {async fetch(request) {
      const mode = new URL(request.url).pathname, calls = [];
      const end = mode === '/current' ? '2026-11-16' : '2026-11-13';
      const paper = {revision:'replay_health_v1',status:'complete',end,bot_ids:['test-account'],accounts:9,
        baskets:Object.fromEntries(['300','146','vn30'].map(k=>[k,{end,accounts:3,sessions:1}]))};
      const fetcher = async (url, options) => {
        // This constructor is Cloudflare's native Request, not Node's implementation.
        const req = new Request(url, options);
        if (req.redirect !== 'manual') throw Error('Redirect must not forward credentials');
        calls.push(url);
        if (url === MARKET) return Response.json(${JSON.stringify(wire)});
        if (url.startsWith(SITE + 'replay-status.json')) return Response.json(paper);
        if (url.startsWith(SITE + 'backtest-status.json')) return Response.json({status:'complete',end,bots:['test-account']});
        if (url.startsWith(API + '/actions/runs?')) return Response.json({workflow_runs:[]});
        if (url.endsWith('/dispatches')) return mode === '/redirect' ? new Response(null,{status:302,headers:{Location:'https://untrusted.example/'}}) : Response.json({workflow_run_id:12345});
        throw Error('Unexpected HTTP request');
      };
      try {
        const operation = mode === '/health' ? health : check;
        const result = await operation({DRY_RUN:'false',GITHUB_TOKEN:'test-only-placeholder',VERIFY_DISPATCH_TARGET: mode === '/health' ? '2026-11-16' : undefined}, {fetcher,now:new Date('2026-11-16T14:00:00Z')});
        return Response.json({result,calls});
      } catch(error) {return Response.json({error:error.message,calls});}
    }};
  `;
  const mf = new Miniflare(convertV4MiniflareOptions({compatibilityDate:'2026-11-17',modulesRoot:root,
    modules:[{type:'ESModule',path:root+'runtime-harness.mjs',contents:harness},
      {type:'ESModule',path:root+'worker.mjs',contents:readFileSync(new URL('./worker.mjs',import.meta.url),'utf8')}]}));
  try {
    let payload = await (await mf.dispatchFetch('http://localhost/current')).json();
    assert.equal(payload.error, undefined);assert.equal(payload.result.action,'current');assert.equal(payload.calls.length,4);
    payload = await (await mf.dispatchFetch('http://localhost/dispatch')).json();
    assert.equal(payload.error, undefined);assert.equal(payload.result.dispatched,true);assert.equal(payload.result.run_id,12345);
    payload = await (await mf.dispatchFetch('http://localhost/redirect')).json();
    assert.match(payload.error,/GitHub dispatch failed: HTTP 302/);
    assert.equal(payload.calls.some(url=>new URL(url).hostname==='untrusted.example'),false);
    payload = await (await mf.dispatchFetch('http://localhost/health')).json();
    assert.equal(payload.error,undefined);assert.equal(payload.result.action,'would_dispatch_paper');
    assert.equal(payload.calls.length,4,'Public diagnostics must never POST a dispatch');
  } finally {await mf.dispose();}
});
