import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { mkdir, mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { startLocalUi } from '../src/ui.mjs';
import { createCollector } from '../src/collector.mjs';
import { PROXY_NOTE, validateReport } from '../src/report.mjs';

const evidence = resolve(process.argv[2] || join(process.cwd(), '.build', 'evidence'));
await mkdir(evidence, { recursive: true });
const temporary = await mkdtemp(join(tmpdir(), 'fanqiang-browser-check-'));
const results = [];
const consoleErrors = [];
const pageErrors = [];
let browser, collector, ui, page;
let submissions = 0;
let deletions = 0;
let runs = 0;
let passed = false;
function mark(name, additional = {}) {
  results.push({ name, status: 'pass', stored_reports: collector.exportReports().length, submissions, deletions, ...additional });
}
function syntheticReport(options) {
  const report = {
    schema_version: '0.1', report_id: randomUUID(), created_at: new Date().toISOString(),
    collector: { name: 'fanqiang-diagnostics', version: '0.1.0', execution_location: 'linux_lab', platform: 'linux', routing_mode: 'os_direct_socket', proxy_note: PROXY_NOTE },
    problem_category: options.problemCategory,
    measurements: { dns: [], tcp: [], tls: [], http: [], throughput: [] },
    summary: { tcp_median_ms: null, http_median_ms: null, tcp_failure_ratio: null, download_mbps: null },
    budget: { max_payload_bytes: 10485760, used_payload_bytes: 0, max_duration_ms: 15000 },
    redaction: { raw_logs_included: false, removed_categories: [] },
    limitations: ['os_direct_socket', 'tun_may_affect_routing', 'no_icmp_packet_loss', 'fixed_target_only', 'no_application_proxy_test', 'throughput_not_requested', 'linux_lab_only']
  };
  assert.equal(options.executionLocation, 'linux_lab');
  assert.equal(validateReport(report).ok, true);
  return report;
}
const runDiagnostics = async options => {
  runs++;
  assert.equal(options.throughput, false);
  for (let completed = 0; completed <= 3; completed++) {
    options.onProgress({ stage: 'dns', completed, total: 3, used_payload_bytes: 0 });
    await new Promise(resolve => setTimeout(resolve, 35));
  }
  return syntheticReport(options);
};
async function newUi() {
  return startLocalUi({ runDiagnostics, publicBase: collector.url, dataDir: join(temporary, 'local'), executionLocation: 'linux_lab' });
}
async function openUi() {
  const current = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
  current.on('pageerror', error => pageErrors.push(error.name));
  current.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text().replace(/http\S+/g, '[LOCAL_URL]').slice(0, 250));
  });
  await current.goto(ui.url);
  await current.locator('#phase').filter({ hasText: '准备开始' }).waitFor();
  return current;
}
try {
  collector = await createCollector({ dataDir: join(temporary, 'collector'), host: '127.0.0.1', port: 0 });
  collector.server.on('request', req => {
    if (req.method === 'POST') submissions++;
    if (req.method === 'DELETE') deletions++;
  });
  ui = await newUi();
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  page = await openUi();
  assert.equal(await page.locator('#throughput').isChecked(), false);
  assert.equal(runs, 0);
  assert.equal(submissions, 0);
  assert.equal(collector.exportReports().length, 0);
  assert.match(await page.locator('.badge').innerText(), /Linux/);
  mark('launch has no diagnostic or upload; download defaults off');

  await page.locator('#problem').selectOption('application');
  await page.locator('#start').click();
  await page.locator('#phase').filter({ hasText: '诊断完成' }).waitFor();
  assert.equal(runs, 1);
  assert.equal(submissions, 0);
  assert.equal(collector.exportReports().length, 0);
  mark('human starts synthetic linux_lab run; no automatic upload');

  await page.locator('#logs').fill('password=DEMO_UI_FIXTURE_ONLY 192.0.2.10 https://example.invalid/test');
  await page.waitForFunction(() => document.getElementById('redacted-log').textContent.includes('REDACTED'));
  const redacted = await page.locator('#redacted-log').textContent();
  assert.doesNotMatch(redacted, /DEMO_UI_FIXTURE_ONLY|192\.0\.2\.10|example\.invalid/);
  await page.locator('#preview').click();
  await page.locator('#review').waitFor({ state: 'visible' });
  const originalDigest = await page.locator('#digest').textContent();
  assert.equal(submissions, 0);
  mark('local log redaction and explicit full preview do not upload');

  await page.locator('#logs').fill('password=DEMO_UI_FIXTURE_ONLY 192.0.2.10 https://example.invalid/test demo@example.invalid');
  await page.locator('#review').waitFor({ state: 'hidden' });
  assert.equal(await page.locator('#submit').isEnabled(), false);
  await page.waitForFunction(() => document.getElementById('log-categories').textContent.includes('email'));
  await page.locator('#preview').click();
  await page.locator('#review').waitFor({ state: 'visible' });
  const previewText = await page.locator('#report-json').textContent();
  const report = JSON.parse(previewText);
  assert.equal(report.collector.execution_location, 'linux_lab');
  assert.equal(report.redaction.raw_logs_included, false);
  assert.doesNotMatch(previewText, /DEMO_UI_FIXTURE_ONLY|192\.0\.2\.10|example\.invalid/);
  assert.notEqual(await page.locator('#digest').textContent(), originalDigest);
  assert.equal(submissions, 0);
  mark('editing logs revokes prior preview; new whitelist preview excludes all raw text');

  await page.locator('#notice').evaluate(element => {
    element.textContent = '浏览器验收演示：合成报告，非设备或网速实测。所有测量值保持“未测”；此时尚未提交。';
  });
  await page.screenshot({ path: join(evidence, 'ui-preview.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.screenshot({ path: join(evidence, 'ui-preview-narrow.png'), fullPage: true });
  await page.setViewportSize({ width: 1360, height: 1000 });
  mark('desktop and narrow layout screenshots; synthetic data prominently labelled');

  await page.locator('#submit').click();
  await page.locator('#receipt-box').waitFor({ state: 'visible' });
  assert.equal(submissions, 1);
  assert.equal(collector.exportReports().length, 1);
  assert.deepEqual(collector.exportReports()[0].report, report);
  assert.equal(await page.locator('#delete-local').isEnabled(), false);
  assert.equal(await page.locator('#submit').isEnabled(), false);
  mark('one deliberate click submits one report to real collector and shows receipt');

  await page.close();
  await ui.close();
  ui = await newUi();
  page = await openUi();
  assert.equal(runs, 1);
  assert.equal(submissions, 1);
  assert.equal(collector.exportReports().length, 1);
  await page.locator('#restore').click();
  await page.locator('#receipt-box').waitFor({ state: 'visible' });
  assert.equal(submissions, 1);
  assert.equal(runs, 1);
  assert.equal(await page.locator('#delete-local').isEnabled(), false);
  mark('restart restores receipt only on human click, with no new run or upload');

  await page.locator('#remote-delete').click();
  await page.locator('#receipt-state').filter({ hasText: '已删除' }).waitFor();
  assert.equal(deletions, 1);
  assert.equal(collector.exportReports().length, 0);
  assert.equal(await page.locator('#remote-delete').isEnabled(), false);
  await page.locator('#delete-local').click();
  await page.locator('#receipt-box').waitFor({ state: 'hidden' });
  assert.equal(ui.preview(), null);
  assert.equal(submissions, 1);
  mark('human deletes remote report, then clears local report and receipt');
  assert.deepEqual(pageErrors, []);
  const realConsoleErrors = consoleErrors.filter(text => !text.includes('404 (Not Found)'));
  assert.deepEqual(realConsoleErrors, []);
  mark('no browser runtime or CSP errors');
  passed = true;
} catch (error) {
  results.push({ name: 'browser workflow', status: 'fail', error_name: error.name, message: String(error.message).replace(/http\S+/g, '[LOCAL_URL]').slice(0, 1200) });
  if (page && !page.isClosed()) await page.screenshot({ path: join(evidence, 'ui-failure.png'), fullPage: true }).catch(() => {});
} finally {
  await page?.close().catch(() => {});
  await browser?.close().catch(() => {});
  await ui?.close().catch(() => {});
  await collector?.close().catch(() => {});
  await rm(temporary, { recursive: true, force: true });
  const output = { status: passed ? 'pass' : 'fail', browser: 'Chromium / Playwright', scope: 'Local browser workflow + real local collector; synthetic linux_lab report, no network measurement claims', screenshots: ['ui-preview.png', 'ui-preview-narrow.png'], runs, submissions, deletions, page_errors: pageErrors, console_errors: consoleErrors, steps: results };
  await writeFile(join(evidence, 'ui-browser-check.json'), JSON.stringify(output, null, 2) + '\n');
  await writeFile(join(evidence, 'ui-browser-check.log'), results.map(row => row.status.toUpperCase() + ' ' + row.name).join('\n') + '\n');
  process.stdout.write(JSON.stringify({ status: output.status, steps: results.length, runs, submissions, deletions, evidence }) + '\n');
}
if (!passed) process.exitCode = 1;
