import test from 'node:test';
import assert from 'node:assert/strict';
import {createIntake,advanceIntake,publicFlow} from '../src/intake.mjs';
const aiQuestion='你现在有能正常使用的 AI 工具吗？豆包、元宝、DeepSeek 等都可以。';
const step=(state,text,options)=>advanceIntake(state,text,options);
const started=()=>step(createIntake(),'我想下载适合安卓手机的客户端').state;
const ready=()=>step(createIntake(),'我有能正常使用的 DeepSeek，设备是 Windows 11 电脑，想下载 v2rayN').state;

test('first technical request is saved but always begins with the fixed AI gate',()=>{
 const r=step(createIntake(),'我要给 RT-AX58U V2 核对梅林支持情况');
 assert.equal(r.reply,aiQuestion);assert.equal(r.generate,false);assert.equal(r.state.stage,'awaiting_ai');
 assert.match(r.state.originalRequest,/RT-AX58U V2/);assert.match(r.state.device,/V2/);
 assert.match(r.state.need,/梅林/);assert.equal(r.query,'');
});

test('no AI → official DeepSeek → ambiguous done → explicit ready → Android need',()=>{
 let r=step(createIntake(),'你好');r=step(r.state,'没有');
 assert.match(r.reply,/https:\/\/www[.]deepseek[.]com\//);assert.match(r.reply,/和DeepSeek对话/);assert.equal(r.state.aiReady,false);
 r=step(r.state,'好了');assert.equal(r.state.aiReady,false);assert.match(r.reply,/正常发送消息/);
 r=step(r.state,'已能用');assert.equal(r.state.aiReady,true);assert.equal(r.state.stage,'awaiting_requirements');
 r=step(r.state,'Android 手机，我想找适合手机的客户端');
 assert.equal(r.generate,true);assert.equal(r.state.stage,'ready');assert.match(r.query,/Android/);assert.match(r.query,/客户端/);
});

test('known device and need are not asked again after AI confirmation',()=>{
 let r=step(createIntake(),'Windows 11 电脑，我要下载 v2rayN');
 assert.equal(r.generate,false);r=step(r.state,'有');
 assert.equal(r.generate,true);assert.doesNotMatch(r.reply,/什么设备|什么系统|具体想/);
});

test('first message with explicitly working AI, concrete device and specific need skips only known fields',()=>{
 const r=step(createIntake(),'我有能正常使用的 DeepSeek，设备是 Windows 11 电脑，想下载 v2rayN');
 assert.equal(r.generate,true);assert.equal(r.state.aiReady,true);assert.equal(r.state.aiTool,'DeepSeek');assert.match(r.state.device,/Windows 11/);
});

for(const answer of ['有','可以','能用','可以用了','已能用'])test('short explicit confirmation in AI gate: '+answer,()=>{
 const r=step(started(),answer);assert.equal(r.state.aiReady,true);
});
for(const answer of ['好了','搞定','DeepSeek','还没登录','尚未登录','打不开','DeepSeek 不能用','我没有 AI','还没试'])test('unclear or unavailable AI never passes: '+answer,()=>{
 const r=step(started(),answer);assert.equal(r.state.aiReady,false);assert.equal(r.generate,false);
});

test('artifact mode cannot bypass AI gate even with complete equipment',()=>{
 const r=step(createIntake(),'给我工程书',{artifactRequested:true,extraContext:'Windows 11 电脑，我要下载 v2rayN'});
 assert.equal(r.state.aiReady,false);assert.equal(r.generate,false);assert.equal(r.reply,aiQuestion);
});

for(const [kind,prompt]of [['手机','手机是安卓、苹果还是鸿蒙'],['电脑','电脑是 Windows、苹果电脑还是 Linux'],['路由器','路由器的完整型号']])test('generic '+kind+' requires a concrete system or model',()=>{
 let r=step(started(),'可以用了');r=step(r.state,'设备改为'+kind);
 assert.equal(r.generate,false);assert.match(r.reply,new RegExp(prompt));
});

test('a complete device does not trigger a demand for unknown software version',()=>{
 let r=step(createIntake(),'我要核对梅林支持情况，路由器是 RT-AX58U V2');r=step(r.state,'能用');
 assert.equal(r.generate,true);assert.match(r.state.device,/RT-AX58U V2/);assert.doesNotMatch(r.reply,/版本|系统|型号/);
});

for(const message of ['你好','我要XXX'])test('generic intent stays incomplete: '+message,()=>{
 let r=step(createIntake(),message);r=step(r.state,'可以用了');r=step(r.state,'Windows 11 电脑');
 assert.equal(r.generate,false);assert.match(r.reply,/具体想完成什么/);
});

test('JSON refresh roundtrip preserves profile and ready condition',()=>{
 const state=ready();const copy=JSON.parse(JSON.stringify(state));
 assert.deepEqual(publicFlow(copy),{stage:'ready',aiReady:true,aiTool:'DeepSeek',canGenerate:true});
 assert.deepEqual(copy,state);
});

test('delivered profile stays delivered for thanks and regenerates after actual correction',()=>{
 const state={...ready(),stage:'delivered'};
 let r=step(state,'谢谢');assert.equal(r.generate,false);assert.equal(r.state.stage,'delivered');
 r=step(r.state,'设备改为 Android 手机，需求改为找适合安卓的客户端');
 assert.equal(r.generate,true);assert.match(r.state.device,/Android/);assert.match(r.state.need,/安卓/);assert.doesNotMatch(r.query,/Windows 11/);
});

test('explicit AI loss sends a completed profile back through the AI gate',()=>{
 const r=step({...ready(),stage:'delivered'},'我的 DeepSeek 现在打不开');
 assert.equal(r.state.aiReady,false);assert.equal(r.state.stage,'awaiting_ai');assert.equal(r.generate,false);assert.match(r.reply,/deepseek[.]com/);
});

test('hardware revision correction preserves exact V1 rather than stale V2',()=>{
 let r=step(createIntake(),'DeepSeek 可以正常使用，RT-AX58U V2，我想核对梅林支持情况');
 assert.equal(r.generate,true);r=step({...r.state,stage:'delivered'},'型号改为 V1');
 assert.equal(r.generate,true);assert.match(r.state.device,/RT-AX58U V1/);assert.doesNotMatch(r.query,/V2/);
});

test('public view ignores invalid stages and does not trust arbitrary ready fields',()=>{
 const r=publicFlow({version:1,stage:'ready',aiReady:'true',canGenerate:true,device:'电脑',need:'我要XXX',evil:'ignored'});
 assert.deepEqual(r,{stage:'awaiting_ai',aiReady:false,aiTool:'',canGenerate:false});
 assert.deepEqual(createIntake(),createIntake());
});

test('state accepts only bounded own plain data and discards executable or unknown fields',()=>{
 const bad={version:1,stage:'delivered',aiReady:true,aiTool:'x'.repeat(1000),device:{name:'Android'},need:['download'],details:['x'.repeat(5000),...Array.from({length:20},(_,i)=>'detail '+i),{},null],originalRequest:'x'.repeat(5000),secret:'must disappear',__proto__:{polluted:true}};
 const r=step(bad,{toString(){throw new Error('must not execute')}});
 assert.deepEqual(r.state,createIntake());
 const own=JSON.parse('{"version":1,"stage":"delivered","aiReady":true,"device":"电脑","need":"我要XXX","__proto__":{"polluted":true}}');
 const s=step(own,'').state;assert.equal(s.stage,'awaiting_requirements');assert.equal(Object.hasOwn(s,'__proto__'),false);assert.equal({}.polluted,undefined);
});

test('all string and details limits hold for large legitimate inputs',()=>{
 let state={...ready(),aiTool:'d'.repeat(500),originalRequest:'z'.repeat(5000),details:Array.from({length:20},(_,i)=>String(i)+'x'.repeat(4000))};
 const r=step(state,'Windows 11 电脑，我想排查连接失败。'+'x'.repeat(10000));
 assert.ok(r.state.aiTool.length<=80);assert.ok(r.state.originalRequest.length<=1500);assert.ok(r.state.device.length<=256);assert.ok(r.state.need.length<=1500);
 assert.ok(r.state.details.length<=8);assert.ok(r.state.details.every(x=>[...x].length<=1500));assert.ok([...r.query].length<=6000);
 assert.deepEqual(Object.keys(r.state).sort(),['version','stage','aiReady','aiTool','originalRequest','device','need','details'].sort());
});

test('direct yes and no apply to the explicit initial awaiting_ai stage',()=>{
 assert.equal(step(createIntake(),'有').state.aiReady,true);
 const no=step(createIntake(),'没有');assert.equal(no.state.aiReady,false);assert.match(no.reply,/deepseek[.]com/);
});

test('a named tool in the awaiting_ai conversation confirms the tool without requiring another prompt',()=>{
 const r=step(started(),'我用豆包');assert.equal(r.state.aiReady,true);assert.equal(r.state.aiTool,'豆包');
});

test('an explicitly supplied complete router model outside the common list is accepted as data',()=>{
 let r=step(createIntake(),'DeepSeek 能正常使用，路由器型号是 TP-LINK TL-WDR7660，我要排查连接失败');
 assert.equal(r.generate,true);assert.match(r.state.device,/TL-WDR7660/);assert.doesNotMatch(r.reply,/完整型号/);
 const copy=JSON.parse(JSON.stringify(r.state));assert.equal(publicFlow(copy).canGenerate,true);
});

test('device correction with a negated old system only retains the actual replacement',()=>{
 const r=step({...ready(),stage:'delivered'},'不是 Windows 11，而是 Android 手机');
 assert.equal(r.generate,true);assert.match(r.state.device,/Android/);assert.doesNotMatch(r.state.device,/Windows/);
});

for(const message of ['我想用 v2rayN','我要用 v2rayN','用 v2rayN','我想用小火箭'])test('ordinary spoken goal is sufficient: '+message,()=>{
 let r=step(createIntake(),message);assert.ok(r.state.need);assert.equal(r.reply,aiQuestion);
 r=step(r.state,'有');r=step(r.state,'Windows 11 电脑');assert.equal(r.generate,true);
});

for(const message of ['我要翻墙','我要科学上网'])test('a real broad goal is retained without demanding technical actions: '+message,()=>{
 let r=step(createIntake(),message);assert.ok(r.state.need);r=step(r.state,'我用豆包');
 assert.equal(r.state.aiReady,true);assert.match(r.reply,/什么设备/);
 const need=r.state.need;r=step(r.state,'我用安卓手机');
 assert.equal(r.generate,true);assert.equal(r.state.need,need);assert.doesNotMatch(r.reply,/具体想完成什么/);
});

test('joined hardware suffix remains a single current revision after correction',()=>{
 let r=step(createIntake(),'DeepSeek 能用，RT-AX58UV2，我要核对梅林支持情况');
 assert.equal(r.generate,true);assert.equal(r.state.device,'RT-AX58U V2');
 r=step({...r.state,stage:'delivered'},'型号改为V1');assert.match(r.state.device,/V1/);assert.doesNotMatch(r.query,/V2/);
});

for(const [kind,expected]of [['手机','苹果手机'],['电脑','苹果电脑']])test('Apple shorthand follows an already provided '+kind+' category',()=>{
 let r=step(createIntake(),'我要翻墙');r=step(r.state,'有');r=step(r.state,kind);
 assert.equal(r.generate,false);r=step(r.state,'苹果');assert.equal(r.state.device,expected);assert.equal(r.generate,true);
});

test('Apple without a device category does not guess a phone',()=>{
 let r=step(createIntake(),'我要翻墙');r=step(r.state,'有');r=step(r.state,'苹果');
 assert.equal(r.state.device,'');assert.equal(r.generate,false);assert.match(r.reply,/什么设备/);
});

for(const [kind,answer,expected]of [['手机','不知道系统','手机（系统未知）'],['电脑','系统我不知道','电脑（系统未知）'],['路由器','不知道型号','路由器（型号未知）']])test('explicit unknown '+kind+' is preserved for the visitors own AI',()=>{
 let r=step(createIntake(),'我要翻墙');r=step(r.state,'有');r=step(r.state,kind);r=step(r.state,answer);
 assert.equal(r.state.device,expected);assert.equal(r.generate,true);assert.match(r.query,/未知/);
 assert.equal(publicFlow(JSON.parse(JSON.stringify(r.state))).canGenerate,true);
});

test('unknown system without any device category still asks for the category',()=>{
 let r=step(createIntake(),'我要翻墙');r=step(r.state,'有');r=step(r.state,'不知道系统');
 assert.equal(r.state.device,'');assert.equal(r.generate,false);assert.match(r.reply,/什么设备/);
});

test('unknown version does not replace an already supplied concrete device',()=>{
 const r=step({...ready(),stage:'delivered'},'不知道版本');assert.match(r.state.device,/Windows 11/);
});

for(const message of ['我有DS','DS可以用了'])test('DS shorthand confirms DeepSeek under the same AI rules: '+message,()=>{
 const r=step(started(),message);assert.equal(r.state.aiReady,true);assert.equal(r.state.aiTool,'DeepSeek');
});

test('DS shorthand does not override an explicit unavailable condition',()=>{
 const r=step(started(),'我有DS，但DS还没登录');assert.equal(r.state.aiReady,false);assert.equal(r.state.aiTool,'DeepSeek');assert.equal(r.generate,false);
});
