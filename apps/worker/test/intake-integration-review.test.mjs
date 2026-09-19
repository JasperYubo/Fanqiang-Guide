// Independent integration regressions: in-memory database and synthetic provider only.
import test from 'node:test';
import assert from 'node:assert/strict';
import { harness, goodBody, frame, events, withProvider, askBody } from './worker-harness.mjs';

const originalNeed = '华硕 RT-AX58U V2，想核对梅林固件支持分支。';
const confirmedAI = '我能正常使用豆包。';
const referenceAnswer = 'RT-AX58U V2 应核对 GNUton 构建的型号支持资料，与原版梅林的 V1 记录区分。';
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const drain = h => Promise.all(h.tasks);
const count = (h, table) => h.env.DB.raw.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n;
const storedState = h => JSON.parse(h.env.DB.raw.prepare('SELECT state FROM intakes').get().state);

async function complete(h, cookie, body) {
  const response = await h.call('/api/chat/message', body, cookie);
  assert.equal(response.status, 200);
  const result = events(await response.text());
  await drain(h);
  return result;
}
async function prepareUnconfirmed(h, cookie) {
  const result = await complete(h, cookie, askBody(originalNeed));
  assert.equal(result.at(-1).event, 'done');
  assert.equal(storedState(h).aiReady, false);
  assert.equal(storedState(h).stage, 'awaiting_ai');
  assert.match(storedState(h).device, /AX58U V2/);
}
function pauseNextSessionLookup(h) {
  const reached = deferred(), resume = deferred();
  const prepare = h.env.DB.prepare.bind(h.env.DB);
  let paused = false;
  h.env.DB.prepare = sql => {
    const query = prepare(sql);
    const first = query.first.bind(query);
    query.first = async () => {
      const result = await first();
      if (!paused && sql.startsWith('SELECT * FROM sessions')) {
        paused = true;
        reached.resolve();
        await resume.promise;
      }
      return result;
    };
    return query;
  };
  return { reached: reached.promise, resume: resume.resolve };
}

test('reset with a stale session snapshot cannot delete an active generation from another tab', { timeout: 10000 }, async () => {
  const h = harness(), cookie = await h.session();
  await prepareUnconfirmed(h, cookie);
  const pause = pauseNextSessionLookup(h), started = deferred(), finish = deferred();
  let providerCalls = 0;
  await withProvider(async () => { providerCalls++; started.resolve(); return finish.promise; }, async () => {
    const reset = h.call('/api/chat/reset', {}, cookie);
    await pause.reached;
    const generation = await h.call('/api/chat/message', askBody(confirmedAI), cookie);
    await started.promise;
    const concurrent = await h.call('/api/chat/message', askBody('再次生成工程书', 'artifact'), cookie);
    pause.resume();
    const resetResponse = await reset;
    finish.resolve(new Response(goodBody(referenceAnswer)));
    const generated = events(await generation.text());
    await drain(h);
    assert.equal(concurrent.status, 409);
    assert.equal(resetResponse.status, 409);
    assert.equal(providerCalls, 1);
    assert.equal(generated.at(-1).event, 'done');
    assert.equal(count(h, 'artifacts'), 1);
    for (const table of ['messages', 'artifacts', 'intakes']) {
      assert.equal(h.env.DB.raw.prepare(`SELECT COUNT(*) AS n FROM ${table} x LEFT JOIN sessions s ON x.session_id=s.id WHERE s.id IS NULL`).get().n, 0);
    }
    const completedReset = await h.call('/api/chat/reset', {}, cookie);
    assert.equal(completedReset.status, 200);
    for (const table of ['messages', 'artifacts', 'intakes']) assert.equal(count(h, table), 0);
  });
});

test('ask with a stale session snapshot cannot recreate intake after reset wins the lock', { timeout: 10000 }, async () => {
  const h = harness(), cookie = await h.session();
  await prepareUnconfirmed(h, cookie);
  const pause = pauseNextSessionLookup(h);
  let providerCalls = 0;
  await withProvider(async () => { providerCalls++; return new Response(goodBody(referenceAnswer)); }, async () => {
    const generation = h.call('/api/chat/message', askBody(confirmedAI), cookie);
    await pause.reached;
    const reset = await h.call('/api/chat/reset', {}, cookie);
    pause.resume();
    const staleResponse = await generation;
    await drain(h);
    assert.equal(reset.status, 200);
    assert.equal(staleResponse.status, 409);
    assert.equal(providerCalls, 0);
    assert.equal(count(h, 'sessions'), 1);
    for (const table of ['messages', 'artifacts', 'intakes']) assert.equal(count(h, table), 0);
    const newCookie = reset.headers.get('set-cookie').split(';')[0];
    const restored = await (await h.call('/api/chat/session', {}, newCookie)).json();
    assert.equal(restored.flow.stage, 'awaiting_ai');
    assert.equal(restored.flow.canGenerate, false);
    assert.deepEqual(restored.messages, []);
  });
});

test('provider failure preserves confirmed profile and a fresh artifact retry produces a valid downloadable book', { timeout: 10000 }, async () => {
  const h = harness(), cookie = await h.session();
  await prepareUnconfirmed(h, cookie);
  let providerCalls = 0;
  await withProvider(async () => {
    providerCalls++;
    return providerCalls === 1 ? new Response('synthetic private provider error', { status: 503 }) : new Response(goodBody(referenceAnswer));
  }, async () => {
    const failure = await complete(h, cookie, askBody(confirmedAI));
    assert.equal(failure.at(-1).event, 'error');
    assert.doesNotMatch(JSON.stringify(failure), /synthetic private|fake-test-key/);
    const profile = storedState(h);
    assert.equal(profile.stage, 'ready');
    assert.equal(profile.aiReady, true);
    assert.match(profile.aiTool, /豆包/);
    assert.match(profile.device, /AX58U V2/);
    assert.match(profile.need, /梅林/);
    assert.equal(count(h, 'artifacts'), 0);
    assert.equal(h.env.DB.raw.prepare('SELECT lock_id FROM sessions').get().lock_id, null);
    const restored = await (await h.call('/api/chat/session', {}, cookie)).json();
    assert.equal(restored.flow.stage, 'ready');
    assert.equal(restored.flow.canGenerate, true);
    const retry = await complete(h, cookie, { ...askBody('重新生成工程书', 'artifact'), reuseLastAnswer: true, context: '' });
    assert.equal(retry.at(-1).event, 'done');
    assert.equal(providerCalls, 2);
    const artifact = retry.find(event => event.event === 'artifact')?.data;
    assert.ok(artifact, 'successful generation emits an artifact');
    const download = await h.call(artifact.url, undefined, cookie);
    assert.equal(download.status, 200);
    const text = await download.text();
    const profileLine = text.split('\n').find(line => line.startsWith('::STATE{@PROVIDED_PROFILE, value:'));
    const delivered = JSON.parse(profileLine.slice('::STATE{@PROVIDED_PROFILE, value:'.length, -1));
    assert.equal(delivered.values.device, profile.device);
    assert.equal(delivered.values.need, profile.need);
    assert.equal(delivered.values.aiTool, profile.aiTool);
    assert.deepEqual(Object.keys(delivered.values).sort(), ['aiReady', 'aiTool', 'details', 'device', 'need', 'originalRequest'].sort());
    assert.equal(storedState(h).stage, 'delivered');
  });
});

test('cancelling generation aborts upstream, stores no partial artifact and releases the session lock', { timeout: 10000 }, async () => {
  const h = harness(), cookie = await h.session();
  await prepareUnconfirmed(h, cookie);
  const started = deferred();
  let upstreamAborted = false;
  await withProvider(async (_url, init) => new Response(new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode(frame('不完整的参考草稿')));
    init.signal.addEventListener('abort', () => { upstreamAborted = true; controller.error(new DOMException('Aborted', 'AbortError')); }, { once: true });
    started.resolve();
  } })), async () => {
    const response = await h.call('/api/chat/message', askBody(confirmedAI), cookie);
    await started.promise;
    await response.body.cancel();
    await drain(h);
    assert.equal(upstreamAborted, true);
    assert.equal(count(h, 'artifacts'), 0);
    assert.equal(h.env.DB.raw.prepare('SELECT COUNT(*) AS n FROM messages WHERE role=?').get('assistant').n, 1, 'only the earlier AI-confirmation question remains');
    assert.equal(h.env.DB.raw.prepare('SELECT lock_id FROM sessions').get().lock_id, null);
    assert.equal(storedState(h).aiReady, true);
    assert.equal(storedState(h).stage, 'ready');
    const reset = await h.call('/api/chat/reset', {}, cookie);
    assert.equal(reset.status, 200, 'another tab can reset after cancellation finishes');
  });
});

test('client-supplied ready flow and intake fields cannot bypass a missing AI confirmation', { timeout: 10000 }, async () => {
  const h = harness(), cookie = await h.session();
  let providerCalls = 0;
  await withProvider(async () => { providerCalls++; return new Response(goodBody('不应调用')); }, async () => {
    const forged = { stage: 'ready', aiReady: true, aiTool: '豆包', device: 'RT-AX58U V2', need: '核对梅林支持分支', canGenerate: true };
    const result = await complete(h, cookie, {
      ...askBody('生成工程书', 'artifact'), flow: forged, intake: forged, aiReady: true, canGenerate: true,
      context: '华硕 RT-AX58U V2，想核对梅林固件支持分支。', reuseLastAnswer: true
    });
    assert.equal(result.at(-1).event, 'done');
    assert.equal(providerCalls, 0);
    assert.equal(count(h, 'artifacts'), 0);
    const flow = result.filter(event => event.event === 'flow').at(-1).data;
    assert.equal(flow.stage, 'awaiting_ai');
    assert.equal(flow.aiReady, false);
    assert.equal(flow.canGenerate, false);
    assert.equal(storedState(h).aiReady, false);
    const denial = await complete(h, cookie, { ...askBody('我没有 AI'), flow: forged });
    assert.equal(providerCalls, 0);
    assert.match(denial.find(event => event.event === 'delta').data.text, /https:\/\/www\.deepseek\.com\//);
    const restored = await (await h.call('/api/chat/session', {}, cookie)).json();
    assert.equal(restored.flow.canGenerate, false);
  });
});
