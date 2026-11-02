import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer, request } from 'node:http';
import { randomUUID } from 'node:crypto';
import { mkdtemp, readdir, readFile, stat, rm, symlink, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createCollector } from '../src/collector.mjs';
import { startLocalUi } from '../src/ui.mjs';
import { PROXY_NOTE, reportDigest, validateReport } from '../src/report.mjs';

const CAP = 10 * 1024 * 1024;
function fixture(overrides = {}) {
  const report = {
    schema_version: '0.1', report_id: randomUUID(), created_at: new Date().toISOString(),
    collector: { name: 'fanqiang-diagnostics', version: '0.1.0', execution_location: 'user_device', platform: 'linux', routing_mode: 'os_direct_socket', proxy_note: PROXY_NOTE },
    problem_category: 'connectivity',
    measurements: { dns: [], tcp: [], tls: [], http: [], throughput: [] },
    summary: { tcp_median_ms: null, http_median_ms: null, tcp_failure_ratio: null, download_mbps: null },
    budget: { max_payload_bytes: CAP, used_payload_bytes: 0, max_duration_ms: 15000 },
    redaction: { raw_logs_included: false, removed_categories: [] },
    limitations: ['os_direct_socket', 'tun_may_affect_routing', 'no_icmp_packet_loss', 'fixed_target_only', 'no_application_proxy_test', 'throughput_not_requested'],
    ...overrides
  };
  assert.equal(validateReport(report).ok, true);
  return report;
}
async function until(fn) {
  for (let i = 0; i < 200; i++) {
    const result = fn();
    if (result) return result;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error('condition timed out');
}
async function setup(t, { run, handler } = {}) {
  const requests = [];
  const remote = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = Buffer.concat(chunks).toString('utf8');
    requests.push({ method: req.method, path: req.url, authorization: req.headers.authorization, body: body ? JSON.parse(body) : null });
    if (handler) return handler(req, res, requests);
    if (req.method === 'DELETE') { res.writeHead(204).end(); return; }
    const now = new Date();
    res.writeHead(201, { 'Content-Type': 'application/json' }).end(JSON.stringify({
      receipt_id: 'receipt-test-1234', received_at: now.toISOString(),
      expires_at: new Date(now.getTime() + 30 * 86400000).toISOString(), delete_token: 'test-delete-token-with-enough-length'
    }));
  });
  await new Promise(resolve => remote.listen(0, '127.0.0.1', resolve));
  const directory = await mkdtemp(join(tmpdir(), 'fanqiang-ui-test-'));
  const calls = [];
  const ui = await startLocalUi({
    dataDir: directory, publicBase: 'http://127.0.0.1:' + remote.address().port,
    runDiagnostics: async options => { calls.push(options); return run ? run(options) : fixture(); }
  });
  t.after(async () => {
    await ui.close();
    await new Promise(resolve => { remote.close(resolve); remote.closeAllConnections(); });
    await rm(directory, { recursive: true, force: true });
  });
  const page = await fetch(ui.url);
  const html = await page.text();
  const key = html.match(/"sessionKey":"([0-9a-f]{64})"/)?.[1];
  assert.ok(key);
  const origin = new URL(ui.url).origin;
  async function api(route, body, headers = {}) {
    const result = await fetch(ui.url + 'api/' + route, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'X-session': key, ...(body === undefined ? {} : { Origin: origin, 'Content-Type': 'application/json' }), ...headers },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    return { status: result.status, body: await result.json(), headers: result.headers };
  }
  async function diagnose() {
    const result = await api('start', { throughput: false, problem_category: 'connectivity' });
    assert.equal(result.status, 200);
    await until(() => ui.getStatus().has_report && ['complete', 'stopped'].includes(ui.getStatus().phase));
  }
  return { ui, api, html, page, directory, requests, calls, diagnose, key, origin, publicBase: 'http://127.0.0.1:' + remote.address().port };
}
function rawRequest(url, headers, method = 'GET', body) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const req = request({ hostname: u.hostname, port: u.port, path: u.pathname, method, headers }, res => {
      const chunks = [];
      res.on('data', value => chunks.push(value));
      res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString(), headers: res.headers }));
    });
    req.on('error', reject);
    req.end(body);
  });
}

test('local page has capability, CSP and complete Chinese plan; no diagnostics or upload on open', async t => {
  const s = await setup(t);
  assert.match(s.ui.url, /^http:\/\/127\.0\.0\.1:\d+\/s\/[a-f0-9]{64}\/$/);
  assert.match(s.html, /10 MiB/);
  assert.match(s.html, /20 MiB/);
  assert.match(s.html, /iPhone/);
  assert.match(s.html, /不提交/);
  assert.match(s.html, /日志全文不会提交/);
  assert.doesNotMatch(s.html, /gtag|googletagmanager|<script src=/);
  assert.equal(s.page.headers.get('referrer-policy'), 'no-referrer');
  assert.match(s.page.headers.get('content-security-policy'), /default-src 'none'/);
  assert.match(s.page.headers.get('content-security-policy'), /frame-ancestors 'none'/);
  assert.equal(s.page.headers.get('access-control-allow-origin'), null);
  assert.equal(s.calls.length, 0);
  assert.equal(s.requests.length, 0);
  assert.equal((await fetch(s.origin + '/')).status, 404);
  assert.equal((await fetch(s.ui.url + '?other=1')).status, 404);
});

test('strict Host, Origin and session validation reject cross-site access and malformed session bytes', async t => {
  const s = await setup(t);
  const body = { throughput: false, problem_category: 'other' };
  assert.equal((await s.api('start', body, { Origin: 'https://evil.example' })).status, 403);
  assert.equal((await s.api('start', body, { Origin: '' })).status, 403);
  assert.equal((await s.api('start', body, { 'X-session': 'wrong' })).status, 403);
  assert.equal((await s.api('start', body, { 'Sec-Fetch-Site': 'cross-site' })).status, 403);
  assert.equal((await s.api('status', undefined, { 'X-session': 'é'.repeat(64) })).status, 403);
  const host = await rawRequest(s.ui.url, { Host: 'evil.example' });
  assert.equal(host.status, 403);
  const duplicate = await rawRequest(s.ui.url, ['Host', new URL(s.ui.url).host, 'Host', new URL(s.ui.url).host]);
  assert.equal(duplicate.status, 403);
  assert.equal(s.calls.length, 0);
  assert.equal(s.requests.length, 0);
});

test('report creation and exported preview never authorize or perform upload', async t => {
  const s = await setup(t);
  await s.diagnose();
  assert.equal(s.calls[0].throughput, false);
  assert.equal(s.calls[0].maxPayloadBytes, CAP);
  const local = s.ui.preview();
  assert.ok(local.report);
  assert.equal(local.sha256, reportDigest(local.report));
  const rejected = await s.api('submit', { preview_sha256: local.sha256, preview_token: 'x'.repeat(64) });
  assert.equal(rejected.status, 409);
  assert.equal(s.requests.length, 0);
  const forged = await s.api('submit', { consent: true, report: local.report });
  assert.equal(forged.status, 400);
  assert.equal(s.requests.length, 0);
});

test('explicit preview freezes whitelist report; local logs never leave, receipt private and submit idempotent', async t => {
  const s = await setup(t);
  await s.diagnose();
  const logs = await s.api('logs', { text: 'private-user@example.com password=not-a-real-secret https://example.invalid/sub?token=test 192.0.2.1 <script>alert(1)</script>' });
  assert.equal(logs.status, 200);
  assert.doesNotMatch(logs.body.text, /private-user@example\.com|not-a-real-secret|192\.0\.2\.1/);
  const view = await s.api('preview', {});
  assert.equal(view.status, 200);
  assert.equal(view.body.retention_days, 30);
  assert.equal(view.body.public, false);
  assert.equal(view.body.preview_sha256, reportDigest(view.body.report));
  assert.equal(s.requests.length, 0);
  const command = { preview_sha256: view.body.preview_sha256, preview_token: view.body.preview_token };
  const result = await s.api('submit', command);
  assert.equal(result.status, 200);
  assert.equal(s.requests.length, 1);
  const envelope = s.requests[0].body;
  assert.deepEqual(envelope.report, view.body.report);
  assert.deepEqual(envelope.consent, { version: '1', preview_sha256: view.body.preview_sha256, action: 'submit' });
  assert.doesNotMatch(JSON.stringify(envelope), /private-user|not-a-real-secret|example\.invalid|192\.0\.2\.1|alert\(1\)/);
  assert.equal(envelope.report.redaction.raw_logs_included, false);
  assert.equal((await s.api('submit', command)).status, 200);
  assert.equal(s.requests.length, 1);
  assert.equal((await s.api('local-delete', {})).status, 409);
  assert.doesNotMatch(JSON.stringify(result.body), /test-delete-token/);
  assert.doesNotMatch(JSON.stringify(s.ui.getStatus()), /test-delete-token/);
  const [session] = await readdir(s.directory);
  const localDirectory = join(s.directory, session);
  assert.equal((await stat(localDirectory)).mode & 0o777, 0o700);
  assert.deepEqual((await readdir(localDirectory)).sort(), ['receipt.json', 'report.json']);
  for (const name of ['receipt.json', 'report.json']) assert.equal((await stat(join(localDirectory, name))).mode & 0o777, 0o600);
  const saved = JSON.parse(await readFile(join(localDirectory, 'receipt.json'), 'utf8'));
  assert.equal(saved.delete_token, 'test-delete-token-with-enough-length');
  assert.doesNotMatch(await readFile(join(localDirectory, 'report.json'), 'utf8'), /private-user|not-a-real-secret/);
});

test('log edit and rerun revoke previously frozen submission permission', async t => {
  const s = await setup(t);
  await s.diagnose();
  const first = (await s.api('preview', {})).body;
  await s.api('logs', { text: 'edited local text' });
  assert.equal((await s.api('submit', { preview_sha256: first.preview_sha256, preview_token: first.preview_token })).status, 409);
  const second = (await s.api('preview', {})).body;
  await s.diagnose();
  assert.equal((await s.api('submit', { preview_sha256: second.preview_sha256, preview_token: second.preview_token })).status, 409);
  assert.equal(s.requests.length, 0);
});

test('stop aborts actual run, single run enforced and unsafe progress text ignored', async t => {
  let options;
  const s = await setup(t, {
    run: value => new Promise(resolve => {
      options = value;
      value.onProgress({ stage: 'tcp', completed: 1, total: 3, used_payload_bytes: 0, secret: 'not-published' });
      value.onProgress({ stage: 'user-sensitive-message', completed: 0, total: 1, used_payload_bytes: 0 });
      value.signal.addEventListener('abort', () => resolve(fixture()), { once: true });
    })
  });
  assert.equal((await s.api('start', { throughput: false, problem_category: 'other' })).status, 200);
  await until(() => !!options);
  assert.equal((await s.api('start', { throughput: true, problem_category: 'slow' })).status, 409);
  assert.equal((await s.api('preview', {})).status, 409);
  assert.doesNotMatch(JSON.stringify(s.ui.getStatus()), /sensitive|secret|not-published/);
  assert.equal((await s.api('stop', {})).status, 200);
  await until(() => s.ui.getStatus().phase === 'stopped');
  assert.equal(options.signal.aborted, true);
  assert.equal(s.requests.length, 0);
});

test('session ceiling passes remaining allowance and rejects more runs at 20 MiB', async t => {
  let runs = 0;
  const s = await setup(t, { run: async options => {
    runs++;
    const amount = runs === 1 ? CAP - 100 : options.maxPayloadBytes;
    return fixture({ budget: { max_payload_bytes: CAP, used_payload_bytes: amount, max_duration_ms: 15000 } });
  } });
  await s.diagnose();
  await s.diagnose();
  assert.equal(s.ui.getStatus().session_budget.used_payload_bytes, 2 * CAP - 100);
  await s.diagnose();
  assert.equal(s.calls[2].maxPayloadBytes, 100);
  assert.equal(s.ui.getStatus().session_budget.used_payload_bytes, 2 * CAP);
  assert.equal((await s.api('start', { throughput: true, problem_category: 'slow' })).status, 409);
  assert.equal(s.calls.length, 3);
  assert.equal((await s.api('local-delete', {})).status, 200);
  assert.equal(s.ui.getStatus().session_budget.used_payload_bytes, 2 * CAP);
  assert.equal(s.ui.getStatus().can_start, false);
});

test('in-flight submit blocks edits, repeat submission and run; token used only on explicit delete', async t => {
  let release;
  const s = await setup(t, { handler: async (req, res) => {
    if (req.method === 'DELETE') { res.writeHead(204).end(); return; }
    await new Promise(resolve => { release = resolve; });
    res.writeHead(201, { 'Content-Type': 'application/json' }).end(JSON.stringify({
      receipt_id: 'receipt-test-1234', received_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 86400000).toISOString(), delete_token: 'test-delete-token-with-enough-length'
    }));
  } });
  await s.diagnose();
  const view = (await s.api('preview', {})).body;
  const command = { preview_sha256: view.preview_sha256, preview_token: view.preview_token };
  const inFlight = s.api('submit', command);
  await until(() => !!release);
  assert.equal((await s.api('logs', { text: 'changed' })).status, 409);
  assert.equal((await s.api('submit', command)).status, 409);
  assert.equal((await s.api('start', { throughput: false, problem_category: 'other' })).status, 409);
  release();
  assert.equal((await inFlight).status, 200);
  assert.equal(s.requests.length, 1);
  assert.equal((await s.api('remote-delete', {})).status, 200);
  assert.equal(s.requests.length, 2);
  assert.equal(s.requests[1].method, 'DELETE');
  assert.equal(s.requests[1].authorization, 'Bearer test-delete-token-with-enough-length');
  assert.equal((await s.api('remote-delete', {})).status, 200);
  assert.equal(s.requests.length, 2);
  assert.ok(s.ui.getStatus().receipt.deleted_at);
  assert.equal((await s.api('local-delete', {})).status, 200);
  const [session] = await readdir(s.directory);
  assert.deepEqual(await readdir(join(s.directory, session)), []);
  assert.equal(s.ui.preview(), null);
});

test('uncertain submission retries same frozen body/idempotency key; no silent new report', async t => {
  const s = await setup(t, { handler: (req, res, requests) => {
    if (requests.length === 1) { res.writeHead(503).end(); return; }
    res.writeHead(201, { 'Content-Type': 'application/json' }).end(JSON.stringify({
      receipt_id: 'receipt-test-1234', received_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 86400000).toISOString(), delete_token: 'test-delete-token-with-enough-length'
    }));
  } });
  await s.diagnose();
  const view = (await s.api('preview', {})).body;
  const command = { preview_sha256: view.preview_sha256, preview_token: view.preview_token };
  assert.equal((await s.api('submit', command)).status, 502);
  assert.equal((await s.api('logs', { text: 'change' })).status, 409);
  assert.equal((await s.api('local-delete', {})).status, 409);
  const newPreview = (await s.api('preview', {})).body;
  assert.equal(newPreview.preview_token, view.preview_token);
  assert.equal((await s.api('submit', command)).status, 200);
  assert.deepEqual(s.requests[0].body, s.requests[1].body);
});

test('malformed plans, arbitrary target/path, bad reports and oversized body cannot reach collector', async t => {
  const s = await setup(t, { run: async () => ({ ...fixture(), username: 'forbidden' }) });
  assert.equal((await s.api('start', { throughput: false, problem_category: 'other', target: 'http://127.0.0.1' })).status, 400);
  assert.equal((await s.api('logs', { text: 'x'.repeat(70000) })).status, 413);
  assert.equal((await s.api('read-file', { path: '/etc/passwd' })).status, 404);
  assert.equal((await s.api('start', { throughput: false, problem_category: 'other' })).status, 200);
  await until(() => s.ui.getStatus().phase === 'error');
  assert.equal(s.ui.preview(), null);
  assert.equal(s.requests.length, 0);
});

test('page renders log/report data with textContent and nonce, never HTML injection sinks', async t => {
  const s = await setup(t);
  assert.match(s.html, /textContent = JSON\.stringify/);
  assert.match(s.html, /redacted-log'\)\.textContent/);
  assert.doesNotMatch(s.html, /\.innerHTML|insertAdjacentHTML|document\.write|localStorage|sessionStorage/);
  const scriptNonce = s.html.match(/<script nonce="([^"]+)"/)[1];
  assert.ok(s.page.headers.get('content-security-policy').includes("'nonce-" + scriptNonce + "'"));
  assert.doesNotMatch(s.html, /style="/);
});


async function connect(ui) {
  const html = await (await fetch(ui.url)).text();
  const key = html.match(/"sessionKey":"([a-f0-9]{64})"/)[1];
  return async function api(route, body = {}) {
    const result = await fetch(ui.url + 'api/' + route, {
      method: 'POST',
      headers: { 'X-session': key, Origin: new URL(ui.url).origin, 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return { status: result.status, body: await result.json() };
  };
}

test('restart restores pending submission with original key and frozen report, without automatic upload', async t => {
  const s = await setup(t, { handler: (req, res) => res.writeHead(503).end() });
  await s.diagnose();
  const first = (await s.api('preview', {})).body;
  await s.api('submit', { preview_sha256: first.preview_sha256, preview_token: first.preview_token });
  assert.equal(s.requests.length, 1);
  const oldEnvelope = s.requests[0].body;
  const [session] = await readdir(s.directory);
  const pendingPath = join(s.directory, session, 'pending.json');
  assert.equal((await stat(pendingPath)).mode & 0o777, 0o600);
  assert.equal(JSON.parse(await readFile(pendingPath, 'utf8')).idempotency, oldEnvelope.idempotency_key);
  await s.ui.close();
  const reopened = await startLocalUi({ dataDir: s.directory, publicBase: s.publicBase, runDiagnostics: async () => fixture() });
  t.after(() => reopened.close());
  assert.equal(reopened.getStatus().can_restore, true);
  assert.equal(reopened.preview(), null);
  assert.equal(s.requests.length, 1);
  const api = await connect(reopened);
  assert.equal((await api('restore')).status, 200);
  assert.equal(s.requests.length, 1);
  assert.equal(reopened.getStatus().submission_pending, true);
  assert.doesNotMatch(JSON.stringify(reopened.getStatus()), /idempotency|delete_token|preview_token/);
  const recovered = (await api('preview')).body;
  assert.equal(recovered.preview_sha256, first.preview_sha256);
  assert.notEqual(recovered.preview_token, first.preview_token);
  assert.equal((await api('submit', { preview_sha256: recovered.preview_sha256, preview_token: recovered.preview_token })).status, 502);
  assert.deepEqual(s.requests[1].body, oldEnvelope);
});

test('restart restores receipt for explicit remote deletion; symlinked sessions and report files are ignored', async t => {
  const s = await setup(t);
  await s.diagnose();
  const preview = (await s.api('preview', {})).body;
  await s.api('submit', { preview_sha256: preview.preview_sha256, preview_token: preview.preview_token });
  await s.ui.close();
  const reopened = await startLocalUi({ dataDir: s.directory, publicBase: s.publicBase, runDiagnostics: async () => fixture() });
  t.after(() => reopened.close());
  assert.equal(s.requests.length, 1);
  const api = await connect(reopened);
  assert.equal((await api('restore')).status, 200);
  assert.equal(reopened.getStatus().receipt.receipt_id, 'receipt-test-1234');
  assert.equal((await api('local-delete')).status, 409);
  assert.equal((await api('remote-delete')).status, 200);
  assert.equal(s.requests.length, 2);
  await reopened.close();
  const directories = await readdir(s.directory);
  let withReport;
  for (const name of directories) if ((await readdir(join(s.directory, name))).includes('report.json')) withReport = name;
  assert.ok(withReport);
  const currentReport = join(s.directory, withReport, 'report.json');
  await rm(currentReport);
  await symlink('/etc/passwd', currentReport);
  await symlink(join(s.directory, withReport), join(s.directory, 'session-fakeaa'));
  const unsafe = await startLocalUi({ dataDir: s.directory, publicBase: s.publicBase, runDiagnostics: async () => fixture() });
  t.after(() => unsafe.close());
  assert.equal(unsafe.getStatus().can_restore, false);
  assert.equal(s.requests.length, 2);
});

test('real collector accepts UI envelope and explicit deletion; persisted JSON has real newline', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'fanqiang-ui-integration-'));
  const collector = await createCollector({ dataDir: join(directory, 'remote'), host: '127.0.0.1', port: 0 });
  const ui = await startLocalUi({
    dataDir: join(directory, 'local'), publicBase: collector.url,
    runDiagnostics: async () => fixture()
  });
  t.after(async () => {
    await ui.close();
    await collector.close();
    await rm(directory, { recursive: true, force: true });
  });
  const api = await connect(ui);
  assert.equal(collector.exportReports().length, 0);
  assert.equal((await api('start', { throughput: false, problem_category: 'connectivity' })).status, 200);
  await until(() => ui.getStatus().phase === 'complete');
  assert.equal(collector.exportReports().length, 0);
  const view = (await api('preview')).body;
  assert.equal(collector.exportReports().length, 0);
  const command = { preview_sha256: view.preview_sha256, preview_token: view.preview_token };
  const submitted = await api('submit', command);
  assert.equal(submitted.status, 200, JSON.stringify(submitted.body));
  assert.equal(collector.exportReports().length, 1);
  assert.deepEqual(collector.exportReports()[0].report, view.report);
  const [session] = await readdir(join(directory, 'local'));
  for (const name of ['report.json', 'receipt.json']) {
    const bytes = await readFile(join(directory, 'local', session, name));
    assert.equal(bytes.at(-1), 10);
    assert.doesNotThrow(() => JSON.parse(bytes.toString('utf8')));
  }
  assert.equal((await api('submit', command)).status, 200);
  assert.equal(collector.exportReports().length, 1);
  assert.equal((await api('remote-delete')).status, 200);
  assert.equal(collector.exportReports().length, 0);
});

for (const failure of ['receipt_write', 'pending_remove']) {
  test('filesystem failure after accepted submit can recover and revoke: ' + failure, async t => {
    let localDirectory;
    const s = await setup(t, { handler: async (req, res, requests) => {
      if (req.method === 'DELETE') { res.writeHead(204).end(); return; }
      if (requests.length === 1) {
        const blocked = join(localDirectory, failure === 'receipt_write' ? 'receipt.json' : 'pending.json');
        if (failure === 'pending_remove') await rm(blocked);
        await mkdir(blocked, { mode: 0o700 });
      }
      res.writeHead(201, { 'Content-Type': 'application/json' }).end(JSON.stringify({
        receipt_id: 'receipt-test-1234', received_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 86400000).toISOString(), delete_token: 'test-delete-token-with-enough-length'
      }));
    } });
    await s.diagnose();
    localDirectory = join(s.directory, (await readdir(s.directory))[0]);
    const view = (await s.api('preview', {})).body;
    const command = { preview_sha256: view.preview_sha256, preview_token: view.preview_token };
    assert.equal((await s.api('submit', command)).status, 502);
    assert.equal(s.requests.length, 1);
    assert.equal(s.ui.getStatus().receipt.receipt_id, 'receipt-test-1234');
    assert.equal((await s.api('local-delete', {})).status, 409);
    const blocked = join(localDirectory, failure === 'receipt_write' ? 'receipt.json' : 'pending.json');
    await rm(blocked, { recursive: true });
    if (failure === 'receipt_write') {
      assert.equal((await s.api('submit', command)).status, 200);
      assert.equal(s.requests.length, 1, 'short circuit must repair local persistence without resubmitting');
      assert.equal((await readdir(localDirectory)).includes('pending.json'), false);
    }
    assert.equal((await s.api('remote-delete', {})).status, 200);
    assert.equal(s.requests.at(-1).method, 'DELETE');
    assert.equal(s.ui.getStatus().submission_pending, false);
    assert.equal((await readdir(localDirectory)).includes('pending.json'), false);
    assert.equal((await s.api('local-delete', {})).status, 200);
    await s.ui.close();
    const reopened = await startLocalUi({ dataDir: s.directory, publicBase: s.publicBase, runDiagnostics: async () => fixture() });
    t.after(() => reopened.close());
    assert.equal(reopened.getStatus().can_restore, false, 'revoked pending state must not reappear after restart');
  });
}
