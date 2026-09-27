// Compile reviewed editorial FAQ only. No sessions, case jobs, network or credentials.
import { readFileSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { validateFaqCacheData } from '../src/faq-cache.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../..');
const args = process.argv.slice(2);
function argument(name, fallback) {
  const at = args.indexOf(name);
  if (at < 0) return fallback;
  if (!args[at + 1] || args[at + 1].startsWith('--')) throw new Error(`${name} needs a path`);
  return resolve(args[at + 1]);
}
try {
  for (const name of args.filter(value => value.startsWith('--'))) if (!['--input', '--output'].includes(name)) throw new Error(`unknown option: ${name}`);
  const input = argument('--input', resolve(root, 'data/faq-cache.json'));
  const output = argument('--output', resolve(root, 'apps/worker/src/faq-cache-data.mjs'));
  const bytes = readFileSync(input);
  const data = JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/, ''));
  const valid = validateFaqCacheData(data);
  if (!valid.ok) throw new Error(`FAQ cache rejected: ${valid.errors.join(', ')}`);
  const sha = createHash('sha256').update(bytes).digest('hex');
  const module = `// Generated from reviewed public FAQ. SHA256: ${sha}\nexport const FAQ_CACHE_DATA = ${JSON.stringify(data)};\n`;
  mkdirSync(dirname(output), { recursive: true });
  const temporary = `${output}.${process.pid}.tmp`;
  writeFileSync(temporary, module, 'utf8');
  renameSync(temporary, output);
  console.log(JSON.stringify({ status: 'compiled', entries: data.entries.length, sources: data.sources.length, sha256: sha, output }));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
