"""Fixed-domain migration exercises successful cutover and durable rollback."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import network_setup as s
import network as n
import egress as e


NGINX = b"""server {
    listen 80;
    server_name old.sslip.io;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name old.sslip.io;
    ssl_certificate /old/fullchain.cer;
    ssl_certificate_key /old/old.sslip.io.key;
    location /keep-node-path {
        proxy_pass http://127.0.0.1:10086;
    }
}
"""


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.info, self.nginx, self.config = (self.root / name for name in ("info.json", "nginx.conf", "network.json"))
        self.network_state = self.root / "network-state"
        self.old = {"domain": "old.sslip.io", "uuid": "keep-node-id", "wsPath": "/keep-node-path",
                    "key": "fixture-deepseek-secret", "whitelist": ["keep.example.com"], "other": {"keep": True}}
        e.write(self.info, self.old, 0o600)
        e.write(self.nginx, NGINX, 0o644)
        e.write(self.config, {"old_config": True, "token": "fixture-old-token"}, 0o600)
        e.write(self.network_state / "state.json", {"domain": "old.sslip.io", "challenges": {"keep": True}})
        self.before = {p: p.read_bytes() for p in (self.info, self.nginx, self.config, self.network_state / "state.json")}
        self.commands, self.probe_calls = [], 0
        self.fail_command, self.fail_new_probe, self.fail_old_probe = None, False, False

        def runner(args, **kwargs):
            self.commands.append((args, kwargs))
            failed = self.fail_command is not None and self.fail_command(args)
            if failed:
                self.fail_command = None
            if "--install-cert" in args and not failed:
                key=Path(args[args.index("--key-file")+1])
                cert=Path(args[args.index("--fullchain-file")+1])
                e.write(key,b"fixture-key");e.write(cert,b"fixture-certificate")
            return types.SimpleNamespace(returncode=1 if failed else 0, stdout=b"", stderr=b"")

        def probe():
            self.probe_calls += 1
            current = json.loads(self.info.read_bytes())["domain"]
            return {"ok": not (self.fail_new_probe if current == "new.example.com" else self.fail_old_probe),
                    "exit_ip": "8.8.8.8", "path": "installed_node"}

        self.setup = s.Setup(info=self.info, nginx=self.nginx, config=self.config, state=self.root / "setup",
                             runner=runner, probe=probe, cert_root=self.root / "certs", network_state=self.network_state)
        self.lock = types.SimpleNamespace(fd=30, network_fd=31, inherited=False)
        self.value = {"domain": "new.example.com"}
        test = self
        class FakeNetwork:
            def __init__(self, config_path, state_dir):
                self.config, self.state = config_path, state_dir
            def configure(self, value, allow_domain_change, info_path):
                test.assertTrue(allow_domain_change)
                e.write(self.config, value)
                e.write(self.state / "state.json", {"domain": value["domain"], "status": "configured"})
            def prepare(self, domain):
                e.write(self.state / "state.json", {"domain": domain, "status": "dns_ready", "challenges": {}})
        self.fake = patch.object(s, "Network", FakeNetwork)
        self.fake.start()
        self.addCleanup(self.fake.stop)

    def assert_original(self):
        for path, expected in self.before.items():
            self.assertEqual(path.read_bytes(), expected, str(path))
        self.assertEqual(stat.S_IMODE(self.nginx.stat().st_mode), 0o644)

    def test_success_preserves_node_identity_whitelist_and_key(self):
        output = self.setup.apply(self.value, self.lock)
        self.assertEqual(output["status"], "verified")
        updated = json.loads(self.info.read_bytes())
        self.assertEqual({k: v for k, v in updated.items() if k not in ("domain", "certDir")},
                         {k: v for k, v in self.old.items() if k != "domain"})
        self.assertEqual(updated["domain"], "new.example.com")
        actual = self.nginx.read_text()
        self.assertIn("location /keep-node-path", actual)
        self.assertIn("proxy_pass http://127.0.0.1:10086", actual)
        self.assertEqual(actual.count("server_name new.example.com;"), 2)
        self.assertFalse(self.setup.journal.exists())
        self.assertEqual(self.probe_calls, 1)
        for _, kwargs in self.commands:
            self.assertEqual(kwargs["env"]["HUARUN_NETWORK_LOCK_FD"], "31")
            self.assertNotIn("HUARUN_UPDATE_LOCK_FD", kwargs["env"])
            self.assertEqual(kwargs["pass_fds"], (30, 31))

    def test_certificate_failure_rolls_back_network_state_as_well_as_node(self):
        self.fail_command = lambda args: "--issue" in args
        with self.assertRaisesRegex(n.NetworkError, "domain_setup_failed_local_configuration_restored"):
            self.setup.apply(self.value, self.lock)
        self.assert_original()
        self.assertFalse(self.setup.journal.exists())
        self.assertEqual(self.probe_calls, 1)

    def test_nginx_validation_failure_restores_every_snapshot(self):
        self.fail_command = lambda args: args == ["nginx", "-t"]
        with self.assertRaisesRegex(n.NetworkError, "domain_setup_failed_local_configuration_restored"):
            self.setup.apply(self.value, self.lock)
        self.assert_original()

    def test_candidate_node_failure_requires_successful_rollback_probe(self):
        self.fail_new_probe = True
        with self.assertRaisesRegex(n.NetworkError, "domain_setup_failed_local_configuration_restored"):
            self.setup.apply(self.value, self.lock)
        self.assert_original()
        self.assertEqual(self.probe_calls, 2)
        self.assertFalse(self.setup.journal.exists())

    def test_failed_rollback_probe_keeps_durable_journal_until_recovery(self):
        self.fail_new_probe = self.fail_old_probe = True
        with self.assertRaisesRegex(n.NetworkError, "domain_setup_failed_recovery_pending"):
            self.setup.apply(self.value, self.lock)
        self.assert_original()
        self.assertTrue(self.setup.journal.exists())
        self.fail_old_probe = False
        self.assertEqual(self.setup.recover(self.lock)["status"], "rolled_back")
        self.assertFalse(self.setup.journal.exists())

    def test_pending_provider_journal_refuses_domain_mutation(self):
        for kind in ("digitalocean", "hetzner-floating", "vultr", "aws-eip"):
            pending = self.network_state / "provider" / kind / "transaction.json"
            e.write(pending, {"status": "pending"})
            with self.subTest(kind=kind), self.assertRaisesRegex(n.NetworkError, "provider_recovery_pending"):
                self.setup.apply(self.value, self.lock)
            self.assert_original()
            pending.unlink()
        self.assertEqual(self.commands, [])

    def test_corrupted_backup_is_rejected_before_any_restoration(self):
        self.setup.snapshot()
        e.write(self.setup.state / "backup-2", b"corrupted")
        e.write(self.info, {"domain": "changed.example.com"})
        with self.assertRaisesRegex(n.NetworkError, "domain_recovery_backup_mismatch"):
            self.setup.recover(self.lock)
        self.assertEqual(json.loads(self.info.read_bytes())["domain"], "changed.example.com")
        self.assertTrue(self.setup.journal.exists())

    def test_new_network_config_is_removed_if_it_did_not_exist_before(self):
        self.config.unlink()
        (self.network_state / "state.json").unlink()
        self.fail_new_probe = True
        with self.assertRaisesRegex(n.NetworkError, "domain_setup_failed_local_configuration_restored"):
            self.setup.apply(self.value, self.lock)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.network_state / "state.json").exists())

    def test_unrecognized_nginx_layout_is_refused_before_snapshot(self):
        e.write(self.nginx, b"server { server_name old.sslip.io; }")
        with self.assertRaisesRegex(n.NetworkError, "nginx_domain_layout_unsupported"):
            self.setup.apply(self.value, self.lock)
        self.assertFalse(self.setup.journal.exists())
        self.assertEqual(self.commands, [])

    def test_same_domain_valid_certificate_only_changes_network_configuration(self):
        self.value["domain"]="old.sslip.io"
        cert=self.root/"existing-certificate"
        e.write(cert/"fullchain.cer",b"fixture-certificate")
        e.write(cert/"old.sslip.io.key",b"fixture-key")
        e.write(self.info,{**self.old,"certDir":str(cert)})
        before_info=self.info.read_bytes();before_nginx=self.nginx.read_bytes()
        self.assertEqual(self.setup.apply(self.value,self.lock)["status"],"verified")
        self.assertEqual(self.info.read_bytes(),before_info)
        self.assertEqual(self.nginx.read_bytes(),before_nginx)
        self.assertFalse(any("--issue" in args or "--install-cert" in args for args,_ in self.commands))
        self.assertFalse(any(args==["systemctl","reload","nginx"] for args,_ in self.commands))

    def test_valid_certificate_from_previous_attempt_is_reused_without_issuing(self):
        cert=self.setup.cert_root/"new.example.com"
        e.write(cert/"fullchain.cer",b"fixture-certificate")
        e.write(cert/"new.example.com.key",b"fixture-key")
        self.assertEqual(self.setup.apply(self.value,self.lock)["status"],"verified")
        self.assertFalse(any("--issue" in args or "--install-cert" in args for args,_ in self.commands))

    def test_acme_existing_certificate_exit_two_installs_and_verifies_cache(self):
        original_runner=self.setup.runner
        def cached(args,**kwargs):
            result=original_runner(args,**kwargs)
            if "--issue" in args:result.returncode=2
            return result
        self.setup.runner=cached
        self.assertEqual(self.setup.apply(self.value,self.lock)["status"],"verified")
        self.assertTrue(any("--install-cert" in args for args,_ in self.commands))


if __name__ == "__main__":
    unittest.main()
