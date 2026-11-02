import test from 'node:test';
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
test('real MCP stdio initialize/list/open/status/preview/stop and unknown parameters',{timeout:20000},async()=>{
 const client=new Client({name:'fanqiang-mcp-integration',version:'0.1.0'});
 const transport=new StdioClientTransport({command:process.execPath,args:[process.env.FQDIAG_TEST_ENTRY||resolve(root,process.env.FQDIAG_TEST_BUNDLE==='1'?'dist/client.mjs':'src/client.mjs'),'--stdio','--lab'],stderr:'pipe'});
 let stderr='';transport.stderr?.on('data',x=>{stderr+=x;});
 try {
  await client.connect(transport);
  const list=await client.listTools();
  assert.deepEqual(list.tools.map(t=>t.name).sort(),['diagnostics_open','diagnostics_preview','diagnostics_status','diagnostics_stop']);
  assert(!list.tools.some(t=>/submit|upload/.test(t.name)));
  const before=JSON.parse((await client.callTool({name:'diagnostics_status',arguments:{}})).content[0].text);
  assert.equal(before.state,'not_started');
  const rejected=await client.callTool({name:'diagnostics_open',arguments:{upload:true}});
  assert.equal(rejected.isError,true);
  const opened=JSON.parse((await client.callTool({name:'diagnostics_open',arguments:{}})).content[0].text);
  assert.match(opened.local_url,/^http:\/\/127\.0\.0\.1:\d+\//);
  const view=await fetch(opened.local_url);assert.equal(view.status,200);
  const preview=JSON.parse((await client.callTool({name:'diagnostics_preview',arguments:{}})).content[0].text);
  assert.equal(preview.state,'no_report');
  const stopped=await client.callTool({name:'diagnostics_stop',arguments:{}});
  assert(!stopped.isError);
 }finally{await client.close();await transport.close();}
 assert(!/SyntaxError|ERR_MODULE_NOT_FOUND/.test(stderr));
});

// npm exposes bin entries through symbolic links; Node resolves the module filename.
test('CLI symlink entry prints version and absolute MCP configuration',{timeout:10000},async()=>{
 const {mkdtemp,symlink,rm}=await import('node:fs/promises');
 const {tmpdir}=await import('node:os');
 const {execFile}=await import('node:child_process');
 const {promisify}=await import('node:util');
 const directory=await mkdtemp(resolve(tmpdir(),'fanqiang-cli-link-'));
 const target=process.env.FQDIAG_TEST_ENTRY||resolve(root,process.env.FQDIAG_TEST_BUNDLE==='1'?'dist/client.mjs':'src/client.mjs');
 const link=resolve(directory,'fanqiang-diagnostics.mjs');
 try {
  await symlink(target,link);
  const version=await promisify(execFile)(process.execPath,[link,'--version']);
  assert.equal(version.stdout.trim(),'0.1.0');
  const config=JSON.parse((await promisify(execFile)(process.execPath,[link,'--print-config'])).stdout);
  assert.equal(config.mcpServers['fanqiang-diagnostics'].command,process.execPath);
  assert.equal(config.mcpServers['fanqiang-diagnostics'].args[0],target);
 }finally{await rm(directory,{recursive:true,force:true});}
});
