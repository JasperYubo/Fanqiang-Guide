import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,events,goodBody,withProvider,askBody,worker} from './worker-harness.mjs';

async function delivered(h,cookie) {
  await withProvider(async()=>new Response(goodBody('v2rayN 的官方资料。')),async()=>{
    for(const text of ['我想用 v2rayN','我有 DeepSeek 可以用','Windows 11电脑']) {
      const response=await h.call('/api/chat/message',askBody(text),cookie);
      assert.equal(events(await response.text()).at(-1).event,'done');
    }
  });
}
const review=(extra={})=>({resolution:'resolved',execution:'not_reported',allowPublish:false,requestId:crypto.randomUUID(),...extra});
const machine=(h,path,body,token='test-machine-token')=>h.call('/api/chat/internal/cases/'+path,body,null,{authorization:'Bearer '+token,origin:''});

test('feedback is session-private, requires a real delivered book and never guesses execution success',async()=>{
  const h=harness(),a=await h.session(),b=await h.session();
  assert.equal((await h.call('/api/chat/review',review(),a)).status,409);
  await delivered(h,a);
  assert.equal((await h.call('/api/chat/review',review(),a,{origin:'https://other.example'})).status,403);
  assert.equal((await h.call('/api/chat/review',review({execution:'auto_success'}),a)).status,400);
  const result=await (await h.call('/api/chat/review',review(),a)).json();
  assert.equal(result.review.execution,'not_reported');assert.equal(result.job.kind,'review_only');
  assert.equal(h.env.DB.raw.prepare("SELECT count(*) n FROM case_jobs WHERE kind='publish'").get().n,0);
  assert.equal((await(await h.call('/api/chat/review',undefined,b)).json()).review,null);
  assert.equal((await(await h.call('/api/chat/session',{},a)).json()).review.resolution,'resolved');
});

test('consent is independent; repeated submission is idempotent and needs-more reopens intake',async()=>{
  const h=harness(),cookie=await h.session();await delivered(h,cookie);
  const body=review({allowPublish:true});
  const first=await(await h.call('/api/chat/review',body,cookie)).json();
  const repeat=await(await h.call('/api/chat/review',body,cookie)).json();
  assert.deepEqual(first,repeat);assert.equal(h.env.DB.raw.prepare("SELECT count(*) n FROM case_jobs WHERE kind='publish'").get().n,1);
  const more=await(await h.call('/api/chat/review',review({resolution:'needs_more',allowPublish:true}),cookie)).json();
  assert.equal(more.job.kind,'review_only');
  assert.equal(h.env.DB.raw.prepare("SELECT status FROM case_jobs WHERE kind='publish'").get().status,'cancelled');
  assert.equal((await(await h.call('/api/chat/session',{},cookie)).json()).flow.stage,'ready');
});

test('machine API requires a separate secret, leases one eligible job and omits session identifiers',async()=>{
  const h=harness(),cookie=await h.session();await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
  assert.equal((await machine(h,'claim',{workerId:'hub'})).status,503);
  h.env.CASE_PIPELINE_TOKEN='test-machine-token';
  assert.equal((await machine(h,'claim',{workerId:'hub'},'wrong')).status,401);
  assert.equal((await h.call('/api/chat/internal/cases/claim',{workerId:'hub'},cookie)).status,401);
  const claim=await(await machine(h,'claim',{workerId:'hub'})).json();
  assert.ok(claim.job);assert.equal(claim.job.payload.publicationConsent,true);
  assert.ok(claim.job.payload.artifact.content.startsWith('::ILANG'));
  const raw=JSON.stringify(claim);for(const forbidden of ['session_id','CF-Connecting-IP','192.0.2.1','__Secure-fg_chat'])assert.ok(!raw.includes(forbidden));
  assert.equal((await(await machine(h,'claim',{workerId:'second'})).json()).job,null);
  const jobId=claim.job.jobId;
  assert.equal((await machine(h,jobId+'/heartbeat',{leaseToken:'incorrect'})).status,409);
  assert.equal((await machine(h,jobId+'/heartbeat',{leaseToken:claim.job.leaseToken})).status,200);
});

test('publication requires live consent, valid public URL and verified redaction; only metadata is stored',async()=>{
  const h=harness(),cookie=await h.session();h.env.CASE_PIPELINE_TOKEN='test-machine-token';await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
  const {job}=await(await machine(h,'claim',{workerId:'hub'})).json();
  const complete={leaseToken:job.leaseToken,outcome:'published',publicUrl:'https://fanqiang.guide/cases/windows-client/',review:{resolution:'resolved',execution:'not_reported',evidenceComplete:true},redaction:{verified:true},article:'must not be retained'};
  assert.equal((await machine(h,job.jobId+'/complete',{...complete,publicUrl:'https://evil.example/cases/windows-client/'})).status,400);
  assert.equal((await machine(h,job.jobId+'/complete',{...complete,redaction:{verified:false}})).status,400);
  assert.equal((await machine(h,job.jobId+'/complete',complete)).status,409);
  assert.equal((await machine(h,job.jobId+'/publishing',{leaseToken:job.leaseToken,publicUrl:complete.publicUrl})).status,200);
  assert.equal((await machine(h,job.jobId+'/complete',complete)).status,200);
  const state=await(await h.call('/api/chat/review',undefined,cookie)).json();assert.equal(state.job.status,'completed');assert.equal(state.job.publicUrl,complete.publicUrl);
  const stored=h.env.DB.raw.prepare("SELECT result FROM case_jobs WHERE kind='publish'").get().result;assert.ok(!stored.includes('must not be retained'));
  assert.equal((await machine(h,job.jobId+'/complete',complete)).status,409);
});

test('revoked permission and reset invalidate an already claimed task before publication',async()=>{
  for(const action of ['revoke','reset']) {
    const h=harness(),cookie=await h.session();h.env.CASE_PIPELINE_TOKEN='test-machine-token';await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
    const {job}=await(await machine(h,'claim',{workerId:'hub'})).json();
    if(action==='revoke')await h.call('/api/chat/review',review({allowPublish:false}),cookie);else await h.call('/api/chat/reset',{},cookie);
    assert.equal((await machine(h,job.jobId+'/heartbeat',{leaseToken:job.leaseToken})).status,409);
    assert.equal((await machine(h,job.jobId+'/complete',{leaseToken:job.leaseToken,outcome:'needs_review',review:{}})).status,409);
  }
});

test('expired leases can be resumed once; old owner cannot complete and retries are bounded',async()=>{
  const h=harness(),cookie=await h.session();h.env.CASE_PIPELINE_TOKEN='test-machine-token';await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
  const first=(await(await machine(h,'claim',{workerId:'first'})).json()).job;
  h.env.DB.raw.prepare('UPDATE case_jobs SET lease_until=0').run();
  const resumed=(await(await machine(h,'claim',{workerId:'second'})).json()).job;
  assert.equal(resumed.jobId,first.jobId);assert.equal(resumed.attempt,2);assert.notEqual(resumed.leaseToken,first.leaseToken);
  assert.equal((await machine(h,first.jobId+'/complete',{leaseToken:first.leaseToken,outcome:'needs_review',review:{}})).status,409);
  const retry=await(await machine(h,resumed.jobId+'/fail',{leaseToken:resumed.leaseToken,errorCode:'provider_timeout',retryable:true})).json();assert.equal(retry.status,'pending');
  assert.equal((await(await machine(h,'claim',{workerId:'third'})).json()).job,null);
  h.env.DB.raw.prepare('UPDATE case_jobs SET available_at=0,attempts=3').run();
  const final=(await(await machine(h,'claim',{workerId:'final'})).json()).job;
  assert.equal(final.attempt,4);
  assert.equal((await(await machine(h,final.jobId+'/fail',{leaseToken:final.leaseToken,errorCode:'provider_timeout',retryable:true})).json()).status,'failed');
});

test('a fresh delivery cancels earlier tasks and clears previous publication permission',async()=>{
  const h=harness(),cookie=await h.session();await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
  await withProvider(async()=>new Response(goodBody('最新资料草稿')),async()=>{await (await h.call('/api/chat/message',askBody('重新生成工程书','artifact'),cookie)).text();});
  const restored=await(await h.call('/api/chat/review',undefined,cookie)).json();assert.equal(restored.review.allowPublish,false);assert.equal(restored.job.kind,'review_only');
  assert.equal(h.env.DB.raw.prepare("SELECT status FROM case_jobs WHERE kind='publish'").get().status,'cancelled');
});

test('case cleanup obeys the existing seven-day retention and expires abandoned final leases',async()=>{
  const h=harness(),cookie=await h.session();await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
  h.env.DB.raw.prepare("UPDATE case_jobs SET status='processing',attempts=4,lease_until=0").run();
  await worker.scheduled({},h.env,h.ctx);await Promise.all(h.tasks);
  assert.equal(h.env.DB.raw.prepare('SELECT status FROM case_jobs').get().status,'failed');
  h.env.DB.raw.prepare('UPDATE case_jobs SET expires_at=0').run();h.env.DB.raw.prepare('UPDATE case_reviews SET expires_at=0').run();h.env.DB.raw.prepare('UPDATE case_review_requests SET created_at=0').run();
  await worker.scheduled({},h.env,h.ctx);await Promise.all(h.tasks);
  for(const table of ['case_jobs','case_reviews','case_review_requests'])assert.equal(h.env.DB.raw.prepare('SELECT count(*) n FROM '+table).get().n,0);
});

test('delivery automatically gets a private reviewer without publication permission',async()=>{
  const h=harness(),cookie=await h.session();h.env.CASE_PIPELINE_TOKEN='test-machine-token';await delivered(h,cookie);
  const {job}=await(await machine(h,'claim',{workerId:'hub'})).json();
  assert.equal(job.kind,'review_only');assert.equal(job.payload.publicationConsent,false);assert.equal(job.payload.feedbackExplicit,false);assert.equal(job.payload.feedbackConfirmedAt,null);
  assert.equal((await machine(h,job.jobId+'/publishing',{leaseToken:job.leaseToken,publicUrl:'https://fanqiang.guide/cases/forbidden/'})).status,400);
  const complete={leaseToken:job.leaseToken,outcome:'reviewed',review:{resolution:'unconfirmed',execution:'not_reported',evidenceComplete:false,summary:'还需确认客户端用途。',missingPoints:['缺少用途'],followupQuestion:'你主要想解决哪一种连接问题？'}};
  assert.equal((await machine(h,job.jobId+'/complete',complete)).status,200);
  const state=await(await h.call('/api/chat/review',undefined,cookie)).json();
  assert.equal(state.review.allowPublish,false);assert.equal(state.review.resolution,'unconfirmed');assert.equal(state.job.assessment.followupQuestion,complete.review.followupQuestion);
});

test('revocation after publication registration creates a priority retract even during a publish race',async()=>{
  for(const action of ['revoke','reset']) {
    const h=harness(),cookie=await h.session();h.env.CASE_PIPELINE_TOKEN='test-machine-token';await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
    const {job}=await(await machine(h,'claim',{workerId:'hub'})).json();const publicUrl='https://fanqiang.guide/cases/windows-client/';
    assert.equal((await machine(h,job.jobId+'/publishing',{leaseToken:job.leaseToken,publicUrl})).status,200);
    if(action==='revoke')await h.call('/api/chat/review',review({allowPublish:false}),cookie);else await h.call('/api/chat/reset',{},cookie);
    const retract=(await(await machine(h,'claim',{workerId:'hub'})).json()).job;
    assert.equal(retract.kind,'retract');assert.equal(retract.payload.publicUrl,publicUrl);assert.ok(!('messages' in retract.payload));
    assert.equal((await machine(h,job.jobId+'/complete',{leaseToken:job.leaseToken,outcome:'published',publicUrl,review:{},redaction:{verified:true}})).status,409);
    assert.equal((await machine(h,retract.jobId+'/complete',{leaseToken:retract.leaseToken,outcome:'retracted',review:{}})).status,200);
  }
});

test('published result permission can be withdrawn and retract completion removes its link',async()=>{
  const h=harness(),cookie=await h.session();h.env.CASE_PIPELINE_TOKEN='test-machine-token';await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
  const {job}=await(await machine(h,'claim',{workerId:'hub'})).json();const publicUrl='https://fanqiang.guide/cases/windows-client/';
  await machine(h,job.jobId+'/publishing',{leaseToken:job.leaseToken,publicUrl});await machine(h,job.jobId+'/complete',{leaseToken:job.leaseToken,outcome:'published',publicUrl,review:{},redaction:{verified:true}});
  const withdrawn=await(await h.call('/api/chat/review',review({allowPublish:false}),cookie)).json();assert.equal(withdrawn.job.kind,'retract');
  const retract=(await(await machine(h,'claim',{workerId:'hub'})).json()).job;
  await machine(h,retract.jobId+'/complete',{leaseToken:retract.leaseToken,outcome:'retracted',review:{}});
  assert.equal(h.env.DB.raw.prepare("SELECT status,result FROM case_jobs WHERE kind='publish'").get().status,'cancelled');
});

test('public OpenAPI describes only implemented visitor routes; migration is repeatable',async()=>{
  const h=harness(),response=await h.call('/api/chat/openapi.json');assert.equal(response.status,200);
  const spec=await response.json();assert.equal(spec.openapi,'3.1.0');assert.equal(spec.info.version,'1.2.0');
  assert.ok(spec.paths['/api/chat/review'].post);assert.ok(!JSON.stringify(spec).includes('/internal/'));assert.ok(!JSON.stringify(spec).includes('CASE_PIPELINE_TOKEN'));
  assert.equal((await(await h.call('/api/chat/health')).json()).openapi,'https://fanqiang.guide/api/chat/openapi.json');
  const {readFileSync}=await import('node:fs');h.env.DB.raw.exec(readFileSync(new URL('../migration-cases-v1.2-2026-09-27.sql',import.meta.url),'utf8'));
});

test('a partially exposed publication gets retract on terminal failure or exhausted lease',async()=>{
  for(const reason of ['terminal_failure','lease_exhausted']) {
    const h=harness(),cookie=await h.session();h.env.CASE_PIPELINE_TOKEN='test-machine-token';await delivered(h,cookie);await h.call('/api/chat/review',review({allowPublish:true}),cookie);
    const {job}=await(await machine(h,'claim',{workerId:'hub'})).json();const publicUrl='https://fanqiang.guide/cases/partial-publication/';await machine(h,job.jobId+'/publishing',{leaseToken:job.leaseToken,publicUrl});
    if(reason==='terminal_failure')await machine(h,job.jobId+'/fail',{leaseToken:job.leaseToken,errorCode:'deploy_failed',retryable:false});
    else {h.env.DB.raw.prepare("UPDATE case_jobs SET attempts=4,lease_until=0 WHERE kind='publish'").run();await worker.scheduled({},h.env,h.ctx);await Promise.all(h.tasks);}
    const retract=(await(await machine(h,'claim',{workerId:'hub'})).json()).job;assert.equal(retract.kind,'retract');assert.equal(retract.payload.publicUrl,publicUrl);
  }
});
