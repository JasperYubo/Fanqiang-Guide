import test from 'node:test';
import assert from 'node:assert/strict';
import {EventEmitter} from 'node:events';
import tls from 'node:tls';
import https from 'node:https';
import {runDiagnostics,isPublicAddress} from '../src/measure.mjs';
import {MAX_PAYLOAD_BYTES,validateReport} from '../src/report.mjs';

const publicRows=[{address:'104.21.1.125',family:4},{address:'2606:4700:3030::1',family:6}];
function fake(overrides={}){
  return {resolve:async()=>publicRows,tcp:async()=>{},tls:async()=>{},
    http:async({maxBytes,onBytes})=>{const bytes=Math.min(32,maxBytes);onBytes(bytes);return {statusCode:200,bytes};},...overrides};
}
test('public address policy blocks private, metadata, mapped/transition and reserved addresses',()=>{
  for(const x of ['0.0.0.0','10.0.0.1','100.100.100.200','127.0.0.1','169.254.169.254','172.16.0.1','192.168.1.1','192.0.2.1','198.18.0.1','198.51.100.1','203.0.113.2','224.0.0.1','255.255.255.255','168.63.129.16','::','::1','::ffff:127.0.0.1','::ffff:104.21.1.125','0:0:0:0:0:ffff:7f00:1','fc00::1','fe80::1%eth0','2001:db8::1','2002:7f00:1::','64:ff9b::7f00:1','3fff::1','not-an-ip'])assert.equal(isPublicAddress(x),false,x);
  for(const x of ['1.1.1.1','8.8.8.8','104.21.1.125','172.67.152.62','2606:4700:3030::1','2001:4860:4860::8888'])assert.equal(isPublicAddress(x),true,x);
});
test('three DNS/TCP/TLS/HTTP samples, pinned targets, honest route and no implicit download',async()=>{
  const seen=[],progress=[];
  const report=await runDiagnostics({executionLocation:'linux_lab',transport:fake({
    resolve:async options=>{assert.equal(options.hostname,'fanqiang.guide');return publicRows;},
    tcp:async options=>{seen.push(options);assert.equal(options.address,publicRows[0].address);},
    http:async options=>{assert.equal(options.path,'/diagnostics-api/v1/ping');assert.equal(options.hostname,'fanqiang.guide');options.onBytes(20);return {statusCode:200,bytes:20};}
  }),onProgress:x=>progress.push(x)});
  for(const stage of ['dns','tcp','tls','http'])assert.equal(report.measurements[stage].length,3);
  assert.equal(report.measurements.throughput.length,0);assert.equal(report.summary.download_mbps,null);
  assert.equal(report.budget.used_payload_bytes,60);assert.equal(report.collector.routing_mode,'os_direct_socket');
  assert.ok(report.limitations.includes('linux_lab_only'));assert.equal(validateReport(report).ok,true);
  assert.equal(seen.length,3);assert.ok(progress.every(x=>Object.keys(x).sort().join(',')==='completed,stage,total,used_payload_bytes'));
});
test('any private result in any DNS response prevents all socket/HTTP connections',async()=>{
  let calls=0,attempts=0;
  const report=await runDiagnostics({transport:fake({
    resolve:async()=>{attempts++;return attempts===2?[...publicRows,{address:'127.0.0.1',family:4}]:publicRows;},
    tcp:async()=>{calls++;},tls:async()=>{calls++;},http:async()=>{calls++;}
  })});
  assert.equal(calls,0);assert.equal(report.measurements.dns[1].error_code,'private_address');
  assert.equal(report.summary.tcp_median_ms,null);assert.equal(report.summary.tcp_failure_ratio,null);
  assert.ok(report.limitations.includes('dns_prevented_connections'));
});
test('DNS failure never becomes zero-latency success and arbitrary errors never leak',async()=>{
  const report=await runDiagnostics({transport:fake({resolve:async()=>{throw new Error('secret user@email.test 192.168.1.1');}})});
  assert.ok(report.measurements.dns.every(s=>s.status==='error'&&s.error_code==='dns_failed'));
  assert.equal(report.summary.tcp_median_ms,null);assert.ok(!JSON.stringify(report).includes('email.test'));
});
test('explicit throughput uses remaining body budget including ping bytes',async()=>{
  const seen=[];
  const report=await runDiagnostics({throughput:true,maxPayloadBytes:1000,transport:fake({http:async options=>{
    const bytes=options.path.includes('/download')?options.maxBytes:20;seen.push(options.path);
    options.onBytes(bytes);return {statusCode:200,bytes};
  }})});
  assert.equal(report.budget.used_payload_bytes,1000);assert.equal(report.measurements.throughput[0].bytes,940);
  assert.ok(seen.includes('/diagnostics-api/v1/download?bytes=940'));
  assert.equal(report.measurements.throughput[0].status,'ok');assert.equal(validateReport(report).ok,true);
});
test('oversized data, redirects and status failures never produce successful throughput',async()=>{
  for(const mode of ['oversize','redirect','status']){
    const report=await runDiagnostics({throughput:true,maxPayloadBytes:100,transport:fake({http:async options=>{
      if(mode==='oversize'){options.onBytes(options.maxBytes+1);return {statusCode:200,bytes:options.maxBytes+1};}
      return {statusCode:mode==='redirect'?302:503,bytes:0};
    }})});
    assert.ok(report.measurements.http.every(s=>s.status==='error'));
    assert.equal(report.summary.http_median_ms,null);assert.equal(report.summary.download_mbps,null);
    assert.ok(report.budget.used_payload_bytes<=100);
  }
});
test('unknown URLs, proxy settings and budget expansion cannot enter network options',async()=>{
  for(const options of [{url:'http://127.0.0.1/'},{host:'metadata.google.internal'},{proxy:'http://localhost'},{maxPayloadBytes:MAX_PAYLOAD_BYTES+1},{maxPayloadBytes:-1},{maxDurationMs:60000},{transport:{hostname:'example.com'}}])await assert.rejects(runDiagnostics(options),TypeError);
});
test('pre-abort performs no requests; active abort terminates despite uncooperative injection',async()=>{
  let calls=0;const a=new AbortController();a.abort();
  const pre=await runDiagnostics({signal:a.signal,transport:fake({resolve:async()=>{calls++;return publicRows;}})});
  assert.equal(calls,0);assert.equal(pre.summary.tcp_failure_ratio,null);assert.ok(pre.limitations.includes('aborted'));
  const b=new AbortController();const started=Date.now();
  const pending=runDiagnostics({signal:b.signal,transport:fake({tcp:async()=>new Promise(()=>{})})});
  setTimeout(()=>b.abort(),30);
  const mid=await pending;
  assert.ok(Date.now()-started<1000);
  assert.equal(mid.measurements.tcp.length,1);assert.equal(mid.measurements.tcp[0].status,'cancelled');
  assert.equal(mid.summary.tcp_failure_ratio,null);assert.equal(mid.measurements.http.length,0);
});
test('partial download bytes survive cancellation while speed stays unmeasured',async()=>{
  const controller=new AbortController();
  const report=await runDiagnostics({throughput:true,signal:controller.signal,transport:fake({http:async options=>{
    if(options.path.includes('/download')){options.onBytes(100);controller.abort();return new Promise(()=>{});}
    options.onBytes(10);return {statusCode:200,bytes:10};
  }})});
  assert.equal(report.measurements.throughput[0].status,'cancelled');assert.equal(report.measurements.throughput[0].bytes,100);
  assert.equal(report.summary.download_mbps,null);assert.equal(report.budget.used_payload_bytes,130);
});
test('native TLS transport pins IP and keeps hostname certificate verification enabled',async()=>{
  const original=tls.connect,seen=[];
  tls.connect=options=>{
    seen.push(options);const socket=new EventEmitter();socket.destroy=()=>{};
    queueMicrotask(()=>socket.emit('error',new Error('certificate rejected')));
    return socket;
  };
  try{
    const transport=fake();delete transport.tls;
    const report=await runDiagnostics({transport});
    assert.equal(seen.length,3);assert.ok(seen.every(o=>o.host==='104.21.1.125'&&o.servername==='fanqiang.guide'&&o.rejectUnauthorized===true));
    assert.ok(report.measurements.tls.every(s=>s.error_code==='tls_failed'));
  }finally{tls.connect=original;}
});
test('native HTTPS refuses redirects before any response body and never uses proxy env',async()=>{
  const original=https.request,seen=[];
  https.request=options=>{
    seen.push(options);const request=new EventEmitter();request.destroy=()=>{};
    request.end=()=>queueMicrotask(()=>{const response=new EventEmitter();response.statusCode=302;response.headers={location:'http://169.254.169.254/'};response.destroy=()=>{};request.emit('response',response);});
    return request;
  };
  try{
    const transport=fake();delete transport.http;
    const report=await runDiagnostics({transport});
    assert.ok(report.measurements.http.every(s=>s.error_code==='redirect_blocked'));
    assert.equal(report.budget.used_payload_bytes,0);
    assert.ok(seen.every(o=>o.hostname==='104.21.1.125'&&o.agent===false&&o.rejectUnauthorized===true&&o.headers.Host==='fanqiang.guide'));
  }finally{https.request=original;}
});
test('a never-ending download is stopped by the fixed run deadline',async()=>{
  const started=Date.now();let aborted=false;
  const report=await runDiagnostics({throughput:true,transport:fake({http:async options=>{
    if(options.path.includes('/download'))return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>{aborted=true;reject(options.signal.reason);},{once:true}));
    options.onBytes(1);return {statusCode:200,bytes:1};
  }})});
  assert.ok(aborted);assert.ok(Date.now()-started>=14000&&Date.now()-started<17000);
  assert.equal(report.measurements.throughput[0].status,'timeout');assert.equal(report.measurements.throughput[0].error_code,'budget_exhausted');
  assert.equal(report.summary.download_mbps,null);assert.ok(report.limitations.includes('budget_exhausted'));
});

test('native DNS resolver cancels both address queries on abort',async()=>{
  const dns=await import('node:dns/promises');
  const object=dns.default,Original=object.Resolver;
  let cancelled=0,constructed=0;
  object.Resolver=class{
    constructor(){constructed++;this.rejects=[];}
    resolve4(){return new Promise((_,reject)=>this.rejects.push(reject));}
    resolve6(){return new Promise((_,reject)=>this.rejects.push(reject));}
    cancel(){cancelled++;for(const reject of this.rejects)reject(new Error('ECANCELLED'));}
  };
  try{
    const controller=new AbortController(),transport=fake();delete transport.resolve;
    const pending=runDiagnostics({signal:controller.signal,transport});
    setTimeout(()=>controller.abort(),20);
    const report=await pending;
    assert.equal(constructed,1);assert.equal(cancelled,1);
    assert.equal(report.measurements.dns[0].status,'cancelled');assert.equal(report.measurements.tcp.length,0);
  }finally{object.Resolver=Original;}
});
test('native HTTPS rejects oversized Content-Length without reading payload',async()=>{
  const original=https.request;
  let destroyed=0;
  https.request=()=>{
    const request=new EventEmitter();request.destroy=()=>{};
    request.end=()=>queueMicrotask(()=>{
      const response=new EventEmitter();response.statusCode=200;response.headers={'content-length':'10485761'};
      response.destroy=()=>{destroyed++;};request.emit('response',response);
    });
    return request;
  };
  try{
    const transport=fake();delete transport.http;
    const report=await runDiagnostics({transport});
    assert.equal(destroyed,3);assert.ok(report.measurements.http.every(s=>s.error_code==='payload_limit'));
    assert.equal(report.budget.used_payload_bytes,0);
  }finally{https.request=original;}
});
test('zero remaining session payload prevents HTTP/download while preserving non-payload checks',async()=>{
  let requests=0;
  const report=await runDiagnostics({throughput:true,maxPayloadBytes:0,transport:fake({http:async()=>{requests++;}})});
  assert.equal(requests,0);assert.equal(report.budget.used_payload_bytes,0);
  assert.equal(report.measurements.tcp.length,3);assert.equal(report.measurements.http.length,0);
  assert.equal(report.summary.download_mbps,null);assert.ok(report.limitations.includes('budget_exhausted'));
});
test('late callbacks from a completed injected transport cannot mutate the completed report',async()=>{
  const callbacks=[];
  const report=await runDiagnostics({transport:fake({http:async options=>{
    options.onBytes(10);callbacks.push(()=>options.onBytes(40));return {statusCode:200,bytes:10};
  }})});
  for(const callback of callbacks)assert.throws(callback);
  assert.equal(report.budget.used_payload_bytes,30);
});
