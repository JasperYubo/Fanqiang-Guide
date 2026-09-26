// Private conversation snapshots stay in D1. The hub pulls leased jobs outbound.
const parse = (value, fallback = null) => { try { return JSON.parse(value); } catch { return fallback; } };
const RESOLUTIONS = ['resolved','needs_more','unconfirmed'];
const EXECUTIONS = ['not_reported','succeeded','failed'];
const LEASE_SECONDS = 600;
const MAX_ATTEMPTS = 4;
const STATUS_LABELS = {pending:'正在排队整理',processing:'正在整理匿名案例',completed:'匿名案例已整理',needs_review:'资料仍需核对',failed:'案例整理暂未完成',cancelled:'已停止案例整理'};
const requestIdValid = id => typeof id === 'string' && /^[a-zA-Z0-9_-]{16,80}$/.test(id);
const publicJob = row => row ? {id:row.id,kind:row.kind,status:row.status,message:['failed','cancelled','needs_review'].includes(row.status)?STATUS_LABELS[row.status]:row.kind==='review_only'?(row.status==='completed'?'本次答案检查已完成':'正在检查本次答案'):row.kind==='retract'?(row.status==='completed'?'公开案例已撤回':'正在撤回公开案例'):STATUS_LABELS[row.status],...(row.status==='completed'||row.status==='needs_review' ? {publicUrl:parse(row.result,{})?.publicUrl || null,assessment:parse(row.result,{})?.review || null} : {})} : null;

export async function caseReviewState(env,sessionId) {
  const review = await env.DB.prepare('SELECT resolution,execution,allow_publish,artifact_id,revision FROM case_reviews WHERE session_id=?').bind(sessionId).first();
  const job = await env.DB.prepare("SELECT j.id,j.kind,j.status,j.result FROM case_jobs j LEFT JOIN case_reviews r ON r.session_id=j.session_id WHERE j.session_id=? AND (j.kind='retract' OR j.artifact_id=r.artifact_id) ORDER BY j.created_at DESC,j.rowid DESC LIMIT 1").bind(sessionId).first();
  return {review: review ? {resolution:review.resolution,execution:review.execution,allowPublish:review.allow_publish===1,artifactId:review.artifact_id} : null,job:publicJob(job)};
}

export function cancelCaseStatements(env,sessionId,stamp) {
  return [env.DB.prepare("INSERT OR IGNORE INTO case_jobs(id,session_id,artifact_id,revision,kind,status,available_at,result,created_at,updated_at,expires_at) SELECT lower(hex(randomblob(4)))||'-'||lower(hex(randomblob(2)))||'-'||lower(hex(randomblob(2)))||'-'||lower(hex(randomblob(2)))||'-'||lower(hex(randomblob(6))),session_id,artifact_id,revision,'retract','pending',?,json_object('publicUrl',public_url,'sourceJobId',id),?,?,expires_at FROM case_jobs WHERE session_id=? AND kind='publish' AND status='processing' AND public_url IS NOT NULL").bind(stamp,stamp,stamp,sessionId),env.DB.prepare("UPDATE case_jobs SET status='cancelled',lease_hash=NULL,lease_until=0,updated_at=? WHERE session_id=? AND kind!='retract' AND status IN ('pending','processing')").bind(stamp,sessionId)];
}

export function resetCaseStatements(env,sessionId,stamp) {
  const statements=cancelCaseStatements(env,sessionId,stamp);
  statements.push(env.DB.prepare("INSERT OR IGNORE INTO case_jobs(id,session_id,artifact_id,revision,kind,status,available_at,result,created_at,updated_at,expires_at) SELECT lower(hex(randomblob(4)))||'-'||lower(hex(randomblob(2)))||'-'||lower(hex(randomblob(2)))||'-'||lower(hex(randomblob(2)))||'-'||lower(hex(randomblob(6))),session_id,artifact_id,revision,'retract','pending',?,json_object('publicUrl',public_url,'sourceJobId',id),?,?,expires_at FROM case_jobs WHERE session_id=? AND kind='publish' AND status='completed' AND public_url IS NOT NULL").bind(stamp,stamp,stamp,sessionId));
  statements.push(env.DB.prepare("DELETE FROM case_jobs WHERE session_id=? AND kind!='retract'").bind(sessionId));
  return statements;
}

export function deliveryReviewStatements(env,session,artifactId,stamp) {
  const id=crypto.randomUUID();
  return [env.DB.prepare("INSERT INTO case_reviews(session_id,artifact_id,resolution,execution,allow_publish,revision,updated_at,expires_at) VALUES(?,?,'unconfirmed','not_reported',0,0,?,?) ON CONFLICT(session_id) DO UPDATE SET artifact_id=excluded.artifact_id,resolution='unconfirmed',execution='not_reported',allow_publish=0,revision=0,updated_at=excluded.updated_at,expires_at=excluded.expires_at").bind(session.id,artifactId,stamp,session.expires_at),env.DB.prepare("INSERT INTO case_jobs(id,session_id,artifact_id,revision,kind,status,available_at,created_at,updated_at,expires_at) VALUES(?,?,?,0,'review_only','pending',?,?,?,?)").bind(id,session.id,artifactId,stamp,stamp,stamp,session.expires_at)];
}

export async function submitCaseReview({request,env,session,readJson,fail,json,stamp}) {
  if(!session)fail(401,'session_required','对话已过期，请开始新对话。');
  const body=await readJson(request);
  if(!requestIdValid(body.requestId)||!RESOLUTIONS.includes(body.resolution)||!EXECUTIONS.includes(body.execution)||typeof body.allowPublish!=='boolean')fail(400,'invalid_review','请选择本次结果，并单独确认是否允许匿名公开。');
  const duplicate=await env.DB.prepare('SELECT response FROM case_review_requests WHERE session_id=? AND request_id=?').bind(session.id,body.requestId).first();
  if(duplicate)return json(parse(duplicate.response));
  const lockId='review-'+body.requestId;
  const locked=await env.DB.prepare('UPDATE sessions SET lock_id=?,lock_until=? WHERE id=? AND (lock_until<=? OR lock_id IS NULL) RETURNING id').bind(lockId,stamp+30,session.id,stamp).first();
  if(!locked)fail(409,'busy','请等当前回答完成后再确认结果。');
  try {
    const intakeRow=await env.DB.prepare('SELECT state FROM intakes WHERE session_id=?').bind(session.id).first();
    const intake=parse(intakeRow?.state,{});
    const artifact=await env.DB.prepare('SELECT id FROM artifacts WHERE session_id=? AND expires_at>? ORDER BY created_at DESC,rowid DESC LIMIT 1').bind(session.id,stamp).first();
    if(!artifact||intake.stage!=='delivered')fail(409,'not_delivered','请先取得本次工程书，再确认结果。');
    const previous=await env.DB.prepare('SELECT * FROM case_reviews WHERE session_id=?').bind(session.id).first();
    const same=previous&&previous.artifact_id===artifact.id&&previous.resolution===body.resolution&&previous.execution===body.execution&&previous.allow_publish===Number(body.allowPublish);
    const revision=same?previous.revision:(previous?.revision||0)+1;
    const statements=[];
    let job=null;
    if(!same) {
      statements.push(...cancelCaseStatements(env,session.id,stamp));
      statements.push(env.DB.prepare('INSERT INTO case_reviews(session_id,artifact_id,resolution,execution,allow_publish,revision,updated_at,expires_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET artifact_id=excluded.artifact_id,resolution=excluded.resolution,execution=excluded.execution,allow_publish=excluded.allow_publish,revision=excluded.revision,updated_at=excluded.updated_at,expires_at=excluded.expires_at').bind(session.id,artifact.id,body.resolution,body.execution,Number(body.allowPublish),revision,stamp,session.expires_at));
      if(!body.allowPublish) {
        const published=await env.DB.prepare("SELECT artifact_id,result,id FROM case_jobs WHERE session_id=? AND kind='publish' AND status='completed'").bind(session.id).all();
        for(const item of published.results) {
          const publicUrl=parse(item.result,{})?.publicUrl;
          if(publicUrl) {
            const id=crypto.randomUUID();
            statements.push(env.DB.prepare("INSERT OR IGNORE INTO case_jobs(id,session_id,artifact_id,revision,kind,status,available_at,result,created_at,updated_at,expires_at) VALUES(?,?,?,?,'retract','pending',?,?,?,?,?)").bind(id,session.id,item.artifact_id,revision,stamp,JSON.stringify({publicUrl,sourceJobId:item.id}),stamp,stamp,session.expires_at));
            job={id,kind:'retract',status:'pending'};
          }
        }
      }
    }
    if(body.allowPublish&&body.resolution!=='needs_more') {
      if(same)job=await env.DB.prepare("SELECT id,kind,status,result FROM case_jobs WHERE session_id=? AND artifact_id=? AND revision=? AND kind='publish'").bind(session.id,artifact.id,revision).first();
      else {job={id:crypto.randomUUID(),kind:'publish',status:'pending'};statements.push(env.DB.prepare("INSERT INTO case_jobs(id,session_id,artifact_id,revision,kind,status,available_at,created_at,updated_at,expires_at) VALUES(?,?,?,?,'publish','pending',?,?,?,?)").bind(job.id,session.id,artifact.id,revision,stamp,stamp,stamp,session.expires_at));}
    }
    else if(!same&&!job) {
      job={id:crypto.randomUUID(),kind:'review_only',status:'pending'};
      statements.push(env.DB.prepare("INSERT INTO case_jobs(id,session_id,artifact_id,revision,kind,status,available_at,created_at,updated_at,expires_at) VALUES(?,?,?,?,'review_only','pending',?,?,?,?)").bind(job.id,session.id,artifact.id,revision,stamp,stamp,stamp,session.expires_at));
    }
    else if(same&&!job)job=await env.DB.prepare("SELECT id,kind,status,result FROM case_jobs WHERE session_id=? AND artifact_id=? AND revision=? ORDER BY rowid DESC LIMIT 1").bind(session.id,artifact.id,revision).first();
    if(body.resolution==='needs_more') {
      intake.stage='ready';
      statements.push(env.DB.prepare('UPDATE intakes SET state=?,updated_at=? WHERE session_id=?').bind(JSON.stringify(intake),stamp,session.id));
    }
    const result={review:{resolution:body.resolution,execution:body.execution,allowPublish:body.allowPublish,artifactId:artifact.id},job:publicJob(job),message:body.resolution==='needs_more'?'已记录。请继续说说哪里还需要补充。':body.allowPublish?'结果已记录。我们会先脱敏、核对资料，再整理匿名案例。':'结果已记录。本次对话不会进入公开案例整理。'};
    statements.push(env.DB.prepare('INSERT INTO case_review_requests(session_id,request_id,response,created_at) VALUES(?,?,?,?)').bind(session.id,body.requestId,JSON.stringify(result),stamp));
    await env.DB.batch(statements);
    return json(result);
  } finally {await env.DB.prepare('UPDATE sessions SET lock_id=NULL,lock_until=0 WHERE id=? AND lock_id=?').bind(session.id,lockId).run();}
}

export async function internalCases({request,env,path,readJson,fail,json,hash,stamp}) {
  if(!env.CASE_PIPELINE_TOKEN)fail(503,'pipeline_unavailable','任务服务尚未启用。');
  const auth=request.headers.get('authorization')||'';
  // Hash comparison avoids prefix or length leakage and never logs either token.
  if(await hash(auth)!==await hash('Bearer '+env.CASE_PIPELINE_TOKEN))fail(401,'machine_auth_required','任务服务认证失败。');
  if(request.method!=='POST')fail(405,'method_not_allowed','请求方法有误。');
  const body=await readJson(request);
  if(path==='/api/chat/internal/cases/claim') {
    if(typeof body.workerId!=='string'||!/^[-a-zA-Z0-9_]{1,80}$/.test(body.workerId))fail(400,'invalid_worker','任务执行标识有误。');
    // Atomic UPDATE RETURNING serializes competing claimants in D1.
    const leaseToken=crypto.randomUUID()+crypto.randomUUID(),leaseHash=await hash(leaseToken);
    const row=await env.DB.prepare("UPDATE case_jobs SET status='processing',attempts=attempts+1,lease_hash=?,lease_until=?,worker_id=?,updated_at=? WHERE id=(SELECT j.id FROM case_jobs j LEFT JOIN case_reviews r ON r.session_id=j.session_id LEFT JOIN sessions s ON s.id=j.session_id WHERE ((j.status='pending' AND j.available_at<=?) OR (j.status='processing' AND j.lease_until<=?)) AND j.attempts<? AND j.expires_at>? AND (j.kind='retract' OR (s.expires_at>? AND r.revision=j.revision AND r.artifact_id=j.artifact_id AND (j.kind='review_only' OR (r.allow_publish=1 AND r.resolution!='needs_more')))) ORDER BY CASE j.kind WHEN 'retract' THEN 0 ELSE 1 END,j.created_at,j.rowid LIMIT 1) RETURNING *").bind(leaseHash,stamp+LEASE_SECONDS,body.workerId,stamp,stamp,stamp,MAX_ATTEMPTS,stamp,stamp).first();
    if(!row)return json({job:null});
    const review=await env.DB.prepare('SELECT resolution,execution,allow_publish,revision,updated_at FROM case_reviews WHERE session_id=?').bind(row.session_id).first();
    if(row.kind==='retract')return json({job:{jobId:row.id,kind:row.kind,leaseToken,leaseUntil:stamp+LEASE_SECONDS,attempt:row.attempts,payload:{publicUrl:parse(row.result,{})?.publicUrl,sourceJobId:parse(row.result,{})?.sourceJobId,publicationConsent:false}}});
    const intake=await env.DB.prepare('SELECT state FROM intakes WHERE session_id=?').bind(row.session_id).first();
    const messages=await env.DB.prepare('SELECT role,content,sources,artifact_id FROM messages WHERE session_id=? ORDER BY id LIMIT 120').bind(row.session_id).all();
    const artifact=await env.DB.prepare('SELECT content,filename FROM artifacts WHERE id=? AND session_id=? AND expires_at>?').bind(row.artifact_id,row.session_id,stamp).first();
    if(!artifact){await env.DB.prepare("UPDATE case_jobs SET status='cancelled',lease_hash=NULL,lease_until=0,updated_at=? WHERE id=? AND lease_hash=?").bind(stamp,row.id,leaseHash).run();return json({job:null});}
    return json({job:{jobId:row.id,kind:row.kind,leaseToken,leaseUntil:stamp+LEASE_SECONDS,attempt:row.attempts,payload:{intake:parse(intake?.state,{}),messages:messages.results.map(m=>({role:m.role,content:m.content,sources:parse(m.sources,[]),hasArtifact:!!m.artifact_id})),artifact:{content:artifact.content,filename:artifact.filename},resolution:review.resolution,execution:review.execution,feedbackExplicit:review.revision>0,feedbackConfirmedAt:review.revision>0?new Date(review.updated_at*1000).toISOString():null,publicationConsent:review.allow_publish===1}}});
  }
  const match=/^\/api\/chat\/internal\/cases\/([a-f0-9-]{36})\/(heartbeat|publishing|complete|fail)$/.exec(path);
  if(!match)fail(404,'not_found','接口不存在。');
  if(typeof body.leaseToken!=='string'||body.leaseToken.length>160)fail(400,'invalid_lease','任务租约有误。');
  const leaseHash=await hash(body.leaseToken),jobId=match[1];
  const owned=await env.DB.prepare("SELECT j.* FROM case_jobs j LEFT JOIN case_reviews r ON r.session_id=j.session_id WHERE j.id=? AND j.status='processing' AND j.lease_hash=? AND j.lease_until>? AND j.expires_at>? AND (j.kind='retract' OR (r.revision=j.revision AND r.artifact_id=j.artifact_id AND (j.kind='review_only' OR r.allow_publish=1)))").bind(jobId,leaseHash,stamp,stamp).first();
  if(!owned)fail(409,'lease_lost','任务已过期、撤回或由另一执行进程接手。');
  if(match[2]==='heartbeat') {
    const updated=await env.DB.prepare("UPDATE case_jobs SET lease_until=?,updated_at=? WHERE id=? AND status='processing' AND lease_hash=? RETURNING id").bind(stamp+LEASE_SECONDS,stamp,jobId,leaseHash).first();
    if(!updated)fail(409,'lease_lost','任务租约已失效。');
    return json({ok:true,leaseUntil:stamp+LEASE_SECONDS});
  }
  if(match[2]==='publishing') {
    if(owned.kind!=='publish')fail(400,'invalid_outcome','只有公开案例任务可以登记发布地址。');
    let publicUrl;
    try{const url=new URL(body.publicUrl);if(url.origin!=='https://fanqiang.guide'||!/^\/cases\/[-a-z0-9]{3,100}\/$/.test(url.pathname)||url.search||url.hash)throw Error();publicUrl=url.href;}catch{fail(400,'invalid_public_url','案例公开地址有误。');}
    if(owned.public_url&&owned.public_url!==publicUrl)fail(409,'publication_url_changed','已登记的公开地址不能变更。');
    const registered=await env.DB.prepare("UPDATE case_jobs SET public_url=?,updated_at=? WHERE id=? AND status='processing' AND lease_hash=? AND lease_until>? AND EXISTS(SELECT 1 FROM case_reviews r WHERE r.session_id=case_jobs.session_id AND r.allow_publish=1 AND r.revision=case_jobs.revision AND r.artifact_id=case_jobs.artifact_id) RETURNING id").bind(publicUrl,stamp,jobId,leaseHash,stamp).first();
    if(!registered)fail(409,'lease_lost','任务已撤回或租约失效。');
    return json({ok:true,publicUrl});
  }
  if(match[2]==='fail') {
    if(typeof body.retryable!=='boolean'||typeof body.errorCode!=='string'||!/^[-a-zA-Z0-9_]{1,80}$/.test(body.errorCode))fail(400,'invalid_failure','任务失败状态有误。');
    const status=body.retryable&&owned.attempts<MAX_ATTEMPTS?'pending':'failed';
    const statements=[];
    if(status==='failed'&&owned.kind==='publish'&&owned.public_url)statements.push(env.DB.prepare("INSERT OR IGNORE INTO case_jobs(id,session_id,artifact_id,revision,kind,status,available_at,result,created_at,updated_at,expires_at) VALUES(?,?,?,?,'retract','pending',?,?,?,?,?)").bind(crypto.randomUUID(),owned.session_id,owned.artifact_id,owned.revision,stamp,JSON.stringify({publicUrl:owned.public_url,sourceJobId:owned.id}),stamp,stamp,owned.expires_at));
    statements.push(env.DB.prepare("UPDATE case_jobs SET status=?,available_at=?,error_code=?,lease_hash=NULL,lease_until=0,updated_at=? WHERE id=? AND status='processing' AND lease_hash=?").bind(status,stamp+Math.min(3600,60*2**owned.attempts),body.errorCode,stamp,jobId,leaseHash));
    await env.DB.batch(statements);
    return json({ok:true,status});
  }
  if(!['published','needs_review','reviewed','retracted'].includes(body.outcome)||!body.review||typeof body.review!=='object'||Array.isArray(body.review))fail(400,'invalid_result','任务结果格式有误。');
  if((owned.kind==='review_only'&&!['reviewed','needs_review'].includes(body.outcome))||(owned.kind==='retract'&&body.outcome!=='retracted')||(owned.kind==='publish'&&!['published','needs_review'].includes(body.outcome)))fail(400,'invalid_outcome','结果与任务类型不匹配。');
  let publicUrl=null;
  if(body.outcome==='published') {
    try {const url=new URL(body.publicUrl);if(url.origin!=='https://fanqiang.guide'||!/^\/cases\/[-a-z0-9]{3,100}\/$/.test(url.pathname)||url.search||url.hash)throw Error();publicUrl=url.href;}catch{fail(400,'invalid_public_url','案例公开地址有误。');}
    if(body.redaction?.verified!==true)fail(400,'redaction_required','公开案例必须先完成脱敏校验。');
    if(!owned.public_url||owned.public_url!==publicUrl)fail(409,'publication_not_registered','请先登记将要发布的案例地址。');
  }
  // The result is a constrained metadata envelope, not a second transcript store.
  const result={publicUrl,review:{resolution:RESOLUTIONS.includes(body.review.resolution)?body.review.resolution:'unconfirmed',execution:EXECUTIONS.includes(body.review.execution)?body.review.execution:'not_reported',evidenceComplete:body.review.evidenceComplete===true,summary:typeof body.review.summary==='string'?body.review.summary.slice(0,500):'',missingPoints:Array.isArray(body.review.missingPoints)?body.review.missingPoints.filter(x=>typeof x==='string').slice(0,8).map(x=>x.slice(0,300)):[],followupQuestion:typeof body.review.followupQuestion==='string'?body.review.followupQuestion.slice(0,500):''},redactionVerified:body.redaction?.verified===true};
  const status=body.outcome==='needs_review'?'needs_review':'completed';
  const updated=await env.DB.prepare("UPDATE case_jobs SET status=?,result=?,lease_hash=NULL,lease_until=0,updated_at=? WHERE id=? AND status='processing' AND lease_hash=? RETURNING id").bind(status,JSON.stringify(result),stamp,jobId,leaseHash).first();
  if(!updated)fail(409,'lease_lost','任务租约已失效。');
  if(owned.kind==='retract') {
    const sourceJobId=parse(owned.result,{})?.sourceJobId;
    if(sourceJobId)await env.DB.prepare("UPDATE case_jobs SET status='cancelled',result=NULL,updated_at=? WHERE id=? AND session_id=? AND kind='publish'").bind(stamp,sourceJobId,owned.session_id).run();
  }
  return json({ok:true,status});
}
