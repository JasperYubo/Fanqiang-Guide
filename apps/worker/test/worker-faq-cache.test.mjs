import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { harness, events, withProvider, askBody, goodBody } from './worker-harness.mjs';
import { validateArtifact } from '../src/ilang.mjs';
import { fixture } from './faq-cache-fixture.mjs';

test('actual knowledge-question ask keeps AI/device gates and delivers a cache book with zero model calls', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'fg-faq-knowledge-'));
  try {
    cpSync(new URL('../src/', import.meta.url), dir, { recursive: true });
    writeFileSync(join(dir, 'faq-cache-data.mjs'), `export const FAQ_CACHE_DATA = ${JSON.stringify(fixture({ canonical_question: 'v2rayN是什么', aliases: [], intent: 'definition' }))};\n`);
    const { default: worker } = await import(pathToFileURL(join(dir, 'worker.mjs')).href);
    const h = harness(worker), cookie = await h.session(); let calls = 0;
    async function message(text) { const response = await h.call('/api/chat/message', askBody(text), cookie); assert.equal(response.status, 200); const es = events(await response.text()); await Promise.all(h.tasks); return es; }
    await withProvider(async () => { calls++; throw new Error('cache hit must not invoke model'); }, async () => {
      const first = await message('v2rayN是什么'); assert.equal(first.findLast(e => e.event === 'flow').data.stage, 'awaiting_ai'); assert.ok(!first.some(e => e.event === 'cache'));
      const ai = await message('DeepSeek 可以正常使用'); assert.equal(ai.findLast(e => e.event === 'flow').data.stage, 'awaiting_requirements'); assert.ok(!ai.some(e => e.event === 'artifact'));
      const result = await message('Windows 11 电脑'); assert.equal(result.find(e => e.event === 'cache').data.status, 'hit'); assert.equal(result.find(e => e.event === 'cache').data.modelCallCount, 0);
      assert.equal(calls, 0); assert.equal(result.at(-1).event, 'done');
      const content = await (await h.call(result.find(e => e.event === 'artifact').data.url, undefined, cookie)).text(); assert.ok(validateArtifact(content).ok);
      for (const value of ['v2rayN是什么', 'Windows 11', 'DeepSeek']) assert.ok(content.includes(value));
    });
  } finally { rmSync(dir, { recursive: true }); }
});

test('actual ask cache hit skips provider/global quota, retains intake and builds private books per visitor; miss falls back', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'fg-faq-worker-'));
  try {
    cpSync(new URL('../src/', import.meta.url), dir, { recursive: true });
    writeFileSync(join(dir, 'faq-cache-data.mjs'), `export const FAQ_CACHE_DATA = ${JSON.stringify(fixture())};\n`);
    const { default: worker } = await import(pathToFileURL(join(dir, 'worker.mjs')).href);
    const h = harness(worker), cookie = await h.session(); let calls = 0;
    async function message(text, requestBody = askBody(text), sessionCookie = cookie) {
      const response = await h.call('/api/chat/message', requestBody, sessionCookie, { 'CF-Connecting-IP': sessionCookie === cookie ? '192.0.2.1' : '192.0.2.2' });
      assert.equal(response.status, 200);
      const es = events(await response.text()); await Promise.all(h.tasks); return es;
    }
    await withProvider(async () => { calls++; return new Response(goodBody('回退模型的测试资料。')); }, async () => {
      const start = await message('下载 v2rayN'); assert.equal(start.findLast(e => e.event === 'flow').data.stage, 'awaiting_ai');
      const noAI = await message('没有 AI'); assert.match(noAI.find(e => e.event === 'delta').data.text, /deepseek\.com/); assert.equal(calls, 0);
      await message('DeepSeek 可以正常使用');
      const unknown = await message('电脑'); assert.equal(unknown.findLast(e => e.event === 'flow').data.stage, 'awaiting_requirements');
      const body = askBody('Windows 11 电脑'), first = await message(body.message, body);
      assert.deepEqual(first.find(e => e.event === 'cache').data, { status: 'hit', reason: null, faqId: 'synthetic-download', modelCallCount: 0 });
      assert.equal(calls, 0); assert.equal(first.at(-1).event, 'done');
      assert.equal(h.env.DB.raw.prepare("SELECT count(*) n FROM quotas WHERE key LIKE 'global:%'").get().n, 0);
      assert.ok(h.env.DB.raw.prepare("SELECT count(*) n FROM quotas WHERE key LIKE 'minute:%'").get().n > 0);
      const book = await (await h.call(first.find(e => e.event === 'artifact').data.url, undefined, cookie)).text();
      assert.ok(validateArtifact(book).ok); for (const value of ['Windows 11', 'DeepSeek', '下载 v2rayN', '测试参考', 'example.com']) assert.ok(book.includes(value));
      assert.equal((await h.call('/api/chat/message', body, cookie)).status, 409);
      assert.equal(h.env.DB.raw.prepare("SELECT count(*) n FROM case_jobs WHERE kind!='review_only'").get().n, 0);
      assert.equal(h.env.DB.raw.prepare('SELECT count(*) n FROM case_reviews WHERE allow_publish=1 OR revision>0').get().n, 0);
      const b = await h.session(); await message('下载 v2rayN', askBody('下载 v2rayN'), b); await message('豆包可以正常使用', askBody('豆包可以正常使用'), b);
      const second = await message('Windows 10 电脑', askBody('Windows 10 电脑'), b);
      const secondBook = await (await h.call(second.find(e => e.event === 'artifact').data.url, undefined, b)).text();
      assert.ok(secondBook.includes('Windows 10')); assert.ok(secondBook.includes('豆包')); assert.ok(!secondBook.includes('Windows 11')); assert.equal(calls, 0);
      const missing = await message('设备改为 Android 14 手机');
      assert.equal(missing.find(e => e.event === 'cache').data.status, 'reject');
      assert.equal(missing.find(e => e.event === 'cache').data.modelCallCount, 1); assert.equal(calls, 1);
      assert.equal(h.env.DB.raw.prepare("SELECT count(*) n FROM quotas WHERE key LIKE 'global:%'").get().n, 1);
      assert.equal(h.env.DB.raw.prepare("SELECT count(*) n FROM case_jobs WHERE kind!='review_only'").get().n, 0);
    });
  } finally { rmSync(dir, { recursive: true }); }
});
