"""Exit selection preserves node identity and whitelist under success/failure."""
import contextlib
import copy
import hashlib
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
import egress as e


def xray_config():
    return {
        "inbounds": [{"tag": "node", "protocol": "vmess", "listen": "127.0.0.1", "port": 10086,
                      "settings": {"clients": [{"id": "00000000-0000-4000-8000-000000000001"}]},
                      "streamSettings": {"network": "ws", "wsSettings": {"path": "/keep-this-path"}}}],
        "outbounds": [{"tag": "direct", "protocol": "freedom"},
                      {"tag": "blocked", "protocol": "blackhole"}],
        "routing": {"domainStrategy": "AsIs", "rules": [
            {"type": "field", "ip": ["geoip:private"], "outboundTag": "blocked"},
            {"type": "field", "domain": ["domain:example.com", "domain:cloudflare.com"], "outboundTag": "direct"},
            {"type": "field", "port": "0-65535", "outboundTag": "blocked"}]},
        "dns": {"servers": ["1.1.1.1"]},
    }


def upstream(protocol="socks5"):
    return {"protocol": protocol, "host": "127.0.0.1", "port": 1080,
            "username": "fixture-user", "password": "fixture-private-password"}


class EgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config, self.xray, self.state = self.root / "egress.json", self.root / "xray.json", self.root / "state"
        self.original = xray_config()
        self.original_bytes = (json.dumps(self.original, indent=2) + "\n").encode()
        e.write(self.xray, self.original_bytes, 0o640)
        self.calls, self.checked, self.probed = [], [], []
        self.fail_restart = False
        self.fail_node = False
        def runner(args, **kwargs):
            self.calls.append(args)
            class Result:
                returncode = 0
            if args == ["systemctl", "restart", "xray"] and self.fail_restart:
                self.fail_restart = False
                Result.returncode = 1
            return Result()
        def check(path):
            self.checked.append(json.loads(path.read_bytes()))
        def probe(value):
            self.probed.append(value)
            return {"ok": True, "exit_ip": "8.8.8.8"}
        def node_probe():
            if self.fail_node:
                return {"ok": False}
            return {"ok": True, "exit_ip": "8.8.8.8", "transport": "tcp"}
        self.manager = e.Egress(config=self.config, state=self.state, xray=self.xray, runner=runner,
                               probe=probe, node_probe=node_probe, lock=contextlib.nullcontext, check=check,
                               identity_fn=lambda: (os.geteuid(), os.getegid(), 0o600))

    def test_profile_credentials_are_private_and_absent_from_status(self):
        self.manager.add("residential", upstream())
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        output = json.dumps(self.manager.status())
        self.assertNotIn("fixture-private-password", output)
        self.assertNotIn("fixture-user", output)
        self.assertEqual(self.manager.status()["profiles"], [{"name": "residential", "protocol": "socks5"}])

    def test_selected_exit_preserves_inbounds_whitelist_and_default_deny(self):
        self.manager.add("residential", upstream())
        self.assertEqual(self.manager.use("residential")["status"], "verified")
        actual = json.loads(self.xray.read_bytes())
        self.assertEqual(actual["inbounds"], self.original["inbounds"])
        self.assertEqual(actual["dns"], self.original["dns"])
        self.assertEqual(actual["routing"]["rules"][0], self.original["routing"]["rules"][0])
        self.assertEqual(actual["routing"]["rules"][-1], self.original["routing"]["rules"][-1])
        self.assertEqual(actual["routing"]["rules"][1]["domain"], self.original["routing"]["rules"][1]["domain"])
        self.assertEqual(actual["routing"]["rules"][1]["outboundTag"], e.TAG)
        self.assertFalse(self.manager.status()["fallback_to_direct"])
        self.assertEqual(len(self.probed), 1)
        self.assertFalse(self.manager.journal.exists())

    def test_switch_to_direct_requires_explicit_use_and_keeps_policy(self):
        self.manager.add("residential", upstream())
        self.manager.use("residential")
        self.manager.use("direct")
        self.assertEqual(json.loads(self.xray.read_bytes()), self.original)
        self.assertEqual(self.manager.status()["active"], "direct")

    def test_restart_failure_restores_original_exact_bytes_and_permissions(self):
        self.manager.add("residential", upstream())
        self.fail_restart = True
        with self.assertRaisesRegex(e.EgressError, "exit_change_failed_rolled_back"):
            self.manager.use("residential")
        self.assertEqual(self.xray.read_bytes(), self.original_bytes)
        self.assertEqual(stat.S_IMODE(self.xray.stat().st_mode), 0o640)
        self.assertEqual((self.xray.stat().st_uid,self.xray.stat().st_gid),(os.geteuid(),os.getegid()))
        self.assertFalse(self.manager.journal.exists())

    def test_installed_node_failure_rolls_back_even_when_upstream_works(self):
        self.manager.add("residential", upstream())
        self.fail_node = True
        with self.assertRaisesRegex(e.EgressError, "exit_change_failed_rolled_back"):
            self.manager.use("residential")
        self.assertEqual(self.xray.read_bytes(), self.original_bytes)

    def test_upstream_failure_never_mutates_installed_configuration(self):
        self.manager.add("residential", upstream())
        def failed(_):
            raise e.EgressError("exit_connectivity_failed")
        self.manager.probe = failed
        with self.assertRaisesRegex(e.EgressError, "exit_connectivity_failed"):
            self.manager.use("residential")
        self.assertEqual(self.xray.read_bytes(), self.original_bytes)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.manager.journal.exists())

    def test_pending_recovery_requires_integrity_checked_backup(self):
        e.write(self.manager.journal, {"schema_version": 1, "before_sha256": hashlib.sha256(b"original").hexdigest(),
                                       "mode": 0o600, "previous_status": {}})
        e.write(self.manager.backup, b"tampered")
        with self.assertRaisesRegex(e.EgressError, "recovery_backup_mismatch"):
            self.manager.recover()
        self.assertTrue(self.manager.journal.exists())
        self.assertEqual(self.xray.read_bytes(), self.original_bytes)

    def test_recovery_restores_previous_proxy_state(self):
        self.manager.add("first", upstream())
        self.manager.use("first")
        before_bytes = self.xray.read_bytes()
        before_status = e.load(self.manager.status_path)
        self.manager.add("second", upstream("http-connect"))
        self.fail_restart = True
        with self.assertRaises(e.EgressError):
            self.manager.use("second")
        self.assertEqual(self.xray.read_bytes(), before_bytes)
        self.assertEqual(e.load(self.manager.status_path), before_status)
        self.assertEqual(self.manager.status()["active"], "first")

    def test_configuration_without_default_deny_is_refused(self):
        bad = copy.deepcopy(self.original)
        bad["routing"]["rules"].pop()
        with self.assertRaisesRegex(e.EgressError, "whitelist_default_deny_missing"):
            e.patch_configuration(bad, upstream())
        self.assertEqual(self.original, xray_config())

    def test_invalid_profiles_and_tls_without_verification_are_refused(self):
        for change in ({"host": "bad/host"}, {"port": 0}, {"username": ""},
                       {"password": "bad\nvalue"}, {"protocol": "unknown"},
                       {"protocol": "socks5", "tls": True}):
            value = upstream()
            value.update(change)
            with self.subTest(change=change), self.assertRaises(e.EgressError):
                e.profile(value)
        secure = e.outbound({**upstream("http-connect"), "tls": True})
        self.assertFalse(secure["streamSettings"]["tlsSettings"]["allowInsecure"])

    def test_probe_node_uses_saved_uuid_path_and_tls_name(self):
        info = self.root / "info.json"
        e.write(info, {"uuid": "kept-node-id", "domain": "node.example.com", "wsPath": "/old-path",
                       "deepseek_key": "must-not-be-read-or-exported"})
        observed = []
        def capture(out, node=False):
            observed.append((out, node))
            return {"ok": True}
        with patch.object(e, "run_probe", capture):
            e.probe_node(info)
        value, through_node = observed[0]
        self.assertTrue(through_node)
        self.assertEqual(value["settings"]["vnext"][0]["users"][0]["id"], "kept-node-id")
        self.assertEqual(value["streamSettings"]["wsSettings"]["path"], "/old-path")
        self.assertEqual(value["streamSettings"]["tlsSettings"]["serverName"], "node.example.com")
        self.assertNotIn("must-not-be-read-or-exported", json.dumps(value))

    def test_apply_uses_service_readable_identity_and_journals_original_metadata(self):
        self.manager.add("residential",upstream())
        seen=[]
        real_install=e.install_xray_config
        def capture(path,raw,**metadata):
            seen.append(metadata)
            return real_install(path,raw,**metadata)
        self.fail_restart=True
        with patch.object(e,"install_xray_config",capture):
            with self.assertRaises(e.EgressError):
                self.manager.use("residential")
        self.assertEqual(seen,[{"uid":os.geteuid(),"gid":os.getegid(),"mode":0o600},
                               {"uid":os.geteuid(),"gid":os.getegid(),"mode":0o640}])
        self.assertEqual(self.xray.read_bytes(),self.original_bytes)

    def test_service_identity_failure_leaves_original_config_and_no_journal(self):
        self.manager.add("residential",upstream())
        def unavailable():raise e.EgressError("xray_service_identity_unavailable")
        self.manager.identity_fn=unavailable
        with self.assertRaisesRegex(e.EgressError,"xray_service_identity_unavailable"):
            self.manager.use("residential")
        self.assertEqual(self.xray.read_bytes(),self.original_bytes)
        self.assertFalse(self.manager.journal.exists())

    def test_atomic_helper_installs_metadata_before_replacing_destination(self):
        observed=[];replace=os.replace
        def inspect(source,destination):
            info=os.stat(source)
            observed.append((info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode)))
            replace(source,destination)
        with patch.object(e.os,"replace",inspect):
            e.install_xray_config(self.xray,b"fixture-private",uid=os.geteuid(),gid=os.getegid(),mode=0o640)
        self.assertEqual(observed,[(os.geteuid(),os.getegid(),0o640)])
        self.assertEqual(self.xray.read_bytes(),b"fixture-private")
        with self.assertRaisesRegex(e.EgressError,"xray_configuration_metadata_invalid"):
            e.install_xray_config(self.xray,b"bad",uid=-1,gid=os.getegid(),mode=0o600)
        self.assertEqual(self.xray.read_bytes(),b"fixture-private")

    def test_legacy_journal_recovers_with_service_identity(self):
        raw=self.xray.read_bytes()
        e.write(self.manager.backup,raw)
        e.write(self.manager.journal,{"schema_version":1,"before_sha256":hashlib.sha256(raw).hexdigest(),
                                     "mode":0o644,"previous_status":{}})
        e.write(self.xray,b"changed")
        self.assertEqual(self.manager.recover()["status"],"rolled_back")
        self.assertEqual(self.xray.read_bytes(),raw)
        self.assertEqual(stat.S_IMODE(self.xray.stat().st_mode),0o600)


class ServiceIdentityTests(unittest.TestCase):
    def runner(self,values,commands):
        def run(args):
            commands.append(args)
            key=args[3].split("=",1)[1]
            return types.SimpleNamespace(returncode=0,stdout=(values.get(key,"")+"\n").encode())
        return run

    def test_nobody_without_explicit_group_uses_its_primary_group(self):
        calls=[]
        with patch.object(e.pwd,"getpwnam",return_value=types.SimpleNamespace(pw_uid=65534,pw_gid=65534)) as lookup:
            self.assertEqual(e.xray_config_identity(self.runner({"User":"nobody","DynamicUser":"no"},calls)),(0,65534,0o640))
        lookup.assert_called_once_with("nobody")
        self.assertEqual(calls,[["systemctl","show","xray.service","--property="+key,"--value"]
                                for key in ("User","Group","DynamicUser")])

    def test_explicit_group_overrides_user_primary_group(self):
        calls=[]
        with patch.object(e.pwd,"getpwnam",return_value=types.SimpleNamespace(pw_uid=1001,pw_gid=1002)), patch.object(e.grp,"getgrnam",return_value=types.SimpleNamespace(gr_gid=2001)):

            self.assertEqual(e.xray_config_identity(self.runner({"User":"xray","Group":"proxyread","DynamicUser":"no"},calls)),
                             (0,2001,0o640))

    def test_empty_user_defaults_to_private_root_configuration(self):
        calls=[]
        with patch.object(e.pwd,"getpwnam",return_value=types.SimpleNamespace(pw_uid=0,pw_gid=0)) as lookup:
            self.assertEqual(e.xray_config_identity(self.runner({},calls)),(0,0,0o600))
        lookup.assert_called_once_with("root")

    def test_numeric_identity_and_numeric_explicit_group(self):
        calls=[]
        with patch.object(e.pwd,"getpwuid",return_value=types.SimpleNamespace(pw_uid=1001,pw_gid=1002)) as lookup:
            self.assertEqual(e.xray_config_identity(self.runner({"User":"1001","Group":"1003"},calls)),(0,1003,0o640))
        lookup.assert_called_once_with(1001)

    def test_unknown_identity_dynamic_identity_and_systemctl_failure_fail_closed(self):
        with patch.object(e.pwd,"getpwnam",side_effect=KeyError("unknown")):
            with self.assertRaisesRegex(e.EgressError,"xray_service_identity_invalid"):
                e.xray_config_identity(self.runner({"User":"missing"},[]))
        with self.assertRaisesRegex(e.EgressError,"xray_dynamic_identity_unsupported"):
            e.xray_config_identity(self.runner({"User":"xray","DynamicUser":"yes"},[]))
        with self.assertRaisesRegex(e.EgressError,"xray_service_identity_unavailable"):
            e.xray_config_identity(lambda args:types.SimpleNamespace(returncode=1,stdout=b""))


if __name__ == "__main__":
    unittest.main()
