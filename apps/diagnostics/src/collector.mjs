import { createServer } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { createHash, createHmac, randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { chmodSync, existsSync, lstatSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { isIP } from 'node:net';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { setImmediate as yieldImmediate } from 'node:timers/promises';
import { VERSION, validateReport, canonicalJson, reportDigest } from './report.mjs';

const MiB = 1024 * 1024;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const HEX = /^[0-9a-f]{64}$/;
const DAY = 86400000;
const defaults = {
  host: '127.0.0.1', port: 8792, dataDir: '/var/lib/fanqiang-diagnostics',
  maxBodyBytes: 65536, bodyTimeoutMs: 5000, socketTimeoutMs: 16000,
  retentionMs: 30 * DAY, cleanupIntervalMs: 60000,
  maxReports: 10000, maxStoredBytes: 64 * MiB, maxDatabaseBytes: 128 * MiB,
  maxConcurrentRequests: 32, maxClientConcurrentRequests: 4, maxClients: 4096,
  rateWindowMs: 60000, maxRequestsPerWindow: 120, maxGlobalRequestsPerWindow: 600,
  submitWindowMs: 3600000, maxSubmissionsPerWindow: 20,
  downloadWindowMs: 3600000, maxClientDownloadBytes: 60 * MiB,
  maxGlobalDownloadBytes: 512 * MiB, maxDownloadBytes: 10 * MiB,
  maxConcurrentDownloads: 2, maxClientConcurrentDownloads: 1,
  downloadTimeoutMs: 15000, downloadChunkBytes: 65536,
};
const sha256 = value => createHash('sha256').update(value).digest('hex');
const hmac = (key, value) => createHmac('sha256', key).update(value).digest();
const plainObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const exactKeys = (value, names) => plainObject(value) && Object.keys(value).length === names.length && names.every(key => Object.hasOwn(value, key));
const loopback = address => address === '127.0.0.1' || address === '::1' || address === '::ffff:127.0.0.1';
const sameHash = (left, right) => typeof left === 'string' && typeof right === 'string' && HEX.test(left) && HEX.test(right) && timingSafeEqual(Buffer.from(left, 'hex'), Buffer.from(right, 'hex'));

function optionsWithDefaults(options) {
  const config = { ...defaults, ...options };
  if (!['127.0.0.1', '::1'].includes(config.host)) throw new Error('collector_loopback_required');
  for (const [key, value] of Object.entries(defaults)) {
    if (typeof value === 'number' && (!Number.isSafeInteger(config[key]) || config[key] < (key === 'port' ? 0 : 1))) throw new Error('invalid_collector_option');
  }
  if (config.port > 65535 || config.maxBodyBytes > 65536 || config.maxDownloadBytes > 10 * MiB || config.retentionMs > 30 * DAY || config.downloadTimeoutMs > 15000) throw new Error('collector_limit_exceeded');
  config.now = options.now ?? Date.now;
  config.dataDir = resolve(config.dataDir);
  return config;
}

function privateFile(path, initial) {
  if (existsSync(path)) {
    const stat = lstatSync(path);
    if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('unsafe_storage_path');
  } else {
    try { writeFileSync(path, initial, { flag: 'wx', mode: 0o600 }); }
    catch (error) { if (error.code !== 'EEXIST') throw error; }
    if (!lstatSync(path).isFile() || lstatSync(path).isSymbolicLink()) throw new Error('unsafe_storage_path');
  }
  chmodSync(path, 0o600);
}

function openStore(config) {
  mkdirSync(config.dataDir, { recursive: true, mode: 0o700 });
  const stat = lstatSync(config.dataDir);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('unsafe_storage_path');
  chmodSync(config.dataDir, 0o700);
  const keyPath = join(config.dataDir, 'collector.key');
  privateFile(keyPath, randomBytes(32));
  const secret = readFileSync(keyPath);
  if (secret.length !== 32) throw new Error('invalid_collector_key');
  const dbPath = join(config.dataDir, 'reports.sqlite');
  privateFile(dbPath, Buffer.alloc(0));
  const db = new DatabaseSync(dbPath);
  db.exec(`PRAGMA journal_mode=DELETE; PRAGMA secure_delete=ON; PRAGMA busy_timeout=1000;
    PRAGMA max_page_count=${Math.ceil(config.maxDatabaseBytes / 4096)};
    CREATE TABLE IF NOT EXISTS reports (
      receipt_id TEXT PRIMARY KEY,
      idempotency_hash TEXT UNIQUE NOT NULL,
      request_hash TEXT NOT NULL,
      report_json TEXT NOT NULL,
      payload_bytes INTEGER NOT NULL,
      received_at INTEGER NOT NULL,
      expires_at INTEGER NOT NULL,
      delete_token_hash TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS reports_expiry ON reports(expires_at);`);
  const statements = {
    expiry: db.prepare('DELETE FROM reports WHERE expires_at <= ?'),
    byKey: db.prepare('SELECT * FROM reports WHERE idempotency_hash = ?'),
    byId: db.prepare('SELECT * FROM reports WHERE receipt_id = ?'),
    insert: db.prepare('INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?, ?, ?)'),
    remove: db.prepare('DELETE FROM reports WHERE receipt_id = ?'),
    stats: db.prepare('SELECT COUNT(*) AS reports, COALESCE(SUM(payload_bytes), 0) AS bytes FROM reports'),
    export: db.prepare('SELECT receipt_id, report_json, received_at, expires_at FROM reports WHERE expires_at > ? ORDER BY received_at, receipt_id'),
  };
  const tokenFor = row => hmac(secret, `delete:v1:${row.receipt_id}:${row.request_hash}`).toString('base64url');
  const receiptFor = row => ({ receipt_id: row.receipt_id, received_at: new Date(row.received_at).toISOString(), expires_at: new Date(row.expires_at).toISOString(), delete_token: tokenFor(row) });
  return { db, statements, secret, tokenFor, receiptFor };
}

function send(res, status, value, retryAfter) {
  if (res.destroyed || res.writableEnded) return;
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  if (status >= 400) res.setHeader('Connection', 'close');
  if (retryAfter) res.setHeader('Retry-After', String(Math.max(1, Math.ceil(retryAfter))));
  res.end(JSON.stringify(value));
}
const fail = (res, status, code, retryAfter) => send(res, status, { error: code }, retryAfter);

function readJson(req, config) {
  return new Promise((resolveBody, reject) => {
    let bytes = 0;
    const chunks = [];
    let done = false;
    const finish = (error, value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      req.off('data', onData); req.off('end', onEnd); req.off('aborted', onAbort); req.off('error', onAbort);
      if (error) { req.pause(); reject(error); } else resolveBody(value);
    };
    const onData = chunk => {
      bytes += chunk.length;
      if (bytes > config.maxBodyBytes) return finish({ status: 413, code: 'body_too_large' });
      chunks.push(chunk);
    };
    const onEnd = () => {
      try {
        const raw = new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks));
        finish(null, JSON.parse(raw));
      } catch { finish({ status: 400, code: 'invalid_json' }); }
    };
    const onAbort = () => finish({ status: 400, code: 'request_aborted' });
    const timer = setTimeout(() => finish({ status: 408, code: 'request_timeout' }), config.bodyTimeoutMs);
    timer.unref();
    req.on('data', onData); req.once('end', onEnd); req.once('aborted', onAbort); req.once('error', onAbort);
  });
}

function counter(now) { return { started: now, used: 0 }; }
function freshCounter(value, now, window) {
  if (now - value.started >= window) { value.started = now; value.used = 0; }
  return value;
}
function retrySeconds(value, now, window) { return Math.max(1, Math.ceil((value.started + window - now) / 1000)); }

async function streamDownload(req, res, bytes, config) {
  let ended = false;
  const completion = new Promise(resolveDone => {
    const done = () => { if (!ended) { ended = true; resolveDone(); } };
    res.once('finish', done); res.once('close', done); res.once('error', done);
  });
  const timer = setTimeout(() => res.destroy(), config.downloadTimeoutMs);
  timer.unref();
  res.statusCode = 200;
  res.setHeader('Content-Type', 'application/octet-stream');
  res.setHeader('Content-Length', String(bytes));
  res.setHeader('Content-Encoding', 'identity');
  res.setHeader('Cache-Control', 'no-store, no-transform');
  res.setHeader('X-Accel-Buffering', 'no');
  try {
    for (let sent = 0; sent < bytes && !ended && !res.destroyed;) {
      const payload = randomBytes(Math.min(config.downloadChunkBytes, bytes - sent));
      sent += payload.length;
      if (!res.write(payload)) {
        await new Promise(resolveDrain => {
          const done = () => { res.off('drain', done); res.off('close', done); res.off('error', done); resolveDrain(); };
          res.once('drain', done); res.once('close', done); res.once('error', done);
        });
      }
      await yieldImmediate();
    }
    if (!ended && !res.destroyed) res.end();
    await completion;
  } finally { clearTimeout(timer); }
}

export async function createCollector(options = {}) {
  const config = optionsWithDefaults(options);
  const store = openStore(config);
  const { statements, db, secret } = store;
  const clientSecret = randomBytes(32);
  const clients = new Map();
  const globalRequests = counter(config.now());
  const globalDownload = counter(config.now());
  let activeRequests = 0;
  let activeDownloads = 0;
  let closed = false;
  const cleanupExpired = () => statements.expiry.run(config.now()).changes;
  cleanupExpired();
  const idleWindow = Math.max(config.rateWindowMs, config.submitWindowMs, config.downloadWindowMs);
  const pruneClients = () => {
    const now = config.now();
    for (const [key, state] of clients) if (state.active === 0 && state.downloads === 0 && now - state.lastSeen >= idleWindow) clients.delete(key);
  };
  const cleanupTimer = setInterval(() => { try { cleanupExpired(); pruneClients(); } catch { /* No submitted data is logged. */ } }, config.cleanupIntervalMs);
  cleanupTimer.unref();

  async function handle(req, res) {
    const now = config.now();
    const forwarded = req.headers['x-diagnostics-client'];
    let client = req.socket.remoteAddress ?? 'unknown';
    if (loopback(client) && forwarded !== undefined) {
      if (typeof forwarded !== 'string' || forwarded.length > 45 || !isIP(forwarded)) return fail(res, 400, 'invalid_proxy_identity');
      client = forwarded;
    }
    const key = hmac(clientSecret, client).toString('hex');
    client = undefined;
    let state = clients.get(key);
    if (!state) {
      pruneClients();
      if (clients.size >= config.maxClients) return fail(res, 503, 'client_capacity', 60);
      state = { requests: counter(now), submissions: counter(now), download: counter(now), lastSeen: now, active: 0, downloads: 0 };
      clients.set(key, state);
    }
    state.lastSeen = now;
    freshCounter(state.requests, now, config.rateWindowMs);
    freshCounter(globalRequests, now, config.rateWindowMs);
    if (state.requests.used >= config.maxRequestsPerWindow || globalRequests.used >= config.maxGlobalRequestsPerWindow) return fail(res, 429, 'rate_limited', Math.max(retrySeconds(state.requests, now, config.rateWindowMs), retrySeconds(globalRequests, now, config.rateWindowMs)));
    state.requests.used++; globalRequests.used++;
    if (activeRequests >= config.maxConcurrentRequests || state.active >= config.maxClientConcurrentRequests) return fail(res, 429, 'concurrency_limited', 1);
    activeRequests++; state.active++;
    let released = false;
    const release = () => { if (!released) { released = true; activeRequests--; state.active--; } };
    res.once('close', release); res.once('finish', release);
    try {
      if (!req.url?.startsWith('/')) return fail(res, 400, 'invalid_path');
      const url = new URL(req.url, 'http://localhost');
      if ((req.method !== 'POST' || url.pathname !== '/v1/reports') && (req.headers['transfer-encoding'] || Number(req.headers['content-length'] ?? 0) > 0)) return fail(res, 400, 'unexpected_body');
      if (req.method === 'GET' && url.pathname === '/health' && !url.search) return send(res, 200, { ok: true, service: 'fanqiang-diagnostics', version: VERSION });
      if (req.method === 'GET' && url.pathname === '/v1/ping' && !url.search) return send(res, 200, { ok: true });
      if (req.method === 'GET' && url.pathname === '/v1/download') {
        const values = [...url.searchParams];
        if (values.length !== 1 || values[0][0] !== 'bytes' || !/^[0-9]{1,8}$/.test(values[0][1])) return fail(res, 400, 'invalid_download_size');
        const bytes = Number(values[0][1]);
        if (bytes < 1 || bytes > config.maxDownloadBytes) return fail(res, 400, 'invalid_download_size');
        freshCounter(state.download, now, config.downloadWindowMs); freshCounter(globalDownload, now, config.downloadWindowMs);
        if (state.download.used + bytes > config.maxClientDownloadBytes || globalDownload.used + bytes > config.maxGlobalDownloadBytes) return fail(res, 429, 'download_budget_exhausted', Math.max(retrySeconds(state.download, now, config.downloadWindowMs), retrySeconds(globalDownload, now, config.downloadWindowMs)));
        if (activeDownloads >= config.maxConcurrentDownloads || state.downloads >= config.maxClientConcurrentDownloads) return fail(res, 429, 'download_concurrency_limited', 1);
        // Reserve the full request so cancellation cannot bypass the traffic budget.
        state.download.used += bytes; globalDownload.used += bytes;
        activeDownloads++; state.downloads++;
        try { await streamDownload(req, res, bytes, config); }
        finally { activeDownloads--; state.downloads--; }
        return;
      }
      if (req.method === 'POST' && url.pathname === '/v1/reports' && !url.search) {
        const type = req.headers['content-type'] ?? '';
        if (!/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(type) || (req.headers['content-encoding'] && req.headers['content-encoding'] !== 'identity')) return fail(res, 415, 'json_required');
        const length = req.headers['content-length'];
        if (length !== undefined && (!/^[0-9]+$/.test(length) || Number(length) > config.maxBodyBytes)) return fail(res, 413, 'body_too_large');
        let envelope;
        try { envelope = await readJson(req, config); }
        catch (error) { return fail(res, error.status ?? 400, error.code ?? 'invalid_body'); }
        if (!exactKeys(envelope, ['report', 'idempotency_key', 'consent']) || typeof envelope.idempotency_key !== 'string' || !UUID.test(envelope.idempotency_key) || !exactKeys(envelope.consent, ['version', 'preview_sha256', 'action']) || envelope.consent.version !== '1' || envelope.consent.action !== 'submit' || !HEX.test(envelope.consent.preview_sha256 ?? '')) return fail(res, 400, 'invalid_envelope');
        let valid;
        try { valid = validateReport(envelope.report); } catch { return fail(res, 400, 'invalid_report'); }
        if (!valid.ok) return fail(res, 400, 'invalid_report');
        if (!sameHash(reportDigest(envelope.report), envelope.consent.preview_sha256)) return fail(res, 400, 'preview_digest_mismatch');
        const requestHash = sha256(canonicalJson(envelope));
        const idempotencyHash = hmac(secret, `idempotency:v1:${envelope.idempotency_key}`).toString('hex');
        cleanupExpired();
        const previous = statements.byKey.get(idempotencyHash);
        if (previous) {
          if (!sameHash(previous.request_hash, requestHash)) return fail(res, 409, 'idempotency_conflict');
          const receipt = store.receiptFor(previous);
          if (!sameHash(sha256(receipt.delete_token), previous.delete_token_hash)) return fail(res, 503, 'storage_key_mismatch');
          return send(res, 200, receipt);
        }
        freshCounter(state.submissions, now, config.submitWindowMs);
        if (state.submissions.used >= config.maxSubmissionsPerWindow) return fail(res, 429, 'submission_rate_limited', retrySeconds(state.submissions, now, config.submitWindowMs));
        const reportJson = canonicalJson(envelope.report);
        const payloadBytes = Buffer.byteLength(reportJson);
        const stats = statements.stats.get();
        if (stats.reports >= config.maxReports || stats.bytes + payloadBytes > config.maxStoredBytes) return fail(res, 503, 'storage_capacity', 60);
        const receivedAt = config.now();
        const row = { receipt_id: randomUUID(), request_hash: requestHash, received_at: receivedAt, expires_at: receivedAt + config.retentionMs };
        const receipt = store.receiptFor(row);
        try { statements.insert.run(row.receipt_id, idempotencyHash, requestHash, reportJson, payloadBytes, receivedAt, row.expires_at, sha256(receipt.delete_token)); }
        catch { return fail(res, 503, 'storage_unavailable', 60); }
        state.submissions.used++;
        return send(res, 201, receipt);
      }
      const match = /^\/v1\/reports\/([0-9a-f-]+)$/i.exec(url.pathname);
      if (req.method === 'DELETE' && match && UUID.test(match[1]) && !url.search) {
        const authorization = req.headers.authorization;
        if (typeof authorization !== 'string' || !/^Bearer [A-Za-z0-9_-]{43}$/.test(authorization)) return fail(res, 401, 'delete_token_required');
        cleanupExpired();
        const row = statements.byId.get(match[1]);
        if (!row || !sameHash(sha256(authorization.slice(7)), row.delete_token_hash)) return fail(res, 404, 'report_not_found');
        statements.remove.run(match[1]);
        return send(res, 200, { deleted: true });
      }
      return fail(res, 404, 'not_found');
    } catch {
      if (res.headersSent) res.destroy(); else fail(res, 500, 'internal_error');
    }
  }

  const server = createServer({ maxHeaderSize: 8192, connectionsCheckingInterval: 1000, headersTimeout: Math.min(5000, config.bodyTimeoutMs + 1000), requestTimeout: config.bodyTimeoutMs + 1000 }, (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Robots-Tag', 'noindex, nofollow, noarchive');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    req.on('error', () => {});
    handle(req, res).catch(() => { if (res.headersSent) res.destroy(); else fail(res, 500, 'internal_error'); });
  });
  server.maxConnections = config.maxConcurrentRequests * 2;
  server.keepAliveTimeout = 1000;
  server.maxRequestsPerSocket = 50;
  server.setTimeout(config.socketTimeoutMs, socket => socket.destroy());
  server.on('clientError', (_error, socket) => {
    if (socket.writable) socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\nCache-Control: no-store\r\nX-Robots-Tag: noindex\r\n\r\n');
  });
  try { await new Promise((resolveListen, reject) => { server.once('error', reject); server.listen(config.port, config.host, () => { server.off('error', reject); resolveListen(); }); }); }
  catch (error) { clearInterval(cleanupTimer); db.close(); throw error; }
  const address = server.address();
  return {
    server,
    url: `http://${config.host === '::1' ? '[::1]' : config.host}:${address.port}`,
    cleanupExpired,
    exportReports: () => statements.export.all(config.now()).map(row => ({ receipt_id: row.receipt_id, received_at: new Date(row.received_at).toISOString(), expires_at: new Date(row.expires_at).toISOString(), report: JSON.parse(row.report_json) })),
    getStats: () => ({ ...statements.stats.get(), activeRequests, activeDownloads, rememberedClients: clients.size }),
    close: async () => {
      if (closed) return;
      closed = true;
      clearInterval(cleanupTimer);
      await new Promise(resolveClose => { server.close(resolveClose); server.closeAllConnections(); });
      db.close();
    },
  };
}

async function cli() {
  const dataDir = resolve(process.env.FQDIAG_DATA_DIR ?? defaults.dataDir);
  if (process.argv[2] === 'export') {
    const db = new DatabaseSync(join(dataDir, 'reports.sqlite'), { readOnly: true });
    try {
      for (const row of db.prepare('SELECT receipt_id, report_json, received_at, expires_at FROM reports WHERE expires_at > ? ORDER BY received_at, receipt_id').iterate(Date.now())) {
        const line = JSON.stringify({ receipt_id: row.receipt_id, received_at: new Date(row.received_at).toISOString(), expires_at: new Date(row.expires_at).toISOString(), report: JSON.parse(row.report_json) }) + '\n';
        if (!process.stdout.write(line)) await new Promise(resolveDrain => process.stdout.once('drain', resolveDrain));
      }
    } finally { db.close(); }
    return;
  }
  if (process.argv.length > 2) throw new Error('unknown_collector_command');
  if (process.getuid?.() === 0) throw new Error('collector_nonroot_required');
  const collector = await createCollector({ dataDir, host: process.env.FQDIAG_HOST ?? defaults.host, port: Number(process.env.FQDIAG_PORT ?? defaults.port) });
  process.stdout.write(JSON.stringify({ status: 'listening', service: 'fanqiang-diagnostics', port: collector.server.address().port }) + '\n');
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { collector.close().then(() => process.exit(0), () => process.exit(1)); });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  cli().catch(() => { process.stderr.write('collector_start_failed\n'); process.exitCode = 1; });
}
