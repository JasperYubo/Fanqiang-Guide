"""Offline behavior tests for the HuaRun installer and generated management tools.

All generated files, downloaded fixtures and command side effects stay in temporary
folders. No network calls, service operations, package installs or root setup occur.
"""
import base64
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import stat
import time
import unittest

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


def heredoc(source, delimiter):
    match = re.search(r"<<\s*'" + re.escape(delimiter) + r"'[ \t]*(?:\|\|[ \t]*return[ \t]+1)?[ \t]*\n(.*?)^" + re.escape(delimiter) + r"\s*$", source, re.M | re.S)
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

    def run_shell(self, body, *, manager=False, env=None, pass_fds=()):
        path = self.manager_path if manager else INSTALLER
        script = f"source {shlex.quote(str(path))}\nset +e\n" + body
        values = {**os.environ, "HUARUN_API_KEY": "", "TEST_DIR": str(self.root)}
        values.pop("AI_KEY", None)
        if env:
            values.update(env)
        return subprocess.run(["bash", "-c", script], text=True, capture_output=True,
                              env=values, timeout=15, input="", pass_fds=pass_fds)

    def gate_request(self, command=None, **arguments):
        if command is not None:
            arguments["command"] = command
        namespace = {"__name__": "test_generated_hook", "__file__": str(self.gate_path)}
        exec(compile(self.gate, str(self.gate_path), "exec"), namespace)
        class EvidenceClient:
            def query_mcp(self, query):
                return {"mcp_attempted": True, "query_id": "fixture", "documents": [{"text": "offline reference"}]}
        engine = namespace["HookEngine"](client_factory=EvidenceClient, audit_dir=False)
        engine.before_llm({"meta": {"TurnID": "fixture"}, "messages": [{"role":"user","content":"检查故障"}]})
        return engine.approve({"meta": {"TurnID": "fixture"}, "tool": "exec",
                               "arguments": {"action": "run", **arguments}})

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


    def isolated_installer(self):
        """Redirect fixed installation destinations before running real functions."""
        source = self.source.replace("/usr/local/lib/huarun", str(self.root / "lib/huarun"))
        source = source.replace("/usr/local/bin/huarun", str(self.root / "huarun"))
        source = source.replace("/usr/local/bin/.huarun.", str(self.root / ".huarun."))
        source = source.replace("/etc/huarun/backup/", str(self.root / "backups") + "/")
        for original, target in [
            ("/run/huarun", self.root / "run/huarun"),
            ("/var/lib/huarun-updater", self.root / "updater-state"),
            ("/etc/systemd/system", self.root / "systemd"),
            ("/usr/local/etc/xray", self.root / "xray"),
            ("/etc/nginx/conf.d", self.root / "nginx"),
            ("/etc/huarun", self.root / "etc/huarun"),
        ]:
            source = source.replace(original, str(target))
        # This copied fixture writes only to self.root. Relax its privilege check
        # so failure/rollback behavior also runs in the unprivileged build sandbox.
        # Assert the production guard still exists; never edit the real installer.
        root_guard = '[[ $EUID -eq 0 && -s "${AI_HOME}/.security.yml"'
        self.assertEqual(source.count(root_guard), 1)
        source = source.replace(root_guard, '[[ -s "${AI_HOME}/.security.yml"', 1)
        path = self.root / "isolated-install.sh"
        path.write_text(source)
        return 'source ' + shlex.quote(str(path)) + '\n'

    def assistant_files(self):
        home = self.root / "assistant"
        template = self.root / "template"
        home.mkdir(exist_ok=True)
        (template / "skills/huarun").mkdir(parents=True, exist_ok=True)
        (home / "config.json").write_text('{}')
        (home / ".security.yml").write_text('model_list:\n  fixture:\n    api_keys:\n      - "sk-offline-upgrade-fixture"\n')
        for name in ["AGENT.md", "SOUL.md", "skills/huarun/SKILL.md", "gate.py", "research.py"]:
            (template / name).write_text('old template\n')
        self.root.joinpath("info.json").write_text('{"assistant":true,"fixture":"unchanged"}')
        (self.root / "systemd").mkdir(exist_ok=True)
        (self.root / "etc/huarun").mkdir(parents=True, exist_ok=True)
        self.root.joinpath("prepared").write_text('#!/bin/sh\nexit 0\n')
        self.root.joinpath("huarun").write_text('old manager fixture')
        binary = self.root / "lib/huarun/picoclaw"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text('#!/bin/sh\nexit 0\n')
        binary.chmod(0o755)
        return r"""
AI_HOME="$TEST_DIR/assistant"
AI_TPL="$TEST_DIR/template"
INFO_FILE="$TEST_DIR/info.json"
PICO_BIN_READY="$TEST_DIR/prepared"
AI_KEY=sk-offline-upgrade-fixture
legacyAssistantIdle() { return 0; }
systemctl() {
    printf '%s\n' "$*" >> "$TEST_DIR/systemctl-calls"
    case "$1" in is-enabled|is-active) return 1 ;; esac
    return 0
}
"""

    def test_assistant_binary_install_failure_propagates_in_upgrade_conditional(self):
        setup = self.isolated_installer() + self.assistant_files()
        result = self.run_shell(setup + r"""
install() { return 73; }
setupAssistantHome() { echo UNEXPECTED_SETUP; }
if ! (installAssistant); then exit 17; else echo UNEXPECTED_SUCCESS; fi
""")
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertNotIn("UNEXPECTED", result.stdout + result.stderr)

    def test_assistant_template_write_failure_stops_in_upgrade_conditional(self):
        setup = self.isolated_installer() + self.assistant_files()
        result = self.run_shell(setup + r"""
cat() { return 73; }
if ! (installAssistantTemplate); then exit 17; else echo UNEXPECTED_SUCCESS; fi
""")
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertEqual((self.root / "template/SOUL.md").read_text(), 'old template\n')
        self.assertNotIn("UNEXPECTED", result.stdout + result.stderr)

    def test_assistant_setup_copy_and_config_failure_do_not_report_success(self):
        for failing_command in ["cp", "install", "python3"]:
            with self.subTest(failing_command=failing_command):
                setup = self.isolated_installer() + self.assistant_files()
                result = self.run_shell(setup + failing_command + r"""() { return 73; }
if ! (setupAssistantHome "$AI_KEY"); then exit 17; else echo UNEXPECTED_SUCCESS; fi
""")
                self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
                self.assertNotIn("UNEXPECTED", result.stdout + result.stderr)
                self.assertNotIn("AI 助手已装好", result.stdout)

    def test_manager_write_and_substitution_failure_propagate(self):
        for failing_command in ["cat", "sed"]:
            with self.subTest(failing_command=failing_command):
                result = self.run_shell(self.isolated_installer() + failing_command + r"""() { return 73; }
if ! (installManager); then exit 17; else echo UNEXPECTED_SUCCESS; fi
""")
                self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
                self.assertNotIn("UNEXPECTED", result.stdout + result.stderr)
                self.assertNotIn("管理命令已安装", result.stdout)

    def test_upgrade_backup_failure_prevents_installation(self):
        setup = self.isolated_installer() + self.assistant_files()
        result = self.run_shell(setup + r"""
cp() { return 73; }
askKey() { echo UNEXPECTED_KEY_REQUEST; }
installAssistantTemplate() { echo UNEXPECTED_INSTALL; }
if upgradeAssistant; then echo UNEXPECTED_SUCCESS; else exit 17; fi
""")
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertNotIn("UNEXPECTED", result.stdout + result.stderr)
        self.assertEqual((self.root / "huarun").read_text(), 'old manager fixture')

    def failing_upgrade(self, *, restore_failure=False):
        setup = self.isolated_installer() + self.assistant_files()
        body = r"""
askKey() { return 0; }
prepareAssistant() { return 0; }
installAssistantTemplate() { printf changed > "$AI_TPL/SOUL.md"; }
installManager() { printf changed > "$TEST_DIR/huarun"; }
installAssistant() {
    printf changed > "$AI_HOME/config.json"
    printf changed > "$TEST_DIR/lib/huarun/picoclaw"
    printf changed > "$INFO_FILE"
    return 73
}
"""
        if restore_failure:
            body += r"""
cp() {
    case "$2" in
        "$TEST_DIR"/backups/*/huarun) return 73 ;;
    esac
    command cp "$@"
}
"""
        return self.run_shell(setup + body + r"""
if upgradeAssistant; then echo UNEXPECTED_SUCCESS; else
    [[ -z "${AI_KEY+x}" ]] || echo UNEXPECTED_KEY_RETAINED
    exit 17
fi
""")

    def test_upgrade_install_failure_restores_previous_files(self):
        result = self.failing_upgrade()
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertNotIn("UNEXPECTED", result.stdout + result.stderr)
        self.assertIn("已恢复备份", result.stderr)
        self.assertEqual((self.root / "huarun").read_text(), 'old manager fixture')
        self.assertEqual((self.root / "lib/huarun/picoclaw").read_text(), '#!/bin/sh\nexit 0\n')
        self.assertEqual((self.root / "assistant/config.json").read_text(), '{}')
        self.assertEqual((self.root / "template/SOUL.md").read_text(), 'old template\n')
        self.assertEqual(json.loads((self.root / "info.json").read_text()), {"assistant": True, "fixture": "unchanged"})

    def test_upgrade_restore_failure_reports_backup_location(self):
        result = self.failing_upgrade(restore_failure=True)
        self.assertEqual(result.returncode, 17, result.stdout + result.stderr)
        self.assertNotIn("UNEXPECTED", result.stdout + result.stderr)
        self.assertIn("部分备份恢复失败", result.stderr)
        self.assertIn(str(self.root / "backups"), result.stderr)
        self.assertNotIn("已恢复备份", result.stderr)
        # One failed restore must not prevent the other files from being restored.
        self.assertEqual((self.root / "assistant/config.json").read_text(), '{}')
        self.assertEqual((self.root / "template/SOUL.md").read_text(), 'old template\n')


    def isolated_manager(self):
        source = self.manager
        for original, target in [
            ("/run/huarun", self.root / "run/huarun"),
            ("/var/lib/huarun-updater", self.root / "updater-state"),
            ("/usr/local/lib/huarun", self.root / "lib/huarun"),
            ("/etc/huarun", self.root / "etc/huarun"),
        ]:
            source = source.replace(original, str(target))
        path = self.root / "isolated-manager.sh"
        path.write_text(source)
        return 'source ' + shlex.quote(str(path)) + '\n'

    def lock_file(self):
        path = self.root / "run/huarun/maintenance.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def test_updater_exclusive_lock_waits_for_shared_management_lock(self):
        with self.lock_file().open('w') as held:
            fcntl.flock(held, fcntl.LOCK_SH)
            result = self.run_shell(self.isolated_installer() + 'acquireMaintenanceLock exclusive')
            self.assertEqual(result.returncode, 75, result.stdout + result.stderr)

    def test_installer_and_manager_accept_real_inherited_exclusive_lock(self):
        with self.lock_file().open('w') as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            for setup in [self.isolated_installer(), self.isolated_manager()]:
                with self.subTest(setup=setup):
                    result = self.run_shell(setup + 'acquireMaintenanceLock shared; rc=$?; [[ $rc -eq 0 && $MAINTENANCE_INHERITED -eq 1 ]]',
                        env={'HUARUN_UPDATE_LOCK_FD': str(held.fileno())}, pass_fds=(held.fileno(),))
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # The child must not release the parent's exclusive lock.
            with self.lock_file().open('r') as contender:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_invalid_inherited_fd_does_not_bypass_exclusive_lock(self):
        with self.lock_file().open('w') as held, (self.root / 'unrelated-file').open('w') as wrong:
            fcntl.flock(held, fcntl.LOCK_EX)
            for setup in [self.isolated_installer(), self.isolated_manager()]:
                for value, descriptors in [('999', ()), (str(wrong.fileno()), (wrong.fileno(),))]:
                    with self.subTest(setup=setup, fd=value):
                        result = self.run_shell(setup + 'acquireMaintenanceLock shared',
                            env={'HUARUN_UPDATE_LOCK_FD': value}, pass_fds=descriptors)
                        self.assertEqual(result.returncode, 75, result.stdout + result.stderr)

    def test_maintenance_lock_symlink_is_rejected_without_touching_target(self):
        target = self.root / 'unrelated-file'; target.write_text('preserve')
        self.lock_file().symlink_to(target)
        for setup in [self.isolated_installer(), self.isolated_manager()]:
            result = self.run_shell(setup + 'acquireMaintenanceLock exclusive')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), 'preserve')

    def test_chat_parent_holds_shared_lock_when_agent_closes_inherited_fds(self):
        setup = self.isolated_manager() + self.assistant_files()
        ready, release = self.root / 'agent-ready', self.root / 'agent-release'
        binary = self.root / 'lib/huarun/picoclaw'
        binary.write_text(f'#!{sys.executable}\nimport os,time,pathlib\n'
            'for fd in range(3,1024):\n try: os.close(fd)\n except OSError: pass\n'
            f'pathlib.Path({str(ready)!r}).touch()\n'
            f'while not pathlib.Path({str(release)!r}).exists(): time.sleep(0.02)\n')
        binary.chmod(0o755)
        environment = {**os.environ, 'TEST_DIR':str(self.root)}
        environment.pop('HUARUN_UPDATE_LOCK_FD', None)
        process = subprocess.Popen(['bash','-c',setup+'manager_entry chat'],env=environment,
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline = time.monotonic() + 3
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            if not ready.exists():
                initial_returncode = process.poll()
                if initial_returncode is None:
                    release.touch()
                    process.terminate()
                stdout, stderr = process.communicate(timeout=3)
                self.fail('fixture agent did not start: '
                          f'initial_returncode={initial_returncode}, returncode={process.returncode}, '
                          f'stdout={stdout!r}, stderr={stderr!r}')
            with self.lock_file().open('r') as contender:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release.touch()
            stdout, stderr = process.communicate(timeout=3)
            self.assertEqual(process.returncode, 0, stdout + stderr)
            with self.lock_file().open('r') as contender:
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            release.touch()
            if process.poll() is None:
                process.terminate(); process.communicate(timeout=3)

    def test_upgrade_installs_without_secret_argument_or_online_key_validation(self):
        setup = self.isolated_installer() + self.assistant_files()
        secret, info = self.root / 'assistant/.security.yml', self.root / 'info.json'
        secret.write_bytes(b'# preserve this layout\nmodel_list: {custom: {api_keys: ["offline-key"]}}\n')
        info.write_bytes(b'{  "assistant": true, "node": "keep-format" }\n')
        secret.chmod(0o640); info.chmod(0o644)
        before = [(p.read_bytes(), stat.S_IMODE(p.stat().st_mode)) for p in (secret, info)]
        (self.root/'prepared').write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_DIR/picoclaw-calls"\nexit 0\n')
        model = {'model_name':'custom','provider':'deepseek','model':'custom-model','api_base':'https://example.invalid/v1'}
        (self.root/'assistant/config.json').write_text(json.dumps({'agents':{'defaults':{'model_name':'custom'}},'model_list':[model]}))
        result = self.run_shell(setup + r"""
askKey() { echo UNEXPECTED_KEY_CHECK; return 99; }
curl() { echo UNEXPECTED_NETWORK; return 99; }
prepareAssistant() { return 0; }
upgradeAssistant
""")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('UNEXPECTED', result.stdout + result.stderr)
        self.assertEqual([(p.read_bytes(),stat.S_IMODE(p.stat().st_mode)) for p in (secret,info)], before)
        updated = json.loads((self.root/'assistant/config.json').read_text())
        self.assertEqual(updated['model_list'], [model])
        self.assertEqual(updated['agents']['defaults']['model_name'], 'custom')
        calls=(self.root/'systemctl-calls').read_text()
        self.assertNotRegex(calls, r'(restart|reload) (xray|nginx)')
        self.assertIn('enable huarun-auto-update.timer', calls)
        self.assertIn('start huarun-auto-update.timer', calls)
        self.assertEqual((self.root/'picoclaw-calls').read_text().splitlines(), ['version'])

    def test_fresh_assistant_install_still_requires_key(self):
        setup = self.isolated_installer() + self.assistant_files()
        result = self.run_shell(setup + 'AI_KEY=""; OPT_UPGRADE_ASSISTANT=0; installAssistant')
        self.assertNotEqual(result.returncode, 0)

    def test_upgrade_mode_never_enters_fresh_network_install(self):
        result = self.run_shell(r'''
upgradeAssistant() { echo UPGRADE_ONLY; return 0; }
checkSystem() { echo UNEXPECTED_FRESH_INSTALL; return 99; }
checkConflicts() { echo UNEXPECTED_FRESH_INSTALL; return 99; }
main --upgrade-assistant
''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("UPGRADE_ONLY", result.stdout)
        self.assertNotIn("UNEXPECTED_FRESH_INSTALL", result.stdout)

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
