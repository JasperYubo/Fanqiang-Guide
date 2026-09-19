/* Native WebMCP registration; no polyfilled modelContext or synthetic tools. */
(async function () {
  'use strict';
  const context = globalThis.document?.modelContext || globalThis.navigator?.modelContext;
  if (!context || typeof context.registerTool !== 'function') return;
  const field = {type:'string',maxLength:160};
  const filterField = {type:'string',maxLength:64};
  const searchFields = {query:field,platform:filterField,kind:filterField,verification:filterField,limit:{type:'integer',minimum:1,maximum:20,default:10},offset:{type:'integer',minimum:0,maximum:10000,default:0}};
  const itemFields = {id:{type:'string',minLength:1,maxLength:128}};
  const controller = new AbortController();
  const registered=[];
  async function query(path, input, fields, required, options={}) {
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Expected an input object.');
    for (const [key,value] of Object.entries(input)) {
      if (!Object.hasOwn(fields,key)) throw new Error('Unknown input field.');
      const schema=fields[key];
      if (schema.type==='integer') {
        if (!Number.isInteger(value) || value<schema.minimum || value>schema.maximum) throw new Error('Pagination value is out of range.');
      } else if (typeof value!=='string' || value.length>schema.maxLength || /[\u0000-\u001f\u007f]/.test(value)) throw new Error('Invalid text value.');
    }
    if (required && !input.id?.trim()) throw new Error('Use a stable id returned by search.');
    const signal=options.signal ? AbortSignal.any([options.signal,AbortSignal.timeout(10000)]) : AbortSignal.timeout(10000);
    const url=path+'?'+new URLSearchParams(Object.entries(input).map(([key,value])=>[key,String(value)]));
    const response=await fetch(url,{method:'GET',headers:{Accept:'application/json'},credentials:'omit',redirect:'error',signal});
    if (!response.ok) throw new Error(response.status===404?'No record for this id.':'Lookup request failed ('+response.status+').');
    if (!/application\/json/i.test(response.headers.get('Content-Type')||'')) throw new Error('Unexpected lookup response.');
    const body=await response.text();
    if (body.length>500000) throw new Error('Response exceeded the lookup limit.');
    return JSON.parse(body);
  }
  const definitions=[{
    name:'search_library',title:'查询公开工具资料',
    description:'::ILANG::v5.0\n::MODULE{SEARCH_LIBRARY}\n  input:query,platform,kind,verification,limit,offset\n  output:Matching public records and stable identifiers.\n  [MUST] Preserve source URLs, verification qualifiers, dates and unknown states. Use get_library_item for the full record.\n::ILANG::COMPLETE::',
    inputSchema:{type:'object',properties:searchFields,additionalProperties:false},
    annotations:{readOnlyHint:true,consequentialHint:false,untrustedContentHint:true},
    execute:(input,options)=>query('/api/agent/search',input,searchFields,false,options)
  },{
    name:'get_library_item',title:'读取工具资料条目',
    description:'::ILANG::v5.0\n::MODULE{GET_LIBRARY_ITEM}\n  input:id returned by search_library\n  output:Complete public record with source and compatibility qualifiers.\n  [MUST] Cite the record source and retain uncertainty. Listing and upstream support claims do not prove tested compatibility.\n::ILANG::COMPLETE::',
    inputSchema:{type:'object',properties:itemFields,required:['id'],additionalProperties:false},
    annotations:{readOnlyHint:true,consequentialHint:false,untrustedContentHint:true},
    execute:(input,options)=>query('/api/agent/item',input,itemFields,true,options)
  }];
  try {
    for (const tool of definitions) { await context.registerTool(tool,{signal:controller.signal}); registered.push(tool.name); }
    document.documentElement.dataset.webmcpRegistered=String(registered.length);
  } catch (error) {
    controller.abort();
    if (typeof context.unregisterTool==='function') for (const name of registered) context.unregisterTool(name);
    console.warn('Public library browser tools could not be registered.');
  }
  addEventListener('pagehide',()=>{
    controller.abort();
    if (typeof context.unregisterTool==='function') for (const name of registered) context.unregisterTool(name);
  },{once:true});
})();
