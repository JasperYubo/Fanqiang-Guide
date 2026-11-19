"""Release trust chain and crash recovery, isolated from the host installation."""
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlsplit

SPEC = importlib.util.spec_from_file_location('auto_update', Path(__file__).resolve().parents[1] / 'auto_update.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def encoded(value):
    return json.dumps(value).encode()


class PublicRelease:
    def __init__(self, source='a' * 40, version='1.2.0', suffix=''):
        self.calls = []
        self.source, self.version = source, version
        self.installer = ('#!/bin/bash\nVERSION="' + version + '"\n# ' + suffix + '\n').encode()
        digest = m.sha256(self.installer)
        self.origin = {'schema_version': 1, 'source_sha': source, 'installer_sha256': digest,
                       'contract_sha256': 'b' * 64, 'sync_id': 'sync-123'}
        self.pages = {**self.origin, 'run_id': '1234', 'run_attempt': 1}
        self.proof = {**self.pages, 'origin_receipt': self.origin.copy(), 'pages_receipt': self.pages.copy(),
                      'assets': {'huarun-install.sh': {'sha256': digest, 'bytes': len(self.installer)}}}
        self.release = {'id': 123, 'draft': False, 'prerelease': False, 'target_commitish': source,
                        'tag_name': 'release-' + source[:12]}
        self.refresh()

    def refresh(self):
        self.assets = {'huarun-install.sh': self.installer, 'deployment-proof.json': encoded(self.proof)}
        self.release['assets'] = [{'name': name, 'state': 'uploaded', 'size': len(raw),
                                  'digest': 'sha256:' + m.sha256(raw),
                                  'browser_download_url': 'https://github.com/' + m.REPOSITORY + '/releases/download/' + self.release['tag_name'] + '/' + name}
                                 for name, raw in self.assets.items()]

    def __call__(self, url):
        self.calls.append(url)
        if url == m.API:
            return encoded(self.release)
        path = urlsplit(url).path
        if path.endswith('/data/site-release.json'):
            return encoded(self.origin)
        if path.endswith('/deployment.json'):
            return encoded(self.pages)
        if path.endswith('/server/install.sh'):
            return self.installer
        return self.assets[path.rsplit('/', 1)[1]]


class Machine:
    def __init__(self, root, release):
        self.root, self.release = root, release
        self.calls, self.applied, self.mode = [], 0, 'success'
        self.timer = {'enabled': 'enabled', 'active': 'active'}
        self.network_timer = {'enabled': 'not-found', 'active': 'inactive'}
        self.initial_doctor = {'checks': {'xray': {'ok': True}, 'dns': {'ok': False}}, 'all_ok': False}
        self.initial_status = {'xray': 'active', 'nginx': 'active', 'port443': True, 'renew_cron': True, 'assistant': True}
        self.lock_passed = []
        self.setup()

    def path(self, target):
        return self.root / target.lstrip('/')

    def put(self, target, raw, mode=0o600):
        path = self.path(target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(mode)

    def setup(self):
        for target in m.PROTECTED_PATHS:
            if target.endswith('/provider/discovered'):
                self.put(target + '/fixture/profile.json', b'{"private_adapter":"unchanged"}')
                self.path(target).chmod(0o700)
                self.path(target + '/fixture').chmod(0o700)
                continue
            self.put(target, ('secret-node-or-key\n' + target).encode(), 0o640 if target.endswith('whitelist.txt') else 0o600)
        for target in m.ASSISTANT_PATHS:
            if target.endswith('assistant-template'):
                self.put(target + '/config.json', b'{"old":true}')
            elif '/systemd/' not in target:
                self.put(target, b'# original\n', 0o755 if '/usr/local/bin/' in target else 0o600)
        self.put('/usr/local/bin/huarun', b'#!/bin/bash\nVERSION="1.1.0"\n', 0o755)
        self.put('/etc/huarun/assistant/workspace/memory/private.md', b'private memory must survive')
        self.put('/etc/huarun/assistant/sessions/chat.json', b'private conversation must survive')

    def __call__(self, args, *, timeout, env, pass_fds):
        self.calls.append(args)
        if 'HUARUN_UPDATE_LOCK_FD' in env:
            fd = int(env['HUARUN_UPDATE_LOCK_FD'])
            assert pass_fds == (fd,)
            assert os.fstat(fd).st_ino == self.path(m.LOCK_PATH).stat().st_ino
            with self.path(m.LOCK_PATH).open('rb') as check:
                try:
                    fcntl.flock(check.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    raise AssertionError('child did not inherit an exclusive update lock')
            self.lock_passed.append(args)
        if args[0] == 'systemctl':
            action = args[1]
            timer = self.network_timer if args[-1] == 'huarun-network.timer' else self.timer
            if action == 'is-enabled':
                if timer['enabled'] == 'not-found':
                    return subprocess.CompletedProcess(args, 1, '', 'Unit file does not exist')
                return subprocess.CompletedProcess(args, 0, timer['enabled'], '')
            if action == 'is-active':
                return subprocess.CompletedProcess(args, 0, timer['active'], '')
            if action == 'show':
                return subprocess.CompletedProcess(args, 0, 'not-found' if timer['enabled'] == 'not-found' else 'loaded', '')
            if action in {'enable', 'disable'}:
                timer['enabled'] = action + 'd'
                if '--now' in args:
                    timer['active'] = 'active' if action == 'enable' else 'inactive'
            if action in {'start', 'stop'}:
                timer['active'] = 'active' if action == 'start' else 'inactive'
            return subprocess.CompletedProcess(args, 0, '', '')
        if args[0] == 'bash' and args[1] == '-n':
            return subprocess.run(args, capture_output=True, text=True)
        if args[0] == 'bash':
            self.applied += 1
            assert args[-2:] == ['--upgrade-assistant', '--yes']
            assert Path(args[1]).read_bytes() == self.release.installer
            self.put('/usr/local/bin/huarun', self.release.installer, 0o755)
            for target in m.ASSISTANT_PATHS:
                if target.endswith('.py'):
                    self.put(target, b'# updated\n')
                elif target.endswith('.service') or target.endswith('.timer'):
                    self.put(target, b'[Unit]\nDescription=Updated\n', 0o644)
            self.put('/etc/huarun/assistant-template/config.json', b'{"new":true}')
            if self.network_timer['enabled'] == 'not-found':
                self.network_timer.update(enabled='enabled', active='active')
            if self.mode in {'protected', 'crash', 'failure', 'symlink'}:
                self.put(m.PROTECTED_PATHS[0], b'corrupted secret', 0o777)
                self.put('/etc/huarun/assistant/.security.yml', b'wrong key', 0o644)
            if self.mode == 'symlink':
                leaf = self.path('/etc/huarun/assistant/research.py')
                leaf.unlink()
                leaf.symlink_to('/does-not-exist')
            if self.mode == 'crash':
                raise KeyboardInterrupt('simulated process death')
            if self.mode == 'busy':
                return subprocess.CompletedProcess(args, 75, '', '')
            if self.mode == 'failure':
                return subprocess.CompletedProcess(args, 1, 'secret-output', 'secret-error')
            if self.mode == 'syntax':
                self.put('/etc/huarun/assistant/gate.py', b'not valid python!')
            return subprocess.CompletedProcess(args, 0, '', '')
        if args[1] == 'version':
            return subprocess.CompletedProcess(args, 0, m.version(Path(args[0]).read_bytes()), '')
        if args[1] in {'doctor', 'status'}:
            value = copy.deepcopy(self.initial_doctor if args[1] == 'doctor' else self.initial_status)
            if self.applied and self.mode == 'regression':
                if args[1] == 'doctor':
                    value['checks']['xray']['ok'] = False
                else:
                    value['xray'] = 'inactive'
            if self.applied and self.mode == 'bad-json':
                return subprocess.CompletedProcess(args, 0, '{bad json', '')
            return subprocess.CompletedProcess(args, 0, json.dumps(value), '')
        raise AssertionError(args)


class VerificationTests(unittest.TestCase):
    def test_verified_release(self):
        release = PublicRelease()
        candidate = m.verify_release(release)
        self.assertEqual(candidate['version'], '1.2.0')
        self.assertEqual(candidate['source_sha'], 'a' * 40)
        self.assertEqual(len(release.calls), 6)

    def test_trust_chain_rejects_tampering(self):
        mutations = [
            lambda r: r.release.update(draft=True),
            lambda r: r.release.update(prerelease=True),
            lambda r: r.release.update(target_commitish='main'),
            lambda r: r.release['assets'][0].update(browser_download_url='https://evil.example/install.sh'),
            lambda r: r.release['assets'][0].update(digest='sha256:' + '0' * 64),
            lambda r: r.proof.update(source_sha='c' * 40),
            lambda r: r.proof.update(assets=[]),
            lambda r: r.origin.update(source_sha='c' * 40),
            lambda r: r.pages.update(sync_id='other-transaction'),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                release = PublicRelease()
                mutate(release)
                if release.proof.get('source_sha') != 'a' * 40 or release.proof.get('assets') == []:
                    release.refresh()
                with self.assertRaises(m.Defer):
                    m.verify_release(release)

    def test_same_source_new_site_transaction_accepted(self):
        release = PublicRelease()
        release.origin['sync_id'] = release.pages['sync_id'] = 'rerun-same-source'
        release.pages['run_id'] = '999'
        self.assertEqual(m.verify_release(release)['source_sha'], release.source)

    def test_fixed_https_paths_and_no_credentials(self):
        for url in ['http://github.com/a', 'https://attacker.example/x', 'https://user:secret@api.github.com/repos/' + m.REPOSITORY + '/releases/latest', 'https://github.com/other/repo/releases/download/x/huarun-install.sh', 'https://api.github.com/user', 'https://fanqiang.guide/secret']:
            with self.subTest(url=url):
                self.assertFalse(m.allowed_url(url))
        self.assertTrue(m.allowed_url(m.API))

    def test_cross_host_redirect_blocked_and_no_auth_header(self):
        class Redirect:
            def open(self, request, timeout):
                self.request = request
                raise HTTPError(request.full_url, 302, '', {'Location': 'https://evil.example/leak'}, None)
        opener = Redirect()
        url = 'https://github.com/' + m.REPOSITORY + '/releases/download/release-' + 'a' * 12 + '/huarun-install.sh'
        with patch.object(m, 'build_opener', return_value=opener), patch.dict(os.environ, {'GITHUB_TOKEN': 'never-send', 'DEEPSEEK_API_KEY': 'never-send'}):
            with self.assertRaisesRegex(m.Defer, 'download_url_not_allowed'):
                m.fetch_public(url)
        self.assertNotIn('Authorization', opener.request.headers)
        self.assertNotIn('never-send', repr(opener.request.headers))


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release = PublicRelease()
        self.machine = Machine(self.root, self.release)
        self.updater = m.Updater(self.root, fetch=self.release, runner=self.machine, clock=lambda: 1700000000)
        self.original = {target: self.updater.snapshot(self.machine.path(target)) for target in m.ALL_PATHS}

    def assert_restored(self):
        for target in m.ALL_PATHS:
            self.assertEqual(self.updater.snapshot(self.machine.path(target)), self.original[target], target)
        self.assertEqual(self.machine.path('/etc/huarun/assistant/workspace/memory/private.md').read_bytes(), b'private memory must survive')
        self.assertEqual(self.machine.path('/etc/huarun/assistant/sessions/chat.json').read_bytes(), b'private conversation must survive')

    def test_success_private_state_protected_bytes_and_lock(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'secret', 'DEEPSEEK_API_KEY': 'secret'}):
            result = self.updater.run()
        self.assertEqual(result['status'], 'updated')
        self.assertEqual(self.machine.applied, 1)
        for target in m.PROTECTED_PATHS:
            self.assertEqual(self.updater.snapshot(self.machine.path(target)), self.original[target])
        self.assertEqual(self.updater.state_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.updater.state_dir.stat().st_mode & 0o777, 0o700)
        self.assertFalse(self.updater.journal_path.exists())
        self.assertTrue(any(args[0] == 'bash' and '--upgrade-assistant' in args for args in self.machine.lock_passed))
        self.assertNotIn('secret-node-or-key', self.updater.state_path.read_text())
        self.assertEqual(self.updater.run()['status'], 'up_to_date')
        self.assertEqual(self.machine.applied, 1)

    def test_disabled_and_status_never_use_network(self):
        self.machine.put(m.DISABLED_MARKER, b'')
        self.assertEqual(self.updater.run()['status'], 'disabled')
        self.assertFalse(self.release.calls)
        status = self.updater.status()
        self.assertTrue(status['disabled'])
        self.assertEqual(status['timer'], {'enabled': 'enabled', 'active': 'active'})
        self.assertFalse(self.release.calls)

    def test_busy_lock_skips(self):
        lock = self.machine.path(m.LOCK_PATH)
        lock.parent.mkdir(parents=True)
        with lock.open('wb') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
            self.assertEqual(self.updater.run()['status'], 'busy')
        self.assertFalse(self.release.calls)

    def test_downgrade_refused_before_apply(self):
        release = PublicRelease(version='1.0.9')
        self.updater.fetch = release
        self.assertEqual(self.updater.run()['reason'], 'downgrade_refused')
        self.assertEqual(self.machine.applied, 0)

    def test_same_version_different_hash_updates(self):
        self.machine.put('/usr/local/bin/huarun', b'VERSION="1.2.0"\n', 0o755)
        self.assertEqual(self.updater.run()['status'], 'updated')

    def test_sites_mismatch_defers_without_backup_or_execution(self):
        self.release.pages['sync_id'] = 'not-yet-live'
        self.assertEqual(self.updater.run()['status'], 'deferred')
        self.assertEqual(self.machine.applied, 0)
        self.assertFalse(list(self.updater.backup_dir.iterdir()))

    def test_failed_checks_restore_exact_files_modes_and_new_units(self):
        for mode in ('protected', 'regression', 'syntax', 'bad-json', 'failure', 'symlink'):
            with self.subTest(mode=mode):
                self.machine.mode = mode
                result = self.updater.run()
                self.assertEqual(result['status'], 'rolled_back')
                self.assert_restored()
                self.assertFalse(self.updater.journal_path.exists())
                self.updater.state_path.unlink()
                self.machine.applied = 0

    def test_failure_same_source_backoff_but_new_source_attempts(self):
        self.machine.mode = 'failure'
        self.assertEqual(self.updater.run()['status'], 'rolled_back')
        self.assertEqual(self.updater.run()['status'], 'backoff')
        self.assertEqual(self.machine.applied, 1)
        release = PublicRelease(source='c' * 40, suffix='next')
        self.updater.fetch = self.machine.release = release
        self.machine.mode = 'success'
        self.assertEqual(self.updater.run()['status'], 'updated')
        self.assertEqual(self.machine.applied, 2)

    def test_crash_recovers_before_network_even_when_disabled(self):
        self.machine.mode = 'crash'
        with self.assertRaises(KeyboardInterrupt):
            self.updater.run()
        self.assertTrue(self.updater.journal_path.exists())
        self.assertNotEqual(self.updater.snapshot(self.machine.path(m.PROTECTED_PATHS[0])), self.original[m.PROTECTED_PATHS[0]])
        self.machine.put(m.DISABLED_MARKER, b'')
        self.release.calls.clear()
        result = self.updater.run()
        self.assertEqual(result['status'], 'rolled_back')
        self.assertEqual(result['last_failure']['code'], 'interrupted_update')
        self.assertFalse(self.release.calls)
        self.assert_restored()

    def test_corrupt_backup_prevents_partial_restore_and_preserves_journal(self):
        self.machine.mode = 'crash'
        with self.assertRaises(KeyboardInterrupt):
            self.updater.run()
        journal = self.updater.read_json(self.updater.journal_path)
        backup = self.updater.backup_dir / journal['transaction'] / '0'
        backup.write_bytes(b'corrupted backup')
        self.release.calls.clear()
        with self.assertRaisesRegex(m.UpdateError, 'backup_integrity_failed'):
            self.updater.run()
        self.assertTrue(self.updater.journal_path.exists())
        self.assertFalse(self.release.calls)

    def test_backups_prune_only_own_marked_directories(self):
        self.updater.private_dir(self.updater.backup_dir)
        foreign = self.updater.backup_dir / 'user-backup'
        foreign.mkdir()
        for index in range(5):
            name = 'txn-20260101T00000' + str(index) + 'Z-' + ('a' * 16)
            self.updater.backup(name)
        self.updater.prune_backups()
        self.assertTrue(foreign.exists())
        self.assertEqual(len(list(self.updater.backup_dir.glob('txn-*'))), 3)

    def test_broken_symlink_in_template_is_rejected_before_install(self):
        self.machine.path('/etc/huarun/assistant-template/danger').symlink_to('/does-not-exist')
        with self.assertRaisesRegex(m.UpdateError, 'unsupported_backup_file'):
            self.updater.run()
        self.assertEqual(self.machine.applied, 0)
        self.assertFalse(list(self.updater.backup_dir.iterdir()))

    def test_health_baseline_false_is_not_a_regression(self):
        self.assertFalse(self.machine.initial_doctor['all_ok'])
        self.assertEqual(self.updater.run()['status'], 'updated')

    def test_installer_busy_rolls_back_without_24_hour_penalty(self):
        self.machine.mode = 'busy'
        result = self.updater.run()
        self.assertEqual(result, {'status': 'deferred', 'reason': 'installer_busy'})
        self.assert_restored()
        self.assertFalse(self.updater.read_json(self.updater.state_path).get('last_failure'))
        self.machine.mode = 'success'
        self.assertEqual(self.updater.run()['status'], 'updated')
        self.assertEqual(self.machine.applied, 2)

    def test_backoff_expires(self):
        self.machine.mode = 'failure'
        self.assertEqual(self.updater.run()['status'], 'rolled_back')
        self.updater.clock = lambda: 1700000000 + m.FAILURE_BACKOFF + 1
        self.machine.mode = 'success'
        self.assertEqual(self.updater.run()['status'], 'updated')

    def test_timeout_kills_descendant_before_rollback_can_start(self):
        marker = self.root / 'must-not-be-created'
        child = "import time,pathlib;time.sleep(.5);pathlib.Path(" + repr(str(marker)) + ").write_text('racing write')"
        parent = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",' + repr(child) + ']);time.sleep(10)'
        with self.assertRaises(subprocess.TimeoutExpired):
            m.default_runner([sys.executable, '-c', parent], timeout=.1, env=os.environ.copy())
        time.sleep(.55)
        self.assertFalse(marker.exists())

    def test_real_child_receives_exclusive_descriptor(self):
        lock = self.machine.path(m.LOCK_PATH)
        lock.parent.mkdir(parents=True)
        with lock.open('wb') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.updater.lock_fd = stream.fileno()
            self.updater.runner = m.default_runner
            child = "import os,fcntl;fd=int(os.environ['HUARUN_UPDATE_LOCK_FD']);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);print(os.fstat(fd).st_ino)"
            result = self.updater.command([sys.executable, '-c', child])
            self.assertEqual(int(result.stdout), lock.stat().st_ino)
            self.updater.lock_fd = None

    def test_restore_systemctl_failure_keeps_journal_for_retry(self):
        self.machine.mode = 'failure'
        original_runner = self.updater.runner
        def systemctl_failure(args, **options):
            if args[:2] == ['systemctl', 'daemon-reload']:
                return subprocess.CompletedProcess(args, 1, '', 'private error')
            return original_runner(args, **options)
        self.updater.runner = systemctl_failure
        with self.assertRaisesRegex(m.UpdateError, 'local_command_failed'):
            self.updater.run()
        self.assertTrue(self.updater.journal_path.exists())
        self.assert_restored()
        self.updater.runner = original_runner
        self.assertEqual(self.updater.run()['status'], 'rolled_back')
        self.assertFalse(self.updater.journal_path.exists())

    def test_status_removes_unknown_nested_fields(self):
        self.updater.private_dir(self.updater.state_dir)
        self.updater.atomic_json(self.updater.state_path, {'last_good': {'version': '1.2.0', 'key': 'secret'}})
        self.assertEqual(self.updater.status()['last_good'], {'version': '1.2.0'})


class NetworkUpgradeTests(unittest.TestCase):
    setUp = TransactionTests.setUp
    assert_restored = TransactionTests.assert_restored
    def test_missing_network_unit_is_detected_from_load_state(self):
        self.assertEqual(self.updater.timer_state('huarun-network.timer'), {'enabled': 'not-found', 'active': 'inactive'})
        self.assertIn(['systemctl', 'show', '--property=LoadState', '--value', 'huarun-network.timer'], self.machine.calls)

    def test_absent_network_configuration_stays_absent_after_upgrade(self):
        for target in ('/etc/huarun/network.json', '/etc/huarun/egress.json'):
            self.machine.path(target).unlink()
        self.assertEqual(self.updater.run()['status'], 'updated')
        for target in ('/etc/huarun/network.json', '/etc/huarun/egress.json'):
            self.assertFalse(self.machine.path(target).exists())
        self.assertEqual(self.machine.network_timer, {'enabled': 'enabled', 'active': 'active'})

    def test_existing_cloudflare_and_exit_credentials_are_byte_and_mode_preserved(self):
        for target in ('/etc/huarun/network.json', '/etc/huarun/egress.json'):
            self.machine.put(target, ('{  "local_secret": "synthetic-private", "path": "'+target+'" }\n').encode(), 0o600)
            self.original[target] = self.updater.snapshot(self.machine.path(target))
        self.assertEqual(self.updater.run()['status'], 'updated')
        for target in m.PROTECTED_PATHS:
            self.assertEqual(self.updater.snapshot(self.machine.path(target)), self.original[target], target)

    def test_each_new_configuration_mutation_forces_exact_rollback(self):
        original_runner = self.machine
        for target in ('/etc/huarun/network.json', '/etc/huarun/egress.json'):
            with self.subTest(target=target):
                def mutate(args, **options):
                    result = original_runner(args, **options)
                    if args[0] == 'bash' and args[1] != '-n':
                        self.machine.put(target, b'{"lost":"private configuration"}', 0o644)
                    return result
                self.updater.runner = mutate
                self.assertEqual(self.updater.run()['status'], 'rolled_back')
                self.assert_restored()
                self.updater.state_path.unlink()
                self.machine.applied = 0

    def test_new_module_syntax_failure_forces_rollback(self):
        original_runner = self.machine
        for name in ('network.py', 'ip_provider.py', 'aws_provider.py', 'egress.py', 'network_setup.py'):
            with self.subTest(name=name):
                def break_module(args, **options):
                    result = original_runner(args, **options)
                    if args[0] == 'bash' and args[1] != '-n':
                        self.machine.put('/usr/local/lib/huarun/'+name, b'invalid python ???')
                    return result
                self.updater.runner = break_module
                result = self.updater.run()
                self.assertEqual(result['status'], 'rolled_back')
                self.assertEqual(result['last_failure']['code'], 'installed_python_invalid')
                self.assert_restored()
                self.updater.state_path.unlink()
                self.machine.applied = 0

    def test_disabled_existing_network_timer_is_preserved_on_success(self):
        self.machine.network_timer = {'enabled': 'disabled', 'active': 'inactive'}
        self.assertEqual(self.updater.run()['status'], 'updated')
        self.assertEqual(self.machine.network_timer, {'enabled': 'disabled', 'active': 'inactive'})

    def test_unexpected_network_timer_change_rolls_back_prior_state(self):
        self.machine.network_timer = {'enabled': 'disabled', 'active': 'inactive'}
        original_runner = self.machine
        def enable_unexpectedly(args, **options):
            result = original_runner(args, **options)
            if args[0] == 'bash' and args[1] != '-n':
                self.machine.network_timer = {'enabled': 'enabled', 'active': 'active'}
            return result
        self.updater.runner = enable_unexpectedly
        result = self.updater.run()
        self.assertEqual(result['status'], 'rolled_back')
        self.assertEqual(result['last_failure']['code'], 'network_timer_changed_unexpectedly')
        self.assertEqual(self.machine.network_timer, {'enabled': 'disabled', 'active': 'inactive'})
        self.assert_restored()

    def test_network_timer_stop_failure_preserves_recovery_journal(self):
        self.machine.mode = 'failure'
        original_runner = self.machine
        def stop_failure(args, **options):
            if args[:2] == ['systemctl', 'disable'] and args[-1] == 'huarun-network.timer':
                return subprocess.CompletedProcess(args, 1, '', 'systemd failure')
            return original_runner(args, **options)
        self.updater.runner = stop_failure
        with self.assertRaisesRegex(m.UpdateError, 'network_timer_restore_failed'):
            self.updater.run()
        self.assertTrue(self.updater.journal_path.exists())
        self.assertEqual(self.machine.network_timer['active'], 'active')
        self.updater.runner = original_runner
        self.assertEqual(self.updater.run()['status'], 'rolled_back')
        self.assertEqual(self.machine.network_timer['active'], 'inactive')

    def legacy_interrupted_update(self):
        self.updater.private_dir(self.updater.state_dir)
        self.updater.private_dir(self.updater.backup_dir)
        transaction = 'txn-20261118T000000Z-'+'c'*16
        # Produce 1.2's exact numeric backup indexes, then remove the newer
        # path_order member which genuinely did not exist in the legacy schema.
        with patch.object(m, 'ALL_PATHS', m.LEGACY_ALL_PATHS):
            folder, manifest = self.updater.backup(transaction)
        manifest.pop('path_order')
        self.updater.atomic_json(folder/'backup.json', manifest)
        journal = {'schema_version':1,'transaction':transaction,'phase':'applying',
                   'candidate':{'source_sha':'a'*40,'installer_sha256':'b'*64},
                   'previous_state':{},'timer_before':{'enabled':'enabled','active':'active'}}
        self.updater.atomic_json(self.updater.journal_path, journal)
        for target in m.LEGACY_ALL_PATHS:
            if target.endswith('assistant-template'):
                self.machine.put(target+'/config.json', b'changed')
            else:
                self.machine.put(target, b'changed by interrupted 1.3 installer', 0o644)
        self.machine.put('/etc/systemd/system/huarun-network.timer', b'new timer from interrupted installer')
        self.machine.network_timer = {'enabled':'enabled','active':'active'}
        return folder, manifest

    def test_legacy_manifest_numeric_indexes_recover_with_new_code(self):
        self.legacy_interrupted_update()
        self.release.calls.clear()
        result = self.updater.run()
        self.assertEqual(result['status'],'rolled_back')
        self.assertFalse(self.release.calls)
        for target in m.LEGACY_ALL_PATHS:
            self.assertEqual(self.updater.snapshot(self.machine.path(target)), self.original[target], target)
        # The old journal cannot claim ownership of new local files: keep them
        # intact and prove the newly introduced timer is no longer executing.
        self.assertTrue(self.machine.path('/etc/systemd/system/huarun-network.timer').exists())
        self.assertEqual(self.machine.network_timer, {'enabled':'disabled','active':'inactive'})

    def test_legacy_manifest_corruption_fails_before_any_partial_restore(self):
        folder, manifest = self.legacy_interrupted_update()
        (folder/'5').write_bytes(b'corrupted manager backup')
        changed = self.machine.path(m.LEGACY_ALL_PATHS[0]).read_bytes()
        with self.assertRaisesRegex(m.UpdateError,'backup_integrity_failed'):
            self.updater.run()
        self.assertEqual(self.machine.path(m.LEGACY_ALL_PATHS[0]).read_bytes(), changed)
        self.assertTrue(self.updater.journal_path.exists())

    def test_reordered_manifest_is_rejected_before_restore(self):
        folder, manifest = self.legacy_interrupted_update()
        manifest['path_order'] = list(reversed(m.LEGACY_ALL_PATHS))
        self.updater.atomic_json(folder/'backup.json', manifest)
        with self.assertRaisesRegex(m.UpdateError,'invalid_backup_manifest'):
            self.updater.run()
        self.assertTrue(self.updater.journal_path.exists())


if __name__ == '__main__':
    unittest.main()
