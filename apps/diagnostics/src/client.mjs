#!/usr/bin/env node
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { ListToolsRequestSchema, CallToolRequestSchema } from '@modelcontextprotocol/sdk/types.js';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { realpathSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { startLocalUi } from './ui.mjs';
import { runDiagnostics } from './measure.mjs';
import { VERSION, PUBLIC_BASE, validateReport } from './report.mjs';

const toolSpecs = [
 {name:'diagnostics_open',description:'打开本机网络诊断页面。先展示测试目标、流量预算和选项；由用户点击开始。不会自动测速或提交报告。',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:false,destructiveHint:false,openWorldHint:false}},
 {name:'diagnostics_status',description:'读取本次本地诊断的进度和状态，不提交数据。',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,openWorldHint:false}},
 {name:'diagnostics_preview',description:'读取当前脱敏结构化报告；原始日志和脱敏日志全文均不传给AI或远端。这不是提交操作。',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,openWorldHint:false}},
 {name:'diagnostics_stop',description:'停止当前本地诊断，保留已得到的样本，不上传。',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:false,destructiveHint:false,openWorldHint:false}},
];
export function createDiagnosticsServer({uiFactory=startLocalUi,measure=runDiagnostics,executionLocation='user_device',dataDir}={}) {
 let ui=null,creating=null,closed=false;
 const getUi=async()=>{
  if(closed) throw new Error('closed');
  if(!ui) {
   creating ??= uiFactory({runDiagnostics:measure,publicBase:PUBLIC_BASE,dataDir,executionLocation});
   ui=await creating;
  }
  return ui;
 };
 const server=new Server({name:'fanqiang-diagnostics',version:VERSION},{capabilities:{tools:{}}});
 server.setRequestHandler(ListToolsRequestSchema,async()=>({tools:toolSpecs}));
 server.setRequestHandler(CallToolRequestSchema,async(request)=>{
  const name=request.params.name;
  if(!toolSpecs.some(t=>t.name===name)) return {isError:true,content:[{type:'text',text:'未知工具。'}]};
  const args=request.params.arguments ?? {};
  if(typeof args!=='object'||Array.isArray(args)||Object.keys(args).length) return {isError:true,content:[{type:'text',text:'此工具不接受额外参数。'}]};
  try {
   let result;
   if(name==='diagnostics_open'){
    const current=await getUi();
    result={local_url:current.url,instructions:'请在本机浏览器打开此页面。用户先选择测试并点击开始，完成后查看脱敏预览。只有在页面点击“提交这份报告”才会上传。',collector:PUBLIC_BASE,max_download_per_run_mib:10,max_download_per_session_mib:20,raw_logs_uploaded:false};
   }else if(!ui){ result={state:'not_started',instructions:'请先调用 diagnostics_open。'}; }
   else if(name==='diagnostics_stop'){ await ui.stop();result={state:'stop_requested'}; }
   else if(name==='diagnostics_preview'){
    const p=await ui.preview();
    const report=p?.report ?? p;
    result=report && validateReport(report).ok ? {report,submission:'只能由用户在本地页面预览后主动点击提交。'} : {state:'no_report',instructions:'请先在本地页面完成诊断。'};
   }else {
    const s=await ui.getStatus();
    result={state:typeof s?.state==='string'?s.state:typeof s?.status==='string'?s.status:typeof s?.phase==='string'?s.phase:'unknown',running:!!s?.running||['running','stopping'].includes(s?.phase),has_report:!!(s?.has_report||s?.hasReport||s?.report),progress:s?.progress?{stage:s.progress.stage,completed:s.progress.completed,total:s.progress.total,used_payload_bytes:s.progress.used_payload_bytes}:null};
   }
   return {content:[{type:'text',text:JSON.stringify(result)}]};
  }catch{return {isError:true,content:[{type:'text',text:'本地操作未完成。请查看本地页面状态或重新启动本地诊断。'}]};}
 });
 const close=async()=>{if(closed)return;closed=true;if(creating){try{await creating;}catch{}}if(ui)await ui.close();};
 server.onclose=()=>{void close();};
 return {server,close};
}
function openBrowser(url) {
 const commands=process.platform==='win32'?['rundll32',['url.dll,FileProtocolHandler',url]]:process.platform==='darwin'?['open',[url]]:['xdg-open',[url]];
 const child=spawn(commands[0],commands[1],{stdio:'ignore',detached:true,windowsHide:true});
 child.on('error',()=>console.error('请手动在浏览器打开上面的本地地址。'));child.unref();
}
export async function main(argv=process.argv.slice(2)){
 const allowed=new Set(['--stdio','--web','--open','--help','--version','--print-config','--lab']);
 if(argv.some(x=>!allowed.has(x)))throw new Error('不支持的参数；使用 --help 查看用法。');
 if(argv.includes('--help')){console.log('Fanqiang 本地网络诊断\n默认：MCP stdio 服务\n--web           启动本地诊断页面\n--web --open    启动并打开本地页面\n--print-config  输出本机 MCP 配置\n--version       显示版本\n--lab           明确标记 Linux 实验环境\n测试与报告默认留在本地；提交必须在预览页面点击按钮。');return;}
 if(argv.includes('--version')){console.log(VERSION);return;}
 if(argv.includes('--print-config')){console.log(JSON.stringify({mcpServers:{"fanqiang-diagnostics":{command:process.execPath,args:[fileURLToPath(import.meta.url),'--stdio']}}},null,2));return;}
 if(argv.includes('--open')&&!argv.includes('--web'))throw new Error('--open 只能与 --web 一起使用。');
 if(argv.includes('--web')&&argv.includes('--stdio'))throw new Error('请选择 --web 或 --stdio。');
 const executionLocation=argv.includes('--lab')?'linux_lab':'user_device';
 if(argv.includes('--web')){
  const ui=await startLocalUi({runDiagnostics,publicBase:PUBLIC_BASE,executionLocation});
  console.log('本地诊断页面：'+ui.url+'\n测速、日志预览均留在本机；仅主动提交后上传脱敏指标。关闭终端即可结束。');
  if(argv.includes('--open'))openBrowser(ui.url);
  const quit=async()=>{await ui.close();process.exit(0);};
  process.once('SIGINT',quit);process.once('SIGTERM',quit);return;
 }
 const app=createDiagnosticsServer({executionLocation});
 process.once('SIGINT',async()=>{await app.close();await app.server.close();});
 process.once('SIGTERM',async()=>{await app.close();await app.server.close();});
 await app.server.connect(new StdioServerTransport());
}
function isEntrypoint(){try{return !!process.argv[1] && import.meta.url===pathToFileURL(realpathSync(resolve(process.argv[1]))).href;}catch{return false;}}
if(isEntrypoint())main().catch(e=>{console.error(e?.message||'启动失败');process.exitCode=1;});
