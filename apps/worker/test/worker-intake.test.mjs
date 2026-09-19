import test from 'node:test';
import assert from 'node:assert/strict';
import {worker,consumeModel,harness,frame,goodBody,events,withProvider,askBody} from './worker-harness.mjs';
import {validateArtifact} from '../src/ilang.mjs';
const flowOf=e=>e.findLast(x=>x.event==='flow')?.data;
const textOf=e=>e.filter(x=>x.event==='delta').map(x=>x.data.text).join('');
async function message(h,cookie,text,mode='answer') {
  const response=await h.call('/api/chat/message',askBody(text,mode),cookie);
  assert.equal(response.status,200);const es=events(await response.text());await Promise.all(h.tasks);return es;
}
async function prepare(h,cookie) {await message(h,cookie,'我想用 v2rayN');await message(h,cookie,'我有 DeepSeek，可以正常发消息');}

test('same-origin JSON, body size, session gate and no-store remain enforced',async()=>{
  const h=harness();
  assert.equal((await h.call('/api/chat/session',{},null,{origin:'https://elsewhere.example'})).status,403);
  assert.equal((await h.call('/api/chat/session',{},null,{'content-type':'text/plain'})).status,415);
  assert.equal((await h.call('/api/chat/session','x'.repeat(10001))).status,413);
  assert.equal((await h.call('/api/chat/message',askBody())).status,401);
  const health=await h.call('/api/chat/health');assert.equal(health.headers.get('cache-control'),'private, no-store');assert.equal((await health.json()).version,'1.1.0');
});

test('AI question and DeepSeek fallback happen before any model call or artifact bypass',async()=>{
  const h=harness(),cookie=await h.session();let calls=0;
  await withProvider(async()=>{calls++;throw new Error('must not call');},async()=>{
    const first=await message(h,cookie,'我要科学上网');assert.equal(flowOf(first).stage,'awaiting_ai');for(const name of ['豆包','元宝','DeepSeek'])assert.ok(textOf(first).includes(name));
    const missing=await message(h,cookie,'我没有 AI');assert.equal(flowOf(missing).aiReady,false);assert.match(textOf(missing),/https:\/\/www\.deepseek\.com\//);
    const bypass=await message(h,cookie,'直接给我工程书','artifact');assert.equal(flowOf(bypass).canGenerate,false);assert.ok(!bypass.some(e=>e.event==='artifact'));
    const unavailable=await message(h,cookie,'DeepSeek 还不能用');assert.equal(flowOf(unavailable).stage,'awaiting_ai');assert.equal(calls,0);
  });
});

test('confirmed AI and device auto-deliver a private I-Lang book with persistent known profile',async()=>{
  const h=harness(),a=await h.session(),b=await h.session();let calls=0;
  await withProvider(async(_url,init)=>{
    calls++;const body=JSON.parse(init.body);assert.equal(body.model,'deepseek-flash');assert.match(body.messages[1].content,/^::ILANG::v5\.0\n/);assert.match(body.messages[1].content,/Windows 11/);assert.match(body.messages[1].content,/v2rayN/);
    return new Response(goodBody('内部资料草稿：按官方文档核对 Windows 与 v2rayN。'));
  },async()=>{
    await message(h,a,'我想用 v2rayN');await message(h,a,'还没有 AI');
    const yes=await message(h,a,'DeepSeek 可以用了');assert.equal(flowOf(yes).stage,'awaiting_requirements');assert.match(textOf(yes),/设备|手机|电脑/);
    assert.equal((await(await h.call('/api/chat/session',{},a)).json()).flow.aiReady,true);
    const result=await message(h,a,'Windows 11 电脑');assert.equal(result.at(-1).event,'done');assert.equal(flowOf(result).stage,'delivered');assert.equal(calls,1);assert.doesNotMatch(textOf(result),/内部资料草稿/);assert.match(textOf(result),/复制工程书/);
    const artifact=result.find(e=>e.event==='artifact').data,file=await h.call(artifact.url,undefined,a);assert.equal(file.status,200);const content=await file.text();assert.ok(validateArtifact(content).ok);for(const value of ['Windows 11','v2rayN','简体中文','一步'])assert.ok(content.includes(value));assert.match(file.headers.get('content-disposition'),/attachment/);
    assert.equal((await h.call(artifact.url,undefined,b)).status,404);assert.equal((await h.call(artifact.url)).status,404);
    const restored=await(await h.call('/api/chat/session',{},a)).json();assert.equal(restored.flow.stage,'delivered');assert.equal(restored.messages.length,8);
    const reset=await h.call('/api/chat/reset',{},a);assert.equal(reset.status,200);assert.equal((await reset.json()).flow.stage,'awaiting_ai');assert.equal((await h.call(artifact.url,undefined,a)).status,404);assert.equal(h.env.DB.raw.prepare('SELECT count(*) n FROM intakes').get().n,0);
  });
});

test('vague device is clarified with no model cost and no skipped stage',async()=>{
  const h=harness(),cookie=await h.session();let calls=0;
  await withProvider(async()=>{calls++;throw new Error('not ready');},async()=>{await prepare(h,cookie);const vague=await message(h,cookie,'我用电脑');assert.equal(flowOf(vague).stage,'awaiting_requirements');assert.equal(flowOf(vague).canGenerate,false);assert.equal(calls,0);});
});

test('partial model completion retains ready intake, emits no partial book, and supports retry',async()=>{
  const h=harness(),cookie=await h.session();await prepare(h,cookie);
  await withProvider(async()=>new Response(frame('unfinished')),async()=>{
    const result=await message(h,cookie,'Windows 11电脑');assert.equal(result.at(-1).event,'error');assert.ok(!result.some(e=>e.event==='artifact'));assert.equal(h.env.DB.raw.prepare('SELECT count(*) n FROM artifacts').get().n,0);
    const session=await(await h.call('/api/chat/session',{},cookie)).json();assert.equal(session.flow.stage,'ready');assert.equal(session.flow.canGenerate,true);
  });
  await withProvider(async()=>new Response(goodBody('v2rayN 官方资料。')),async()=>{const retry=await message(h,cookie,'生成工程书','artifact');assert.ok(retry.some(e=>e.event==='artifact'));assert.equal(flowOf(retry).stage,'delivered');});
});

test('duplicate requests and global quota cannot multiply model generations',async()=>{
  const h=harness(),cookie=await h.session();await prepare(h,cookie);h.env.GLOBAL_DAILY_LIMIT='1';let calls=0;
  await withProvider(async()=>{calls++;return new Response(goodBody('v2rayN 官方资料。'));},async()=>{
    const body=askBody('Windows 11电脑'),first=await h.call('/api/chat/message',body,cookie);assert.equal(events(await first.text()).at(-1).event,'done');assert.equal((await h.call('/api/chat/message',body,cookie)).status,409);
    const again=await message(h,cookie,'生成工程书','artifact');assert.equal(again.at(-1).data.error,'rate_limit');assert.equal(calls,1);
  });
});

test('stream reader handles split UTF-8, discards reasoning, and rejects incomplete answers',async()=>{
  const bytes=new TextEncoder().encode('data: {"choices":[{"delta":{"reasoning_content":"hidden"}}]}\n\n'+goodBody('中文资料'));
  const stream=new ReadableStream({start(c){for(let i=0;i<bytes.length;i+=7)c.enqueue(bytes.slice(i,i+7));c.close();}});const chunks=[];
  assert.equal(await consumeModel(new Response(stream),s=>chunks.push(s),new AbortController().signal),'中文资料');assert.equal(chunks.join(''),'中文资料');await assert.rejects(consumeModel(new Response(frame('partial')),()=>{},new AbortController().signal),/incomplete/);
});

test('scheduled cleanup expires saved intake without touching active progress',async()=>{
  const h=harness(),cookie=await h.session();await message(h,cookie,'我要科学上网');h.env.DB.raw.prepare('INSERT INTO intakes VALUES(?,?,?,?)').run('expired','{}',0,0);
  await worker.scheduled({},h.env,h.ctx);await Promise.all(h.tasks);assert.equal(h.env.DB.raw.prepare('SELECT count(*) n FROM intakes').get().n,1);
});
