import {createHash} from 'node:crypto';
import {isIP} from 'node:net';

export const VERSION = '0.1.0';
export const PUBLIC_BASE = 'https://fanqiang.guide/diagnostics-api';
export const PROXY_NOTE = 'explicit OS/HTTP proxies are not used; TUN may affect routing';
export const MAX_PAYLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_DURATION_MS = 15000;
export const ERROR_CODES = Object.freeze(['dns_failed','private_address','no_addresses','tcp_failed','tls_failed','http_failed','http_status','redirect_blocked','payload_limit','timeout','cancelled','budget_exhausted','transport_error']);
export const REDACTION_CATEGORIES = Object.freeze(['ipv4','ipv6','mac','email','url','subscription','credential','path']);
export const LIMITATIONS = Object.freeze(['os_direct_socket','tun_may_affect_routing','no_icmp_packet_loss','fixed_target_only','no_application_proxy_test','throughput_not_requested','aborted','budget_exhausted','linux_lab_only','tls_includes_tcp','dns_prevented_connections','dns_uses_system_servers']);
const REQUIRED_LIMITS = ['os_direct_socket','tun_may_affect_routing','no_icmp_packet_loss','fixed_target_only','no_application_proxy_test'];
const STAGES = ['dns','tcp','tls','http','throughput'];
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const plain = value => value !== null && typeof value === 'object' && !Array.isArray(value) && [Object.prototype,null].includes(Object.getPrototypeOf(value));
const finite = (value,min,max) => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
const integer = (value,min,max) => Number.isSafeInteger(value) && finite(value,min,max);
const date = value => typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
export function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a,b)=>a-b), at = Math.floor(sorted.length/2);
  return sorted.length%2 ? sorted[at] : (sorted[at-1]+sorted[at])/2;
}
export function summarize(measurements) {
  const good = name => measurements[name].filter(s=>s.status==='ok').map(s=>s.duration_ms);
  const attempted = measurements.tcp.filter(s=>s.status!=='cancelled');
  const downloaded = measurements.throughput.find(s=>s.status==='ok');
  return {tcp_median_ms:median(good('tcp')),http_median_ms:median(good('http')),
    tcp_failure_ratio:attempted.length ? attempted.filter(s=>s.status!=='ok').length/attempted.length : null,
    download_mbps:downloaded ? downloaded.mbps : null};
}

// This transport schema intentionally omits full logs, hosts, IPs, device identifiers,
// screenshots and arbitrary evidence text from the larger editorial evidence template.
export function validateReport(report) {
  const errors = [];
  const bad = (code,path) => { if(errors.length<50) errors.push(code+':'+path); };
  const shape = (value,keys,path) => {
    if(!plain(value)){bad('object_required',path);return false;}
    const actual = Reflect.ownKeys(value);
    if(actual.some(k=>typeof k!=='string'||!keys.includes(k)))bad('unknown_field',path);
    for(const k of keys)if(!Object.hasOwn(value,k))bad('missing_field',path+'.'+k);
    return true;
  };
  const list = (value,allowed,max,path) => {
    if(!Array.isArray(value)||value.length>max||new Set(value).size!==value.length||value.some(x=>typeof x!=='string'||!allowed.includes(x)))bad('invalid_enum_list',path);
  };
  try {
    if(!shape(report,['schema_version','report_id','created_at','collector','problem_category','measurements','summary','budget','redaction','limitations'],'report'))return {ok:false,errors};
    if(report.schema_version!=='0.1')bad('invalid_version','schema_version');
    if(typeof report.report_id!=='string'||!UUID.test(report.report_id))bad('invalid_uuid','report_id');
    if(!date(report.created_at))bad('invalid_date','created_at');
    if(!['connectivity','slow','dns','application','other'].includes(report.problem_category))bad('invalid_enum','problem_category');
    if(shape(report.collector,['name','version','execution_location','platform','routing_mode','proxy_note'],'collector')){
      const c=report.collector;
      if(c.name!=='fanqiang-diagnostics'||c.version!==VERSION||c.routing_mode!=='os_direct_socket'||c.proxy_note!==PROXY_NOTE)bad('invalid_constant','collector');
      if(!['user_device','linux_lab'].includes(c.execution_location)||!['linux','win32','darwin','other'].includes(c.platform))bad('invalid_enum','collector');
    }
    let sampleShapeOK=true;
    if(shape(report.measurements,STAGES,'measurements')){
      for(const stage of STAGES){
        const samples=report.measurements[stage], cap=stage==='throughput'?1:3;
        if(!Array.isArray(samples)||samples.length>cap){bad('sample_count','measurements.'+stage);sampleShapeOK=false;continue;}
        for(const s of samples){
          const p='measurements.'+stage;
          const keys=['started_at','duration_ms','status','error_code'];
          if(stage==='throughput')keys.push('bytes','mbps');
          if(!shape(s,keys,p)){sampleShapeOK=false;continue;}
          if(!date(s.started_at))bad('invalid_date',p);
          if(s.duration_ms!==null&&!finite(s.duration_ms,0,MAX_DURATION_MS))bad('invalid_duration',p);
          if(!['ok','error','timeout','cancelled'].includes(s.status)){bad('invalid_status',p);sampleShapeOK=false;}
          if(s.status==='ok'){
            if(s.error_code!==null||s.duration_ms===null)bad('invalid_success',p);
          }else if(!ERROR_CODES.includes(s.error_code))bad('invalid_error',p);
          if(s.status==='error'&&['timeout','cancelled','budget_exhausted'].includes(s.error_code))bad('invalid_error_status',p);
          if(s.status==='cancelled'&&s.error_code!=='cancelled')bad('invalid_cancelled',p);
          if(s.status==='timeout'&&!['timeout','budget_exhausted'].includes(s.error_code))bad('invalid_timeout',p);
          if(stage==='throughput'){
            if(!integer(s.bytes,0,MAX_PAYLOAD_BYTES))bad('invalid_bytes',p);
            if(s.status==='ok'){
              if(!finite(s.mbps,0,1e8)||!s.bytes||!(s.duration_ms>0))bad('invalid_throughput',p);
              else if(Math.abs(s.mbps-(s.bytes*8/s.duration_ms/1000))>Math.max(0.000001,s.mbps*0.000001))bad('throughput_mismatch',p);
            }else if(s.mbps!==null)bad('failed_throughput_must_be_null',p);
          }
        }
      }
    }else sampleShapeOK=false;
    if(shape(report.summary,['tcp_median_ms','http_median_ms','tcp_failure_ratio','download_mbps'],'summary')){
      for(const [k,max] of [['tcp_median_ms',MAX_DURATION_MS],['http_median_ms',MAX_DURATION_MS],['tcp_failure_ratio',1],['download_mbps',1e8]]){
        if(report.summary[k]!==null&&!finite(report.summary[k],0,max))bad('invalid_summary',k);
      }
      if(sampleShapeOK){
        const calculated=summarize(report.measurements);
        for(const k of Object.keys(calculated))if(report.summary[k]!==calculated[k])bad('summary_mismatch',k);
      }
    }
    if(shape(report.budget,['max_payload_bytes','used_payload_bytes','max_duration_ms'],'budget')){
      if(report.budget.max_payload_bytes!==MAX_PAYLOAD_BYTES||report.budget.max_duration_ms!==MAX_DURATION_MS||!integer(report.budget.used_payload_bytes,0,MAX_PAYLOAD_BYTES))bad('invalid_budget','budget');
      if(sampleShapeOK&&report.measurements.throughput.reduce((n,s)=>n+(Number.isSafeInteger(s.bytes)?s.bytes:0),0)>report.budget.used_payload_bytes)bad('payload_mismatch','budget');
    }
    if(shape(report.redaction,['raw_logs_included','removed_categories'],'redaction')){
      if(report.redaction.raw_logs_included!==false)bad('logs_forbidden','redaction');
      list(report.redaction.removed_categories,REDACTION_CATEGORIES,REDACTION_CATEGORIES.length,'redaction.removed_categories');
    }
    list(report.limitations,LIMITATIONS,LIMITATIONS.length,'limitations');
    if(Array.isArray(report.limitations)){
      for(const code of REQUIRED_LIMITS)if(!report.limitations.includes(code))bad('missing_limitation','limitations');
      if(report.collector?.execution_location==='linux_lab'&&!report.limitations.includes('linux_lab_only'))bad('missing_limitation','limitations');
    }
    if(Buffer.byteLength(canonicalJson(report))>16384)bad('report_too_large','report');
  }catch{bad('invalid_json_value','report');}
  return {ok:errors.length===0,errors};
}

export function canonicalJson(value) {
  const seen=new Set();let nodes=0;
  function visit(v,depth){
    if(++nodes>10000||depth>20)throw new TypeError('JSON value exceeds bounds');
    if(v===null||typeof v==='boolean')return v;
    if(typeof v==='number'){if(!Number.isFinite(v))throw new TypeError('Non-finite number');return v;}
    if(typeof v==='string'){if(v.length>65536)throw new TypeError('String too long');return v;}
    if(typeof v!=='object'||seen.has(v))throw new TypeError('Non-JSON or cyclic value');
    seen.add(v);let result;
    if(Array.isArray(v))result=v.map(x=>visit(x,depth+1));
    else {
      if(!plain(v)||Reflect.ownKeys(v).some(k=>typeof k!=='string'))throw new TypeError('Non-JSON object');
      result=Object.create(null);
      for(const k of Object.keys(v).sort())result[k]=visit(v[k],depth+1);
    }
    seen.delete(v);return result;
  }
  return JSON.stringify(visit(value,0));
}
export function reportDigest(report){return createHash('sha256').update(canonicalJson(report)).digest('hex');}

// Best-effort LOCAL preview only. Neither the input nor this output belongs in a report.
export function redactText(input){
  if(typeof input!=='string'||input.length>262144)throw new TypeError('Local log text must be at most 256 Ki characters');
  let text=input;const categories=new Set();
  const replace=(expression,category,replacement='[REDACTED_'+category.toUpperCase()+']')=>{
    text=text.replace(expression,(...args)=>{categories.add(category);return typeof replacement==='function'?replacement(...args):replacement;});
  };
  replace(/-----BEGIN [^\r\n-]*(?:PRIVATE KEY|SECRET)[^\r\n-]*-----[\s\S]*?-----END [^\r\n-]+-----/g,'credential');
  replace(/\b(?:ss|ssr|vmess|vless|trojan|hysteria2?|hy2|tuic|wireguard):\/\/[^\s<>"']+/gi,'subscription');
  replace(/\b(?:Bearer|Basic)\s+[A-Za-z0-9+/_=.-]+/gi,'credential');
  replace(/\b(?:Set-Cookie|Cookie)\s*:\s*[^\r\n]+/gi,'credential');
  replace(/\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,'credential');
  replace(/(["']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret|private[_-]?key|authorization|client[_-]?secret|uuid|psk|session[_-]?id)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}\]]+)/gi,'credential',(_all,prefix)=>prefix+'[REDACTED_CREDENTIAL]');
  replace(/\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|AIza[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16})\b/g,'credential');
  replace(/\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}\b/g,'credential');
  replace(/\b[A-Za-z0-9_+-]{48,}\b/g,'credential');
  replace(/\b[a-z][a-z0-9+.-]*:\/\/[^\s<>"']+/gi,'url');
  replace(/[^\s<>@"']+@[^\s<>@"']+\.[^\s<>@"']+/g,'email');
  text=text.replace(/(?<![A-Za-z0-9])(?:[A-Fa-f0-9]{0,4}:){2,}[A-Fa-f0-9:.]*(?:%[A-Za-z0-9_.-]+)?/g,value=>{
    const raw=value.replace(/[.,;]+$/,'');
    if(isIP(raw.split('%')[0])!==6)return value;
    categories.add('ipv6');return '[REDACTED_IPV6]'+value.slice(raw.length);
  });
  replace(/\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b/gi,'mac');
  text=text.replace(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g,value=>{
    if(isIP(value)!==4)return value;categories.add('ipv4');return '[REDACTED_IPV4]';
  });
  replace(/\b[A-Za-z]:[\\/][^\r\n"'<>|]*/g,'path');
  replace(/\\\\[^\\\s]+\\[^\r\n"'<>|]*/g,'path');
  replace(/(?:~\/|\.{1,2}\/|(?<![A-Za-z0-9:])\/)(?:[^/\s"'<>]+\/)*[^/\s"'<>]+/g,'path');
  return {text,categories:REDACTION_CATEGORIES.filter(c=>categories.has(c))};
}
