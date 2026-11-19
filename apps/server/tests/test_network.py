"""Network safety, recovery and protocol tests; no production credentials."""
import copy
import fcntl
import http.client
import http.server
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import network as n

AID, ZID = "a" * 32, "b" * 32
KEY = "probe-test-key-not-a-real-secret-" + "x" * 32
NOW = 1700000000


def config():
    return {"schema_version": 1, "domain": "node.example.com",
            "cloudflare": {"account_id": AID, "zone_id": ZID,
                           "api_token": "TEST-full-account-token-not-real", "proxied": False},
            "address_source": {"mode": "static", "addresses": {"A": "8.8.8.8"}},
            "notification": {"kind": "none"}, "probes": []}


def probes():
    return [{"url": "https://probe-one.example.com/probe", "key": KEY, "region": "cn-one"},
            {"url": "https://probe-two.example.com/probe", "key": KEY, "region": "cn-two"}]


def signer(reachable=True, mutate=None):
    def call(url, value, key):
        output = {k: value[k] for k in ("nonce", "domain", "connect_ip", "at")}
        output.update(tcp_ok=reachable, tls_ok=reachable, websocket_ok=reachable)
        if mutate:
            mutate(output)
        return {"result": output, "signature": n.probe_signature(key, output)}
    return call


class FakeCF:
    def __init__(self):
        self.rows = {}
        self.calls = []
        self.counter = 0
        self.zone = {"id": ZID, "account": {"id": AID}, "name": "example.com", "status": "active"}
        self.token_status = "active"
        self.ssl_mode = "strict"
        self.telegram_ok = True
        self.sent = []
        self.public_ips = ["8.8.8.8", "8.8.8.8"]
        self.corrupt_readback = False

    def add(self, kind="A", content="1.1.1.1", name="node.example.com", **extra):
        self.counter += 1
        ident = format(self.counter, "032x")
        self.rows[ident] = {"id": ident, "name": name, "type": kind, "content": content, "ttl": 600,
                            "proxied": False, **extra}
        return ident

    def __call__(self, method, url, payload=None, headers=None):
        if url in n.IP_SERVICES:
            return self.public_ips[n.IP_SERVICES.index(url)]
        if url.startswith("https://api.telegram.org/"):
            if not self.telegram_ok:
                raise n.NetworkError("upstream_http_502")
            self.sent.append(copy.deepcopy(payload))
            return {"ok": True, "result": {"message_id": len(self.sent)}}
        self.calls.append((method, urlsplit(url).path, copy.deepcopy(payload)))
        if url.endswith("/tokens/verify"):
            return {"success": True, "result": {"status": self.token_status}}
        if url.endswith("/zones/" + ZID + "/settings/ssl"):
            return {"success": True, "result": {"id": "ssl", "value": self.ssl_mode}}
        if url.endswith("/zones/" + ZID):
            return {"success": True, "result": copy.deepcopy(self.zone)}
        path = urlsplit(url).path
        prefix = "/client/v4/zones/" + ZID + "/dns_records"
        if path == prefix:
            if method == "GET":
                name = parse_qs(urlsplit(url).query)["name"][0]
                result = [copy.deepcopy(r) for r in self.rows.values() if r["name"] == name]
                return {"success": True, "result": result, "result_info": {"total_pages": 1}}
            if method == "POST":
                row = copy.deepcopy(payload)
                ident = self.add(kind=row.pop("type"), content=row.pop("content"), name=row.pop("name"), **row)
                return {"success": True, "result": copy.deepcopy(self.rows[ident])}
        if path.startswith(prefix + "/"):
            ident = path.rsplit("/", 1)[1]
            if ident not in self.rows:
                raise n.NetworkError("upstream_http_404")
            if method == "DELETE":
                del self.rows[ident]
                return {"success": True, "result": {"id": ident}}
            if method == "PATCH":
                self.rows[ident].update(payload)
            result = copy.deepcopy(self.rows[ident])
            if method == "GET" and self.corrupt_readback:
                result["content"] = "9.9.9.9"
            return {"success": True, "result": result}
        raise AssertionError("unexpected fixed API route")

    def mutations(self):
        return [c for c in self.calls if c[0] in ("POST", "PATCH", "DELETE")]


class FakeProvider:
    def __init__(self, pending=False, outcome="deferred"):
        self.is_pending = pending
        self.outcome = outcome
        self.rotations = []
        self.restored = 0
        self.inbound_calls = 0

    def restore_local_address(self):
        self.restored += 1

    def pending(self):
        return self.is_pending

    def get_inbound_addresses(self):
        self.inbound_calls += 1
        return {"A": "8.8.8.8"}

    def rotate(self, incident_id, verify, commit):
        self.rotations.append(incident_id)
        if self.outcome == "rotated":
            if not verify("9.9.9.9"):
                return {"status": "rolled_back", "code": "verification_failed"}
            if not commit("9.9.9.9"):
                return {"status": "failed", "code": "dns_failed"}
        return {"status": self.outcome, "code": "controlled", "addresses": {"A": "9.9.9.9"}}


class NetworkCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cfg = config()
        self.cf = FakeCF()
        self.clock = NOW
        self.instance = n.Network(self.base / "private" / "network.json", self.base / "state",
                                  transport=self.cf, clock=lambda: self.clock, doctor_fn=lambda fd: True)
        self.info = self.base / "info.json"

    def install(self):
        self.instance.configure(self.cfg, info_path=self.info)

    def test_full_account_token_is_accepted_and_status_redacts_secrets(self):
        self.cfg["notification"] = {"kind": "telegram", "bot_token": "123456:" + "A" * 32, "chat_id": "123"}
        self.cfg["probes"] = probes()
        self.install()
        output = json.dumps(self.instance.status())
        for secret in (self.cfg["cloudflare"]["api_token"], self.cfg["notification"]["bot_token"], KEY):
            self.assertNotIn(secret, output)
        self.assertIn("Full account and zone access", output)
        self.assertEqual(stat.S_IMODE(self.instance.config_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.instance.state_path.stat().st_mode), 0o600)
        self.assertFalse(self.cf.mutations())

    def test_unconfigured_run_does_not_create_state_or_import_provider(self):
        self.assertEqual(self.instance.run(), {"status": "not_configured"})
        self.assertEqual(self.instance.status()["notification"], "not_configured")
        self.assertFalse(self.instance.state_path.exists())
        self.assertEqual(self.cf.calls, [])

    def test_domain_migration_requires_explicit_flag_and_does_not_edit_node(self):
        original = {"domain": "old.sslip.io", "uuid": "unchanged", "key": "must-preserve", "whitelist": ["1"]}
        self.info.write_text(json.dumps(original))
        with self.assertRaisesRegex(n.NetworkError, "domain_change_requires_migration"):
            self.install()
        self.assertFalse(self.instance.config_path.exists())
        self.instance.configure(self.cfg, allow_domain_change=True, info_path=self.info)
        self.assertEqual(json.loads(self.info.read_text()), original)

    def test_zone_account_domain_and_token_validation_precedes_writes(self):
        variants = [
            ("account", {"id": "c" * 32}, "cloudflare_zone_account_mismatch"),
            ("status", "pending", "cloudflare_zone_not_active"),
            ("name", "other.example.org", "domain_outside_selected_zone"),
        ]
        for field, value, error in variants:
            original = copy.deepcopy(self.cf.zone)
            self.cf.zone[field] = value
            with self.assertRaisesRegex(n.NetworkError, error):
                self.install()
            self.cf.zone = original
        self.cf.token_status = "expired"
        with self.assertRaisesRegex(n.NetworkError, "cloudflare_token_inactive"):
            self.install()
        self.assertFalse(self.cf.mutations())
        self.assertFalse(self.instance.config_path.exists())

    def test_consensus_requires_owner_confirmation_and_two_matching_public_ips(self):
        self.cfg["address_source"] = {"mode": "consensus"}
        with self.assertRaisesRegex(n.NetworkError, "inbound_ip_confirmation_required"):
            self.install()
        self.cfg["address_source"]["no_nat_confirmed"] = True
        self.cf.public_ips = ["8.8.8.8", "1.1.1.1"]
        with self.assertRaisesRegex(n.NetworkError, "public_ip_sources_disagree"):
            self.install()
        self.cf.public_ips = ["127.0.0.1", "127.0.0.1"]
        with self.assertRaisesRegex(n.NetworkError, "non_public_ip"):
            self.install()
        self.assertFalse(self.cf.mutations())

    def test_sync_touches_only_selected_a_and_preserves_proxy_ttl_and_aaaa(self):
        ident = self.cf.add(proxied=True, ttl=1, comment="owner comment", tags=["keep"])
        other = self.cf.add(name="other.example.com", content="9.9.9.9")
        ipv6 = self.cf.add(kind="AAAA", content="2606:4700:4700::1111")
        before_other, before_ipv6 = copy.deepcopy(self.cf.rows[other]), copy.deepcopy(self.cf.rows[ipv6])
        self.install()
        result = self.instance.prepare()
        self.assertEqual(result["changed"], ["A"])
        self.assertEqual(self.cf.rows[ident]["content"], "8.8.8.8")
        self.assertEqual(self.cf.rows[ident]["ttl"], 1)
        self.assertTrue(self.cf.rows[ident]["proxied"])
        self.assertEqual(self.cf.rows[ident]["tags"], ["keep"])
        self.assertEqual(self.cf.rows[other], before_other)
        self.assertEqual(self.cf.rows[ipv6], before_ipv6)
        self.assertEqual(self.cf.mutations(), [("PATCH", "/client/v4/zones/" + ZID + "/dns_records/" + ident,
                                               {"content": "8.8.8.8"})])

    def test_dns_preflight_checks_every_family_before_mutating(self):
        self.cf.add()
        self.cf.add(kind="AAAA", content="2606:4700:4700::1111")
        self.cf.add(kind="AAAA", content="2606:4700:4700::1001")
        with self.assertRaisesRegex(n.NetworkError, "multiple_address_records"):
            n.Cloudflare(self.cfg, self.cf).sync({"A": "8.8.8.8", "AAAA": "2001:4860:4860::8888"})
        self.assertFalse(self.cf.mutations())

    def test_cname_is_not_overwritten(self):
        self.cf.add(kind="CNAME", content="other.example.com")
        with self.assertRaisesRegex(n.NetworkError, "domain_has_cname"):
            n.Cloudflare(self.cfg, self.cf).sync({"A": "8.8.8.8"})
        self.assertFalse(self.cf.mutations())

    def test_write_is_not_declared_ready_without_readback(self):
        self.cf.add()
        self.install()
        self.cf.corrupt_readback = True
        with self.assertRaisesRegex(n.NetworkError, "dns_write_readback_mismatch"):
            self.instance.prepare()
        self.assertNotEqual(self.instance.status()["status"], "dns_ready")

    def test_txt_cleanup_deletes_only_owned_exact_challenge(self):
        name, one, two = "_acme-challenge.node.example.com", "A" * 32, "B" * 32
        foreign = self.cf.add(kind="TXT", name=name, content=one)
        unrelated = self.cf.add(kind="TXT", name=name, content="third-party-challenge")
        self.install()
        self.instance.challenge("dns-add", name, one)
        self.instance.challenge("dns-remove", name, one)
        self.assertIn(foreign, self.cf.rows)
        self.instance.challenge("dns-add", name, two)
        owned = [k for k, v in self.cf.rows.items() if v["content"] == two][0]
        self.instance.challenge("dns-remove", name, two)
        self.instance.challenge("dns-remove", name, two)
        self.assertNotIn(owned, self.cf.rows)
        self.assertIn(foreign, self.cf.rows)
        self.assertIn(unrelated, self.cf.rows)

    def test_txt_changed_after_creation_is_never_deleted(self):
        name, value = "_acme-challenge.node.example.com", "A" * 32
        state = {}
        api = n.Cloudflare(self.cfg, self.cf)
        api.dns_add(name, value, state)
        ident = next(iter(self.cf.rows))
        self.cf.rows[ident]["content"] = "owner-edited-value"
        with self.assertRaisesRegex(n.NetworkError, "challenge_record_changed"):
            api.dns_remove(name, value, state)
        self.assertIn(ident, self.cf.rows)

    def test_txt_already_deleted_is_idempotent(self):
        name, value, state = "_acme-challenge.node.example.com", "A" * 32, {}
        api = n.Cloudflare(self.cfg, self.cf)
        api.dns_add(name, value, state)
        self.cf.rows.clear()
        self.assertTrue(api.dns_remove(name, value, state))
        self.assertEqual(state["challenges"], {})

    def test_probe_response_must_bind_domain_nonce_ip_and_fresh_time(self):
        self.cfg["probes"] = probes()
        for field, value in (("domain", "attacker.example.com"), ("nonce", "0" * 32),
                             ("connect_ip", "9.9.9.9"), ("at", NOW - 91)):
            with self.subTest(field=field):
                result = n.probe_results(self.cfg, path="/fixed", now=lambda: NOW,
                                         transport=signer(mutate=lambda out, k=field, v=value: out.update({k: v})))
                self.assertTrue(all(not r["verified"] for r in result))
        result = n.probe_results(self.cfg, now=lambda: NOW, transport=signer())
        self.assertTrue(n.Network.confirmed(result, True))

    def test_unsigned_probes_and_same_region_cannot_authorize_rotation(self):
        self.cfg["probes"] = probes()
        def unsigned(url, value, key):
            result = signer(False)(url, value, key)
            result["signature"] = "0" * 64
            return result
        self.assertFalse(n.Network.confirmed(n.probe_results(self.cfg, transport=unsigned, now=lambda: NOW), False))
        self.cfg["probes"][1]["region"] = "cn-one"
        self.assertFalse(n.Network.confirmed(n.probe_results(self.cfg, transport=signer(False), now=lambda: NOW), False))

    def test_mixed_regional_evidence_cannot_rotate(self):
        results = [{"host": str(i), "region": str(i), "verified": True, "reachable": i == 2} for i in range(3)]
        self.assertFalse(n.Network.confirmed(results, False))

    def test_no_probe_and_local_fault_do_not_rotate(self):
        provider = FakeProvider()
        self.cfg["provider"] = {"kind": "digitalocean"}
        self.instance.provider_factory = lambda *args: provider
        self.install()
        for _ in range(4):
            self.assertEqual(self.instance.run()["status"], "reachability_unconfirmed")
        self.cfg["probes"] = probes()
        n.atomic_private(self.instance.config_path, self.cfg)
        self.instance.probe_transport = signer(False)
        self.instance.doctor_fn = lambda fd: False
        for _ in range(4):
            self.assertEqual(self.instance.run()["status"], "local_service_fault")
        self.assertEqual(provider.rotations, [])
        self.assertGreater(provider.restored, 0)

    def test_three_signed_failures_start_one_incident_and_notices_are_deduplicated(self):
        self.cfg["probes"] = probes()
        self.instance.probe_transport = signer(False)
        provider = FakeProvider()
        self.cfg["provider"] = {"kind": "digitalocean"}
        self.instance.provider_factory = lambda *args: provider
        self.install()
        for _ in range(2):
            self.assertEqual(self.instance.run()["status"], "regional_access_suspected")
        self.assertEqual(provider.rotations, [])
        for _ in range(4):
            self.assertEqual(self.instance.run()["status"], "recovery_deferred")
        self.assertEqual(len(set(provider.rotations)), 1)
        codes = [row["code"] for row in self.instance.state()["events"]]
        self.assertEqual(codes.count("regional_access_failure"), 1)
        self.assertEqual(codes.count("provider_action_required"), 1)

    def test_recovery_clears_incident_and_new_failure_is_new_incident(self):
        self.cfg["probes"] = probes()
        self.instance.probe_transport = signer(False)
        self.install()
        for _ in range(3):
            self.instance.run()
        old = self.instance.state()["incident_id"]
        self.instance.probe_transport = signer(True)
        self.assertEqual(self.instance.run()["status"], "healthy")
        self.assertNotIn("incident_id", self.instance.state())
        self.instance.probe_transport = signer(False)
        for _ in range(3):
            self.instance.run()
        self.assertNotEqual(self.instance.state()["incident_id"], old)

    def test_proxied_domain_never_triggers_origin_rotation(self):
        self.cf.add(proxied=True)
        self.cfg["probes"] = probes()
        self.cfg["provider"] = {"kind": "digitalocean"}
        provider = FakeProvider()
        self.instance.provider_factory = lambda *args: provider
        self.instance.probe_transport = signer(False)
        self.install()
        for _ in range(4):
            result = self.instance.run()
        self.assertEqual(result["status"], "cdn_path_fault_manual_review")
        self.assertEqual(provider.rotations, [])

    def test_pending_provider_transaction_precedes_ddns_and_probe_classification(self):
        self.cf.add()
        provider = FakeProvider(pending=True, outcome="pending")
        self.cfg["provider"] = {"kind": "digitalocean"}
        self.cfg["address_source"] = {"mode": "provider"}
        self.instance.provider_factory = lambda *args: provider
        self.install()
        provider.inbound_calls = 0
        self.cf.calls.clear()
        result = self.instance.run()
        self.assertEqual(result["status"], "recovery_pending")
        self.assertEqual(provider.inbound_calls, 0)
        self.assertEqual(len(provider.rotations), 1)
        self.assertEqual(self.cf.mutations(), [])

    def test_pending_recovery_requires_candidate_verification_before_dns(self):
        provider = FakeProvider(pending=True, outcome="rotated")
        self.cfg["probes"] = probes()
        self.cfg["provider"] = {"kind": "digitalocean"}
        self.instance.provider_factory = lambda *args: provider
        self.instance.probe_transport = signer(False)
        self.install()
        self.assertEqual(self.instance.run()["status"], "recovery_rolled_back")
        self.assertFalse(self.cf.mutations())
        self.instance.probe_transport = signer(True)
        self.assertEqual(self.instance.run()["status"], "recovery_rotated")
        self.assertEqual(self.instance.status()["addresses"]["A"], "9.9.9.9")

    def test_notification_delivery_failure_retries_and_absence_is_honest(self):
        self.install()
        with self.assertRaisesRegex(n.NetworkError, "notification_not_configured"):
            self.instance.notify_test()
        self.cfg["notification"] = {"kind": "telegram", "bot_token": "123456:" + "A" * 32, "chat_id": "123"}
        n.atomic_private(self.instance.config_path, self.cfg)
        self.cf.telegram_ok = False
        self.assertEqual(self.instance.notify_test()["status"], "retry_pending")
        self.assertEqual(self.instance.status()["pending_notifications"], 1)
        self.cf.telegram_ok = True
        state = self.instance.state()
        self.instance.deliver(self.cfg, state)
        self.assertEqual(self.cf.sent, [])
        self.clock += 121
        self.instance.deliver(self.cfg, state)
        self.assertEqual(len(self.cf.sent), 1)
        self.assertEqual(self.instance.status()["pending_notifications"], 0)
        self.assertEqual(self.instance.status()["last_notification"]["status"], "delivered")

    def test_provider_error_does_not_expose_exception_secrets(self):
        class Broken(FakeProvider):
            def pending(self):
                raise RuntimeError("Bearer TOP-SECRET-NOT-FOR-OUTPUT")
        self.cfg["provider"] = {"kind": "digitalocean"}
        self.instance.provider_factory = lambda *args: Broken()
        self.install()
        result = self.instance.run()
        self.assertEqual(result["last_error"], "provider_or_runtime_failed")
        self.assertNotIn("TOP-SECRET", json.dumps(result))
        self.assertNotIn("TOP-SECRET", self.instance.state_path.read_text())

    def test_private_configuration_symlink_and_open_permissions_rejected(self):
        self.install()
        os.chmod(self.instance.config_path, 0o644)
        with self.assertRaisesRegex(n.NetworkError, "private_file_permissions"):
            self.instance.status()
        os.chmod(self.instance.config_path, 0o600)
        link = self.base / "link"
        link.symlink_to(self.instance.config_path)
        with self.assertRaisesRegex(n.NetworkError, "private_file_permissions"):
            n.load_private(link)
        with self.assertRaisesRegex(n.NetworkError, "private_path_symlink"):
            n.atomic_private(link, {})

    def test_automatic_rotation_requires_provider_address_source(self):
        self.cfg["provider"] = {"kind": "digitalocean", "auto_rotate": True}
        with self.assertRaisesRegex(n.NetworkError, "automatic_rotation_requires_provider_address_source"):
            self.install()
        self.assertFalse(self.instance.config_path.exists())

    def test_pending_provider_failure_queues_owner_notice(self):
        provider = FakeProvider(pending=True, outcome="failed")
        self.cfg["provider"] = {"kind": "digitalocean"}
        self.instance.provider_factory = lambda *args: provider
        self.install()
        self.assertEqual(self.instance.run()["status"], "recovery_failed")
        self.assertIn("provider_action_required", [row["code"] for row in self.instance.state()["events"]])

    def test_successful_rotation_waits_for_dns_propagation_before_another_attempt(self):
        provider = FakeProvider(outcome="rotated")
        self.cfg["provider"] = {"kind": "digitalocean"}
        self.cfg["address_source"] = {"mode": "provider"}
        self.cfg["probes"] = probes()
        self.instance.provider_factory = lambda *args: provider
        self.instance.probe_transport = lambda url, value, key: signer(value["connect_ip"] is not None)(url, value, key)
        self.install()
        for _ in range(3):
            result = self.instance.run()
        self.assertEqual(result["status"], "recovery_rotated")
        provider.get_inbound_addresses = lambda: {"A": "9.9.9.9"}
        for _ in range(4):
            result = self.instance.run()
        self.assertEqual(result["status"], "dns_propagating")
        self.assertEqual(len(provider.rotations), 1)
        self.assertEqual(result["addresses"]["A"], "9.9.9.9")
        self.assertEqual(result["failures"], 0)

    def test_aws_menu_uses_hidden_credentials_and_explicit_cost_authorization(self):
        answers = ["123456789012", "us-east-1", "i-0123456789abcdef0", "", "", "y", "1", "20", ""]
        with patch("builtins.input", side_effect=answers), patch.object(n.getpass, "getpass", side_effect=["TESTACCESSID", "TESTSECRETKEY", "TESTSESSION"]) as hidden:
            result = n.interactive_provider("aws_eip")
        self.assertEqual(hidden.call_count, 3)
        self.assertEqual(result["kind"], "aws_eip")
        self.assertEqual(result["max_monthly_ipv4_usd"], 20)
        self.assertTrue(result["allow_downtime"])
        self.assertTrue(result["cleanup_owned_old_ip"])

    def test_provider_menus_expose_hetzner_and_vultr_supported_address_operations(self):
        cases = [
            ("hetzner_floating", ["42", "fsn1", "eth0", "", "y", "1", "6", ""], "allow_floating_ip_allocation"),
            ("vultr", ["00000000-0000-4000-8000-000000000001", "sea", "ens3", "", "y", "1", "6", ""], "allow_reserved_ip_allocation"),
        ]
        for kind, answers, field in cases:
            with self.subTest(kind=kind), patch("builtins.input", side_effect=answers), patch.object(n.getpass, "getpass", return_value="TEST-TOKEN"):
                result = n.interactive_provider(kind)
            self.assertTrue(result[field])
            self.assertTrue(result["allow_guest_network_changes"])
            self.assertEqual(result["interface"], "eth0" if kind == "hetzner_floating" else "ens3")

    def test_local_handshake_binds_installed_domain_and_path_without_public_probe_ssrf(self):
        self.info.write_text(json.dumps({"domain": "node.example.com", "wsPath": "/saved-path"}))
        checks = {"tcp_ok": True, "tls_ok": True, "websocket_ok": True}
        with patch.object(n, "_observe_connection", return_value=checks) as local:
            self.assertTrue(n.local_node_healthy(self.info))
            local.assert_called_once_with("node.example.com", "127.0.0.1", "/saved-path")
        with patch.object(n, "_observe_connection") as remote:
            result = n.observe_target("node.example.com", "127.0.0.1", "/saved-path")
            self.assertFalse(result["tcp_ok"])
            remote.assert_not_called()
        with patch.object(n, "_observe_connection", return_value={**checks, "websocket_ok": False}):
            self.assertFalse(n.local_node_healthy(self.info))

    def test_proxied_records_require_read_only_full_strict_check_before_mutation(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                self.cf = FakeCF()
                if existing:
                    self.cf.add(proxied=True)
                self.cfg["cloudflare"]["proxied"] = not existing
                self.cf.ssl_mode = "flexible"
                with self.assertRaisesRegex(n.NetworkError, "cloudflare_full_strict_required"):
                    n.Cloudflare(self.cfg, self.cf).sync({"A": "8.8.8.8"})
                self.assertFalse(self.cf.mutations())
                self.assertTrue(any(path.endswith("/settings/ssl") for _, path, _ in self.cf.calls))

    def test_dns_only_mode_does_not_require_or_mutate_zone_tls_settings(self):
        self.cf.ssl_mode = "flexible"
        self.cfg["cloudflare"]["proxied"] = False
        n.Cloudflare(self.cfg, self.cf).sync({"A": "8.8.8.8"})
        self.assertFalse(any(path.endswith("/settings/ssl") for _, path, _ in self.cf.calls))


class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "maintenance.lock"
        self.network_path = Path(self.tmp.name) / "network.lock"
        self.clean = patch.dict(os.environ, {"HUARUN_UPDATE_LOCK_FD": "", "HUARUN_NETWORK_LOCK_FD": ""})
        self.clean.start()
        self.addCleanup(self.clean.stop)

    def open_lock(self, path, mode):
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, mode | fcntl.LOCK_NB)
        self.addCleanup(os.close, fd)
        return fd

    def test_chat_shared_lock_allows_network_and_network_blocks_updater(self):
        self.open_lock(self.path, fcntl.LOCK_SH)
        with n.MaintenanceLock(self.path, self.network_path) as lock:
            self.assertFalse(lock.inherited)
            self.assertIsNotNone(lock.network_fd)
            another = os.open(self.path, os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(another, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(another)

    def test_network_mutations_are_serialized(self):
        with n.MaintenanceLock(self.path, self.network_path):
            with self.assertRaisesRegex(n.NetworkError, "maintenance_busy"):
                with n.MaintenanceLock(self.path, self.network_path):
                    pass

    def test_updater_excludes_network(self):
        self.open_lock(self.path, fcntl.LOCK_EX)
        with self.assertRaisesRegex(n.NetworkError, "maintenance_busy"):
            with n.MaintenanceLock(self.path, self.network_path):
                pass

    def test_verified_inherited_descriptors_support_nested_migration(self):
        parent = self.open_lock(self.path, fcntl.LOCK_EX)
        with patch.dict(os.environ, {"HUARUN_UPDATE_LOCK_FD": str(parent)}):
            with n.MaintenanceLock(self.path, self.network_path) as first:
                self.assertTrue(first.inherited)
                with patch.dict(os.environ, {"HUARUN_NETWORK_LOCK_FD": str(first.network_fd)}):
                    with n.MaintenanceLock(self.path, self.network_path) as nested:
                        self.assertEqual(nested.network_fd, first.network_fd)
                        self.assertTrue(nested.network_inherited)
            self.assertTrue(os.fstat(parent))

    def test_fake_inherited_descriptor_does_not_bypass_lock(self):
        self.open_lock(self.path, fcntl.LOCK_EX)
        other = self.open_lock(Path(self.tmp.name) / "other", fcntl.LOCK_EX)
        with patch.dict(os.environ, {"HUARUN_UPDATE_LOCK_FD": str(other)}):
            with self.assertRaisesRegex(n.NetworkError, "maintenance_busy"):
                with n.MaintenanceLock(self.path, self.network_path):
                    pass


class ProbeServerTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def observer(domain, ip, path):
            self.calls.append((domain, ip, path))
            return {"tcp_ok": True, "tls_ok": True, "websocket_ok": True}
        handler = n.make_probe_handler({"domain": "node.example.com", "key": KEY, "path": "/fixed"},
                                       observer=observer, clock=lambda: NOW)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def send(self, value, signature=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            headers = {"Content-Type": "application/json"}
            if signature:
                headers["X-HuaRun-Signature"] = n.probe_signature(KEY, value)
            connection.request("POST", "/probe", n.encoded(value), headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def value(self):
        return {"schema_version": 1, "domain": "node.example.com", "connect_ip": "8.8.8.8",
                "path": "/fixed", "at": NOW, "nonce": os.urandom(16).hex()}

    def test_real_http_signed_exchange_and_replay_rejection(self):
        value = self.value()
        status, raw = self.send(value)
        self.assertEqual(status, 200)
        body = json.loads(raw)
        self.assertEqual(body["signature"], n.probe_signature(KEY, body["result"]))
        self.assertEqual(body["result"]["connect_ip"], "8.8.8.8")
        self.assertEqual(self.send(value)[0], 403)
        self.assertEqual(len(self.calls), 1)

    def test_unsigned_wrong_target_private_ip_and_stale_requests_never_probe(self):
        self.assertEqual(self.send(self.value(), False)[0], 403)
        for field, value in (("domain", "other.example.com"), ("path", "/other"),
                             ("connect_ip", "127.0.0.1"), ("at", NOW - 100)):
            data = self.value()
            data[field] = value
            self.assertEqual(self.send(data)[0], 403)
        self.assertEqual(self.calls, [])


class FixedTransportTests(unittest.TestCase):
    def test_secrets_are_never_redirected_and_unknown_upstreams_rejected(self):
        with self.assertRaisesRegex(n.NetworkError, "redirect_rejected"):
            n.NoRedirect().redirect_request(None, None, 302, "", {}, "https://attacker.example.com")
        with self.assertRaisesRegex(n.NetworkError, "upstream_not_allowed"):
            n.request("GET", "https://api.cloudflare.com.attacker.example.com/client/v4/zones",
                      headers={"Authorization": "Bearer never-send"})
        with self.assertRaisesRegex(n.NetworkError, "upstream_not_allowed"):
            n.request("POST", "https://attacker.example.com/sendMessage", {})

    def test_doctor_requires_all_checks_including_tls_and_does_not_invent_success(self):
        class Result:
            returncode = 0
            stdout = json.dumps({"all_ok": True, "checks": {key: {"ok": True} for key in n.DOCTOR_CHECKS}})
        with patch.object(n, "local_node_healthy", return_value=True):
            self.assertTrue(n.doctor(runner=lambda *args, **kwargs: Result()))
        with patch.object(n, "local_node_healthy", return_value=False):
            self.assertFalse(n.doctor(runner=lambda *args, **kwargs: Result()))
        Result.stdout = json.dumps({"all_ok": True, "checks": {}})
        self.assertFalse(n.doctor(runner=lambda *args, **kwargs: Result()))


if __name__ == "__main__":
    unittest.main()
