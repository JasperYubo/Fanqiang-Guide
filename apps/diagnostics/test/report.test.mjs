import test from 'node:test';
import assert from 'node:assert/strict';
import {VERSION,PUBLIC_BASE,PROXY_NOTE,MAX_PAYLOAD_BYTES,validateReport,canonicalJson,reportDigest,redactText,summarize} from '../src/report.mjs';

function fixture(){
  return {schema_version:'0.1',report_id:'123e4567-e89b-42d3-a456-426614174000',created_at:'2026-11-02T20:00:00.000Z',
    collector:{name:'fanqiang-diagnostics',version:VERSION,execution_location:'linux_lab',platform:'linux',routing_mode:'os_direct_socket',proxy_note:PROXY_NOTE},
    problem_category:'other',measurements:{dns:[],tcp:[],tls:[],http:[],throughput:[]},
    summary:{tcp_median_ms:null,http_median_ms:null,tcp_failure_ratio:null,download_mbps:null},
    budget:{max_payload_bytes:MAX_PAYLOAD_BYTES,used_payload_bytes:0,max_duration_ms:15000},
    redaction:{raw_logs_included:false,removed_categories:[]},
    limitations:['os_direct_socket','tun_may_affect_routing','no_icmp_packet_loss','fixed_target_only','no_application_proxy_test','linux_lab_only','throughput_not_requested']};
}
const sample=(status='ok',duration=10,error_code=null)=>({started_at:'2026-11-02T20:00:00.000Z',duration_ms:duration,status,error_code});
test('empty measurement arrays remain unmeasured nulls and fixed target is HTTPS',()=>{
  const r=fixture();assert.deepEqual(validateReport(r),{ok:true,errors:[]});
  assert.equal(PUBLIC_BASE,'https://fanqiang.guide/diagnostics-api');
});
test('strict report excludes raw AND redacted logs and other free-form identifying fields',()=>{
  for(const mutation of [
    r=>r.hostname='private-laptop',r=>r.collector.ip='192.168.1.9',
    r=>r.redaction.text='already-redacted-log',r=>r.redaction.raw_logs_included=true,
    r=>r.redaction.removed_categories=['arbitrary free text'],r=>r.limitations.push('visit https://private.example'),
    r=>r.measurements.tcp.push({...sample(),address:'10.0.0.1'})
  ]){
    const r=fixture();mutation(r);const result=validateReport(r);assert.equal(result.ok,false);
    assert.ok(!JSON.stringify(result).includes('private-laptop'));assert.ok(!JSON.stringify(result).includes('192.168'));
  }
});
test('finite numbers, bounded fields, UUID/date, sample count and consistency are checked',()=>{
  const cases=[
    r=>r.report_id='x'.repeat(300),r=>r.created_at='2026-02-30T20:00:00.000Z',
    r=>r.collector.proxy_note='proxy was tested',r=>r.problem_category='anything',
    r=>r.measurements.dns=Array(4).fill(sample()),
    r=>r.measurements.tcp=[sample('ok',NaN)],r=>r.measurements.tcp=[sample('ok',Infinity)],
    r=>r.measurements.tcp=[sample('ok',null)],r=>r.measurements.tcp=[sample('error',1,null)],
    r=>r.measurements.tcp=[sample('cancelled',null,'tcp_failed')],
    r=>r.summary.tcp_median_ms=0,r=>r.summary.download_mbps=Infinity,
    r=>r.budget.used_payload_bytes=MAX_PAYLOAD_BYTES+1,r=>r.budget.used_payload_bytes=-1,
    r=>r.budget.max_duration_ms=16000,r=>r.limitations=[],
    r=>r.redaction.removed_categories=['ip'],r=>r.redaction.removed_categories=['ipv4','ipv4'],
    r=>r.measurements.tcp=[{...sample(),bytes:12}]
  ];
  for(const mutate of cases){const r=fixture();mutate(r);assert.equal(validateReport(r).ok,false);}
});
test('failure duration cannot dilute latency; cancellation is not connection failure',()=>{
  const r=fixture();
  r.measurements.tcp=[sample('ok',10),sample('error',400,'tcp_failed'),sample('cancelled',null,'cancelled')];
  r.summary=summarize(r.measurements);
  assert.equal(r.summary.tcp_median_ms,10);assert.equal(r.summary.tcp_failure_ratio,0.5);
  assert.equal(validateReport(r).ok,true);
  r.measurements.tcp=[sample('error',null,'tcp_failed')];r.summary=summarize(r.measurements);
  assert.equal(r.summary.tcp_median_ms,null);assert.equal(r.summary.tcp_failure_ratio,1);
  assert.equal(validateReport(r).ok,true);
});
test('throughput validates bytes/time relation and failed throughput stays null',()=>{
  const r=fixture();r.measurements.throughput=[{...sample('ok',1000),bytes:1000000,mbps:8}];
  r.budget.used_payload_bytes=1000000;r.summary=summarize(r.measurements);
  assert.equal(validateReport(r).ok,true);
  r.measurements.throughput[0].mbps=16;r.summary=summarize(r.measurements);assert.equal(validateReport(r).ok,false);
  r.measurements.throughput=[{...sample('error',20,'http_failed'),bytes:20,mbps:0}];r.summary=summarize(r.measurements);
  assert.equal(validateReport(r).ok,false);
});
test('canonical JSON and report digests do not depend on key insertion order',()=>{
  const a={z:[3,{b:2,a:1}],a:'\u4e2d\u6587'},b={a:'\u4e2d\u6587',z:[3,{a:1,b:2}]};
  assert.equal(canonicalJson(a),canonicalJson(b));assert.equal(reportDigest(a),reportDigest(b));
  assert.match(reportDigest(fixture()),/^[a-f0-9]{64}$/);
  const cyclic={};cyclic.me=cyclic;
  for(const x of [cyclic,{x:undefined},{x:()=>{}},{x:NaN},{x:1n},new Date(),{[Symbol('x')]:1}])assert.throws(()=>canonicalJson(x));
});
test('local redaction covers addresses, paths, subscriptions, credentials and URLs',()=>{
  const inputs=[
    ['ipv4','peer 192.168.100.1:443','192.168.100.1'],
    ['ipv6','peer [2001:db8:abcd::19]:443','2001:db8:abcd::19'],
    ['ipv6','mapped ::ffff:192.168.0.8','::ffff:192.168.0.8'],
    ['ipv6','local fe80::1%eth0','fe80::1'],
    ['mac','device aa:bb:cc:dd:ee:ff','aa:bb:cc:dd:ee:ff'],
    ['email','person.name+tag@example.com','person.name'],
    ['url','https://host.example/sub?token=abc123','host.example'],
    ['subscription','vless://password@node.example:443/path','node.example'],
    ['subscription','vmess://eyJ2IjoiMiIsInBzIjoiZXhhbXBsZSJ9','eyJ2'],
    ['credential','Authorization: Bearer abcDEF_123456789','abcDEF'],
    ['credential','token="my-secret-value"','my-secret-value'],
    ['credential','-----BEGIN PRIVATE KEY-----\nABCDEFG\n-----END PRIVATE KEY-----','ABCDEFG'],
    ['path','config C:\\Users\\Alice\\secret profile\\config.json','Alice'],
    ['path','file /custom/user/config.yaml','/custom/user'],
    ['path','config \\\\secretserver\\home\\Alice','secretserver']
  ];
  for(const [category,input,privatePart] of inputs){
    const result=redactText(input);
    assert.ok(result.categories.includes(category),category+': '+JSON.stringify(result));
    assert.ok(!result.text.includes(privatePart),category+': '+result.text);
  }
  assert.throws(()=>redactText('x'.repeat(262145)));
});

test('local UUID credentials and complete cookie headers are removed',()=>{
  for(const text of ['uuid: "c8b130d4-5f20-4cba-947d-dd59cfbd3a12"','Cookie: session=alice-secret; key=bob-secret','Set-Cookie: auth=secret123; HttpOnly']){
    const result=redactText(text);
    assert.ok(result.categories.includes('credential'));
    for(const part of ['c8b130d4','alice-secret','bob-secret','secret123'])assert.ok(!result.text.includes(part));
  }
});

test('internationalized email and inconsistent error status are rejected or redacted',()=>{
  const text='\u7528\u6237@\u4f8b\u5b50.\u516c\u53f8';
  assert.ok(redactText(text).categories.includes('email'));
  assert.ok(!redactText(text).text.includes('@'));
  for(const code of ['cancelled','timeout','budget_exhausted']){
    const r=fixture();r.measurements.tcp=[sample('error',1,code)];r.summary=summarize(r.measurements);
    assert.equal(validateReport(r).ok,false);
  }
});
