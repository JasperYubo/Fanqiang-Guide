// Read-only matching audit. It never calls a model or writes visitor/session data.
import { readFileSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { createFaqCache, validateFaqCacheData } from '../src/faq-cache.mjs';
import { createIntake, advanceIntake } from '../src/intake.mjs';

const args = process.argv.slice(2);
function path(name) {
  const at = args.indexOf(name);
  if (at < 0 || !args[at + 1] || args[at + 1].startsWith('--')) throw new Error(`${name} is required`);
  return resolve(args[at + 1]);
}
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
function fallbackDevice(question, currentDevice) {
  const platforms = question.platforms || [], facets = question.facets || [];
  if (currentDevice === '路由器' || question.entities?.includes('router') || /^路由器/.test(question.canonical_question || '')) return 'RT-AX86U V2';
  if (platforms.includes('android')) return 'Android 14 手机';
  if (platforms.includes('ios')) return 'iPhone 16';
  if (platforms.includes('macos')) return 'macOS 15 电脑';
  if (platforms.includes('linux')) return 'Linux 电脑';
  if (platforms.includes('windows')) return 'Windows 11 电脑';
  if (facets.includes('apple_device_unknown')) return 'iPhone 16';
  if (facets.includes('phone_device')) return 'Android 14 手机';
  return 'Windows 11 电脑';
}
function visitorFlow(alias, question) {
  let step = advanceIntake(createIntake(), alias);
  step = advanceIntake(step.state, 'DeepSeek 可以正常使用');
  if (!step.generate) step = advanceIntake(step.state, fallbackDevice(question, step.state.device));
  return step;
}
try {
  const cacheBytes = readFileSync(path('--cache')), questionBytes = readFileSync(path('--questions'));
  const data = JSON.parse(cacheBytes.toString('utf8').replace(/^\uFEFF/, ''));
  const valid = validateFaqCacheData(data);
  if (!valid.ok) throw new Error(`Invalid reviewed cache: ${valid.errors.join(', ')}`);
  const questions = questionBytes.toString('utf8').replace(/^\uFEFF/, '').split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line));
  const approved = new Map(data.entries.map(entry => [entry.question_id, entry]));
  const byFaqId = new Map(data.entries.map(entry => [entry.faq_id, entry]));
  const lookup = createFaqCache(data), cases = [], counts = {};
  const eligible = questions.filter(question => question.eligibility === 'ready');
  for (const question of eligible) for (const alias of question.aliases) {
    const step = visitorFlow(alias, question);
    const result = step.generate ? lookup(step.state) : { status: 'miss', reason: 'intake_not_ready' };
    const available = approved.has(question.question_id);
    const returnedQuestion = result.status === 'hit' ? byFaqId.get(result.faqId)?.question_id : null;
    const classification = result.status === 'hit' ? returnedQuestion === question.question_id ? 'correct_hit' : 'wrong_question_hit' : available ? `available_${result.status}` : 'no_approved_entry';
    counts[classification] = (counts[classification] || 0) + 1;
    cases.push({ question_id: question.question_id, alias, approved_entry_available: available, classification, cache_status: result.status, reason: result.reason || null, returned_question_id: returnedQuestion, intake_need: step.state.need, intake_device: step.state.device, facets: question.facets || [] });
  }
  const reasons = {};
  for (const item of cases.filter(item => item.approved_entry_available && item.classification !== 'correct_hit')) reasons[item.reason || item.classification] = (reasons[item.reason || item.classification] || 0) + 1;
  const report = {
    version: '1.0', checked_at_utc: new Date().toISOString(), scope: 'frozen ready aliases replayed through deterministic intake and reviewed public cache; local matching only, not real visitor hit-rate or online acceptance',
    questions_sha256: sha(questionBytes), cache_sha256: sha(cacheBytes), cache_entries: data.entries.length,
    frozen_ready_questions: eligible.length, available_ready_questions: eligible.filter(question => approved.has(question.question_id)).length,
    alias_samples: cases.length, available_alias_samples: cases.filter(item => item.approved_entry_available).length, counts, available_rejection_reasons: reasons,
    wrong_question_hits: cases.filter(item => item.classification === 'wrong_question_hit').length, official_model_calls: 0, cases,
  };
  const output = path('--output'); mkdirSync(dirname(output), { recursive: true });
  const temporary = `${output}.${process.pid}.tmp`; writeFileSync(temporary, JSON.stringify(report, null, 2) + '\n'); renameSync(temporary, output);
  const { cases: _cases, ...summary } = report;
  console.log(JSON.stringify({ ...summary, output }));
  if (report.wrong_question_hits) process.exitCode = 1;
} catch (error) { console.error(error.message); process.exitCode = 1; }
