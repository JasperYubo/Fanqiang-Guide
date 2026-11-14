"""Offline behavior tests for the HuaRun installer and generated management tools.

All generated files, downloaded fixtures and command side effects stay in temporary
folders. No network calls, service operations, package installs or root setup occur.
"""
import base64
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


def heredoc(source, delimiter):
    match = re.search(r"<<\s*'" + re.escape(delimiter) + r"'\s*\n(.*?)^" + re.escape(delimiter) + r"\s*$", source, re.M | re.S)
    if not match:
        raise AssertionError(f"Missing generated {delimiter} payload")
    return match.group(1)


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = INSTALLER.read_text()
        # Source only a file whose execution is explicitly guarded. This suite never
        # runs the installer main on the test host with its real mutation functions.
        if not re.search(r'if\s+\[\[\s*["\']?\$\{BASH_SOURCE\[0\]\}["\']?\s*==\s*["\']?\$0', cls.source):
            raise AssertionError("install.sh needs a BASH_SOURCE guard before it can be sourced in tests")
        cls.manager = heredoc(cls.source, "MGRSCRIPT")
        cls.gate = heredoc(cls.source, "GATEEOF")
        dispatch = re.search(r'^manager_main\s*\(\)\s*\{', cls.manager, re.M) or re.search(r'^case\s+"\$\{1:-\}"\s+in', cls.manager, re.M)
        if not dispatch:
            raise AssertionError("Missing manager command dispatch boundary")
        cls.manager_library = cls.manager[:dispatch.start()]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="huarun-unit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager_path = self.root / "manager.sh"
        self.manager_path.write_text(self.manager_library)
        self.gate_path = self.root / "gate.py"
        self.gate_path.write_text(self.gate)

    def run_shell(self, body, *, manager=False, env=None):
        path = self.manager_path if manager else INSTALLER
        script = f"source {shlex.quote(str(path))}\nset +e\n" + body
        values = {**os.environ, "HUARUN_API_KEY": "", "TEST_DIR": str(self.root)}
        values.pop("AI_KEY", None)
        if env:
            values.update(env)
        return subprocess.run(["bash", "-c", script], text=True, capture_output=True,
                              env=values, timeout=15, input="")

    def gate_request(self, command=None, **arguments):
        if command is not None:
            arguments["command"] = command
        request = {"jsonrpc": "2.0", "id": 1, "method": "hook.approve_tool",
                   "params": {"tool": "exec", "arguments": {"action": "run", **arguments}}}
        result = subprocess.run(["python3", str(self.gate_path)], input=json.dumps(request) + "\n",
                                text=True, capture_output=True, timeout=5, check=True)
        return json.loads(result.stdout)["result"]

    def test_installer_and_generated_manager_shell_syntax(self):
        result = subprocess.run(["bash", "-n", str(INSTALLER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.root / "full-manager.sh"
        generated.write_text(self.manager)
        result = subprocess.run(["bash", "-n", str(generated)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        compile(self.gate, "gate.py", "exec")

    def test_missing_key_fails_before_network(self):
        result = self.run_shell('''
OPT_YES=1
curl() { echo CURL_MUST_NOT_RUN; return 99; }
askKey
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("CURL_MUST_NOT_RUN", result.stdout + result.stderr)

    def test_invalid_key_format_fails_without_request_or_secret_leak(self):
        secret = "invalid-KEY-SECRET-12345"
        result = self.run_shell('''
OPT_YES=1
curl() { echo CURL_MUST_NOT_RUN; return 99; }
askKey
''', env={"HUARUN_API_KEY": secret})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertNotIn("CURL_MUST_NOT_RUN", result.stdout + result.stderr)

    def test_rejected_api_key_does_not_leak_or_pass(self):
        secret = "sk-rejected-SECRET-12345"
        result = self.run_shell('''
OPT_YES=1
curl() { cat >/dev/null; printf '{"error":{"message":"unauthorized"}}\\n401'; }
askKey
''', env={"HUARUN_API_KEY": secret})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_api_key_uses_stdin_and_clears_inherited_export_attribute(self):
        secret = "sk-valid-SECRET-12345"
        result = self.run_shell('''
OPT_YES=1
curl() {
    printf '%s\\n' "$@" > "$TEST_DIR/curl-args"
    cat > "$TEST_DIR/curl-config"
    env > "$TEST_DIR/child-env"
    printf '{"data":[{"id":"deepseek-flash"}]}\\n200'
}
askKey
''', env={"HUARUN_API_KEY": secret, "AI_KEY": ""})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.assertNotIn(secret, (self.root / "curl-args").read_text())
        self.assertNotIn(secret, (self.root / "child-env").read_text())
        self.assertIn(secret, (self.root / "curl-config").read_text())

    def test_gate_allows_bounded_operational_commands(self):
        for command in ["huarun doctor --json", "huarun status --json", "huarun info --json",
                        "huarun fix", "huarun logs 50", "huarun whitelist add example.com", "free -m"]:
            with self.subTest(command=command):
                self.assertTrue(self.gate_request(command)["approved"])

    def test_gate_blocks_shell_injection_and_destructive_or_recursive_commands(self):
        commands = ["huarun fix; id", "huarun info --json && env", "$(id)", "bash -c id",
                    "huarun uninstall --yes", "huarun whitelist clear --yes", "huarun whitelist reset",
                    "huarun assistant setup", "huarun assistant remove", "huarun chat",
                    "huarun whitelist add example.com;id", "huarun fix\nwhoami"]
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(self.gate_request(command)["approved"])

    def test_gate_blocks_background_pty_and_directory_override(self):
        for options in [{"background": True}, {"background": "true"}, {"pty": True},
                        {"cwd": "/etc"}, {"action": "start"}]:
            with self.subTest(options=options):
                self.assertFalse(self.gate_request("huarun fix", **options)["approved"])

    def test_connection_link_contains_importable_tls_transport(self):
        result = self.run_shell('''
DOMAIN=example.com
UUID=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
WS_PATH=/fixture123
vmessLink
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        link = result.stdout.strip()
        self.assertTrue(link.startswith("vmess://"))
        config = json.loads(base64.b64decode(link.removeprefix("vmess://")))
        self.assertEqual(config["add"], "example.com")
        self.assertEqual(config["port"], "443")
        self.assertEqual(config["id"], "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        self.assertEqual(config["path"], "/fixture123")
        self.assertEqual(config["net"], "ws")
        self.assertEqual(config["tls"], "tls")

    def test_default_domain_rules_are_unique_and_include_core_platforms(self):
        result = self.run_shell('domainJson')
        self.assertEqual(result.returncode, 0, result.stderr)
        domains = json.loads("[" + result.stdout.strip() + "]")
        self.assertEqual(len(domains), len(set(domains)))
        self.assertGreaterEqual(len(domains), 380)
        for name in ["domain:google.com", "domain:youtube.com", "domain:x.com", "domain:amazon.com"]:
            self.assertIn(name, domains)


    def update_fixture(self, *, install_exit=0, restart_exit=0, active_exit=0, download_exit=0):
        self.root.joinpath("xray").write_text("#!/bin/sh\nprintf 'Xray 99.1.0 (fixture)\\n'\n")
        self.root.joinpath("xray").chmod(0o755)
        return self.run_shell(r'''
XRAY_BIN="$TEST_DIR/xray"
curl() {
    [ "$DOWNLOAD_EXIT" = 0 ] || return "$DOWNLOAD_EXIT"
    while [ "$#" -gt 0 ]; do
        if [ "$1" = -o ]; then
            shift
            printf '#!/bin/sh\nexit %s\n' "$INSTALL_EXIT" > "$1"
        fi
        shift
    done
}
sha256sum() { cat >/dev/null; return 0; }
systemctl() {
    printf '%s\n' "$*" >> "$TEST_DIR/systemctl-calls"
    case "$1" in
        restart) return "$RESTART_EXIT" ;;
        is-active) return "$ACTIVE_EXIT" ;;
    esac
    return 0
}
update_xray
''', manager=True, env={"INSTALL_EXIT": str(install_exit), "RESTART_EXIT": str(restart_exit),
                        "ACTIVE_EXIT": str(active_exit), "DOWNLOAD_EXIT": str(download_exit)})

    def test_update_failure_does_not_restart_or_report_success(self):
        result = self.update_fixture(install_exit=17)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("已更新到", result.stdout)
        self.assertFalse((self.root / "systemctl-calls").exists())

    def test_update_restart_failure_returns_nonzero(self):
        result = self.update_fixture(restart_exit=9)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("已更新到", result.stdout)

    def test_update_inactive_service_returns_nonzero(self):
        result = self.update_fixture(active_exit=3)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("已更新到", result.stdout)

    def test_successful_update_reports_verified_version(self):
        result = self.update_fixture()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("99.1.0", result.stdout)

    def test_update_download_failure_does_not_restart(self):
        result = self.update_fixture(download_exit=22)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("已更新到", result.stdout)
        self.assertFalse((self.root / "systemctl-calls").exists())

    def routing_fixture(self, action, domains="example.com\n", validate_exit=0, restart_exit=0):
        self.root.joinpath("whitelist").write_text(domains)
        self.root.joinpath("xray-config.json").write_text(json.dumps({
            "inbounds": [], "outbounds": [{"tag": "direct", "protocol": "freedom"},
                                          {"tag": "blocked", "protocol": "blackhole"}],
            "routing": {"rules": []}}))
        self.root.joinpath("xray").write_text("#!/bin/sh\nexit \"$VALIDATE_EXIT\"\n")
        self.root.joinpath("xray").chmod(0o755)
        return self.run_shell(r'''
WHITELIST="$TEST_DIR/whitelist"
XRAY_CFG="$TEST_DIR/xray-config.json"
XRAY_BIN="$TEST_DIR/xray"
systemctl() { return "$RESTART_EXIT"; }
''' + action, manager=True, env={"VALIDATE_EXIT": str(validate_exit), "RESTART_EXIT": str(restart_exit)})

    def test_whitelist_routes_allowed_domain_and_rejects_other_destinations(self):
        result = self.routing_fixture("rebuild_routing")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rules = json.loads((self.root / "xray-config.json").read_text())["routing"]["rules"]
        self.assertEqual(rules[0]["domain"], ["domain:example.com"])
        self.assertEqual(rules[0]["outboundTag"], "direct")
        self.assertEqual(rules[-1]["outboundTag"], "blocked")
        self.assertEqual(rules[-1]["port"], "0-65535")

    def test_failed_routing_validation_preserves_installed_config(self):
        result = self.routing_fixture("rebuild_routing", validate_exit=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads((self.root / "xray-config.json").read_text())["routing"]["rules"], [])

    def test_whitelist_add_is_normalized_and_deduplicated(self):
        result = self.routing_fixture('wl_add HTTPS://WWW.NewDomain.COM/path; wl_add newdomain.com')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        domains = (self.root / "whitelist").read_text().splitlines()
        self.assertEqual(domains, ["example.com", "newdomain.com"])

    def test_whitelist_invalid_domain_does_not_change_file(self):
        result = self.routing_fixture("wl_add not_a_domain")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "whitelist").read_text(), "example.com\n")

    def test_whitelist_removal_validation_failure_preserves_whitelist(self):
        result = self.routing_fixture("wl_remove example.com", domains="example.com\nsecond.example\n", validate_exit=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "whitelist").read_text(), "example.com\nsecond.example\n")

    def test_last_whitelist_entry_is_not_silently_retained(self):
        result = self.routing_fixture("wl_remove example.com")
        # The product can reject an empty whitelist, or remove it explicitly;
        # it must never report success while leaving the requested entry intact.
        if result.returncode == 0:
            self.assertNotIn("example.com", (self.root / "whitelist").read_text().splitlines())
            rules = json.loads((self.root / "xray-config.json").read_text())["routing"]["rules"]
            self.assertEqual(rules, [{"type": "field", "port": "0-65535", "outboundTag": "blocked"}])
        else:
            self.assertEqual((self.root / "whitelist").read_text(), "example.com\n")

    def test_main_rejects_missing_key_before_any_mutating_step(self):
        result = self.run_shell(r'''
checkSystem() { return 0; }
checkConflicts() { return 0; }
curl() { echo UNEXPECTED_NETWORK; return 99; }
mkdir() { echo UNEXPECTED_MUTATION; return 98; }
cp() { echo UNEXPECTED_MUTATION; return 98; }
preflight() { echo UNEXPECTED_MUTATION; return 98; }
installDeps() { echo UNEXPECTED_MUTATION; return 98; }
set -e
main --yes --domain example.com
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("UNEXPECTED_MUTATION", result.stdout + result.stderr)
        self.assertNotIn("UNEXPECTED_NETWORK", result.stdout + result.stderr)

    def test_reinstall_refuses_and_preserves_existing_information(self):
        self.root.joinpath("existing-info.json").write_text('{"uuid":"preserve-me"}')
        result = self.run_shell(r'''
INFO_FILE="$TEST_DIR/existing-info.json"
checkConflicts
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.root.joinpath("existing-info.json").read_text(), '{"uuid":"preserve-me"}')

    def test_existing_nginx_is_not_taken_over(self):
        result = self.run_shell(r'''
INFO_FILE="$TEST_DIR/missing-info.json"
command() {
    if [ "$1" = -v ] && [ "$2" = nginx ]; then
        printf '/usr/sbin/nginx\n'
        return 0
    fi
    builtin command "$@"
}
checkConflicts
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("nginx", (result.stdout + result.stderr).lower())

    def test_occupied_https_port_is_not_taken_over(self):
        result = self.run_shell(r'''
INFO_FILE="$TEST_DIR/missing-info.json"
command() {
    if [ "$1" = -v ] && { [ "$2" = nginx ] || [ "$2" = xray ]; }; then
        return 1
    fi
    builtin command "$@"
}
ss() { printf 'LISTEN 0 128 0.0.0.0:443 0.0.0.0:*\n'; }
checkConflicts
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("443", result.stdout + result.stderr)

    def test_model_missing_from_api_is_rejected_before_installation(self):
        result = self.run_shell(r'''
OPT_YES=1
curl() { cat >/dev/null; printf '{"data":[{"id":"unrelated-model"}]}\n200'; }
askKey
''', env={"HUARUN_API_KEY": "sk-valid-SECRET-12345"})
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("sk-valid-SECRET-12345", result.stdout + result.stderr)

    def doctor_fixture(self, dns):
        self.root.joinpath("info.json").write_text(json.dumps({"domain": "cdn.example", "ip": "203.0.113.10"}))
        self.root.joinpath("cron").write_text("23 3 * * * root /usr/local/bin/acme.sh --cron\n")
        return self.run_shell(r'''
INFO_FILE="$TEST_DIR/info.json"
CRON_FILE="$TEST_DIR/cron"
XRAY_BIN=/bin/true
XRAY_CFG="$TEST_DIR/unused.json"
cert_days() { printf 90; }
systemctl() { [[ "$*" != *firewalld* ]]; }
ss() { printf 'LISTEN 0 128 0.0.0.0:443 0.0.0.0:*\n'; }
nginx() { return 0; }
which() { [[ "$1" != ufw ]] && builtin command -v "$1"; }
getent() { [[ -n "$FIXTURE_DNS" ]] && printf '%s STREAM cdn.example\n' "$FIXTURE_DNS"; }
run_doctor --json
''', manager=True, env={"FIXTURE_DNS": dns})

    def test_cdn_dns_different_from_origin_is_not_false_failure(self):
        result = self.doctor_fixture("198.51.100.77")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["checks"]["dns"]["ok"])
        self.assertEqual(report["scope"], "server")
        self.assertEqual(report["client_connectivity"], "not_tested")

    def test_unresolvable_domain_is_reported_as_dns_failure(self):
        result = self.doctor_fixture("")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["checks"]["dns"]["ok"])
        self.assertFalse(report["all_ok"])

    def test_failed_route_restart_restores_config_and_whitelist(self):
        result = self.routing_fixture("wl_add newdomain.example", restart_exit=1)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "whitelist").read_text(), "example.com\n")
        self.assertEqual(json.loads((self.root / "xray-config.json").read_text())["routing"]["rules"], [])

if __name__ == "__main__":
    unittest.main()
