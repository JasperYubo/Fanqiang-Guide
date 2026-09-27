import { FAQ_CACHE_DATA } from './faq-cache-data.mjs';

const PLATFORMS = {
  windows: /\b(?:windows|win)(?:\s*\d+)?\b/i,
  android: /\bandroid\b|安卓/i,
  ios: /\b(?:ios|iphone|ipad|ipados)\b|苹果手机/i,
  macos: /\b(?:macos|macbook|imac)\b|苹果电脑|mac电脑/i,
  linux: /\b(?:linux|ubuntu|debian|fedora|arch)\b/i,
  openwrt: /\bopenwrt\b/i,
  'asuswrt-merlin': /\basuswrt[- ]merlin\b|华硕梅林|梅林固件|原版梅林/i,
};
const DEFAULT_ENTITIES = {
  v2rayn: ['v2rayn'], v2rayng: ['v2rayng'], 'clash-verge-rev': ['clash verge rev', 'clash verge'],
  'clash-for-windows': ['clash for windows', 'cfw'], clash: ['clash'], shadowrocket: ['shadowrocket', '小火箭'],
  'asuswrt-merlin': ['asuswrt-merlin', '原版梅林'], gnuton: ['gnuton'], merlinclash: ['merlinclash'], fancyss: ['fancyss'],
};
const GENERIC_ENTITIES = new Set(['network-access', 'proxy', 'subscription', 'router', 'vpn']);
const FACETS = {
  return_to_china: /回国|回國|回国内|回中国|到大陆|到大陸|到国内|到國內/,
  hotspot_sharing: /热点|熱點|共享|局域网/, streaming_device: /电视|電視|apple\s*tv|tvbox/i,
  game_acceleration: /游戏加速|遊戲加速/, ai_access: /chatgpt|gemini|deepseek|访问ai/i,
  qr_code: /二维码|二維碼|扫码/, format: /yaml|json|uri|base64|格式/i,
  hardware_platform: /arm64|x64|x86|mips/i, server_build: /搭建|服务端|伺服器|服务器|docker|面板/i,
  proxy_service: /机场|機場/, proxy_node: /节点|節點/, subscription_address: /订阅|訂閱/,
  subscription_merge: /合并|合併/, subscription_import: /导入|匯入/, subscription_export: /导出|匯出/,
  subscription_management: /管理/, subscription_parse: /解析/, sharing: /分享/,
  speed_test: /测速|測速|速度测试|速度測試|延迟测试/, ip_check: /纯净度|純淨度|固定ip|独立ip|ip检查/i,
  qr_generation: /二维码.*生成|二維碼.*生成/, qr_import: /扫码|掃碼/,
  phone_device: /手机|手機/, computer_device: /电脑|電腦/, apple_device_unknown: /苹果翻墙|蘋果翻牆|苹果梯子|蘋果梯子/,
  ipv6: /ipv6/i, bypass_router: /旁路由/, compile_source: /编译|編譯/, config_template: /配置.*(?:模板|范例|例子)|config.*template/i,
  config_generator: /配置.*生成/, firmware_flash: /刷/, firmware_branch: /固件|firmware|分支/i,
  chain_proxy: /链式代理|鏈式代理/, scripts_modules: /脚本|腳本|模块|模組/,
  target_tiktok: /tiktok/i, target_youtube: /youtube/i, target_whatsapp: /whatsapp/i, target_wechat: /微信/,
  package_ipk: /\bipk\b/i, installation: /安装|安裝|install/i, blocked_address: /被墙|被牆|被封/,
  language_translation: /中文|汉化|漢化/, blocklist_allowlist: /白名单|白名單|黑名单|黑名單/, preprocessing: /预处理|預處理/,
};
const DEVICE_FACETS = new Set(['phone_device', 'computer_device', 'apple_device_unknown']);
// An unscoped answer must not replace a different requested operation or target app.
const STRICT_FACETS = new Set(['subscription_merge', 'subscription_import', 'subscription_export', 'subscription_management', 'subscription_parse', 'sharing', 'speed_test', 'ip_check', 'qr_generation', 'qr_import', 'return_to_china', 'hotspot_sharing', 'streaming_device', 'game_acceleration', 'server_build', 'hardware_platform', 'ipv6', 'bypass_router', 'compile_source', 'config_template', 'config_generator', 'firmware_flash', 'chain_proxy', 'scripts_modules', 'target_tiktok', 'target_youtube', 'target_whatsapp', 'target_wechat', 'package_ipk', 'blocked_address', 'language_translation', 'blocklist_allowlist', 'preprocessing']);
const REALTIME = /今天|今日|现在(?:能|可|还|是否)|当前(?:可用|价格|版本)|最新版本|实时|免费节点|可用节点|节点.*(?:可用|能用)|我的(?:账号|账户|订阅地址)|私人订阅/;
const record = value => value && typeof value === 'object' && !Array.isArray(value);
const strings = value => Array.isArray(value) && value.every(item => typeof item === 'string' && item.trim());
const date = value => typeof value === 'string' && Number.isFinite(Date.parse(value));
const compact = value => normalizeFaqText(value).replace(/[\s_-]/g, '');
export const normalizeFaqText = value => typeof value === 'string' ? value.normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim().replace(/[?？。！!]+$/g, '').trim() : '';

function validURL(value) {
  if (typeof value !== 'string' || /[\u0000-\u0020\u007f]/.test(value)) return false;
  try {
    const url = new URL(value), host = url.hostname.toLowerCase();
    return url.protocol === 'https:' && !url.username && !url.password && host.includes('.') && !/^(?:localhost|\d+(?:\.\d+){3})$/.test(host) && !/\.(?:local|internal|localhost)$/.test(host);
  } catch { return false; }
}

// Compiler and runtime share the same fail-closed approval adapter.
export function adaptFaqAnswer(entry, manifest, nowMs = Date.now()) {
  if (!record(entry) || entry.review_state !== 'approved' || entry.cache_eligible !== true || entry.origin_kind !== 'google_autocomplete_editorial_faq') return { ok: false, reason: 'not_approved' };
  if (!['stable', 'source_navigation'].includes(entry.dynamic_class)) return { ok: false, reason: 'dynamic_answer' };
  if (!date(entry.checked_at_utc) || Date.parse(entry.checked_at_utc) > nowMs) return { ok: false, reason: 'invalid_check_date' };
  if (entry.expires_at_utc_or_null !== null && (!date(entry.expires_at_utc_or_null) || Date.parse(entry.expires_at_utc_or_null) <= nowMs)) return { ok: false, reason: 'expired_answer' };
  if ((entry.version_constraints?.length || entry.hardware_constraints?.length) && entry.expires_at_utc_or_null === null) return { ok: false, reason: 'expiry_required' };
  if (typeof entry.short_answer !== 'string' || !entry.short_answer.trim() || !/[\u4e00-\u9fff]/.test(entry.short_answer)) return { ok: false, reason: 'invalid_answer' };
  if (!Array.isArray(entry.answer_sections)) return { ok: false, reason: 'invalid_sections' };
  const sections = [];
  for (const section of entry.answer_sections) {
    if (typeof section === 'string' && section.trim()) sections.push(section.trim());
    else if (record(section) && typeof section.content === 'string' && section.content.trim() && (section.title === undefined || typeof section.title === 'string')) sections.push([section.title, section.content].filter(Boolean).join('：'));
    else return { ok: false, reason: 'invalid_sections' };
  }
  const answer = [entry.short_answer.trim(), ...sections].join('\n\n');
  if (answer.length > 12000 || /::ILANG|::MODULE|::RULE/.test(answer)) return { ok: false, reason: 'invalid_answer' };
  if (!strings(entry.source_ids) || !entry.source_ids.length) return { ok: false, reason: 'missing_sources' };
  const claims = Array.isArray(entry.source_claim_map) ? entry.source_claim_map.map(item => item?.source_ids) : record(entry.source_claim_map) ? Object.values(entry.source_claim_map) : [];
  if (!claims.length || claims.some(ids => !strings(ids) || !ids.length || ids.some(id => !entry.source_ids.includes(id)))) return { ok: false, reason: 'invalid_claim_sources' };
  const sources = [];
  for (const id of entry.source_ids) {
    const source = manifest.get(id);
    if (!source || source.verification_status !== 'verified' || typeof source.title !== 'string' || !source.title.trim() || !validURL(source.url) || !date(source.checked_at_utc) || Date.parse(source.checked_at_utc) > nowMs || !/^[a-f0-9]{64}$/i.test(source.content_sha256 || '')) return { ok: false, reason: 'invalid_source' };
    if (source.expires_at_utc_or_null !== undefined && source.expires_at_utc_or_null !== null && (!date(source.expires_at_utc_or_null) || Date.parse(source.expires_at_utc_or_null) <= nowMs)) return { ok: false, reason: 'expired_source' };
    if (!sources.some(item => item.url === source.url)) sources.push({ title: source.title, url: source.url });
  }
  if (sources.length > 32) return { ok: false, reason: 'too_many_sources' };
  return { ok: true, answer, sources };
}

export function validateFaqCacheData(data, nowMs = Date.now()) {
  const errors = [];
  if (!record(data) || data.schema_version !== 1 || !record(data.entity_aliases) || !Array.isArray(data.entries) || !Array.isArray(data.sources)) return { ok: false, errors: ['invalid_envelope'] };
  for (const [id, aliases] of Object.entries(data.entity_aliases)) if (!id || !strings(aliases)) errors.push('invalid_entity_aliases');
  const manifest = new Map();
  for (const source of data.sources) {
    if (!record(source) || typeof source.source_id !== 'string' || !source.source_id || manifest.has(source.source_id)) errors.push('invalid_source_id');
    else manifest.set(source.source_id, source);
  }
  const ids = new Set(), questions = new Set();
  for (const entry of data.entries) {
    if (!record(entry)) { errors.push('invalid_entry'); continue; }
    const id = entry.faq_id;
    if (typeof id !== 'string' || !id || ids.has(id) || typeof entry.question_id !== 'string' || !entry.question_id || questions.has(entry.question_id)) errors.push('duplicate_or_invalid_id');
    ids.add(id); questions.add(entry.question_id);
    if (typeof entry.canonical_question !== 'string' || !entry.canonical_question.trim() || typeof entry.intent !== 'string' || !entry.intent.trim() || !strings(entry.aliases) || !strings(entry.entities) || !strings(entry.platforms) || entry.platforms.some(p => !Object.hasOwn(PLATFORMS, p))) errors.push(`${id}:invalid_match_fields`);
    if (!Array.isArray(entry.version_constraints) || entry.version_constraints.some(c => !record(c) || typeof c.entity !== 'string' || !strings(c.versions) || !c.versions.length)) errors.push(`${id}:invalid_version_constraints`);
    if (!Array.isArray(entry.hardware_constraints) || entry.hardware_constraints.some(c => !record(c) || typeof c.model !== 'string' || !c.model || (c.revision !== undefined && (typeof c.revision !== 'string' || !c.revision)))) errors.push(`${id}:invalid_hardware_constraints`);
    if (!strings(entry.required_slots) || entry.required_slots.some(slot => !/^(?:platform|entity|hardware:model|hardware:revision|version:[a-z0-9_-]+)$/.test(slot)) || !strings(entry.forbidden_mismatch)) errors.push(`${id}:invalid_slots`);
    if (entry.facets !== undefined && (!strings(entry.facets) || entry.facets.some(facet => !Object.hasOwn(FACETS, facet)))) errors.push(`${id}:invalid_facets`);
    const adapted = adaptFaqAnswer(entry, manifest, nowMs);
    if (!adapted.ok) errors.push(`${id}:${adapted.reason}`);
  }
  return { ok: errors.length === 0, errors };
}

function entityPatterns(dictionary) {
  const patterns = [];
  const escape = char => char.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  for (const [id, aliases] of Object.entries(dictionary)) for (const alias of aliases) {
    const needle = normalizeFaqText(alias);
    if (!needle) continue;
    let expression = [...needle].map((char, at, chars) => /[\s_-]/.test(char) ? '[\\s_-]*' : escape(char) + (/[\u4e00-\u9fff]/.test(char) && /[\u4e00-\u9fff]/.test(chars[at + 1] || '') ? '[\\s_-]*' : '')).join('');
    if (/^[a-z0-9]/.test(needle)) expression = '(?<![a-z0-9])' + expression;
    if (/[a-z0-9]$/.test(needle)) expression += '(?![a-z0-9])';
    patterns.push({ id, length: needle.length, specific: !GENERIC_ENTITIES.has(id), expression: new RegExp(expression, 'ig') });
  }
  return patterns.sort((a, b) => Number(b.specific) - Number(a.specific) || b.length - a.length);
}
function entitiesIn(text, patterns) {
  const found = [], spans = [];
  for (const pattern of patterns) {
    pattern.expression.lastIndex = 0;
    for (const match of text.matchAll(pattern.expression)) {
      const start = match.index, end = start + match[0].length;
      if (spans.some(([a, b]) => start < b && end > a)) continue;
      found.push(pattern.id); spans.push([start, end]);
    }
  }
  const specific = found.filter(id => !GENERIC_ENTITIES.has(id));
  return [...new Set(specific.length ? specific : found)];
}
function reviewedAliasKey(value, patterns) {
  const text = normalizeFaqText(value), spans = [], found = [];
  const rawFacets = Object.entries(FACETS).filter(([, expression]) => expression.test(compact(text))).map(([facet]) => facet);
  for (const pattern of patterns) {
    pattern.expression.lastIndex = 0;
    for (const match of text.matchAll(pattern.expression)) {
      const start = match.index, end = start + match[0].length;
      if (spans.some(([a, b]) => start < b && end > a)) continue;
      spans.push([start, end]); found.push({ start, end, id: pattern.id });
    }
  }
  // Generic domain words also carry question scope (for example 节点 versus
  // 节点二维码). They are not interchangeable product names.
  const replacements = found.filter(item => !GENERIC_ENTITIES.has(item.id)).sort((a, b) => b.start - a.start);
  let key = text;
  for (const item of replacements) key = key.slice(0, item.start) + `{{${item.id}}}` + key.slice(item.end);
  // A product alias may contain a scope word (梅林固件, for example).
  // Substitution must preserve that original question scope in the index key.
  return JSON.stringify([key.replace(/\s+/g, ''), rawFacets]);
}
const platformsIn = text => {
  const subject = text.replace(/clash\s*for\s*windows|clashforwindows|sing[\s-]*box[\s-]*windows/ig, '');
  return Object.entries(PLATFORMS).filter(([, expression]) => expression.test(subject)).map(([id]) => id);
};
function osVersions(text) {
  const found = new Map();
  for (const [id, pattern] of Object.entries({ windows: /(?<![a-z0-9])(?:windows|win)\s*(\d+(?:\.\d+)?)/ig, android: /(?<![a-z0-9])(?:android|安卓)\s*(\d+(?:\.\d+)?)/ig, ios: /(?<![a-z0-9])(?:ios|ipados)\s*(\d+(?:\.\d+)?)/ig, macos: /(?<![a-z0-9])macos\s*(\d+(?:\.\d+)?)/ig })) {
    const values = [...new Set([...text.matchAll(pattern)].map(match => match[1]))];
    if (values.length) found.set(id, values);
  }
  return found;
}
function versionIn(text, aliases) {
  const values = [];
  for (const alias of aliases) {
    const escaped = alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    for (const match of text.matchAll(new RegExp(`${escaped}\\s*(?:版本\\s*[:：]?\\s*|v\\s*)?(\\d+(?:\\.\\d+){1,3})(?![\\d.])`, 'ig'))) values.push(match[1]);
  }
  return [...new Set(values)];
}

function applicableOriginal(flow) {
  const need = normalizeFaqText(flow.need), original = normalizeFaqText(flow.originalRequest), device = normalizeFaqText(flow.device);
  if (!need || !original) return '';
  if (original.includes(need)) return original;
  // Intake refines a generic device word inside the saved need. Recover that
  // approved alias only for the same category; an actual changed goal stays new.
  if (!device || !need.includes(device)) return '';
  const kind = /手机|手機|android|安卓|iphone|ipad|ios|鸿蒙|harmonyos/i.test(device) ? '手机'
    : /电脑|電腦|windows|macos|macbook|linux|ubuntu|debian/i.test(device) ? '电脑'
    : /路由器|\b(?:rt|dsl|gt|tuf|gl)[\s_-]*(?:ax|ac|be|mt)[0-9]/i.test(device) ? '路由器' : '';
  return kind && original.includes(need.replaceAll(device, kind)) ? original : '';
}

function conditions(entry, flow, dictionary, patterns) {
  const need = normalizeFaqText(flow.need), details = (flow.details || []).filter(t => typeof t === 'string' && compact(t) !== compact(flow.device)).join('\n');
  const current = normalizeFaqText([flow.device, flow.need, details].join('\n'));
  const entities = entitiesIn(normalizeFaqText([flow.need, details].join('\n')), patterns);
  if (!entities.length) entities.push(...entitiesIn(normalizeFaqText(flow.originalRequest), patterns));
  const platforms = platformsIn(normalizeFaqText(flow.device));
  const original = applicableOriginal(flow);
  const scopedNeed = original && !original.includes(need) ? original : need;
  const contextText = normalizeFaqText([scopedNeed, details, original].join('\n'));
  const explicitPlatforms = platformsIn(contextText).filter(p => !(p === 'openwrt' && entities.includes('openwrt')) && !(p === 'asuswrt-merlin' && entities.some(id => id === 'asuswrt-merlin' || id === 'asuswrt-merlin-gnuton' || id === 'gnuton')));
  if (explicitPlatforms.some(p => platforms.length && !platforms.includes(p))) return 'platform_conflict';
  if (entry.entities.length && entities.some(id => !entry.entities.includes(id))) return 'entity_mismatch';
  if (entry.entities.length && entry.entities.some(id => !entities.includes(id))) return 'missing_entity';
  if (entry.platforms.length && (!platforms.length || platforms.some(p => !entry.platforms.includes(p)))) return 'platform_mismatch';
  if (explicitPlatforms.length && (explicitPlatforms.length !== entry.platforms.length || explicitPlatforms.some(p => !entry.platforms.includes(p)))) return 'platform_scope_mismatch';
  const needVersions = osVersions(scopedNeed), requestVersions = needVersions.size ? needVersions : osVersions(contextText), deviceVersions = osVersions(normalizeFaqText(flow.device));
  for (const [platform, versions] of requestVersions) if (deviceVersions.has(platform) && versions.some(version => !deviceVersions.get(platform).includes(version))) return 'platform_version_conflict';
  if (entry.forbidden_mismatch.some(value => current.includes(normalizeFaqText(value)))) return 'forbidden_mismatch';
  const requestText = compact(contextText);
  const facets = entry.facets || [];
  const observed = Object.entries(FACETS).filter(([, expression]) => expression.test(requestText)).map(([facet]) => facet);
  // An exact approved canonical question carries its explicit scope even when
  // its human-readable facet labels differ from the raw suggestion vocabulary.
  if (need === normalizeFaqText(entry.canonical_question) || original === normalizeFaqText(entry.canonical_question)) observed.push(...facets);
  const device = normalizeFaqText(flow.device);
  for (const facet of facets) {
    if (facet === 'phone_device') { if (!/手机|手機|android|安卓|iphone|ipad|ios|鸿蒙|harmonyos/i.test(device)) return 'device_facet_mismatch'; }
    else if (facet === 'computer_device') { if (!/电脑|電腦|windows|macos|macbook|linux|ubuntu|debian/i.test(device)) return 'device_facet_mismatch'; }
    else if (facet === 'apple_device_unknown') { if (!/苹果|蘋果|iphone|ipad|ios|macos|macbook/i.test(device)) return 'device_facet_mismatch'; }
    else if (!observed.includes(facet)) return 'missing_facet';
  }
  if (observed.some(facet => !DEVICE_FACETS.has(facet) && STRICT_FACETS.has(facet) && !facets.includes(facet))) return 'facet_mismatch';
  if (entry.intent === 'troubleshooting' && entry.error_family) {
    const errorText = [flow.need, details].join('\n');
    const family = /导入|匯入|profile|订阅|訂閱/i.test(errorText) ? 'import' : /\bdns\b|域名|解析/i.test(errorText) ? 'dns' : /\btun\b|虚拟网卡/i.test(errorText) ? 'tun' : /启动|啟動|闪退|閃退/.test(errorText) ? 'launch' : /慢|延迟|延遲|掉线|斷線|断线/.test(errorText) ? 'slow' : 'connection';
    if (family !== entry.error_family) return 'error_family_mismatch';
  }
  const versions = new Map();
  for (const id of new Set([...entry.entities, ...entry.version_constraints.map(c => c.entity)])) versions.set(id, versionIn(current, dictionary[id] || [id]));
  for (const constraint of entry.version_constraints) {
    const values = versions.get(constraint.entity) || [];
    if (!values.length) return 'missing_version';
    if (values.some(value => !constraint.versions.includes(value))) return 'version_mismatch';
  }
  const hardware = [...current.matchAll(/\b(?:rt|dsl|gt|tuf|gl)[\s_-]*(?:ax|ac|be|mt)[0-9]{2,5}[a-z0-9]*(?:[\s_-]*(?:v[0-9]+|pro))?\b/gi)].map(match => match[0]);
  const revisions = [...new Set([...current.matchAll(/\b(v[0-9]+|pro)\b/gi)].map(match => match[1].toLowerCase()))];
  for (const constraint of entry.hardware_constraints) {
    const matches = hardware.filter(value => compact(value.replace(/(?:[\s_-]*v\d+|[\s_-]*pro)$/i, '')) === compact(constraint.model));
    if (!matches.length || hardware.some(value => !matches.includes(value))) return 'hardware_mismatch';
    if (constraint.revision && (!revisions.length || revisions.some(value => value !== normalizeFaqText(constraint.revision)))) return 'hardware_revision_mismatch';
  }
  for (const slot of entry.required_slots) {
    if (slot === 'platform' && !platforms.length) return 'missing_platform';
    if (slot === 'entity' && !entities.length) return 'missing_entity';
    if (slot === 'hardware:model' && !hardware.length) return 'missing_hardware';
    if (slot === 'hardware:revision' && !revisions.length) return 'missing_hardware_revision';
    if (slot.startsWith('version:') && !(versions.get(slot.slice(8)) || []).length) return 'missing_version';
  }
  return null;
}

export function createFaqCache(data) {
  const usable = record(data) && data.schema_version === 1 && Array.isArray(data.entries) && Array.isArray(data.sources);
  const entries = usable ? data.entries.filter(record) : [];
  const manifest = new Map((usable ? data.sources.filter(record) : []).map(source => [source.source_id, source]));
  const aliases = usable && record(data.entity_aliases) ? Object.fromEntries(Object.entries(data.entity_aliases).filter(([, values]) => strings(values))) : {};
  // Reviewed dictionary insertion order resolves equal-length alias collisions
  // exactly as the preparation pass; fallback aliases must not win that tie.
  const dictionary = { ...aliases, ...Object.fromEntries(Object.entries(DEFAULT_ENTITIES).filter(([id]) => !Object.hasOwn(aliases, id))) };
  const patterns = entityPatterns(dictionary);
  const index = new Map(), reviewedIndex = new Map();
  for (const entry of entries) for (const alias of [entry.canonical_question, ...(Array.isArray(entry.aliases) ? entry.aliases : [])]) {
    const key = normalizeFaqText(alias);
    if (!key) continue;
    if (!index.has(key)) index.set(key, new Set());
    index.get(key).add(entry);
    const reviewedKey = reviewedAliasKey(alias, patterns);
    if (!reviewedIndex.has(reviewedKey)) reviewedIndex.set(reviewedKey, new Set());
    reviewedIndex.get(reviewedKey).add(entry);
  }
  return function lookup(flow, nowMs = Date.now()) {
    if (!usable || !record(flow) || typeof flow.need !== 'string') return { status: 'miss', reason: 'invalid_input' };
    const current = normalizeFaqText(flow.need), original = applicableOriginal(flow);
    if (REALTIME.test([flow.need, ...(flow.details || [])].join('\n'))) return { status: 'reject', reason: 'realtime_request' };
    const exact = [...new Set([...(index.get(current) || []), ...(index.get(original) || [])])];
    // Only reviewed wording can hit. Whitespace and official entity aliases may
    // vary; no open entity+intent inference may discard an extra goal or app.
    const candidates = exact.length ? exact : [...new Set([...(reviewedIndex.get(reviewedAliasKey(current, patterns)) || []), ...(original ? reviewedIndex.get(reviewedAliasKey(original, patterns)) || [] : [])])];
    if (!candidates.length) return { status: 'miss', reason: 'no_candidate' };
    const hits = [], rejected = [];
    for (const entry of candidates) {
      const schema = validateFaqCacheData({ schema_version: 1, entity_aliases: dictionary, entries: [entry], sources: data.sources }, nowMs);
      if (!schema.ok) { rejected.push({ faqId: entry.faq_id, reason: schema.errors[0].split(':').at(-1) }); continue; }
      const reason = conditions(entry, flow, dictionary, patterns);
      if (reason) { rejected.push({ faqId: entry.faq_id, reason }); continue; }
      const answer = adaptFaqAnswer(entry, manifest, nowMs);
      hits.push({ status: 'hit', faqId: entry.faq_id, match: exact.length ? 'exact' : 'reviewed_alias', answer: answer.answer, sources: answer.sources });
    }
    if (hits.length === 1) return hits[0];
    if (hits.length > 1) return { status: 'reject', reason: 'ambiguous_candidates' };
    return { status: 'reject', reason: rejected[0]?.reason || 'invalid_candidate', ...(rejected.length === 1 ? { faqId: rejected[0].faqId } : {}) };
  };
}

export const lookupFaqCache = createFaqCache(FAQ_CACHE_DATA);
