import dns from 'node:dns/promises';
import net from 'node:net';
import tls from 'node:tls';
import https from 'node:https';
import {randomUUID} from 'node:crypto';
import {performance} from 'node:perf_hooks';
import {VERSION,PUBLIC_BASE,PROXY_NOTE,MAX_PAYLOAD_BYTES,MAX_DURATION_MS,ERROR_CODES,summarize,validateReport} from './report.mjs';

const HOST=new URL(PUBLIC_BASE).hostname;
const PREFIX=new URL(PUBLIC_BASE).pathname;
const STAGES=['dns','tcp','tls','http'];
const TIMEOUTS={dns:1000,tcp:1000,tls:1500,http:1500,throughput:MAX_DURATION_MS};
const safeError=code=>Object.assign(new Error(code),{safeCode:code});
function ip4Number(value){return value.split('.').reduce((n,x)=>(n*256+Number(x))>>>0,0);}
function prefix4(value,base,bits){return (value>>>(32-bits))===(ip4Number(base)>>>(32-bits));}
function ip6Number(value){
  let v=value.toLowerCase();
  if(v.includes('.')){
    const at=v.lastIndexOf(':'),v4=ip4Number(v.slice(at+1));
    v=v.slice(0,at+1)+(v4>>>16).toString(16)+':'+(v4&65535).toString(16);
  }
  const parts=v.split('::');if(parts.length>2)throw new Error('invalid IP');
  const left=parts[0]?parts[0].split(':'):[],right=parts.length===2&&parts[1]?parts[1].split(':'):[];
  const words=parts.length===2?[...left,...Array(8-left.length-right.length).fill('0'),...right]:left;
  if(words.length!==8)throw new Error('invalid IP');
  return words.reduce((n,x)=>(n<<16n)+BigInt('0x'+x),0n);
}
function prefix6(value,base,bits){return value>>BigInt(128-bits)===ip6Number(base)>>BigInt(128-bits);}
// Conservative global-unicast allowlist; all special, mapped and transition ranges
// are excluded, even when an exception may be globally reachable (IANA registries).
export function isPublicAddress(address){
  if(typeof address!=='string'||address.includes('%'))return false;
  const family=net.isIP(address);
  if(family===4){
    const n=ip4Number(address);
    const denied=[['0.0.0.0',8],['10.0.0.0',8],['100.64.0.0',10],['127.0.0.0',8],['169.254.0.0',16],['172.16.0.0',12],['192.0.0.0',24],['192.0.2.0',24],['192.88.99.0',24],['192.168.0.0',16],['198.18.0.0',15],['198.51.100.0',24],['203.0.113.0',24],['224.0.0.0',4],['240.0.0.0',4]];
    return address!=='168.63.129.16'&&!denied.some(([base,bits])=>prefix4(n,base,bits));
  }
  if(family!==6)return false;
  const n=ip6Number(address);
  return prefix6(n,'2000::',3)&&!([['2001::',23],['2001:db8::',32],['2002::',16],['3fff::',20]].some(([base,bits])=>prefix6(n,base,bits)));
}
function validateAddresses(rows){
  if(!Array.isArray(rows)||!rows.length)throw safeError('no_addresses');
  if(rows.length>64||rows.some(row=>!row||!isPublicAddress(row.address)||net.isIP(row.address)!==row.family))throw safeError('private_address');
  return rows.map(({address,family})=>({address,family}));
}
function guardTarget(options){
  if(options.hostname!==HOST||options.port!==443||!isPublicAddress(options.address)||net.isIP(options.address)!==options.family)throw safeError('private_address');
}
function socketProbe(options,secure){
  guardTarget(options);
  return new Promise((resolve,reject)=>{
    if(options.signal.aborted){reject(options.signal.reason);return;}
    let settled=false;
    const socket=secure?tls.connect({host:options.address,port:443,family:options.family,servername:HOST,rejectUnauthorized:true,ALPNProtocols:['http/1.1']}):net.connect({host:options.address,port:443,family:options.family});
    const finish=(error)=>{
      if(settled)return;settled=true;
      options.signal.removeEventListener('abort',onAbort);
      socket.destroy();
      error?reject(error):resolve({});
    };
    const onAbort=()=>finish(options.signal.reason);
    options.signal.addEventListener('abort',onAbort,{once:true});
    socket.once('error',finish);
    socket.once(secure?'secureConnect':'connect',()=>{
      if(secure&&!socket.authorized){finish(safeError('tls_failed'));return;}
      finish();
    });
  });
}
function httpProbe(options){
  guardTarget(options);
  if(options.path!==PREFIX+'/v1/ping'&&!new RegExp('^'+PREFIX+'/v1/download\\?bytes=[1-9][0-9]{0,7}$').test(options.path))throw safeError('transport_error');
  if(!Number.isSafeInteger(options.maxBytes)||options.maxBytes<1||options.maxBytes>MAX_PAYLOAD_BYTES)throw safeError('payload_limit');
  return new Promise((resolve,reject)=>{
    if(options.signal.aborted){reject(options.signal.reason);return;}
    let settled=false,bytes=0,response=null;
    const request=https.request({hostname:options.address,family:options.family,port:443,servername:HOST,path:options.path,method:'GET',agent:false,rejectUnauthorized:true,headers:{Host:HOST,'User-Agent':'fanqiang-diagnostics/'+VERSION,'Accept-Encoding':'identity','Cache-Control':'no-store'}});
    const finish=(error,value)=>{
      if(settled)return;settled=true;
      options.signal.removeEventListener('abort',onAbort);
      response?.destroy();request.destroy();
      error?reject(error):resolve(value);
    };
    const onAbort=()=>finish(options.signal.reason);
    options.signal.addEventListener('abort',onAbort,{once:true});
    request.once('error',error=>finish(error));
    request.once('response',res=>{
      response=res;
      if(res.statusCode>=300&&res.statusCode<400){finish(safeError('redirect_blocked'));return;}
      if(res.statusCode!==200){finish(safeError('http_status'));return;}
      const declared=res.headers['content-length'];
      if((declared!==undefined&&(!/^\d+$/.test(declared)||Number(declared)>options.maxBytes))||(res.headers['content-encoding']&&res.headers['content-encoding']!=='identity')){
        finish(safeError('payload_limit'));return;
      }
      res.on('data',chunk=>{
        if(settled)return;
        if(bytes+chunk.length>options.maxBytes){finish(safeError('payload_limit'));return;}
        try{options.onBytes(chunk.length);bytes+=chunk.length;}catch(error){finish(error);}
      });
      res.once('error',error=>finish(error));
      res.once('aborted',()=>finish(safeError('http_failed')));
      res.once('end',()=>finish(null,{statusCode:res.statusCode,bytes}));
    });
    request.end();
  });
}
async function resolvePublicHost({hostname,signal}){
  if(hostname!==HOST)throw safeError('dns_failed');
  if(signal.aborted)throw signal.reason;
  // A private Resolver per sample permits cancelling A and AAAA requests together.
  // It uses configured system DNS servers, not browser DoH, proxy DNS or hosts/NSS.
  const resolver=new dns.Resolver({timeout:1000,tries:1});
  const abort=()=>resolver.cancel();
  signal.addEventListener('abort',abort,{once:true});
  try{
    const results=await Promise.allSettled([resolver.resolve4(hostname),resolver.resolve6(hostname)]);
    if(signal.aborted)throw signal.reason;
    const rows=results.flatMap((result,index)=>result.status==='fulfilled'?result.value.map(address=>({address,family:index===0?4:6})):[]);
    if(!rows.length)throw safeError('dns_failed');
    return rows;
  }finally{signal.removeEventListener('abort',abort);}
}
const DEFAULT_TRANSPORT=Object.freeze({
  resolve:resolvePublicHost,
  tcp:options=>socketProbe(options,false),
  tls:options=>socketProbe(options,true),
  http:httpProbe
});
function rounded(value){return Math.round(value*1000)/1000;}
function progress(callback,state){if(typeof callback==='function'){try{callback(Object.freeze({...state}));}catch{/* Progress observers cannot alter network policy. */}}}

export async function runDiagnostics(options={}){
  if(!options||typeof options!=='object'||Array.isArray(options))throw new TypeError('Invalid diagnostics options');
  const allowed=['throughput','problemCategory','executionLocation','signal','onProgress','transport','maxPayloadBytes'];
  if(Object.keys(options).some(k=>!allowed.includes(k)))throw new TypeError('Unknown diagnostics option');
  const {throughput=false,problemCategory='other',executionLocation='user_device',signal,onProgress,transport,maxPayloadBytes=MAX_PAYLOAD_BYTES}=options;
  if(typeof throughput!=='boolean'||!['connectivity','slow','dns','application','other'].includes(problemCategory)||!['user_device','linux_lab'].includes(executionLocation)||!Number.isSafeInteger(maxPayloadBytes)||maxPayloadBytes<0||maxPayloadBytes>MAX_PAYLOAD_BYTES)throw new TypeError('Invalid diagnostics options');
  if(signal!==undefined&&(!(signal instanceof AbortSignal)))throw new TypeError('Invalid AbortSignal');
  if(onProgress!==undefined&&typeof onProgress!=='function')throw new TypeError('Invalid progress callback');
  if(transport!==undefined&&(!transport||typeof transport!=='object'||Object.keys(transport).some(k=>!['resolve','tcp','tls','http'].includes(k)||typeof transport[k]!=='function')))throw new TypeError('Invalid test transport');
  // Test injection is a trusted JavaScript dependency, never a serializable MCP option.
  const io={...DEFAULT_TRANSPORT,...transport};
  const started=performance.now(),deadline=started+MAX_DURATION_MS,created=new Date().toISOString();
  const controller=new AbortController();
  const onExternalAbort=()=>controller.abort(safeError('cancelled'));
  if(signal?.aborted)onExternalAbort();else signal?.addEventListener('abort',onExternalAbort,{once:true});
  const globalTimer=setTimeout(()=>controller.abort(safeError('budget_exhausted')),MAX_DURATION_MS);
  let used=0,pinned=null,unsafeDNS=false;
  const limits=new Set(['os_direct_socket','tun_may_affect_routing','no_icmp_packet_loss','fixed_target_only','no_application_proxy_test','tls_includes_tcp','dns_uses_system_servers']);
  if(!throughput)limits.add('throughput_not_requested');
  if(executionLocation==='linux_lab')limits.add('linux_lab_only');
  const measurements={dns:[],tcp:[],tls:[],http:[],throughput:[]};
  const active=()=>!controller.signal.aborted&&performance.now()<deadline;
  async function sample(stage,perform){
    const beforeBytes=used,sampleStarted=performance.now();
    const result={started_at:new Date().toISOString(),duration_ms:null,status:'error',error_code:'transport_error'};
    if(stage==='throughput'){result.bytes=0;result.mbps=null;}
    const local=new AbortController();
    const inherit=()=>local.abort(controller.signal.reason);
    controller.signal.addEventListener('abort',inherit,{once:true});
    if(controller.signal.aborted)inherit();
    const remaining=Math.max(1,deadline-performance.now());
    const wait=Math.min(TIMEOUTS[stage],remaining);
    const timer=setTimeout(()=>local.abort(safeError(remaining<=TIMEOUTS[stage]?'budget_exhausted':'timeout')),wait);
    let onAbort;
    const aborted=new Promise((_,reject)=>{
      onAbort=()=>reject(local.signal.reason||safeError('cancelled'));
      if(local.signal.aborted)onAbort();else local.signal.addEventListener('abort',onAbort,{once:true});
    });
    try{
      await Promise.race([aborted,Promise.resolve().then(()=>{if(local.signal.aborted)throw local.signal.reason;return perform(local.signal);})]);
      result.status='ok';result.error_code=null;
    }catch(error){
      const code=local.signal.aborted?local.signal.reason?.safeCode:(ERROR_CODES.includes(error?.safeCode)?error.safeCode:({dns:'dns_failed',tcp:'tcp_failed',tls:'tls_failed',http:'http_failed',throughput:'http_failed'})[stage]);
      result.error_code=ERROR_CODES.includes(code)?code:'transport_error';
      result.status=code==='cancelled'?'cancelled':['timeout','budget_exhausted'].includes(code)?'timeout':'error';
      if(code==='private_address')unsafeDNS=true;
      if(code==='cancelled')limits.add('aborted');
      if(code==='budget_exhausted')limits.add('budget_exhausted');
    }finally{
      clearTimeout(timer);controller.signal.removeEventListener('abort',inherit);local.signal.removeEventListener('abort',onAbort);
      const elapsed=rounded(performance.now()-sampleStarted);
      // Do not turn a delayed event-loop timeout into a fabricated capped latency.
      result.duration_ms=elapsed<=MAX_DURATION_MS?elapsed:null;
      if(elapsed>MAX_DURATION_MS&&result.status==='ok'){result.status='timeout';result.error_code='budget_exhausted';limits.add('budget_exhausted');}
      if(!local.signal.aborted)local.abort(safeError('cancelled'));
      if(stage==='throughput'){
        result.bytes=used-beforeBytes;
        if(result.status==='ok'&&result.bytes>0&&result.duration_ms>0)result.mbps=result.bytes*8/result.duration_ms/1000;
        else if(result.status==='ok'){result.status='error';result.error_code='http_failed';}
      }
      measurements[stage].push(result);
    }
  }
  function pinnedOptions(localSignal){
    if(!pinned||unsafeDNS)throw safeError('private_address');
    const result={hostname:HOST,address:pinned.address,family:pinned.family,port:443,signal:localSignal};
    guardTarget(result);return result;
  }
  async function http(stage,localSignal){
    const available=maxPayloadBytes-used;
    const cap=stage==='throughput'?available:Math.min(4096,available);
    if(cap<1)throw safeError('budget_exhausted');
    let counted=0;
    const path=stage==='throughput'?PREFIX+'/v1/download?bytes='+cap:PREFIX+'/v1/ping';
    const result=await io.http({...pinnedOptions(localSignal),path,maxBytes:cap,onBytes:count=>{
      if(localSignal.aborted)throw localSignal.reason;
      if(!Number.isSafeInteger(count)||count<0||counted+count>cap||used+count>maxPayloadBytes)throw safeError('payload_limit');
      counted+=count;used+=count;
    }});
    if(result?.statusCode>=300&&result?.statusCode<400)throw safeError('redirect_blocked');
    if(result?.statusCode!==200)throw safeError('http_status');
    if(!Number.isSafeInteger(result.bytes)||result.bytes!==counted||result.bytes>cap)throw safeError('payload_limit');
  }
  try{
    for(const stage of STAGES){
      if(!active())break;
      if(stage!=='dns'&&(!pinned||unsafeDNS)){limits.add('dns_prevented_connections');continue;}
      if(stage==='http'&&used>=maxPayloadBytes){limits.add('budget_exhausted');continue;}
      progress(onProgress,{stage,completed:0,total:3,used_payload_bytes:used});
      for(let index=0;index<3&&active();index++){
        if(stage==='http'&&used>=maxPayloadBytes){limits.add('budget_exhausted');break;}
        await sample(stage,async localSignal=>{
          if(stage==='dns'){
            const rows=validateAddresses(await io.resolve({hostname:HOST,signal:localSignal}));
            if(localSignal.aborted)throw localSignal.reason;
            pinned=rows[0];
          }else if(stage==='http')await http(stage,localSignal);
          else await io[stage](pinnedOptions(localSignal));
        });
        progress(onProgress,{stage,completed:index+1,total:3,used_payload_bytes:used});
      }
    }
    if(throughput&&active()&&pinned&&!unsafeDNS&&used<maxPayloadBytes){
      progress(onProgress,{stage:'throughput',completed:0,total:1,used_payload_bytes:used});
      await sample('throughput',localSignal=>http('throughput',localSignal));
      progress(onProgress,{stage:'throughput',completed:1,total:1,used_payload_bytes:used});
    }else if(throughput&&used>=maxPayloadBytes)limits.add('budget_exhausted');
  }finally{
    clearTimeout(globalTimer);signal?.removeEventListener('abort',onExternalAbort);
    if(controller.signal.aborted)limits.add(controller.signal.reason?.safeCode==='cancelled'?'aborted':'budget_exhausted');
    else if(performance.now()>=deadline)limits.add('budget_exhausted');
  }
  const report={schema_version:'0.1',report_id:randomUUID(),created_at:created,collector:{name:'fanqiang-diagnostics',version:VERSION,execution_location:executionLocation,platform:['linux','win32','darwin'].includes(process.platform)?process.platform:'other',routing_mode:'os_direct_socket',proxy_note:PROXY_NOTE},problem_category:problemCategory,measurements,summary:summarize(measurements),budget:{max_payload_bytes:MAX_PAYLOAD_BYTES,used_payload_bytes:used,max_duration_ms:MAX_DURATION_MS},redaction:{raw_logs_included:false,removed_categories:[]},limitations:[...limits]};
  const valid=validateReport(report);
  if(!valid.ok)throw new Error('Diagnostics produced an invalid report: '+valid.errors.join(','));
  return report;
}
