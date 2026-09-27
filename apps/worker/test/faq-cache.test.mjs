import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { createFaqCache, validateFaqCacheData, normalizeFaqText } from '../src/faq-cache.mjs';
import { createIntake, advanceIntake } from '../src/intake.mjs';
import { fixture, flow } from './faq-cache-fixture.mjs';
const stamp = Date.parse('2026-09-27T00:00:00Z');
const lookup = (entry = {}, input = {}) => createFaqCache(fixture(entry))(flow(input), stamp);

test('reviewed exact aliases normalize only case, width, whitespace and trailing punctuation', () => {
  assert.equal(normalizeFaqText(' Ｖ２ＲＡＹＮ下载？ '), 'v2rayn下载');
  assert.equal(lookup({}, { need: '下载 V2RAYN？' }).status, 'hit');
  assert.deepEqual(lookup().sources, [{ title: '测试发行页', url: 'https://example.com/release' }]);
  assert.match(lookup().answer, /适用范围/);
  assert.equal(lookup({}, { need: 'v2rayN有风险吗', originalRequest: 'v2rayN有风险吗' }).status, 'miss');
});

test('intake-extracted short needs preserve original exact question without hijacking changed intent', () => {
  assert.equal(lookup({}, { originalRequest: 'v2rayN下载', need: '下载' }).status, 'hit');
  assert.equal(lookup({}, { need: '支持安卓吗' }).status, 'miss');
});

test('generic device refinement retains the approved alias only for the same category and unchanged goal', () => {
  const data = fixture({ canonical_question: '手机怎么用v2rayNG', aliases: [], entities: ['v2rayng'], platforms: [], intent: 'how_to_use', facets: ['phone_device'] });
  const cache = createFaqCache(data);
  const input = { originalRequest: '手机怎么用v2rayNG', need: 'Android 14 手机怎么用v2rayNG', device: 'Android 14 手机' };
  assert.equal(cache(flow(input), stamp).status, 'hit');
  assert.notEqual(cache(flow({ ...input, need: 'Windows 11 电脑怎么用v2rayNG', device: 'Windows 11 电脑' }), stamp).status, 'hit');
  assert.notEqual(cache(flow({ ...input, need: 'Android 14 手机怎么用v2rayNG访问YouTube' }), stamp).status, 'hit');
  const router = fixture({ canonical_question: 'nekobox 怎么选路由器', aliases: [], entities: ['nekobox'], platforms: [], required_slots: ['entity'], intent: 'client_selection' });
  router.entity_aliases.nekobox = ['NekoBox'];
  assert.equal(createFaqCache(router)(flow({ originalRequest: 'nekobox 怎么选路由器', need: '选RT-AX86U V2', device: 'RT-AX86U V2' }), stamp).status, 'hit');
});

test('distinct entities and platforms never share answers; negative compatibility questions can match their asked platform', () => {
  assert.equal(lookup({}, { need: '下载 v2rayNG', originalRequest: '下载 v2rayNG' }).status, 'miss');
  assert.equal(lookup({}, { device: 'Android 14 手机' }).reason, 'platform_mismatch');
  assert.notEqual(lookup({}, { need: '下载 v2rayN 安卓', device: 'Windows 11' }).status, 'hit');
  const result = lookup({ canonical_question: 'Shadowrocket有Windows版吗', aliases: [], entities: ['shadowrocket'], intent: 'compatibility' }, { originalRequest: 'Shadowrocket有Windows版吗', need: 'Shadowrocket有Windows版吗', device: 'Windows 11' });
  assert.equal(result.status, 'hit');
});

test('unreviewed, expired, malformed or unverified answers fail closed', () => {
  for (const changes of [{ review_state: 'unreviewed' }, { cache_eligible: false }, { short_answer: '' }, { expires_at_utc_or_null: '2026-09-26T00:00:00Z' }, { dynamic_class: 'live_value' }, { source_ids: ['missing'] }, { source_claim_map: { short_answer: ['missing'] } }, { answer_sections: [{ text: 'unsupported' }] }]) assert.equal(lookup(changes).status, 'reject');
  const data = fixture(); data.sources[0].verification_status = 'reference_only';
  assert.equal(createFaqCache(data)(flow(), stamp).reason, 'invalid_source');
  data.sources[0].verification_status = 'verified'; data.sources[0].url = 'http://example.com/release';
  assert.equal(validateFaqCacheData(data, stamp).ok, false);
  data.sources[0].url = 'https://example.com/release'; data.sources[0].expires_at_utc_or_null = '2026-09-20T00:00:00Z';
  assert.equal(createFaqCache(data)(flow(), stamp).reason, 'expired_source');
});

test('version constraints and required version slots reject absent or changed values', () => {
  const entry = { version_constraints: [{ entity: 'v2rayn', versions: ['7.19'] }], required_slots: ['version:v2rayn'], expires_at_utc_or_null: '2026-10-01T00:00:00Z' };
  assert.equal(lookup(entry).reason, 'missing_version');
  assert.equal(lookup(entry, { details: ['v2rayN 7.19'] }).status, 'hit');
  assert.equal(lookup(entry, { details: ['v2rayN 7.20'] }).reason, 'version_mismatch');
  assert.equal(lookup(entry, { details: ['v2rayN 7.19', 'v2rayN 7.20'] }).reason, 'version_mismatch');
});

test('explicit operating system versions conflict only when the request and current device both name a version', () => {
  const windows = fixture({ canonical_question: 'v2rayN支持Win7吗', aliases: ['v2rayN支持Windows 11吗'], intent: 'compatibility' });
  const cache = createFaqCache(windows);
  const input = { need: 'v2rayN支持Win7吗', originalRequest: 'v2rayN支持Win7吗' };
  assert.equal(cache(flow(input), stamp).reason, 'platform_version_conflict');
  assert.equal(cache(flow({ ...input, device: 'Windows 7 电脑' }), stamp).status, 'hit');
  assert.equal(cache(flow({ ...input, device: 'Windows 电脑' }), stamp).status, 'hit');
  assert.equal(lookup({}, { device: 'Windows 7 电脑' }).status, 'hit');
  const android = fixture({ canonical_question: 'v2rayNG支持Android14吗', aliases: [], entities: ['v2rayng'], platforms: ['android'], intent: 'compatibility' });
  const androidInput = { need: 'v2rayNG支持Android14吗', originalRequest: 'v2rayNG支持Android14吗', device: 'Android 12 手机' };
  assert.equal(createFaqCache(android)(flow(androidInput), stamp).reason, 'platform_version_conflict');
  assert.equal(createFaqCache(android)(flow({ ...androidInput, device: 'Android 14 手机' }), stamp).status, 'hit');
});

test('router models, hardware revisions and firmware branches are checked separately', () => {
  const entry = { canonical_question: '原版梅林兼容吗', aliases: [], entities: ['asuswrt-merlin'], platforms: [], required_slots: ['hardware:model', 'hardware:revision'], hardware_constraints: [{ model: 'RT-AX86U', revision: 'V2' }], expires_at_utc_or_null: '2026-10-01T00:00:00Z' };
  const input = { originalRequest: '原版梅林兼容吗', need: '原版梅林兼容吗', device: 'RT-AX86U V2' };
  assert.equal(lookup(entry, input).status, 'hit');
  assert.equal(lookup(entry, { ...input, device: 'RT-AX86U V1' }).reason, 'hardware_revision_mismatch');
  assert.equal(lookup(entry, { ...input, device: 'RT-AX86U' }).status, 'reject');
  assert.equal(lookup(entry, { ...input, device: 'RT-AX88U V2' }).reason, 'hardware_mismatch');
  assert.equal(lookup(entry, { ...input, details: ['GNUton固件'] }).reason, 'entity_mismatch');
  assert.equal(lookup(entry, { ...input, need: 'GNUton兼容吗', originalRequest: 'GNUton兼容吗' }).status, 'miss');
});

test('real-time, private subscription and ambiguous matches never become cache hits', () => {
  for (const need of ['今天下载 v2rayN 最新版本', '我的订阅地址能用吗', '免费节点今天可用吗']) assert.equal(lookup({}, { need }).reason, 'realtime_request');
  const data = fixture(); data.entries.push({ ...data.entries[0], faq_id: 'other', question_id: 'other-q' });
  assert.equal(createFaqCache(data)(flow(), stamp).reason, 'ambiguous_candidates');
  assert.equal(lookup({ required_slots: ['version:v2rayn'] }).reason, 'missing_version');
});

test('specific entities suppress generic subscription terms under the same frozen preparation rules', () => {
  const data = fixture({ canonical_question: 'v2rayN怎么导入订阅', aliases: ['v2rayN 导入 订阅'], intent: 'how_to_use', facets: ['subscription_import', 'subscription_address'] });
  data.entity_aliases.subscription = ['订阅', '节点二维码', '机场'];
  const cache = createFaqCache(data);
  assert.equal(cache(flow({ need: '导入订阅', originalRequest: 'v2rayN怎么导入订阅', details: ['v2rayN怎么导入订阅'] }), stamp).status, 'hit');
  assert.equal(cache(flow({ need: 'v2rayN 导入 订阅' }), stamp).status, 'hit');
  assert.equal(cache(flow({ need: 'v2rayNG 导入 订阅', originalRequest: 'v2rayNG 导入 订阅' }), stamp).status, 'miss');
});

test('actual intake combination matrix rejects changed entities, device classes, operations and target apps', () => {
  const data = fixture({ canonical_question: 'v2rayN怎么导入订阅', aliases: [], intent: 'how_to_use', facets: ['subscription_import', 'subscription_address'] });
  data.entity_aliases.subscription = ['订阅'];
  const cache = createFaqCache(data);
  const matrix = [
    ['v2rayN怎么导入订阅', 'Windows 11 电脑', true],
    ['v2rayNG怎么导入订阅', 'Windows 11 电脑', false],
    ['v2rayN怎么导入订阅', 'Android 14 手机', false],
    ['v2rayN怎么导入并合并订阅', 'Windows 11 电脑', false],
    ['v2rayN怎么导入订阅并访问YouTube', 'Windows 11 电脑', false],
    ['v2rayNG怎么导入并合并订阅访问YouTube', 'Android 14 手机', false],
  ];
  for (const [question, device, expectedHit] of matrix) {
    let step = advanceIntake(createIntake(), question);
    assert.equal(step.state.stage, 'awaiting_ai');
    step = advanceIntake(step.state, 'DeepSeek 可以正常使用');
    step = advanceIntake(step.state, device);
    assert.equal(step.generate, true, question);
    assert.equal(cache(step.state, stamp).status === 'hit', expectedHit, `${question}; ${device}`);
  }
});

test('facet scope gates reviewed aliases without restricting general answers to a device kind', () => {
  assert.equal(lookup({}, { device: 'Windows 11 电脑' }).status, 'hit');
  assert.equal(lookup({}, { need: '下载 v2rayN', details: ['想导入订阅'] }).reason, 'facet_mismatch');
  assert.notEqual(lookup({ platforms: [] }, { need: '下载 v2rayN 访问YouTube' }).status, 'hit');
  assert.equal(lookup({ facets: ['subscription_merge'] }).reason, 'missing_facet');
  assert.equal(lookup({ facets: ['phone_device'] }).reason, 'device_facet_mismatch');
  assert.equal(lookup({ facets: ['computer_device'] }).status, 'hit');
  assert.equal(lookup({ facets: ['unregistered_scope'] }).status, 'reject');
});

test('platform words in an exact product name do not override the visitor platform', () => {
  const data = fixture({ canonical_question: 'Clash for Windows支持Android吗', aliases: [], entities: ['clash-for-windows'], platforms: ['android'], intent: 'compatibility' });
  const result = createFaqCache(data)(flow({ need: 'Clash for Windows支持Android吗', originalRequest: 'Clash for Windows支持Android吗', device: 'Android 14 手机' }), stamp);
  assert.equal(result.status, 'hit');
});

test('reviewed multi-word aliases allow separators without merging longer named projects into shorter cores', () => {
  const data = fixture({ canonical_question: 'OpenClash怎么下载', aliases: ['open clash 下载'], entities: ['openclash'], platforms: [], required_slots: ['entity'] });
  data.entity_aliases.openclash = ['OpenClash', 'open clash']; data.entity_aliases.clash = ['Clash'];
  assert.equal(createFaqCache(data)(flow({ need: 'open clash 下载', originalRequest: 'open clash 下载', device: 'RT-AX86U V2' }), stamp).status, 'hit');
  const corrected = fixture({ canonical_question: 'sing-box for android下载', aliases: ['SFA下载'], entities: ['box-for-android'], platforms: [], required_slots: ['entity'] });
  corrected.entity_aliases['box-for-android'] = ['Box for Root']; corrected.entity_aliases['sing-box'] = ['sing-box', 'SFA'];
  for (const need of ['sing-box for android下载', 'SFA下载']) assert.equal(createFaqCache(corrected)(flow({ need, originalRequest: need, device: 'Android 14 手机' }), stamp).reason, 'entity_mismatch');
});

test('unreviewed phrasing cannot borrow a same-entity answer through intent inference', () => {
  const data = fixture({ canonical_question: 'v2rayN是什么', aliases: [], entities: ['v2rayn'], platforms: [], intent: 'definition' });
  assert.equal(createFaqCache(data)(flow({ need: 'v2rayN无法连接 是什么意思', originalRequest: 'v2rayN无法连接 是什么意思' }), stamp).status, 'miss');
  assert.equal(createFaqCache(data)(flow({ need: 'v2rayN是什么', originalRequest: 'v2rayN是什么' }), stamp).status, 'hit');
});

test('reviewed alias keys allow only whitespace and official entity aliases without dropping additional meaning', () => {
  const data = fixture({ canonical_question: 'Shadowrocket 是什么', aliases: [], entities: ['shadowrocket'], platforms: [], intent: 'definition', required_slots: ['entity'] });
  data.entity_aliases.shadowrocket = ['Shadowrocket', '小火箭'];
  const cache = createFaqCache(data);
  for (const need of ['Shadowrocket是什么', '小火箭是什么', '小 火 箭 是 什 么']) assert.equal(cache(flow({ need, originalRequest: need }), stamp).status, 'hit', need);
  for (const need of ['小火箭是什么玄幻小说', '小火箭是什么并关闭防火墙', '小火箭是什么如何访问Claude', '小火箭是什么如何访问Netflix', '小火箭是什么访问未知App']) assert.notEqual(cache(flow({ need, originalRequest: need }), stamp).status, 'hit', need);
  const how = createFaqCache(fixture({ canonical_question: 'v2rayN怎么用', aliases: [], platforms: [], intent: 'how_to_use', required_slots: ['entity'] }));
  for (const need of ['v2rayN怎么用访问Claude', 'v2rayN怎么用访问Netflix', 'v2rayN怎么用访问未知应用', 'v2rayN怎么用重写系统注册表']) assert.notEqual(how(flow({ need, originalRequest: need }), stamp).status, 'hit', need);
  const nodes = fixture({ canonical_question: '节点是什么意思', aliases: [], entities: ['subscription'], platforms: [], intent: 'definition', required_slots: ['entity'], facets: ['proxy_node'] });
  nodes.entity_aliases.subscription = ['节点', '节点二维码', '订阅'];
  const nodeCache = createFaqCache(nodes);
  assert.equal(nodeCache(flow({ need: '节点 是 什么 意思', originalRequest: '节点 是 什么 意思' }), stamp).status, 'hit');
  assert.notEqual(nodeCache(flow({ need: '节点二维码 是什么意思', originalRequest: '节点二维码 是什么意思' }), stamp).status, 'hit');
});

test('official product aliases cannot erase firmware facets from rejected or unreviewed questions', () => {
  for (const [approved, unreviewed, intent] of [['华硕梅林 教程 2024', '梅林固件 教程 2024', 'how_to_use'], ['asuswrt merlin 官网', '梅林固件官网', 'official_source']]) {
    const data = fixture({ canonical_question: approved, aliases: [], entities: ['asuswrt-merlin'], platforms: [], required_slots: ['entity'], intent, facets: [] });
    data.entity_aliases['asuswrt-merlin'] = ['Asuswrt-Merlin', 'asuswrt merlin', '华硕梅林', '梅林固件', '梅林'];
    const cache = createFaqCache(data);
    assert.equal(cache(flow({ need: approved, originalRequest: approved }), stamp).status, 'hit');
    assert.notEqual(cache(flow({ need: unreviewed, originalRequest: unreviewed }), stamp).status, 'hit', unreviewed);
  }
});

test('compiler validates independently, writes atomically and cannot replace a good artifact with rejected data', () => {
  const dir = mkdtempSync(join(tmpdir(), 'fg-faq-compile-'));
  try {
    const input = join(dir, 'fixture.json'), output = join(dir, 'faq-cache-data.mjs');
    writeFileSync(input, JSON.stringify(fixture()));
    const compile = () => spawnSync(process.execPath, [new URL('../scripts/build_faq_cache.mjs', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'), '--input', input, '--output', output], { encoding: 'utf8' });
    const first = compile(); assert.equal(first.status, 0, first.stderr);
    const before = readFileSync(output, 'utf8'); assert.match(before, /SHA256: [a-f0-9]{64}/);
    writeFileSync(input, JSON.stringify(fixture({ review_state: 'unreviewed' })));
    assert.equal(compile().status, 1); assert.equal(readFileSync(output, 'utf8'), before);
  } finally { rmSync(dir, { recursive: true }); }
});
