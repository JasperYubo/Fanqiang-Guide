import { createServer } from 'node:http';
import { randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { mkdir, mkdtemp, lstat, chmod, writeFile, rename, rm, readdir, open } from 'node:fs/promises';
import { constants } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { PUBLIC_BASE, validateReport, canonicalJson, reportDigest, redactText } from './report.mjs';
import { renderUiPage } from './ui-page.mjs';

const RUN_CAP = 10 * 1024 * 1024;
const SESSION_CAP = 20 * 1024 * 1024;
const BODY_CAP = 64 * 1024;
const stages = new Set(['dns', 'tcp', 'tls', 'http', 'throughput']);
const categories = new Set(['connectivity', 'slow', 'dns', 'application', 'other']);
const secret = () => randomBytes(32).toString('hex');
const clone = value => JSON.parse(JSON.stringify(value));
const same = (a, b) => typeof a === 'string' && typeof b === 'string' && Buffer.byteLength(a) === Buffer.byteLength(b) && timingSafeEqual(Buffer.from(a), Buffer.from(b));
const fault = (code, status = 409) => Object.assign(new Error(code), { code, status });

function destination(value) {
  const url = new URL(value);
  const local = ['127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.username || url.password || url.search || url.hash ||
      !((url.protocol === 'https:' && url.hostname === 'fanqiang.guide' && !url.port && url.pathname.replace(/\/$/, '') === '/diagnostics-api') ||
      (url.protocol === 'http:' && local))) throw new Error('invalid_public_base');
  return url.href.replace(/\/$/, '');
}

async function readJson(request) {
  if (request.headers['content-type'] !== 'application/json') throw fault('json_required', 415);
  const chunks = [];
  let length = 0;
  for await (const chunk of request) {
    length += chunk.length;
    if (length > BODY_CAP) throw fault('request_too_large', 413);
    chunks.push(chunk);
  }
  try {
    const value = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error();
    return value;
  } catch { throw fault('invalid_json', 400); }
}

function keys(body, allowed) {
  if (Object.keys(body).some(key => !allowed.includes(key))) throw fault('unknown_field', 400);
}

async function remoteJson(response) {
  let size = 0;
  const chunks = [];
  for await (const chunk of response.body ?? []) {
    size += chunk.length;
    if (size > BODY_CAP) throw fault('invalid_receipt', 502);
    chunks.push(chunk);
  }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw fault('invalid_receipt', 502); }
}


function validReceipt(value) {
  return value && typeof value === 'object' && !Array.isArray(value) &&
    Object.keys(value).every(key => ['receipt_id', 'received_at', 'expires_at', 'delete_token', 'deleted_at'].includes(key)) &&
    /^[A-Za-z0-9_-]{8,128}$/.test(value.receipt_id) &&
    /^[A-Za-z0-9_-]{20,256}$/.test(value.delete_token) &&
    typeof value.received_at === 'string' && Number.isFinite(Date.parse(value.received_at)) &&
    typeof value.expires_at === 'string' && Number.isFinite(Date.parse(value.expires_at)) &&
    (!value.deleted_at || typeof value.deleted_at === 'string' && Number.isFinite(Date.parse(value.deleted_at)));
}
async function privateJson(directory, name) {
  let handle;
  try {
    const file = join(directory, name);
    const before = await lstat(file);
    if (!before.isFile() || before.isSymbolicLink() || before.size > BODY_CAP ||
        process.platform !== 'win32' && ((before.mode & 0o077) !== 0 || before.uid !== process.getuid())) return null;
    handle = await open(file, constants.O_RDONLY | (constants.O_NOFOLLOW || 0));
    const after = await handle.stat();
    if (after.dev !== before.dev || after.ino !== before.ino || after.size > BODY_CAP) return null;
    return JSON.parse(await handle.readFile('utf8'));
  } catch { return null; }
  finally { await handle?.close(); }
}
async function recoverable(directory) {
  const info = await lstat(directory);
  if (!info.isDirectory() || info.isSymbolicLink() ||
      process.platform !== 'win32' && ((info.mode & 0o077) !== 0 || info.uid !== process.getuid())) return null;
  const [report, receipt, pending] = await Promise.all(['report.json', 'receipt.json', 'pending.json'].map(name => privateJson(directory, name)));
  if (!report || !validateReport(report).ok) return null;
  if (validReceipt(receipt) && !receipt.deleted_at) return { directory, report, receipt, pending: null, modified: info.mtimeMs };
  if (receipt) return null;
  if (!pending || Object.keys(pending).sort().join(',') !== 'digest,idempotency,report' ||
      !validateReport(pending.report).ok || !/^[a-f0-9]{64}$/.test(pending.digest) ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(pending.idempotency) ||
      reportDigest(pending.report) !== pending.digest || reportDigest(report) !== pending.digest) return null;
  return { directory, report, receipt: null, pending, modified: info.mtimeMs };
}
async function latestRecoverable(root, current) {
  const entries = (await readdir(root, { withFileTypes: true })).filter(entry =>
    entry.isDirectory() && !entry.isSymbolicLink() && /^session-[A-Za-z0-9_-]{6}$/.test(entry.name)).slice(-1000);
  let latest = null;
  for (const entry of entries) {
    const directory = join(root, entry.name);
    if (directory === current) continue;
    let value;
    try { value = await recoverable(directory); } catch { continue; }
    if (value && (!latest || value.modified > latest.modified)) latest = value;
  }
  return latest;
}

/** A private browser session. preview() does not grant submission permission. */
export async function startLocalUi({ runDiagnostics, publicBase = PUBLIC_BASE, dataDir, executionLocation = 'user_device' } = {}) {
  if (typeof runDiagnostics !== 'function') throw new TypeError('runDiagnostics is required');
  if (!['user_device', 'linux_lab'].includes(executionLocation)) throw new TypeError('invalid executionLocation');
  const target = destination(publicBase);
  const root = dataDir || join(homedir(), '.local', 'share', 'fanqiang-diagnostics');
  await mkdir(root, { recursive: true, mode: 0o700 });
  const rootStat = await lstat(root);
  if (!rootStat.isDirectory() || rootStat.isSymbolicLink()) throw new Error('unsafe_data_directory');
  let directory = await mkdtemp(join(root, 'session-'));
  await chmod(directory, 0o700);
  let recovery = await latestRecoverable(root, directory);
  const capability = secret();
  const sessionKey = secret();
  const nonce = randomBytes(24).toString('base64');
  const basePath = '/s/' + capability + '/';
  let origin;
  let expectedHost;
  let closed = false;
  let epoch = 0;
  let revision = 0;
  let usedBytes = 0;
  let phase = 'idle';
  let progress = null;
  let report = null;
  let receipt = null;
  let previewGrant = null;
  let attempted = false;
  let localLog = '';
  let logCategories = [];
  let active = null;
  let error = null;
  let queue = Promise.resolve();
  let remoteController = null;
  const locked = action => {
    const result = queue.then(action);
    queue = result.catch(() => {});
    return result;
  };
  const invalidated = () => { previewGrant = null; revision++; };
  const busy = () => phase === 'submitting' || phase === 'deleting';
  const assertEditable = () => {
    if (busy() || active) throw fault('busy');
    if (attempted) throw fault('submission_pending');
    if (receipt && !receipt.deleted_at) throw fault('delete_remote_first');
  };
  async function persist(name, value) {
    const temporary = join(directory, name + '.' + secret() + '.tmp');
    const handle = await open(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL, 0o600);
    try {
      await handle.writeFile(canonicalJson(value) + '\n', 'utf8');
      await handle.sync();
    } finally { await handle.close(); }
    try { await rename(temporary, join(directory, name)); }
    catch (failure) { await rm(temporary, { force: true }); throw failure; }
  }
  const receiptView = () => receipt ? {
    receipt_id: receipt.receipt_id,
    received_at: receipt.received_at,
    expires_at: receipt.expires_at,
    deleted_at: receipt.deleted_at || null
  } : null;
  function getStatus() {
    return clone({
      phase, execution_location: executionLocation, progress,
      has_report: !!report, revision, error,
      preview_sha256: previewGrant?.digest || null,
      session_budget: { max_payload_bytes: SESSION_CAP, used_payload_bytes: usedBytes + (active?.observed || 0) },
      can_start: !active && !busy() && !attempted && (!receipt || !!receipt.deleted_at) && usedBytes < SESSION_CAP,
      receipt: receiptView(), submission_pending: attempted && !receipt,
      can_restore: !!recovery && !active && !busy() && !report && !receipt && !attempted
    });
  }
  function preview() {
    return report ? { report: clone(report), sha256: reportDigest(report) } : null;
  }
  function stop() {
    if (active) {
      active.controller.abort();
      phase = 'stopping';
      invalidated();
    }
    return getStatus();
  }
  function cleanProgress(value, run) {
    if (!value || !stages.has(value.stage)) return;
    const valid = n => Number.isSafeInteger(n) && n >= 0;
    if (!valid(value.completed) || !valid(value.total) || value.completed > value.total || value.total > 100 ||
        !valid(value.used_payload_bytes) || value.used_payload_bytes > run.cap) return;
    run.observed = Math.max(run.observed, value.used_payload_bytes);
    progress = { stage: value.stage, completed: value.completed, total: value.total, used_payload_bytes: value.used_payload_bytes };
  }
  async function start(body) {
    keys(body, ['throughput', 'problem_category']);
    if (typeof body.throughput !== 'boolean' || !categories.has(body.problem_category)) throw fault('invalid_plan', 400);
    assertEditable();
    const cap = Math.min(RUN_CAP, SESSION_CAP - usedBytes);
    if (cap <= 0) throw fault('budget_exhausted');
    invalidated();
    epoch++;
    report = null;
    receipt = null;
    error = null;
    localLog = '';
    logCategories = [];
    attempted = false;
    phase = 'running';
    progress = null;
    const run = { id: epoch, controller: new AbortController(), observed: 0, cap };
    active = run;
    await Promise.all(['report.json', 'receipt.json', 'pending.json'].map(name => rm(join(directory, name), { force: true })));
    const complete = async (result, failure) => locked(async () => {
      if (closed || active !== run || run.id !== epoch) return;
      let charge = run.observed;
      try {
        if (failure) throw failure;
        const copy = clone(result);
        if (!validateReport(copy).ok || copy.collector.execution_location !== executionLocation ||
            copy.budget.used_payload_bytes > run.cap) throw new Error('invalid_report');
        charge = Math.max(charge, copy.budget.used_payload_bytes);
        report = copy;
        await persist('report.json', report);
        phase = run.controller.signal.aborted ? 'stopped' : 'complete';
      } catch {
        // A failed producer cannot prove the unreported body size; reserve its whole allowance.
        charge = run.cap;
        report = null;
        error = run.controller.signal.aborted ? 'cancelled' : 'diagnostic_failed';
        phase = run.controller.signal.aborted ? 'stopped' : 'error';
      }
      usedBytes = Math.min(SESSION_CAP, usedBytes + charge);
      active = null;
      invalidated();
    });
    Promise.resolve().then(() => runDiagnostics({
      throughput: body.throughput,
      problemCategory: body.problem_category,
      executionLocation,
      maxPayloadBytes: cap,
      signal: run.controller.signal,
      onProgress: value => { if (active === run && !closed) cleanProgress(value, run); }
    })).then(result => complete(result), failure => complete(null, failure)).catch(() => {});
    return getStatus();
  }
  async function updateLogs(body) {
    keys(body, ['text']);
    if (typeof body.text !== 'string' || Buffer.byteLength(body.text) > 48 * 1024) throw fault('invalid_log', 400);
    assertEditable();
    invalidated();
    const redacted = redactText(body.text);
    localLog = redacted.text;
    logCategories = [...new Set(redacted.categories)];
    if (report) {
      const copy = clone(report);
      copy.redaction = { raw_logs_included: false, removed_categories: logCategories };
      if (!validateReport(copy).ok) throw fault('invalid_report', 500);
      report = copy;
      await persist('report.json', report);
    }
    return { text: localLog, categories: logCategories, revision, status: getStatus() };
  }
  async function createPreview(body) {
    keys(body, []);
    if (active || busy() || !report) throw fault('report_not_ready');
    if (receipt && !receipt.deleted_at) throw fault('already_submitted');
    if (!validateReport(report).ok) throw fault('invalid_report', 500);
    if (!attempted) {
      const frozen = clone(report);
      previewGrant = {
        report: frozen, digest: reportDigest(frozen), revision,
        token: secret(), idempotency: randomUUID()
      };
    }
    if (!previewGrant) throw fault('preview_required');
    phase = 'review';
    return {
      report: clone(previewGrant.report), preview_sha256: previewGrant.digest,
      preview_token: previewGrant.token, revision,
      destination: target + '/v1/reports', retention_days: 30, public: false
    };
  }
  async function settleReceipt(value = receipt) {
    await persist('receipt.json', value);
    await rm(join(directory, 'pending.json'), { force: true });
    receipt = value;
    attempted = false;
    error = null;
    phase = receipt.deleted_at ? 'remote_deleted' : 'submitted';
  }
  async function submit(body) {
    keys(body, ['preview_sha256', 'preview_token']);
    if (receipt && !receipt.deleted_at) {
      try { await settleReceipt(); }
      catch { throw fault('receipt_storage_failed', 502); }
      return { receipt: receiptView(), status: getStatus() };
    }
    if (active || busy()) throw fault('busy');
    const grant = previewGrant;
    if (!grant || grant.revision !== revision || !same(body.preview_sha256, grant.digest) ||
        !same(body.preview_token, grant.token) || reportDigest(report) !== grant.digest) throw fault('preview_required');
    phase = 'submitting';
    attempted = true;
    error = null;
    remoteController = new AbortController();
    const timeout = setTimeout(() => remoteController?.abort(), 12000);
    try {
      await persist('pending.json', { report: grant.report, digest: grant.digest, idempotency: grant.idempotency });
      const response = await fetch(target + '/v1/reports', {
        method: 'POST', redirect: 'error',
        headers: { 'Content-Type': 'application/json' },
        body: canonicalJson({
          report: grant.report, idempotency_key: grant.idempotency,
          consent: { version: '1', preview_sha256: grant.digest, action: 'submit' }
        }),
        signal: remoteController.signal
      });
      if (!response.ok) { await response.body?.cancel(); throw fault('submission_failed', 502); }
      const value = await remoteJson(response);
      if (!validReceipt(value)) throw fault('invalid_receipt', 502);
      receipt = {
        receipt_id: value.receipt_id, received_at: value.received_at,
        expires_at: value.expires_at, delete_token: value.delete_token
      };
      await settleReceipt();
      return { receipt: receiptView(), status: getStatus() };
    } catch {
      phase = 'review';
      error = 'submission_uncertain';
      throw fault('submission_uncertain', 502);
    } finally { clearTimeout(timeout); remoteController = null; }
  }
  async function deleteRemote(body) {
    keys(body, []);
    if (active || busy()) throw fault('busy');
    if (!receipt) throw fault('receipt_required');
    if (receipt.deleted_at) {
      try { await settleReceipt(); }
      catch { throw fault('receipt_storage_failed', 502); }
      return { receipt: receiptView(), status: getStatus() };
    }
    phase = 'deleting';
    remoteController = new AbortController();
    const timeout = setTimeout(() => remoteController?.abort(), 12000);
    try {
      const response = await fetch(target + '/v1/reports/' + encodeURIComponent(receipt.receipt_id), {
        method: 'DELETE', redirect: 'error',
        headers: { Authorization: 'Bearer ' + receipt.delete_token },
        signal: remoteController.signal
      });
      await response.body?.cancel();
      if (!response.ok && response.status !== 404) throw new Error();
      await settleReceipt({ ...receipt, deleted_at: new Date().toISOString() });
      invalidated();
      return { receipt: receiptView(), status: getStatus() };
    } catch { phase = 'submitted'; throw fault('delete_failed', 502); }
    finally { clearTimeout(timeout); remoteController = null; }
  }
  async function deleteLocal(body) {
    keys(body, []);
    if (active || busy()) throw fault('busy');
    if (attempted) throw fault('submission_pending');
    if (receipt && !receipt.deleted_at) throw fault('delete_remote_first');
    epoch++;
    invalidated();
    report = null; receipt = null; attempted = false;
    localLog = ''; logCategories = []; progress = null; error = null;
    await Promise.all(['report.json', 'receipt.json', 'pending.json'].map(name => rm(join(directory, name), { force: true })));
    phase = 'idle';
    return getStatus();
  }

  async function restore(body) {
    keys(body, []);
    assertEditable();
    if (report || receipt) throw fault('delete_local_first');
    if (!recovery) throw fault('nothing_to_restore');
    const found = await recoverable(recovery.directory);
    if (!found) { recovery = null; throw fault('nothing_to_restore'); }
    directory = found.directory;
    report = clone(found.report);
    receipt = found.receipt ? clone(found.receipt) : null;
    invalidated();
    localLog = ''; logCategories = []; progress = null;
    attempted = !!found.pending;
    if (found.pending) {
      previewGrant = {
        report: clone(found.pending.report), digest: found.pending.digest,
        idempotency: found.pending.idempotency, token: secret(), revision
      };
    }
    phase = receipt ? 'submitted' : 'review';
    error = attempted ? 'submission_uncertain' : null;
    recovery = null;
    return getStatus();
  }

  function respond(response, status, value, html = false) {
    response.writeHead(status, {
      'Content-Type': html ? 'text/html; charset=utf-8' : 'application/json; charset=utf-8',
      'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
      'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
      'Cross-Origin-Resource-Policy': 'same-origin', 'Cross-Origin-Opener-Policy': 'same-origin',
      'Content-Security-Policy': "default-src 'none'; script-src 'nonce-" + nonce + "'; style-src 'nonce-" + nonce + "'; connect-src 'self'; img-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    });
    response.end(html ? value : JSON.stringify(value));
  }
  const server = createServer(async (request, response) => {
    try {
      const countHeader = name => request.rawHeaders.filter((_, index) => index % 2 === 0 && request.rawHeaders[index].toLowerCase() === name).length;
      if (closed || request.headers.host !== expectedHost || countHeader('host') !== 1) throw fault('invalid_host', 403);
      const suppliedOrigin = request.headers.origin;
      if (countHeader('origin') > 1 || (suppliedOrigin && suppliedOrigin !== origin)) throw fault('invalid_origin', 403);
      if (request.method === 'GET' && request.url === basePath) {
        respond(response, 200, renderUiPage({ nonce, sessionKey, basePath, target, executionLocation }), true);
        return;
      }
      if (!request.url?.startsWith(basePath + 'api/')) throw fault('not_found', 404);
      if (!same(request.headers['x-session'], sessionKey) || countHeader('x-session') !== 1) throw fault('invalid_session', 403);
      if (request.headers['sec-fetch-site'] && request.headers['sec-fetch-site'] !== 'same-origin') throw fault('invalid_origin', 403);
      const route = request.url.slice((basePath + 'api/').length);
      if (request.method === 'GET' && route === 'status') { respond(response, 200, getStatus()); return; }
      if (request.method !== 'POST') throw fault('method_not_allowed', 405);
      if (suppliedOrigin !== origin) throw fault('invalid_origin', 403);
      if (busy()) throw fault('busy');
      const body = await readJson(request);
      const actions = { start, restore, stop: async b => { keys(b, []); return stop(); }, logs: updateLogs, preview: createPreview, submit, 'remote-delete': deleteRemote, 'local-delete': deleteLocal };
      if (!Object.hasOwn(actions, route)) throw fault('not_found', 404);
      const result = await locked(() => { if (closed || busy()) throw fault('busy'); return actions[route](body); });
      respond(response, 200, result);
    } catch (failure) {
      if (!response.headersSent) respond(response, failure.status || 500, { error: failure.code || 'local_error' });
      else response.end();
    }
  });
  server.requestTimeout = 10000;
  server.headersTimeout = 10000;
  server.maxHeadersCount = 32;
  server.keepAliveTimeout = 1000;
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  expectedHost = '127.0.0.1:' + server.address().port;
  origin = 'http://' + expectedHost;
  return {
    url: origin + basePath, getStatus, preview, stop,
    close: async () => {
      if (closed) return;
      closed = true;
      active?.controller.abort();
      remoteController?.abort();
      invalidated();
      await new Promise(resolve => { server.close(resolve); server.closeAllConnections(); });
    }
  };
}
