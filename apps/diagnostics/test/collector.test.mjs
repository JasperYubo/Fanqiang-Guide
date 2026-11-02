import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdtemp, readFile, rm, stat, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { request } from 'node:http';
import { gzipSync } from 'node:zlib';
import { setTimeout as delay } from 'node:timers/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createCollector } from '../src/collector.mjs';
import { reportDigest, validateReport } from '../src/report.mjs';

const run = promisify(execFile);
const MiB = 1024 * 1024;
function report() {
  return {
    schema_version: '0.1', report_id: randomUUID(), created_at: new Date().toISOString(),
    collector: { name: 'fanqiang-diagnostics', version: '0.1.0', execution_location: 'linux_lab', platform: 'linux', routing_mode: 'os_direct_socket', proxy_note: 'explicit OS/HTTP proxies are not used; TUN may affect routing' },
    problem_category: 'other', measurements: { dns: [], tcp: [], tls: [], http: [], throughput: [] },
    summary: { tcp_median_ms: null, http_median_ms: null, tcp_failure_ratio: null, download_mbps: null },
    budget: { max_payload_bytes: 10 * MiB, used_payload_bytes: 0, max_duration_ms: 15000 },
    redaction: { raw_logs_included: false, removed_categories: [] },
    limitations: ['os_direct_socket', 'tun_may_affect_routing', 'no_icmp_packet_loss', 'fixed_target_only', 'no_application_proxy_test', 'throughput_not_requested', 'linux_lab_only'],
  };
}
function envelope(value = report(), key = randomUUID()) {
  return { report: value, idempotency_key: key, consent: { version: '1', preview_sha256: reportDigest(value), action: 'submit' } };
}
async function setup(t, options = {}) {
  const dataDir = await mkdtemp(join(tmpdir(), 'fqdiag-collector-'));
  const app = await createCollector({ dataDir, port: 0, ...options });
  t.after(async () => { await app.close(); await rm(dataDir, { recursive: true, force: true }); });
  return { ...app, dataDir };
}
async function post(app, value, headers = {}) {
  const response = await fetch(app.url + '/v1/reports', { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(value) });
  return { status: response.status, headers: response.headers, body: await response.json() };
}
async function get(app, path, headers = {}) {
  const response = await fetch(app.url + path, { headers });
  return { status: response.status, headers: response.headers, bytes: Buffer.from(await response.arrayBuffer()) };
}
async function until(predicate, timeout = 1500) {
  const start = Date.now();
  while (!predicate()) { if (Date.now() - start > timeout) throw new Error('condition_timeout'); await delay(10); }
}
function slowPost(app) {
  let req;
  const response = new Promise((resolveResponse, reject) => {
    req = request(app.url + '/v1/reports', { method: 'POST', headers: { 'Content-Type': 'application/json' } }, res => {
      let body = ''; res.on('data', data => { body += data; });
      res.on('end', () => resolveResponse({ status: res.statusCode, body: JSON.parse(body) }));
    });
    req.on('error', reject); req.write('{');
  });
  return { req, response };
}
function pausedDownload(app, bytes = 10 * MiB, headers = {}) {
  let req;
  const ready = new Promise((resolveReady, reject) => {
    req = request(app.url + '/v1/download?bytes=' + bytes, { headers }, res => { res.pause(); resolveReady(res); });
    req.on('error', reject); req.end();
  });
  return { req, ready };
}

test('health/ping are private responses and no public report listing or GET exists', async t => {
  const app = await setup(t);
  for (const path of ['/health', '/v1/ping']) {
    const result = await get(app, path);
    assert.equal(result.status, 200);
    assert.equal(result.headers.get('cache-control'), 'no-store');
    assert.match(result.headers.get('x-robots-tag'), /noindex/);
    assert.equal(result.headers.get('access-control-allow-origin'), null);
    assert.equal(result.bytes.includes(Buffer.from('gtag')), false);
  }
  assert.equal((await get(app, '/v1/reports')).status, 404);
  assert.equal((await get(app, '/v1/reports/' + randomUUID())).status, 404);
});

test('approved preview submission is idempotent across restart and persists no client IP or delete token', async t => {
  const app = await setup(t);
  const value = envelope();
  assert.equal(validateReport(value.report).ok, true);
  const first = await post(app, value, { 'X-Diagnostics-Client': '198.51.100.7' });
  assert.equal(first.status, 201);
  assert.equal(first.body.delete_token.length, 43);
  assert.equal(Date.parse(first.body.expires_at) - Date.parse(first.body.received_at), 30 * 86400000);
  const second = await post(app, JSON.parse(JSON.stringify(value)));
  assert.equal(second.status, 200); assert.deepEqual(second.body, first.body);
  assert.equal(app.getStats().reports, 1);
  const database = await readFile(join(app.dataDir, 'reports.sqlite'));
  assert.equal(database.includes(Buffer.from('198.51.100.7')), false);
  assert.equal(database.includes(Buffer.from(first.body.delete_token)), false);
  assert.equal(database.includes(Buffer.from(value.idempotency_key)), false);
  assert.equal((await stat(app.dataDir)).mode & 0o777, 0o700);
  assert.equal((await stat(join(app.dataDir, 'collector.key'))).mode & 0o777, 0o600);
  assert.equal((await stat(join(app.dataDir, 'reports.sqlite'))).mode & 0o777, 0o600);
  await app.close();
  const resumed = await createCollector({ dataDir: app.dataDir, port: 0 });
  t.after(() => resumed.close());
  assert.deepEqual((await post(resumed, value)).body, first.body);
  await resumed.close();
});

test('preview hash mismatch and changed body under the same idempotency key are rejected', async t => {
  const app = await setup(t); const value = envelope();
  const badHash = structuredClone(value); badHash.consent.preview_sha256 = '0'.repeat(64);
  assert.deepEqual((await post(app, badHash)).body, { error: 'preview_digest_mismatch' });
  assert.equal((await post(app, value)).status, 201);
  const changed = structuredClone(value); changed.report.problem_category = 'slow'; changed.consent.preview_sha256 = reportDigest(changed.report);
  const result = await post(app, changed);
  assert.equal(result.status, 409); assert.equal(result.body.error, 'idempotency_conflict');
  assert.equal(app.getStats().reports, 1);
});


test('envelope and report reject free text, raw/redacted logs, IPs, subscription and arbitrary nested fields', async t => {
  const app = await setup(t);
  const mutations = [
    x => { x.raw_logs = 'private input'; },
    x => { x.consent.extra = 'not allowed'; },
    x => { x.consent.action = 'automatic'; },
    x => { x.idempotency_key = 'arbitrary-secret'; },
    x => { x.report.raw_logs = ['raw']; },
    x => { x.report.redacted_logs = '[REDACTED]'; },
    x => { x.report.client_ip = '203.0.113.7'; },
    x => { x.report.subscription = 'https://private.example/token'; },
    x => { x.report.collector.hostname = 'personal-laptop'; },
    x => { x.report.problem_category = 'free form'; },
    x => { x.report.redaction.raw_logs_included = true; },
    x => { x.report.measurements.dns = [{ started_at: new Date().toISOString(), duration_ms: 1, status: 'ok', error_code: null, address: '192.168.0.1' }]; },
  ];
  for (const mutate of mutations) {
    const value = envelope(); mutate(value);
    value.consent.preview_sha256 = reportDigest(value.report);
    const result = await post(app, value);
    assert.equal(result.status, 400, JSON.stringify(result));
  }
  assert.equal(app.getStats().reports, 0);
});

test('body type, encoding, byte bound and malformed JSON are rejected before persistence', async t => {
  const app = await setup(t);
  const requests = [
    { headers: { 'Content-Type': 'text/plain' }, body: '{}' },
    { headers: { 'Content-Type': 'application/json', 'Content-Encoding': 'gzip' }, body: '{}' },
    { headers: { 'Content-Type': 'application/json' }, body: 'x'.repeat(65537) },
    { headers: { 'Content-Type': 'application/json' }, body: '{' },
    { headers: { 'Content-Type': 'application/json' }, body: Buffer.from([0xff, 0xfe]) },
  ];
  for (const options of requests) {
    const response = await fetch(app.url + '/v1/reports', { method: 'POST', ...options });
    assert.ok([400, 413, 415].includes(response.status)); await response.text();
  }
  assert.equal(app.getStats().reports, 0);
});

test('delete requires possession of the receipt token and removes idempotency state', async t => {
  const app = await setup(t); const value = envelope(); const first = await post(app, value);
  const url = app.url + '/v1/reports/' + first.body.receipt_id;
  let response = await fetch(url, { method: 'DELETE' }); assert.equal(response.status, 401); await response.text();
  response = await fetch(url, { method: 'DELETE', headers: { Authorization: 'Bearer ' + 'a'.repeat(43) } }); assert.equal(response.status, 404); await response.text();
  assert.equal(app.getStats().reports, 1);
  response = await fetch(url, { method: 'DELETE', headers: { Authorization: 'Bearer ' + first.body.delete_token } });
  assert.equal(response.status, 200); assert.deepEqual(await response.json(), { deleted: true });
  assert.equal(app.getStats().reports, 0); assert.deepEqual(app.exportReports(), []);
  const retried = await post(app, value);
  assert.equal(retried.status, 201); assert.notEqual(retried.body.receipt_id, first.body.receipt_id);
});

test('automatic retention removes expired reports and their idempotency records', async t => {
  let now = Date.now(); const app = await setup(t, { now: () => now, cleanupIntervalMs: 10 });
  const value = envelope(); const first = await post(app, value);
  now += 30 * 86400000 + 1;
  await until(() => app.getStats().reports === 0);
  const second = await post(app, value);
  assert.equal(second.status, 201); assert.notEqual(second.body.receipt_id, first.body.receipt_id);
});

test('record and payload storage ceilings reject new data without evicting existing receipts', async t => {
  const app = await setup(t, { maxReports: 1 });
  const value = envelope(); assert.equal((await post(app, value)).status, 201);
  assert.equal((await post(app, envelope())).body.error, 'storage_capacity');
  assert.equal((await post(app, value)).status, 200);
  const tiny = await setup(t, { maxStoredBytes: 1 });
  assert.equal((await post(tiny, envelope())).body.error, 'storage_capacity');
  assert.equal(tiny.getStats().reports, 0);
});

test('request and submission rate limits return safe codes and Retry-After and reset by window', async t => {
  let now = Date.now(); const app = await setup(t, { now: () => now, maxRequestsPerWindow: 2, maxGlobalRequestsPerWindow: 4, rateWindowMs: 1000 });
  await get(app, '/v1/ping'); await get(app, '/v1/ping');
  let result = await get(app, '/v1/ping'); assert.equal(result.status, 429); assert.ok(Number(result.headers.get('retry-after')) >= 1);
  assert.deepEqual(JSON.parse(result.bytes), { error: 'rate_limited' });
  now += 1001; assert.equal((await get(app, '/v1/ping')).status, 200);
  assert.equal((await get(app, '/v1/ping', { 'X-Diagnostics-Client': '203.0.113.8' })).status, 200);
  const writes = await setup(t, { maxSubmissionsPerWindow: 1 });
  const value = envelope(); assert.equal((await post(writes, value)).status, 201);
  result = await post(writes, envelope()); assert.equal(result.status, 429); assert.equal(result.body.error, 'submission_rate_limited');
  assert.equal((await post(writes, value)).status, 200);
});

test('invalid proxy identity and bounded in-memory identity capacity fail closed', async t => {
  const app = await setup(t, { maxClients: 2 });
  assert.equal((await get(app, '/health', { 'X-Diagnostics-Client': '198.51.100.1, 203.0.113.1' })).status, 400);
  assert.equal((await get(app, '/health', { 'X-Diagnostics-Client': '198.51.100.1' })).status, 200);
  assert.equal((await get(app, '/health', { 'X-Diagnostics-Client': '198.51.100.2' })).status, 200);
  assert.equal((await get(app, '/health', { 'X-Diagnostics-Client': '198.51.100.3' })).status, 503);
  assert.equal(app.getStats().rememberedClients, 2);
});

test('slow bodies time out and cannot exceed request concurrency', async t => {
  const app = await setup(t, { bodyTimeoutMs: 150, maxConcurrentRequests: 1 });
  const pending = slowPost(app);
  await until(() => app.getStats().activeRequests === 1);
  const limited = await get(app, '/v1/ping', { 'X-Diagnostics-Client': '203.0.113.10' });
  assert.equal(limited.status, 429); assert.equal(JSON.parse(limited.bytes).error, 'concurrency_limited');
  const timeout = await pending.response;
  assert.equal(timeout.status, 408); assert.equal(timeout.body.error, 'request_timeout');
  pending.req.destroy();
  await until(() => app.getStats().activeRequests === 0);
  assert.equal(app.getStats().reports, 0);
});


test('download is bounded random bytes with no compression or caching and enforced byte budgets', async t => {
  const app = await setup(t, { maxClientDownloadBytes: 256 * 1024, maxGlobalDownloadBytes: 384 * 1024 });
  const first = await get(app, '/v1/download?bytes=131072');
  assert.equal(first.status, 200); assert.equal(first.bytes.length, 131072);
  assert.equal(first.headers.get('content-length'), '131072'); assert.equal(first.headers.get('content-encoding'), 'identity');
  assert.equal(first.headers.get('cache-control'), 'no-store, no-transform');
  assert.match(first.headers.get('content-type'), /application\/octet-stream/);
  assert.ok(gzipSync(first.bytes).length / first.bytes.length > 0.98);
  await get(app, '/v1/download?bytes=131072');
  let limited = await get(app, '/v1/download?bytes=1'); assert.equal(limited.status, 429);
  assert.equal(JSON.parse(limited.bytes).error, 'download_budget_exhausted');
  assert.equal((await get(app, '/v1/download?bytes=131072', { 'X-Diagnostics-Client': '203.0.113.20' })).status, 200);
  limited = await get(app, '/v1/download?bytes=1', { 'X-Diagnostics-Client': '203.0.113.21' }); assert.equal(limited.status, 429);
  for (const query of ['bytes=10485761', 'bytes=-1', 'bytes=0', 'bytes=1&bytes=2', 'bytes=1&host=example.com', '']) assert.equal((await get(app, '/v1/download?' + query)).status, 400);
});

test('download cancellation releases concurrency and cannot refund reserved traffic budget', async t => {
  const app = await setup(t, { maxConcurrentDownloads: 1, maxClientDownloadBytes: 10 * MiB, maxGlobalDownloadBytes: 20 * MiB });
  const pending = pausedDownload(app); const response = await pending.ready;
  assert.equal(response.statusCode, 200);
  const limited = await get(app, '/v1/download?bytes=10', { 'X-Diagnostics-Client': '203.0.113.30' });
  assert.equal(limited.status, 429); assert.equal(JSON.parse(limited.bytes).error, 'download_concurrency_limited');
  response.destroy(); pending.req.destroy();
  await until(() => app.getStats().activeDownloads === 0);
  assert.equal((await get(app, '/v1/download?bytes=1')).status, 429);
  assert.equal((await get(app, '/v1/download?bytes=10', { 'X-Diagnostics-Client': '203.0.113.30' })).status, 200);
});

test('paused download has a hard deadline', async t => {
  const app = await setup(t, { downloadTimeoutMs: 50 });
  const pending = pausedDownload(app); const response = await pending.ready;
  await until(() => app.getStats().activeDownloads === 0, 1000);
  response.destroy(); pending.req.destroy();
  assert.equal(app.getStats().activeDownloads, 0);
});

test('local export emits only live reports, excludes credentials and has no HTTP equivalent', async t => {
  const app = await setup(t); const first = await post(app, envelope());
  const { stdout } = await run(process.execPath, [fileURLToPath(new URL('../src/collector.mjs', import.meta.url)), 'export'], { env: { ...process.env, FQDIAG_DATA_DIR: app.dataDir } });
  const exported = JSON.parse(stdout.trim());
  assert.equal(exported.receipt_id, first.body.receipt_id);
  assert.deepEqual(Object.keys(exported).sort(), ['expires_at', 'receipt_id', 'received_at', 'report']);
  assert.equal(stdout.includes(first.body.delete_token), false);
  assert.equal((await get(app, '/export')).status, 404);
});

test('collector rejects public listeners and unsafe symlink storage', async t => {
  await assert.rejects(createCollector({ host: '0.0.0.0', port: 0 }), /loopback/);
  const root = await mkdtemp(join(tmpdir(), 'fqdiag-link-')); t.after(() => rm(root, { recursive: true, force: true }));
  await symlink(root, join(root, 'linked'));
  await assert.rejects(createCollector({ dataDir: join(root, 'linked'), port: 0 }), /unsafe_storage/);
});


test('chunked bodies cannot bypass the 64 KiB cap', async t => {
  const app = await setup(t);
  const result = await new Promise((resolveResponse, reject) => {
    const req = request(app.url + '/v1/reports', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Transfer-Encoding': 'chunked' } }, res => {
      let body = ''; res.on('data', data => { body += data; });
      res.on('end', () => resolveResponse({ status: res.statusCode, body: JSON.parse(body) }));
    });
    req.on('error', reject);
    req.write(Buffer.alloc(32768, 32)); req.write(Buffer.alloc(32768, 32)); req.end(' ');
  });
  assert.equal(result.status, 413); assert.deepEqual(result.body, { error: 'body_too_large' });
  assert.equal(app.getStats().reports, 0);
});

test('global request budget applies across distinct proxy identities', async t => {
  const app = await setup(t, { maxGlobalRequestsPerWindow: 2 });
  for (const address of ['198.51.100.40', '198.51.100.41']) assert.equal((await get(app, '/v1/ping', { 'X-Diagnostics-Client': address })).status, 200);
  const third = await get(app, '/v1/ping', { 'X-Diagnostics-Client': '198.51.100.42' });
  assert.equal(third.status, 429); assert.equal(JSON.parse(third.bytes).error, 'rate_limited');
  assert.ok(Number(third.headers.get('retry-after')) > 0);
});

test('aborted submission never stores partial data and releases its slot', async t => {
  const app = await setup(t);
  const req = request(app.url + '/v1/reports', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
  req.on('error', () => {}); req.write('{"report":');
  await until(() => app.getStats().activeRequests === 1);
  req.destroy();
  await until(() => app.getStats().activeRequests === 0);
  assert.equal(app.getStats().reports, 0);
  assert.equal((await get(app, '/health')).status, 200);
});
