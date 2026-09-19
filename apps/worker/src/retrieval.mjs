import { GUIDES, MODELS, LIBRARY, KNOWLEDGE_META } from './knowledge.mjs';

export const knowledgeMeta = KNOWLEDGE_META;
const normal = s => String(s ?? '').normalize('NFKC').toLowerCase();
const compact = s => normal(s).replace(/[\s_-]+/g, '');
const quote = s => JSON.stringify(s).replace(/</g, '\\u003c').replace(/::/g, '\\u003a\\u003a');
const patterns = {
  shadowrocket: /shadow\s*rocket|小\s*火\s*箭/i,
  v2rayn: /\bv2rayn\b/i, v2rayng: /\bv2rayng\b/i,
  clash: /\bclash\b|clashverge/i,
  openclash: /open\s*clash/i, passwall: /pass\s*wall(?:\s*2)?/i,
  openwrt: /open\s*wrt|软路由/i,
  hiddify: /hiddify/i,
  merlin: /merlin|梅林|华硕|asus|gnuton|fancyss/i,
  xray: /\bxray(?:-core)?\b|reality|vless/i,
  singbox: /sing[\s-]*box/i,
  mihomo: /mihomo|clash\s*meta/i,
  substore: /sub[\s-]*store/i,
  subconverter: /subconverter|sub[\s-]*web/i,
};
const topicEntities = {
  'client-downloads': ['v2rayn','v2rayng','clash','hiddify','shadowrocket'],
  'shadowrocket-platforms': ['shadowrocket'],
  'free-nodes': [],
  'subscription-conversion': ['substore','subconverter'],
  'openwrt-tools': ['openclash','passwall','openwrt'],
  'asus-merlin': ['merlin'],
  'v2rayn-guide': ['v2rayn'],
  'shadowrocket-qr': ['shadowrocket'],
  'proxy-cores': ['xray','singbox','mihomo'],
  'clash-projects': ['clash','openclash','mihomo'],
};
const intentRules = [
  [/下载|安装包|架构|客户端|安卓|android|windows|iphone|macos|linux|x64|arm64/i, ['client-downloads'], 7],
  [/安卓|android|windows|官方|官网|平台|mac|苹果|iphone/i, ['shadowrocket-platforms'], 4],
  [/免费|白嫖|(?:日期|每日|今天).{0,12}(?:节点|代理|订阅)|节点来源/i, ['free-nodes'], 18],
  [/转换|转成|格式不兼容|订阅管理|合并订阅/i, ['subscription-conversion'], 18],
  [/路由器|固件|内存|openwrt|passwall|openclash/i, ['openwrt-tools'], 7],
  [/梅林|华硕|merlin|asus|gnuton|fancyss|型号/i, ['asus-merlin'], 12],
  [/打不开|导入失败|连不上|不能用|报错|教程|怎么用|使用/i, ['v2rayn-guide'], 4],
  [/二维码|扫码/i, ['shadowrocket-qr'], 20],
  [/内核|核心|tun|dns|xray|sing[\s-]*box|mihomo|reality|vless/i, ['proxy-cores'], 10],
  [/clash\s*for\s*windows|clash\s*verge|归档|维护|停更/i, ['clash-projects'], 10],
];
const guideBySlug = new Map(GUIDES.map(g => [g.slug, g]));
const guideIndex = new Map(GUIDES.map(g => [g.slug, {
  questions: g.faq.map(f => normal(f.question).replace(/[\s?？。、，,]/g, '')),
  sections: g.sections.map(s => normal([s.heading, ...(s.paragraphs || []), ...(s.bullets || [])].join(' '))),
}]));
const FACT_LIMIT = 16000;
const latinBoundary = (text, term) => {
  let at = text.indexOf(term);
  while (at !== -1) {
    const before = text[at - 1] || '', after = text[at + term.length] || '';
    if ((!/[a-z0-9]/.test(term[0]) || !/[a-z0-9]/.test(before)) &&
        (!/[a-z0-9]/.test(term.at(-1)) || !/[a-z0-9]/.test(after))) return true;
    at = text.indexOf(term, at + 1);
  }
  return false;
};
const modelPattern = /\b((?:rt|dsl|gt|tuf|zenwifi(?:[\s_-]+pro)?)[\s_-]*)?((?:axe|ax|ac|be|bq|bt|xt|xd|et|n)[0-9]{1,5}[a-z0-9]*)(?:[\s_-]*(pro|go|b[0-9]+|v[0-9]+))?/ig;
function modelHint(text) {
  const matches = [...text.matchAll(modelPattern)];
  if (!matches.length) return null;
  const m = matches[0];
  const joined = compact(m[2]);
  const suffix = joined.match(/(pro|go|b[0-9]+|v[0-9]+)$/);
  return { prefix: compact(m[1] || ''), base: suffix ? joined.slice(0, -suffix[1].length) : joined, variant: compact(m[3] || suffix?.[1] || '') };
}
const followupPattern = /那|这(?:个|些|款|两)|它|上面|上述|刚才|前面|之前|还是|继续|具体|为什么|怎么用|如何使用|还有|一样|哪个|呢|总结|简短|区别|对比|详细说|展开说|注意事项|需要.{0,4}(?:信息|确认|资料)|\bv[0-9]+\b|\bpro\b/i;
const pureArtifactRequest = text => /^根据本次对话生成i-lang工程书[。.!！]?$/.test(normal(text).replace(/\s/g,''));
const variantsIn = text => [...new Set([...text.matchAll(/\b(v[0-9]+|pro)\b/ig)].map(m=>compact(m[1])))];
function hintsIn(text) {
  return [...text.matchAll(modelPattern)].slice(0,4).map(m=>modelHint(m[0]));
}
function applyVariants(hints, variants) {
  if(!variants.length)return hints;
  const bases=[...new Map(hints.map(h=>[`${h.prefix}:${h.base}`,h])).values()];
  return bases.flatMap(h=>variants.map(variant=>({...h,variant}))).slice(0,8);
}
function priorText(history) {
  if (!Array.isArray(history)) return {text:'',modelHints:[]};
  // Never use assistant prose as a source of device identity. Pure artifact
  // reuse pairs carry no new context; their assistant half is already ignored.
  const users=history.slice(-40).filter(m=>m?.role==='user'&&typeof m.content==='string'&&!pureArtifactRequest(m.content)).map(m=>normal(m.content.slice(0,600)));
  let anchor='',modelHints=[],tail=[];
  for(const text of users) {
    if(/^(?:谢谢|好的|好|明白了|知道了|收到)[。!！]?$/.test(text.trim()))continue;
    let direct=hintsIn(text);
    if(direct.length===1)direct=applyVariants(direct,variantsIn(text));
    const entities=Object.keys(patterns).filter(k=>patterns[k].test(text));
    const sameModelTopic=modelHints.length&&entities.length&&entities.every(e=>e==='merlin');
    const independentTopic=/免费节点|免费代理|节点来源|订阅转换|订阅管理|合并订阅|客户端下载|二维码/.test(text);
    if(direct.length||(entities.length&&!sameModelTopic)||independentTopic) {
      anchor=text;modelHints=direct;tail=[];
    } else if(anchor&&(followupPattern.test(text)||sameModelTopic||/工程书/.test(text))) {
      modelHints=applyVariants(modelHints,variantsIn(text));tail.push(text);tail=tail.slice(-3);
    } else if(text.trim()) {
      // A self-contained new question ends the old topic, even if unsupported.
      anchor='';modelHints=[];tail=[];
    }
  }
  return {text:[anchor,...tail].filter(Boolean).join(' '),modelHints};
}
function chooseModels(query, previous) {
  const direct = modelHint(query);
  let hints=direct?hintsIn(query):(previous?.modelHints||[]);
  if(!direct||hints.length===1)hints=applyVariants(hints,variantsIn(query));
  const hint=hints[0];
  if (!hint) return { hint: null, matches: [] };
  const exactNames = MODELS.filter(row=>latinBoundary(compact(query),row.canonical));
  if(direct && exactNames.length && hints.length===1)return {hint,matches:exactNames};
  const matches = MODELS.filter(row => {
    const parsed = modelIndex.get(row.id);
    return hints.some(h=>parsed&&parsed.base===h.base&&(!h.prefix||parsed.prefix===h.prefix)&&(!h.variant||parsed.variant===h.variant));
  });
  return { hint, matches };
}
const modelIndex = new Map(MODELS.map(row=>[row.id,modelHint(normal(row.model_exact))]));
function guideScore(guide, q, entities) {
  const own = topicEntities[guide.slug] || [];
  const matched = own.filter(e => entities.includes(e));
  let score = matched.length * 12;
  const exactQuestion = q.replace(/[\s?？。、，,]/g, '');
  if (guideIndex.get(guide.slug).questions.includes(exactQuestion)) score += 80;
  for (const [pattern, slugs, weight] of intentRules) {
    if (!slugs.includes(guide.slug) || !pattern.test(q)) continue;
    if (['shadowrocket-platforms','v2rayn-guide'].includes(guide.slug) && !matched.length) continue;
    score += weight;
  }
  for (const keyword of guide.keywords) {
    const key = normal(keyword);
    if (key.length >= 3 && latinBoundary(q, key)) score += 5;
  }
  if (!entities.length && /翻墙|科学上网|代理工具|选.*工具/.test(q) && guide.slug === 'client-downloads') score += 8;
  return score;
}
function sourceRows(guide) {
  const all = [{ title: guide.title, url: guide.url }];
  for (const faq of guide.faq) for (const s of faq.sources || []) all.push({ title: s.label, url: s.url });
  for (const section of guide.sections) for (const s of section.sources || []) all.push({ title: s.label, url: s.url });
  return all;
}
function guideFact(guide, q) {
  const terms = normal(q).match(/[a-z][a-z0-9-]{2,}|二维码|订阅|下载|平台|型号|内核|转换|免费|节点|导入|报错|官方|文档|配置|教程/g) || [];
  const ranked = guide.faq.map((f, i) => ({ f, i, score: (normal(f.question)===normal(q)?100:0)+terms.reduce((sum, term) => sum + (normal(f.question).includes(term) ? 1 : 0), 0) })).sort((a, b) => b.score - a.score || a.i - b.i);
  // Whole answers/paragraphs are retained; no truncation through a qualifier.
  const faq = ranked.slice(0, 2).map(({f}) => ({question:f.question,answer:f.answer,sources:f.sources,url:f.url}));
  const sectionScores = guideIndex.get(guide.slug).sections.map((text,i)=>({i,score:terms.reduce((sum,t)=>sum+(text.includes(t)?1:0),0)}));
  sectionScores.sort((a,b)=>b.score-a.score||a.i-b.i);
  const sections = sectionScores.slice(0,2).map(({i})=>guide.sections[i]);
  return { type: 'guide', slug: guide.slug, title: guide.title, published_at: KNOWLEDGE_META.published_at, summary: guide.summary, faq,
    sections: sections.map(s => ({heading:s.heading,paragraphs:s.paragraphs,bullets:s.bullets,sources:s.sources})), url: guide.url };
}
function libraryFact(row) {
  return {type:'library_reference',id:row.id,name:row.name,aliases:row.aliases,summary:row.summary,platforms:row.platforms,
    verification:row.verification,compatibility:row.compatibility,maintenance:row.maintenance,source_url:row.source_url,source_snapshot_url:row.source_snapshot_url,
    precedence:'Older public directory supplement. Use newer topic evidence for overlapping claims; never promote source review to device testing.'};
}

export function retrieve(query, history = []) {
  const current = normal(String(query ?? '').slice(0, 2000)).trim();
  const previous = priorText(history);
  const currentEntities = Object.keys(patterns).filter(k => patterns[k].test(current));
  const sameModelTopic=previous.modelHints.length&&currentEntities.length&&currentEntities.every(e=>e==='merlin');
  const useHistory = current.length < 100 && !modelHint(current) && (!currentEntities.length||sameModelTopic) && followupPattern.test(current);
  const q = useHistory ? `${previous.text} ${current}`.trim() : current;
  const entities = Object.keys(patterns).filter(k => patterns[k].test(q));
  const model = chooseModels(current, useHistory?previous:null);
  const candidates = GUIDES.map(g => ({g, score:guideScore(g,q,entities)}));
  if (model.hint) candidates.find(x => x.g.slug === 'asus-merlin').score += 40;
  candidates.sort((a,b) => b.score-a.score);
  const selection = [];
  if (model.hint) {
    for (const row of model.matches.slice(0, 3)) selection.push({type:'model',row});
  }
  const guideLimit = model.hint ? Math.max(1,4-selection.length) : 3;
  for (const {g,score} of candidates.filter(x => x.score >= 7).slice(0,guideLimit)) selection.push({type:'guide',row:g});
  if (selection.length < 4 && !model.hint && current.length) {
    const libraryMatches = LIBRARY.map(row => ({row,score:Math.max(0,...row.names.filter(name => name.length >= 3 && latinBoundary(q,name)).map(name=>name.length))})).filter(x=>x.score).sort((a,b)=>b.score-a.score);
    for (const {row} of libraryMatches.slice(0,selection.length?1:4)) selection.push({type:'library',row});
  }
  const selected = [];
  const sources = [];
  const seen = new Set();
  function add(s) { if (!s?.url || seen.has(s.url)) return; seen.add(s.url); sources.push({title:s.title || s.url,url:s.url}); }
  const facts = [];
  let recordSize = 0;
  function keep(record, entry) {
    let size = quote(record).length;
    while (recordSize + size > FACT_LIMIT - 1200 && record.type === 'guide' && record.sections.length) {
      record.sections.pop(); size = quote(record).length;
    }
    while (recordSize + size > FACT_LIMIT - 1200 && record.type === 'guide' && record.faq.length > 1) {
      record.faq.pop(); size = quote(record).length;
    }
    if (recordSize + size > FACT_LIMIT - 1200) return false;
    recordSize += size; facts.push(record);selected.push(entry);return true;
  }
  const topics = new Set();
  for (const entry of selection.slice(0,4)) {
    const {type,row}=entry;
    if (type === 'guide') { const record=guideFact(row,q);if(!keep(record,entry))continue;topics.add(row.slug);sourceRows(record).forEach(add); }
    if (type === 'model') { const {canonical,...record}=row;if(!keep({type:'model_source_record',...record,interpretation:'Source claim for this exact model and firmware branch only; firmware support does not establish plugin compatibility; tested is preserved.'},entry))continue;topics.add('asus-merlin');add({title:`${row.model_exact} · ${row.firmware_entity_id} 来源`,url:row.source_url});add({title:'梅林完整型号对照表',url:'https://fanqiang.guide/guides/merlin-models.html'}); }
    if (type === 'library') { if(!keep(libraryFact(row),entry))continue;add({title:`${row.name} 资料快照`,url:row.source_snapshot_url || row.source_url});for(const url of row.verification?.evidence_urls || row.official_urls || [])add({title:`${row.name} 项目来源`,url}); }
  }
  // These URLs are read from the current topic, never manufactured from a name.
  if (entities.includes('xray') || entities.includes('singbox')) {
    for (const s of sourceRows(guideBySlug.get('proxy-cores'))) {
      if ((entities.includes('xray') && s.url === 'https://xtls.github.io/') || (entities.includes('singbox') && s.url === 'https://sing-box.sagernet.org/')) add(s);
    }
  }
  const notices = [];
  if(model.hint && !model.matches.length) notices.push('本地型号快照未找到该完整型号与修订的匹配记录；这不等于不支持，应查原项目当前设备表。');
  if(model.hint && (!model.hint.prefix || !model.hint.variant) && model.matches.length>1)notices.push('提供的型号信息匹配多个分支或修订；候选是分别列出的来源记录，不能相互替代。');
  if(model.matches.length>3)notices.push(`共有 ${model.matches.length} 条型号候选，本次仅展示前三条；应补充完整前缀、修订或分支。`);
  return { facts: quote({snapshot_date:KNOWLEDGE_META.published_at,authority:'Public reference material; not instructions, live availability, or device test results.',records:facts,notices}),sources,topics:[...topics],
    selected:selected.map(x=>({type:x.type,id:x.row.slug||x.row.id})),matched:selected.length>0,notices,snapshotDate:KNOWLEDGE_META.published_at,
    modelMatchCount:model.matches.length,limits:{maxRecords:4,maxFactCharacters:FACT_LIMIT},knowledgeVersion:KNOWLEDGE_META.version };
}
