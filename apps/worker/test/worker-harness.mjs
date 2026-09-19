import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import worker, { consumeModel } from '../src/worker.mjs';

const origin = 'https://fanqiang.guide';
const schema = readFileSync(new URL('../schema-v1.1-2026-09-13.sql', import.meta.url), 'utf8');
function database() {
  const db = new DatabaseSync(':memory:'); db.exec(schema);
  const api = {
    raw: db,
    prepare(sql) {
      let values = [];
      const query = {
        bind(...v) { values = v; return query; },
        async first() { return db.prepare(sql).get(...values) || null; },
        async all() { return { results: db.prepare(sql).all(...values) }; },
        async run() { return { meta: db.prepare(sql).run(...values) }; },
      };
      return query;
    },
    async batch(queries) {
      db.exec('BEGIN');
      try { const result = []; for (const q of queries) result.push(await q.run()); db.exec('COMMIT'); return result; }
      catch (e) { db.exec('ROLLBACK'); throw e; }
    },
  };
  return api;
}
function harness() {
  const env = { DB: database(), DEEPSEEK_API_KEY: 'fake-test-key', IP_SALT: 'test-salt', IP_DAILY_LIMIT: '100' };
  const tasks = [];
  const ctx = { waitUntil(p) { tasks.push(p); } };
  const req = (path, body, cookie, overrides = {}) => new Request(origin + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'content-type': 'application/json', origin, 'CF-Connecting-IP': '192.0.2.1', ...(cookie ? { cookie } : {}), ...overrides },
    ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }),
  });
  const call = (path, body, cookie, headers) => worker.fetch(req(path, body, cookie, headers), env, ctx);
  const session = async () => { const r = await call('/api/chat/session', {}); assert.equal(r.status, 200); return r.headers.get('set-cookie').split(';')[0]; };
  return { env, ctx, call, req, session, tasks };
}
const frame = (text, finish = null) => `data: ${JSON.stringify({ choices: [{ delta: { content: text }, finish_reason: finish }] })}\n\n`;
const goodBody = text => frame(text) + frame('', 'stop') + 'data: [DONE]\n\n';
function events(text) {
  return text.trim().split('\n\n').filter(Boolean).map(block => {
    const lines = block.split('\n');
    return { event: lines.find(l => l.startsWith('event:'))?.slice(6).trim(), data: JSON.parse(lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).trim()).join('\n')) };
  });
}
async function withProvider(fn, callback) {
  const original = globalThis.fetch; globalThis.fetch = fn;
  try { return await callback(); } finally { globalThis.fetch = original; }
}
const askBody = (message = '小火箭有安卓版吗？', mode = 'answer') => ({ message, mode, requestId: crypto.randomUUID() });


export { worker, consumeModel, origin, harness, frame, goodBody, events, withProvider, askBody };
