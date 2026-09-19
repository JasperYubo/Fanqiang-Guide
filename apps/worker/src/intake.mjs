// Deterministic visitor intake. No model calls, network access or executable user data.
const LIMIT = Object.freeze({ text:1500, device:256, tool:80, details:8, query:6000 });
const STAGES = new Set(['awaiting_ai','awaiting_requirements','ready','delivered']);
const REPLY = Object.freeze({
  ai:'你现在有能正常使用的 AI 工具吗？豆包、元宝、DeepSeek 等都可以。',
  noAI:'先打开 DeepSeek 官网：https://www.deepseek.com/ ，点击“和DeepSeek对话”。能正常发送消息后，回来回复“可以用了”。',
  confirmAI:'请先确认你的 AI 工具能正常发送消息。能正常发送消息后，回复“可以用了”。',
  both:'请告诉我你现在用的设备和具体想完成什么。手机或电脑请说系统；路由器请说完整型号。',
  device:'你准备用什么设备？手机或电脑请说系统；路由器请说完整型号。',
  phone:'这台手机是安卓、苹果还是鸿蒙？如果不知道系统，直接说“不知道系统”就可以。',
  computer:'这台电脑是 Windows、苹果电脑还是 Linux？如果不知道系统，直接说“不知道系统”就可以。',
  router:'请告诉我路由器的完整型号，包括型号末尾的 V1、V2 或 Pro 等标记。',
  need:'你具体想完成什么？例如：找适合设备的客户端、核对路由器型号是否支持，或排查遇到的问题。',
  ready:'信息齐了，正在为你整理工程书。下载后交给你自己的 AI 继续处理。',
  delivered:'工程书已生成。需要调整时，告诉我新的设备或需求。',
});
const toolPattern=/(\bDS\b|DeepSeek|ChatGPT|Claude|Gemini|Copilot|Grok|Kimi|豆包|元宝|通义千问|千问|文心一言|AI\s*工具|人工智能)/i;
const aiPattern=/(?:\bDS\b|DeepSeek|ChatGPT|Claude|Gemini|Copilot|Grok|Kimi|豆包|元宝|通义千问|千问|文心一言|AI|人工智能)/i;
const unavailable=/(?:不能用|还不能|尚不能|用不了|不可用|无法使用|没法用|打不开|无法打开|打开不了|登不上|登录不了|不能登录|未登录|尚未登录|还没登录|没有登录|没登录|不会用|不能正常发送|无法发送|没法发消息|还没试|尚未试)/;
const shortYes=/^(?:有|有的|我有|可以|能用|可以用了|已经可以用了|现在可以用了|已能用|已经能用|现在能用|能正常用|能正常使用|可以正常使用|能正常发送消息|可以正常发送消息)[。！!\s]*$/;
const generic=/^(?:你好|您好|嗨|哈喽|在吗|开始|谢谢|好的|好了|搞定|明白|收到|我(?:想|要|想要)?(?:翻墙|科学上网|上网|弄一下|试试|XXX|xxx|某某|这个|那个)|翻墙|科学上网|上网|我要|我想|帮我|请帮我|需求|生成工程书|再生成|再次生成工程书|我要(?:一个|一份)?工程书|根据本次对话生成\s*I-Lang\s*工程书)[。！!？?\s]*$/i;
const broadGoal=/^(?:(?:我)?(?:想|要|想要|需要)|帮我|请帮我)?(翻墙|科学上网)[。！!？?\s]*$/;
const routerPattern=/(?:(?:华硕|ASUS|小米|红米|Redmi|TP-Link|华为|荣耀|GL[.]?iNet)\s*)?(?:(?:RT|DSL|GT|TUF|ZenWiFi|GL)[\s_-]*)?(?:AX|AC|BE|BQ|BT|XT|XD|ET|MT)[0-9]{2,5}[A-Z0-9]*(?:[\s_-]*(?:V[0-9]+|PRO|GO|B[0-9]+))?/ig;
const clean=(value,max=LIMIT.text)=>typeof value==='string'?[...value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g,'').trim()].slice(0,max).join(''):'';
const plain=value=>value!==null&&typeof value==='object'&&!Array.isArray(value)&&(Object.getPrototypeOf(value)===Object.prototype||Object.getPrototypeOf(value)===null);
const own=(value,key)=>Object.prototype.hasOwnProperty.call(value,key)?value[key]:undefined;
const norm=value=>clean(value).replace(/\s+/g,' ').toLowerCase();

export function createIntake() {
  return {version:1,stage:'awaiting_ai',aiReady:false,aiTool:'',originalRequest:'',device:'',need:'',details:[]};
}

function sanitize(previous) {
  const state=createIntake();
  if(!plain(previous)||own(previous,'version')!==1)return state;
  state.aiReady=own(previous,'aiReady')===true;
  state.aiTool=clean(own(previous,'aiTool'),LIMIT.tool);
  state.originalRequest=clean(own(previous,'originalRequest'));
  state.device=clean(own(previous,'device'),LIMIT.device);
  state.need=clean(own(previous,'need'));
  const details=own(previous,'details');
  if(Array.isArray(details))state.details=[...new Set(details.filter(x=>typeof x==='string').map(x=>clean(x)).filter(Boolean))].slice(-LIMIT.details);
  const stage=own(previous,'stage');
  state.stage=STAGES.has(stage)?stage:'awaiting_ai';
  if(!state.aiReady)state.stage='awaiting_ai';
  else if(!completeDevice(state.device)||!concreteNeed(state.need))state.stage='awaiting_requirements';
  else if(!['ready','delivered'].includes(state.stage))state.stage='ready';
  return state;
}

function aiStatus(text,canUseShort) {
  const clauses=text.split(/[，,。；;\n]/).map(s=>s.trim()).filter(Boolean);
  const named=text.match(toolPattern)?.[1]||'';
  const tool=/^DS$/i.test(named)?'DeepSeek':named;
  const explicitNo=/(?:没有|还没有|暂时没有|没|不再有)\s*(?:能正常使用的|可正常使用的|可以用的|能用的|可用的|任何|一个)?\s*(?:\bDS\b|AI|人工智能|DeepSeek|ChatGPT|Claude|Gemini|豆包|元宝)/i.test(text)
    ||clauses.some(s=>aiPattern.test(s)&&unavailable.test(s))
    ||(canUseShort&&/^(?:没有|还没有|暂时没有|不能用|还不能用|用不了|打不开|不行|未登录|尚未登录|还没登录|没登录|不会用|还没试)[。！!\s]*$/.test(text));
  if(explicitNo)return {value:false,tool};
  if(canUseShort&&shortYes.test(text))return {value:true,tool};
  const explicitYes=clauses.some(s=>aiPattern.test(s)&&!unavailable.test(s)&&!/(?:没有|还没有|不可以|不能|没法|无法|未|没)/.test(s)&&(
    /(?:能正常|可以正常|已经能|现在能|已经可以|现在可以|可以用|能用|可用|能发消息|可以发消息|正常发送|正常使用)/.test(s)
    ||(canUseShort&&/(?:我有|我在用|我用|正在用|已经有|有一个|用的是)/.test(s))
  ));
  return {value:explicitYes?true:null,tool};
}

function correctionText(text) {
  const swap=text.match(/(?:不是|不再用|不用)[^，,。；;\n]{1,100}?(?:而是|改用|换成|改成|改为|，是|,是|，用|,用)([\s\S]+)$/);
  if(swap)return swap[1];
  const markers=[...text.matchAll(/(?:设备(?:改成|改为|换成|是)|改用|换成|改成|改为|现在用|实际用|实际是|我用的是)/g)]
    .filter(m=>!/(?:需求|目标)$/.test(text.slice(Math.max(0,m.index-2),m.index)));
  return markers.length?text.slice(markers.at(-1).index+markers.at(-1)[0].length):text;
}

function extractDevice(text,previous='') {
  const target=correctionText(text).replace(/[，,；;\n]\s*(?:需求|目标)[\s\S]*$/,'');
  const knownUnknown=target.match(/(?:手机|电脑)（系统未知）|路由器（型号未知）/);
  if(knownUnknown)return knownUnknown[0];
  if(/^苹果[。！!\s]*$/.test(target)){
    const kind=deviceKind(previous);
    return kind==='手机'?'苹果手机':kind==='电脑'?'苹果电脑':'';
  }
  const modelMatches=[...target.matchAll(routerPattern)].map(m=>m[0].trim().replace(/([A-Z0-9])((?:V[0-9]+|PRO))$/i,'$1 $2'));
  if(modelMatches.length)return clean([...new Set(modelMatches)].join(' / '),LIMIT.device);
  const explicitModel=target.match(/(?:路由器(?:的)?(?:完整)?型号|型号|路由器)\s*(?:是|为|[:：])\s*([^，,。；;\n]+)/)?.[1];
  if(explicitModel&&/[a-z]/i.test(explicitModel)&&/\d/.test(explicitModel))return clean('路由器 '+explicitModel,LIMIT.device);
  if(/^路由器\s+/.test(target)&&/[a-z]/i.test(target)&&/\d/.test(target))return clean(target,LIMIT.device);
  const variants=[...target.matchAll(/\b(V[0-9]+|PRO)\b/ig)];
  if(variants.length===1&&previous&&/\d/.test(previous)&&/(?:改|换|不是|实际|设备|型号|那|是)/.test(text)){
    const variant=variants[0][1].toUpperCase();
    return clean(/\b(?:V[0-9]+|PRO)\b/i.test(previous)?previous.replace(/\b(?:V[0-9]+|PRO)\b/ig,variant):previous+' '+variant,LIMIT.device);
  }
  const matches=[];
  const rules=[
    [/(?:Windows|Win)\s*(?:11|10|8[.]1|8|7)?(?:\s*(?:电脑|笔记本|台式机))?/ig,m=>m.replace(/^win(?=\s|\d|$)/i,'Windows')],
    [/(?:macOS(?:\s*[0-9.]+)?|MacBook(?:\s*(?:Air|Pro))?|iMac|苹果电脑|Mac电脑)/ig,m=>m],
    [/(?:Linux|Ubuntu|Debian|Fedora|Arch)(?:\s*[0-9.]+)?(?:\s*电脑)?/ig,m=>m],
    [/(?:Android|安卓)(?:\s*[0-9.]+)?(?:\s*(?:手机|平板))?/ig,m=>m],
    [/(?:iOS(?:\s*[0-9.]+)?|iPhone(?:\s*[0-9]+(?:\s*(?:Pro(?:\s*Max)?|Plus))?)?|iPad(?:OS)?(?:\s*[0-9.]+)?|苹果手机)/ig,m=>m],
    [/(?:HarmonyOS|鸿蒙)(?:\s*[0-9.]+)?(?:\s*手机)?/ig,m=>m],
  ];
  for(const [pattern,map]of rules)for(const match of target.matchAll(pattern)){
    const before=target.slice(Math.max(0,match.index-4),match.index);
    if(!/(?:不是|不用|没有|不再用)\s*$/.test(before))matches.push(map(match[0].trim()));
  }
  if(matches.length)return clean([...new Set(matches)].join(' / '),LIMIT.device);
  const basic=[...target.matchAll(/手机|电脑|笔记本|台式机|路由器/g)].filter(m=>!/(?:没有|不用|不是)\s*$/.test(target.slice(Math.max(0,m.index-4),m.index)));
  if(basic.length){const kind=basic.at(-1)[0];return /笔记本|台式机/.test(kind)?'电脑':kind;}
  return '';
}

function deviceKind(value) {
  if(/手机|平板|Android|安卓|iPhone|iOS|iPad|鸿蒙|HarmonyOS/i.test(value))return '手机';
  if(/电脑|Windows|Mac|Linux|Ubuntu|Debian|Fedora|Arch/i.test(value))return '电脑';
  if(/路由器/.test(value)||/[A-Z].*\d/i.test(value))return '路由器';
  return '';
}

function explicitUnknown(text) {
  return /(?:不知道|不清楚|不确定)(?:是什么|什么|自己的|这个|是啥)?(?:系统|型号)/.test(text)
    ||/(?:系统|型号)[^，,。；;\n]{0,12}(?:不知道|不清楚|不确定|未知)/.test(text)
    ||/^(?:我)?(?:不知道|不清楚|不确定)[。！!\s]*$/.test(text);
}

function completeDevice(value) {
  if(!value||/^(?:手机|电脑|路由器|笔记本|台式机)$/.test(value))return false;
  if(/^(?:手机|电脑)（系统未知）$|^路由器（型号未知）$/.test(value))return true;
  return Boolean(extractDevice(value));
}

function concreteNeed(value) {
  const text=clean(value);
  if(broadGoal.test(text))return true;
  if(!text||generic.test(text)||/^(?:::ILANG|<|\{)/.test(text))return false;
  if(/^(?:生成|下载|要|我要|给我|请给我|再次生成)?\s*(?:一份|一个)?\s*(?:I-Lang\s*)?工程书[。！!?？\s]*$/i.test(text))return false;
  if(/(?:XXX|待补充|随便弄|随便搞|某某)/i.test(text))return false;
  if(/^(?:我)?(?:想用|要用|用|使用)(?:这个|那个|一下|东西)[。！!？?\s]*$/.test(text))return false;
  return /(?:下载|安装|找|选择|选|对比|比较|核对|检查|查|了解|访问|打开|导入|转换|解决|排查|修复|刷|配置|设置|连接|使用|想用|要用|用|支持|区别|报错|失败|连不上|打不开)/.test(text)
    &&text.replace(/(?:我|想|要|请|帮|一下|下载|安装|找|选择|选|核对|查|配置|设置|使用|用|支持|吗|呢|吧|[\s。！!?？])/g,'').length>=2;
}

function extractNeed(text) {
  const broad=text.match(broadGoal);if(broad)return broad[1];
  if(!text||generic.test(text)||text.includes('::MODULE{ARTIFACT_REQUEST}'))return '';
  const focus=text.match(/(?:需求|目标)(?:改成|改为|换成|是)[：:\s]*([\s\S]+)/)?.[1]||text;
  const clauses=focus.split(/[，,。；;\n]/).map(s=>s.trim()).filter(Boolean);
  const candidates=[];
  for(const clause of clauses){
    const goal=clause.match(broadGoal);if(goal){candidates.push(goal[1]);continue;}
    if(aiPattern.test(clause)&&!/(?:客户端|梅林|固件|订阅|节点|v2ray|clash|shadowrocket|网络|网站|科学上网|翻墙)/i.test(clause))continue;
    const device=extractDevice(clause);
    if(device&&norm(clause).replace(norm(device),'').replace(/[我想要用的设备现在目前准备使用是：:\s]/g,'')==='')continue;
    if(!concreteNeed(clause))continue;
    const action=clause.match(/(?:下载|安装|寻找|找|选择|选|对比|比较|核对|检查|查|了解|访问|打开|导入|转换|解决|排查|修复|刷|配置|设置|连接|使用|想用|要用|用|支持|区别|报错|失败|连不上|打不开)/);
    const candidate=action?clause.slice(action.index):clause;
    if(concreteNeed(candidate))candidates.push(candidate);
  }
  return clean(candidates.join('；'));
}

function queryFor(state) {
  const relevant=state.details.filter(t=>{
    const device=extractDevice(t);
    return !device||norm(device)===norm(state.device);
  }).filter(t=>norm(t)!==norm(state.need)&&norm(t)!==norm(state.device)).slice(-4);
  return clean(['设备：'+state.device,'需求：'+state.need,...relevant.map(t=>'补充：'+t)].join('\n'),LIMIT.query);
}

export function publicFlow(previous) {
  const state=sanitize(previous);
  return {stage:state.stage,aiReady:state.aiReady,aiTool:state.aiTool,canGenerate:state.aiReady&&completeDevice(state.device)&&concreteNeed(state.need)};
}

export function advanceIntake(previous,message,{artifactRequested=false,extraContext=''}={}) {
  const state=sanitize(previous),before={...state,details:[...state.details]};
  const extra=clean(extraContext);
  const input=extra||clean(message);
  const alreadyAsked=before.stage==='awaiting_ai';
  const ai=aiStatus(input,alreadyAsked);
  if(ai.value!==null){state.aiReady=ai.value;if(ai.tool)state.aiTool=clean(ai.tool,LIMIT.tool);if(ai.value===false&&!ai.tool)state.aiTool='';}
  else if(ai.tool&&!state.aiReady)state.aiTool=clean(ai.tool,LIMIT.tool);

  let device=extractDevice(input,state.device);
  if(explicitUnknown(input)){
    const kind=deviceKind(device||state.device);
    if(kind&&!completeDevice(device||state.device))device=kind+(kind==='路由器'?'（型号未知）':'（系统未知）');
  }
  const need=extractNeed(input);
  if(device)state.device=device;
  if(need)state.need=need;
  if(input&&(!state.originalRequest||(!concreteNeed(state.originalRequest)&&need)))state.originalRequest=input;
  const changedDevice=device&&norm(device)!==norm(before.device);
  const changedNeed=need&&norm(need)!==norm(before.need);
  if(changedDevice&&before.device&&state.need.includes(before.device))state.need=state.need.replaceAll(before.device,state.device);
  if((changedDevice||changedNeed)&&['ready','delivered'].includes(before.stage))state.details=[];
  if((device||need)&&input&&!generic.test(input))state.details=[...new Set([...state.details,input])].slice(-LIMIT.details);

  const canGenerate=state.aiReady&&completeDevice(state.device)&&concreteNeed(state.need);
  const changed=Boolean(changedDevice||changedNeed||state.aiReady!==before.aiReady);
  const repeatRequested=artifactRequested===true||/^(?:重新|再次|再)生成(?:一份)?(?:工程书)?[。！!\s]*$/.test(input);
  const generate=canGenerate&&(before.stage!=='delivered'||changed||repeatRequested);
  state.stage=!state.aiReady?'awaiting_ai':!canGenerate?'awaiting_requirements':generate?'ready':'delivered';
  let reply;
  if(!state.aiReady)reply=ai.value===false?REPLY.noAI:alreadyAsked&&/^(?:好了|好的|搞定|收到|明白)[。！!\s]*$/.test(input)?REPLY.confirmAI:REPLY.ai;
  else if(!completeDevice(state.device))reply=state.device==='手机'?REPLY.phone:state.device==='电脑'?REPLY.computer:state.device==='路由器'?REPLY.router:state.need?REPLY.device:REPLY.both;
  else if(!concreteNeed(state.need))reply=REPLY.need;
  else reply=generate?REPLY.ready:REPLY.delivered;
  return {state,reply,generate,query:canGenerate?queryFor(state):''};
}
