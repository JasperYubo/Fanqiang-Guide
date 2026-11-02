import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { chmod, chown, copyFile, mkdir, mkdtemp, rm, stat, symlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

// Production's current/ directory is a symlink. Node resolves import.meta.url to
// the release path, while argv[1] retains current/: exercise the real CLI entry.
test('collector CLI starts through a symlink parent as a non-root user and stops cleanly', { skip: process.platform !== 'linux', timeout: 10000 }, async t => {
  const root = await mkdtemp(join(tmpdir(), 'fqdiag-collector-cli-'));
  let child;
  let closed;
  t.after(async () => {
    if (child && child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    if (closed) await closed;
    await rm(root, { recursive: true, force: true });
  });
  await chmod(root, 0o755);
  const release = join(root, 'release');
  const data = join(root, 'data');
  await mkdir(release, { mode: 0o755 });
  await mkdir(data, { mode: 0o700 });
  for (const name of ['collector.mjs', 'report.mjs']) {
    await copyFile(new URL('../src/' + name, import.meta.url), join(release, name));
    await chmod(join(release, name), 0o644);
  }
  await symlink(release, join(root, 'current'), 'dir');
  const identity = process.getuid() === 0 ? { uid: 65534, gid: 65534 } : {};
  const expectedUid = identity.uid ?? process.getuid();
  assert.notEqual(expectedUid, 0);
  if (identity.uid !== undefined) await chown(data, identity.uid, identity.gid);
  child = spawn(process.execPath, [join(root, 'current', 'collector.mjs')], {
    ...identity, cwd: root,
    env: { ...process.env, FQDIAG_DATA_DIR: data, FQDIAG_HOST: '127.0.0.1', FQDIAG_PORT: '0' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  closed = new Promise(resolve => child.once('close', (code, signal) => resolve({ code, signal })));
  let output = '', errors = '', spawnError;
  child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
  child.stdout.on('data', value => { output += value; });
  child.stderr.on('data', value => { errors += value; });
  child.once('error', error => { spawnError = error; });
  const deadline = Date.now() + 5000;
  while (!output.includes('\n')) {
    assert.equal(spawnError, undefined);
    assert.equal(child.exitCode, null, 'collector exited before listening: ' + errors);
    assert.equal(child.signalCode, null);
    assert.ok(Date.now() < deadline, 'collector never reported listening: ' + errors);
    await delay(20);
  }
  const ready = JSON.parse(output.split('\n')[0]);
  assert.equal(ready.status, 'listening');
  assert.equal(ready.service, 'fanqiang-diagnostics');
  assert.ok(Number.isInteger(ready.port) && ready.port > 0);
  const response = await fetch('http://127.0.0.1:' + ready.port + '/health', { signal: AbortSignal.timeout(2000) });
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ok: true, service: 'fanqiang-diagnostics', version: '0.1.0' });
  assert.equal((await stat(join(data, 'reports.sqlite'))).uid, expectedUid);
  assert.equal((await stat(join(data, 'collector.key'))).mode & 0o777, 0o600);
  child.kill('SIGTERM');
  const stopped = await Promise.race([closed, delay(2000).then(() => { throw new Error('collector did not stop'); })]);
  assert.deepEqual(stopped, { code: 0, signal: null });
});
