import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { mkdir, mkdtemp, readFile, writeFile, rm, open } from 'node:fs/promises';
import { join, resolve, sep } from 'node:path';
import { startLocalUi } from '../src/ui.mjs';
import { runDiagnostics } from '../src/measure.mjs';
import { PUBLIC_BASE, validateReport, reportDigest } from '../src/report.mjs';

if (!process.argv.includes('--run-live')) {
  process.stdout.write('Prepared only. Run with --run-live after the public collector is live; --ui-only reserves one measurement round instead of two.\n');
  process.exit(0);
}
const uiOnly = process.argv.includes('--ui-only');
const evidence = resolve(process.env.FQDIAG_EVIDENCE_DIR || join(process.cwd(), '.build', 'evidence'));
const privateRoot = resolve(process.env.FQDIAG_PRIVATE_DIR || join(process.cwd(), '.build', 'private-public-check'));
await mkdir(evidence, { recursive: true, mode: 0o700 });
await mkdir(privateRoot, { recursive: true, mode: 0o700 });
const ledgerFile = join(evidence, 'public-check-budget.json');
const lockFile = join(evidence, 'public-check.lock');
const lock = await open(lockFile, 'wx', 0o600);
await lock.close();
let privateRun;
let browser, page, ui;
let success = false;
let cleanupRequired = false;
let directReport = null, uiReport = null;
let receipt = null;
let browserErrors = [];
let consoleErrors = [];
let localRuns = 0;
let submissions = 0;
let deletions = 0;
let serverRequests = [];
const steps = [];
const startedAt = new Date().toISOString();
const nativeFetch = globalThis.fetch;
let ledger = [];
function cleanError(error) {
  return { name: error.name, message: String(error.message).replace(/https?:\/\/\S+/g, '[URL]').replace(/[A-Za-z0-9_-]{43,}/g, '[LONG_VALUE]').slice(0, 1200) };
}
async function save(name, value) {
  await writeFile(join(evidence, name), JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
}
function mark(name, detail = {}) {
  steps.push({ name, status: 'pass', submissions, deletions, ...detail });
}
async function reserve(kind) {
  const current = ledger.filter(row => Date.now() - Date.parse(row.started_at) < 3600000);
  if (current.length >= 3) throw new Error('Three 10 MiB rounds already reserved in the last hour; do not retry yet.');
  const row = { kind, started_at: new Date().toISOString(), reserved_payload_bytes: 10485760, used_payload_bytes: null, status: 'started' };
  ledger.push(row);
  await save('public-check-budget.json', ledger);
  return row;
}
function verifyMeasurement(report, name) {
  assert.equal(validateReport(report).ok, true, name + ': invalid report');
  assert.equal(report.collector.execution_location, 'linux_lab');
  for (const stage of ['dns', 'tcp', 'tls', 'http']) {
    assert.equal(report.measurements[stage].length, 3, name + ': missing ' + stage + ' samples');
    assert.ok(report.measurements[stage].every(sample => sample.status === 'ok' && sample.error_code === null && Number.isFinite(sample.duration_ms)), name + ': ' + stage + ' was not fully successful');
  }
  assert.equal(report.measurements.throughput.length, 1, name + ': missing download');
  const sample = report.measurements.throughput[0];
  assert.equal(sample.status, 'ok', name + ': download failed');
  assert.ok(Number.isFinite(sample.mbps) && sample.mbps > 0, name + ': download speed not finite positive');
  assert.ok(sample.bytes > 0 && sample.bytes <= 10485760);
  assert.ok(report.budget.used_payload_bytes <= 10485760);
  assert.equal(report.summary.download_mbps, sample.mbps);
  return { samples: Object.fromEntries(Object.entries(report.measurements).map(([stage, samples]) => [stage, samples.length])), download_mbps: sample.mbps, used_payload_bytes: report.budget.used_payload_bytes };
}
async function measure(kind, options) {
  const row = await reserve(kind);
  try {
    const report = await runDiagnostics({ ...options, throughput: true, executionLocation: 'linux_lab', maxPayloadBytes: 10485760 });
    row.used_payload_bytes = report.budget.used_payload_bytes;
    row.status = 'returned';
    await save('public-check-budget.json', ledger);
    return report;
  } catch (error) {
    row.status = 'failed';
    await save('public-check-budget.json', ledger);
    throw error;
  }
}
async function createUi() {
  return startLocalUi({
    publicBase: PUBLIC_BASE, dataDir: privateRun, executionLocation: 'linux_lab',
    runDiagnostics: options => {
      localRuns++;
      assert.equal(localRuns, 1, 'unexpected extra UI measurement');
      assert.equal(options.throughput, true);
      return measure('browser-ui', options);
    }
  });
}
async function openPage() {
  const current = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
  current.setDefaultTimeout(30000);
  current.on('pageerror', error => browserErrors.push(cleanError(error)));
  current.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(cleanError({ name: 'BrowserConsole', message: message.text() }));
  });
  await current.goto(ui.url);
  await current.locator('#phase').filter({ hasText: '准备开始' }).waitFor();
  return current;
}
try {
  try { ledger = JSON.parse(await readFile(ledgerFile, 'utf8')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  assert.ok(Array.isArray(ledger) && ledger.every(row => typeof row.started_at === 'string' && Number.isFinite(Date.parse(row.started_at))));
  const recent = ledger.filter(row => Date.now() - Date.parse(row.started_at) < 3600000).length;
  assert.ok(recent + (uiOnly ? 1 : 2) <= 3, 'Insufficient reserved rounds for this workflow; full run needs two slots, --ui-only needs one.');
  privateRun = await mkdtemp(join(privateRoot, 'live-'));
  // Count all application POSTs and DELETEs without recording tokens or request credentials.
  globalThis.fetch = async (url, options = {}) => {
    const address = String(url);
    const method = options.method || 'GET';
    if (address.startsWith(PUBLIC_BASE + '/v1/reports')) {
      if (method === 'POST') {
        submissions++;
        const envelope = JSON.parse(options.body);
        assert.equal(validateReport(envelope.report).ok, true);
        assert.equal(envelope.report.collector.execution_location, 'linux_lab');
        assert.equal(envelope.consent.preview_sha256, reportDigest(envelope.report));
        assert.doesNotMatch(String(options.body), /PUBLIC_CHECK_SYNTHETIC_LOG|demo@example\.invalid|192\.0\.2\.10/);
      }
      if (method === 'DELETE') deletions++;
      const response = await nativeFetch(url, options);
      serverRequests.push({ method, status: response.status });
      return response;
    }
    return nativeFetch(url, options);
  };

  const health = await nativeFetch(PUBLIC_BASE + '/health', { redirect: 'error', signal: AbortSignal.timeout(10000) });
  assert.equal(health.ok, true, 'public collector health failed');
  assert.equal((await health.json()).service, 'fanqiang-diagnostics');
  mark('public collector health');

  if (!uiOnly) {
    directReport = await measure('direct', { problemCategory: 'slow' });
    await save('public-direct-report.json', directReport);
    mark('direct real Linux measurement', verifyMeasurement(directReport, 'direct'));
    assert.equal(submissions, 0);
  } else {
    steps.push({ name: 'direct measurement intentionally omitted in --ui-only mode', status: 'skipped' });
  }
  ui = await createUi();
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  page = await openPage();
  assert.equal(submissions, 0);
  assert.equal(localRuns, 0);
  assert.equal(await page.locator('#throughput').isChecked(), false);
  mark('opening browser does not measure or submit');

  await page.locator('#problem').selectOption('slow');
  await page.locator('#throughput').check();
  await page.locator('#start').click();
  await page.waitForFunction(() => ['诊断完成', '已停止', '本次未完成'].includes(document.getElementById('phase').textContent));
  assert.equal(ui.getStatus().phase, 'complete', 'real UI run did not complete');
  uiReport = ui.preview()?.report;
  assert.ok(uiReport, 'real UI report missing');
  await save('public-ui-report.json', uiReport);
  mark('browser starts real fixed-target Linux measurement', verifyMeasurement(uiReport, 'browser'));
  assert.equal(submissions, 0);
  await page.locator('#logs').fill('PUBLIC_CHECK_SYNTHETIC_LOG password=DEMO_ONLY 192.0.2.10 demo@example.invalid');
  await page.waitForFunction(() => document.getElementById('log-categories').textContent.includes('email'));
  await page.locator('#preview').click();
  await page.locator('#review').waitFor({ state: 'visible' });
  uiReport = JSON.parse(await page.locator('#report-json').textContent());
  await save('public-ui-report.json', uiReport);
  assert.equal(uiReport.redaction.raw_logs_included, false);
  assert.doesNotMatch(JSON.stringify(uiReport), /PUBLIC_CHECK_SYNTHETIC_LOG|demo@example\.invalid|192\.0\.2\.10/);
  assert.equal(submissions, 0);
  mark('real report preview and synthetic local log stay unsubmitted');
  await page.locator('#notice').evaluate(element => {
    element.textContent = '公网验收：测量实际发生在 Linux 服务器；不能代表用户设备或 iPhone 的网络。日志片段是合成测试文本，全文不提交。';
  });
  await page.screenshot({ path: join(evidence, 'public-ui-preview.png'), fullPage: true });

  await page.locator('#submit').click();
  await page.locator('#receipt-box').waitFor({ state: 'visible' });
  receipt = ui.getStatus().receipt;
  assert.ok(receipt);
  assert.equal(submissions, 1);
  assert.equal(serverRequests.filter(row => row.method === 'POST').length, 1);
  assert.ok(serverRequests.some(row => row.method === 'POST' && [200, 201].includes(row.status)));
  assert.ok(Date.parse(receipt.expires_at) > Date.parse(receipt.received_at));
  assert.ok(Date.parse(receipt.expires_at) - Date.parse(receipt.received_at) <= 30 * 86400000);
  assert.equal(await page.locator('#delete-local').isEnabled(), false);
  mark('one explicit browser click submits the frozen report and receives expiry', { receipt });
  await page.close();
  await ui.close();

  ui = await createUi();
  page = await openPage();
  assert.equal(submissions, 1);
  assert.equal(localRuns, 1);
  await page.locator('#restore').click();
  await page.locator('#receipt-box').waitFor({ state: 'visible' });
  assert.equal(submissions, 1);
  assert.equal(localRuns, 1);
  assert.equal(ui.getStatus().receipt.receipt_id, receipt.receipt_id);
  mark('restart and explicit recovery do not measure or resubmit');

  await page.locator('#remote-delete').click();
  await page.locator('#receipt-state').filter({ hasText: '已删除' }).waitFor();
  receipt = ui.getStatus().receipt;
  assert.ok(receipt.deleted_at);
  assert.equal(deletions, 1);
  assert.ok(serverRequests.some(row => row.method === 'DELETE' && [200, 204].includes(row.status)), 'public deletion did not positively acknowledge');
  await page.screenshot({ path: join(evidence, 'public-ui-deleted.png'), fullPage: true });
  await page.locator('#delete-local').click();
  await page.locator('#receipt-box').waitFor({ state: 'hidden' });
  assert.equal(ui.preview(), null);
  mark('explicit public deletion acknowledged; private local receipt cleared', { receipt });
  assert.deepEqual(browserErrors, []);
  assert.deepEqual(consoleErrors.filter(row => !row.message.includes('404 (Not Found)')), []);
  success = true;
} catch (error) {
  steps.push({ name: 'public workflow', status: 'fail', error: cleanError(error) });
  if (page && !page.isClosed()) await page.screenshot({ path: join(evidence, 'public-ui-failure.png'), fullPage: true }).catch(() => {});
} finally {
  // A failed run preserves its private receipt/pending state so an operator can finish revocation.
  const status = ui?.getStatus();
  cleanupRequired = !!(status?.submission_pending || status?.receipt && !status.receipt.deleted_at || submissions > deletions && !receipt?.deleted_at);
  if (status?.receipt) receipt = status.receipt;
  await page?.close().catch(() => {});
  await browser?.close().catch(() => {});
  await ui?.close().catch(() => {});
  globalThis.fetch = nativeFetch;
  if (privateRun && !cleanupRequired) {
    assert.ok(privateRun.startsWith(privateRoot + sep));
    await rm(privateRun, { recursive: true, force: true });
  }
  const result = {
    status: success ? 'pass' : 'fail', started_at: startedAt, finished_at: new Date().toISOString(),
    scope: uiOnly ? 'real public UI workflow only; direct stage skipped' : 'direct measurement + Chromium UI + public collector',
    execution_location: 'linux_lab', public_base: PUBLIC_BASE, synthetic_measurements: false,
    synthetic_log_only: true, max_rounds_per_hour: 3, round_payload_cap_bytes: 10485760,
    direct_report: directReport ? 'public-direct-report.json' : null, ui_report: uiReport ? 'public-ui-report.json' : null,
    measurement_rounds_this_run: localRuns + (directReport ? 1 : 0), submissions, deletions,
    network_request_statuses: serverRequests, receipt, cleanup_required: cleanupRequired,
    private_recovery_directory: cleanupRequired ? privateRun : null,
    browser_errors: browserErrors, console_errors: consoleErrors, steps
  };
  await save('public-check.json', result);
  await writeFile(join(evidence, 'public-check.log'), steps.map(row => row.status.toUpperCase() + ' ' + row.name).join('\n') + '\n', { mode: 0o600 });
  await rm(lockFile, { force: true });
  process.stdout.write(JSON.stringify({ status: result.status, submissions, deletions, cleanup_required: cleanupRequired, evidence, private_recovery_directory: result.private_recovery_directory }) + '\n');
}
if (!success) process.exitCode = 1;
