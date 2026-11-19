#!/usr/bin/env python3
"""Verified, crash-recoverable assistant-only updates for an installed HuaRun VPS."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

REPOSITORY = "JasperYubo/Fanqiang-Guide"
API = "https://api.github.com/repos/" + REPOSITORY + "/releases/latest"
ORIGIN = "https://fanqiang.guide/"
PAGES = "https://jasperyubo.github.io/Fanqiang-Guide/"
STATE_DIR = "/var/lib/huarun-updater"
LOCK_PATH = "/run/huarun/maintenance.lock"
DISABLED_MARKER = "/etc/huarun/auto-update.disabled"
TIMER = "huarun-auto-update.timer"
MAX_DOWNLOAD = 2 * 1024 * 1024
FAILURE_BACKOFF = 24 * 60 * 60
TRANSACTION_NAME = re.compile(r"txn-\d{8}T\d{6}Z-[a-f0-9]{16}\Z")
PROTECTED_PATHS = (
    "/usr/local/etc/xray/config.json", "/usr/local/etc/xray/whitelist.txt",
    "/etc/nginx/conf.d/huarun.conf", "/etc/huarun/info.json",
    "/etc/huarun/assistant/.security.yml",
    "/etc/huarun/network.json", "/etc/huarun/egress.json",
)
ASSISTANT_PATHS = (
    "/usr/local/bin/huarun", "/usr/local/lib/huarun/picoclaw",
    "/usr/local/lib/huarun/auto_update.py", "/etc/huarun/assistant/config.json",
    "/etc/huarun/assistant/gate.py", "/etc/huarun/assistant/research.py",
    "/etc/huarun/assistant/workspace/AGENT.md", "/etc/huarun/assistant/workspace/SOUL.md",
    "/etc/huarun/assistant/workspace/skills/huarun/SKILL.md",
    "/etc/huarun/assistant-template", "/etc/systemd/system/huarun-auto-update.service",
    "/etc/systemd/system/huarun-auto-update.timer",
    '/usr/local/lib/huarun/network.py',
    '/usr/local/lib/huarun/aws_provider.py',
    '/usr/local/lib/huarun/ip_provider.py',
    '/usr/local/lib/huarun/egress.py',
    '/usr/local/lib/huarun/network_setup.py',
    '/etc/huarun/acme/dnsapi/dns_huarun.sh',
    '/etc/systemd/system/huarun-network.service',
    '/etc/systemd/system/huarun-network.timer',

)
ALL_PATHS = PROTECTED_PATHS + ASSISTANT_PATHS
LEGACY_ALL_PATHS = ('/usr/local/etc/xray/config.json', '/usr/local/etc/xray/whitelist.txt', '/etc/nginx/conf.d/huarun.conf', '/etc/huarun/info.json', '/etc/huarun/assistant/.security.yml', '/usr/local/bin/huarun', '/usr/local/lib/huarun/picoclaw', '/usr/local/lib/huarun/auto_update.py', '/etc/huarun/assistant/config.json', '/etc/huarun/assistant/gate.py', '/etc/huarun/assistant/research.py', '/etc/huarun/assistant/workspace/AGENT.md', '/etc/huarun/assistant/workspace/SOUL.md', '/etc/huarun/assistant/workspace/skills/huarun/SKILL.md', '/etc/huarun/assistant-template', '/etc/systemd/system/huarun-auto-update.service', '/etc/systemd/system/huarun-auto-update.timer')


class UpdateError(Exception):
    """A fixed public error code, never a raw response or command output."""


class Defer(UpdateError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def file_digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def allowed_url(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        host = parsed.hostname
        if host == "api.github.com":
            return parsed.path == "/repos/" + REPOSITORY + "/releases/latest"
        if host == "github.com":
            return bool(re.fullmatch("/" + re.escape(REPOSITORY) + r"/releases/download/release-[a-f0-9]{12}/(?:huarun-install\.sh|deployment-proof\.json)", parsed.path))
        if host in {"release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com"}:
            return True
        if host == "fanqiang.guide":
            return parsed.path in {"/data/site-release.json", "/server/install.sh"}
        if host == "jasperyubo.github.io":
            return parsed.path == "/Fanqiang-Guide/deployment.json"
    except ValueError:
        pass
    return False


def fetch_public(url, *, timeout=12, max_bytes=MAX_DOWNLOAD):
    """Anonymous fixed-host HTTPS only; signed release redirects carry no key."""
    deadline = time.monotonic() + timeout
    for _ in range(4):
        if not allowed_url(url):
            raise Defer("download_url_not_allowed")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Defer("download_timeout")
        request = Request(url, headers={"Accept": "application/vnd.github+json" if urlsplit(url).hostname == "api.github.com" else "application/octet-stream",
                                        "User-Agent": "HuaRunUpdater/1.0 (+https://fanqiang.guide/server/)",
                                        "Cache-Control": "no-cache", "X-GitHub-Api-Version": "2026-03-10"})
        try:
            with build_opener(NoRedirect).open(request, timeout=remaining) as response:
                chunks, total = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise Defer("download_timeout")
                    chunk = response.read1(min(65536, max_bytes + 1 - total))
                    if not chunk:
                        return b"".join(chunks)
                    total += len(chunk)
                    if total > max_bytes:
                        raise Defer("download_too_large")
                    chunks.append(chunk)
        except HTTPError as error:
            if error.code in (301, 302, 303, 307, 308) and urlsplit(url).hostname in {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com"}:
                url = error.headers.get("Location", "")
                continue
            raise Defer("download_http_" + str(error.code)) from None
        except (URLError, TimeoutError, OSError):
            raise Defer("download_unavailable") from None
    raise Defer("download_redirect_limit")


def object_json(raw):
    try:
        result = json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        raise Defer("invalid_json") from None
    if not isinstance(result, dict):
        raise Defer("invalid_json_object")
    return result


def version(raw):
    try:
        values = set(re.findall(r'^VERSION="(\d+\.\d+\.\d+)"$', raw.decode("utf-8"), re.M))
    except UnicodeError:
        raise Defer("invalid_installer_encoding") from None
    if len(values) != 1:
        raise Defer("invalid_installer_version")
    return values.pop()


def semver(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise UpdateError("invalid_installed_version")
    return tuple(int(part) for part in value.split("."))


def verify_release(fetch=fetch_public):
    release = object_json(fetch(API))
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise Defer("release_not_stable")
    source = release.get("target_commitish", "")
    if not isinstance(source, str) or not re.fullmatch(r"[a-f0-9]{40}", source):
        raise Defer("release_source_not_pinned")
    tag = "release-" + source[:12]
    if release.get("tag_name") != tag or type(release.get("id")) is not int or release["id"] < 1:
        raise Defer("release_identity_mismatch")
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise Defer("release_assets_invalid")
    selected = {}
    for name in ("huarun-install.sh", "deployment-proof.json"):
        matches = [item for item in assets if isinstance(item, dict) and item.get("name") == name]
        if len(matches) != 1:
            raise Defer("release_asset_missing_or_duplicate")
        asset = matches[0]
        expected_url = "https://github.com/" + REPOSITORY + "/releases/download/" + tag + "/" + name
        if asset.get("browser_download_url") != expected_url or asset.get("state") != "uploaded":
            raise Defer("release_asset_identity_mismatch")
        checksum = asset.get("digest", "")
        if not isinstance(checksum, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", checksum):
            raise Defer("release_asset_digest_missing")
        size = asset.get("size")
        if not isinstance(size, int) or not 0 < size <= MAX_DOWNLOAD:
            raise Defer("release_asset_size_invalid")
        raw = fetch(expected_url)
        if len(raw) != size or sha256(raw) != checksum[7:]:
            raise Defer("release_asset_digest_mismatch")
        selected[name] = raw
    installer = selected["huarun-install.sh"]
    proof = object_json(selected["deployment-proof.json"])
    installer_sha = sha256(installer)
    contract_sha = proof.get("contract_sha256", "")
    if (proof.get("schema_version") != 1 or proof.get("source_sha") != source
            or proof.get("installer_sha256") != installer_sha or not isinstance(contract_sha, str)
            or not re.fullmatch(r"[a-f0-9]{64}", contract_sha)):
        raise Defer("deployment_proof_identity_mismatch")
    expected = {"schema_version": 1, "source_sha": source, "contract_sha256": contract_sha, "installer_sha256": installer_sha}
    if not isinstance(proof.get("assets"), dict) or proof["assets"].get("huarun-install.sh") != {"sha256": installer_sha, "bytes": len(installer)}:
        raise Defer("deployment_proof_installer_mismatch")
    if not isinstance(proof.get("sync_id"), str) or not proof["sync_id"] or not re.fullmatch(r"[1-9][0-9]*", str(proof.get("run_id", ""))) or type(proof.get("run_attempt")) is not int or proof["run_attempt"] < 1:
        raise Defer("deployment_proof_run_invalid")
    for receipt_name in ("origin_receipt", "pages_receipt"):
        receipt = proof.get(receipt_name)
        if not isinstance(receipt, dict) or any(receipt.get(k) != v for k, v in expected.items()) or receipt.get("sync_id") != proof.get("sync_id"):
            raise Defer("deployment_proof_receipt_mismatch")
    if proof["pages_receipt"].get("run_id") != proof.get("run_id") or proof["pages_receipt"].get("run_attempt") != proof.get("run_attempt"):
        raise Defer("deployment_proof_run_mismatch")
    suffix = "?source=" + source + "&check=" + str(time.time_ns())
    origin = object_json(fetch(ORIGIN + "data/site-release.json" + suffix))
    pages = object_json(fetch(PAGES + "deployment.json" + suffix))
    for receipt in (origin, pages):
        if any(receipt.get(k) != v for k, v in expected.items()):
            raise Defer("sites_not_on_release")
    if not isinstance(origin.get("sync_id"), str) or not origin["sync_id"] or origin["sync_id"] != pages.get("sync_id"):
        raise Defer("sites_not_same_transaction")
    if not re.fullmatch(r"[1-9][0-9]*", str(pages.get("run_id", ""))) or not isinstance(pages.get("run_attempt"), int) or pages["run_attempt"] < 1:
        raise Defer("pages_run_identity_invalid")
    if sha256(fetch(ORIGIN + "server/install.sh" + suffix)) != installer_sha:
        raise Defer("origin_installer_mismatch")
    return {"source_sha": source, "installer_sha256": installer_sha, "version": version(installer),
            "release_id": release["id"], "tag": tag, "release_url": "https://github.com/" + REPOSITORY + "/releases/tag/" + tag,
            "installer": installer}


def default_runner(args, *, timeout, env, pass_fds=()):
    # Terminate the complete installer process group before rollback: killing only
    # its shell could leave a downloader or writer racing restored files.
    process = subprocess.Popen(args, env=env, pass_fds=pass_fds, start_new_session=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace")
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        raise
    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


class Updater:
    def __init__(self, root=Path("/"), *, fetch=fetch_public, runner=default_runner, clock=time.time):
        self.root = Path(root).resolve()
        self.fetch, self.runner, self.clock = fetch, runner, clock
        self.state_dir = self.path(STATE_DIR)
        self.state_path = self.state_dir / "state.json"
        self.journal_path = self.state_dir / "transaction.json"
        self.backup_dir = self.state_dir / "backups"
        self.lock_fd = None

    def path(self, absolute, *, restore_leaf=False):
        if not absolute.startswith("/") or ".." in Path(absolute).parts:
            raise UpdateError("unsafe_local_path")
        path = self.root / absolute.lstrip("/")
        checked = path.parent if restore_leaf else path
        if not checked.resolve().is_relative_to(self.root):
            raise UpdateError("unsafe_local_path")
        current = checked
        while current != self.root:
            if current.is_symlink():
                raise UpdateError("symlink_local_path")
            current = current.parent
        return path

    @staticmethod
    def private_dir(path):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
            raise UpdateError("unsafe_state_owner")
        path.chmod(0o700)

    @staticmethod
    def atomic_json(path, value):
        temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def read_json(path, default=None):
        if not path.exists() and not path.is_symlink():
            return copy.deepcopy(default if default is not None else {})
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise UpdateError("unsafe_state_file")
        if info.st_size > MAX_DOWNLOAD:
            raise UpdateError("state_too_large")
        value = object_json(path.read_bytes())
        return value

    def command(self, args, timeout=15, *, check=True):
        env = {k: v for k, v in os.environ.items() if k not in {"GITHUB_TOKEN", "GH_TOKEN", "HUARUN_API_KEY", "DEEPSEEK_API_KEY", "AI_KEY", "SETUP_KEY", "HUARUN_UPDATE_LOCK_FD"}}
        descriptors = ()
        if self.lock_fd is not None:
            env["HUARUN_UPDATE_LOCK_FD"] = str(self.lock_fd)
            descriptors = (self.lock_fd,)
        try:
            result = self.runner(list(map(str, args)), timeout=timeout, env=env, pass_fds=descriptors)
        except (subprocess.TimeoutExpired, OSError):
            raise UpdateError("local_command_failed") from None
        if check and result.returncode:
            raise UpdateError("local_command_failed")
        return result

    def timer_state(self, timer=TIMER):
        result = {}
        for name, option in (("enabled", "is-enabled"), ("active", "is-active")):
            try:
                command = self.command(["systemctl", option, timer], timeout=5, check=False)
                value = command.stdout.strip()
                allowed = {"enabled", "disabled", "static", "masked", "not-found", "active", "inactive", "failed", "activating", "deactivating"}
                if name == "enabled" and not value:
                    # systemctl is-enabled prints a missing-unit error on stderr,
                    # not the literal "not-found" on stdout.
                    loaded = self.command(["systemctl", "show", "--property=LoadState", "--value", timer], timeout=5, check=False)
                    if loaded.stdout.strip() == "not-found":
                        value = "not-found"
                result[name] = value if value in allowed else "unknown"
            except UpdateError:
                result[name] = "unknown"
        return result

    def status(self):
        state = self.read_json(self.state_path, {})
        safe = {key: state[key] for key in ("status", "last_check") if key in state}
        for name in ("last_good", "last_failure"):
            record = state.get(name)
            safe[name] = {key: record[key] for key in ("source_sha", "installer_sha256", "version", "release_id", "tag", "release_url", "at", "code") if key in record} if isinstance(record, dict) else None
        safe["timer"] = self.timer_state()
        safe["disabled"] = self.path(DISABLED_MARKER).exists()
        safe["pending_recovery"] = self.journal_path.exists()
        return safe

    def write_state(self, state, status, **fields):
        result = {**state, "schema_version": 1, "status": status, "last_check": int(self.clock()), **fields}
        self.atomic_json(self.state_path, result)
        return {"status": status, **fields}

    def snapshot(self, path):
        if not path.exists() and not path.is_symlink():
            return {"exists": False}
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise UpdateError("unsupported_backup_file")
        record = {"exists": True, "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}
        if path.is_dir():
            record.update({"type": "directory", "children": {child.name: self.snapshot(child) for child in sorted(path.iterdir())}})
        else:
            record.update({"type": "file", "bytes": info.st_size, "sha256": file_digest(path)})
        return record

    @staticmethod
    def sync_tree(path):
        if path.is_symlink():
            raise UpdateError("symlink_installed_path")
        if path.is_dir():
            for child in path.iterdir():
                Updater.sync_tree(child)
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        else:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def sync_parent_chain(self, path):
        current = path.parent
        while current.is_relative_to(self.root):
            if not current.exists():
                current = current.parent
                continue
            descriptor = os.open(current, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if current == self.root:
                break
            current = current.parent

    def sync_installed(self):
        for target in ALL_PATHS:
            path = self.path(target)
            if path.exists():
                self.sync_tree(path)
            self.sync_parent_chain(path)

    def clear_journal(self):
        self.journal_path.unlink()
        directory = os.open(self.state_dir, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def backup(self, transaction):
        if not TRANSACTION_NAME.fullmatch(transaction):
            raise UpdateError("invalid_transaction_name")
        folder = self.backup_dir / transaction
        folder.mkdir(mode=0o700)
        # A durable ownership marker also identifies an interrupted pre-journal
        # backup; retention never deletes arbitrary user-created directories.
        self.atomic_json(folder / "owner.json", {"schema_version": 1, "transaction": transaction})
        entries = {}
        try:
            for index, target in enumerate(ALL_PATHS):
                source = self.path(target)
                before = self.snapshot(source)
                destination = folder / str(index)
                if before["exists"]:
                    if before["type"] == "directory":
                        shutil.copytree(source, destination, copy_function=shutil.copy2)
                    else:
                        shutil.copy2(source, destination)
                    self.sync_tree(destination)
                    # Backup ownership is root; source mode/owner is sealed separately.
                    if self.snapshot(source) != before:
                        raise UpdateError("source_changed_during_backup")
                entries[target] = before
            manifest = {"schema_version": 1, "transaction": transaction, "entries": entries, "path_order": list(ALL_PATHS)}
            self.atomic_json(folder / "backup.json", manifest)
            self.sync_parent_chain(folder)
            return folder, manifest
        except Exception:
            if folder.parent == self.backup_dir and not folder.is_symlink():
                shutil.rmtree(folder)
            raise

    def restore_metadata(self, path, snapshot):
        if snapshot["type"] == "directory":
            for name, child in snapshot["children"].items():
                if not isinstance(name, str) or name in {".", ".."} or "/" in name:
                    raise UpdateError("invalid_backup_manifest")
                self.restore_metadata(path / name, child)
        os.chown(path, snapshot["uid"], snapshot["gid"])
        path.chmod(snapshot["mode"])

    def backup_matches(self, path, snapshot):
        actual = self.snapshot(path)
        def content_only(value):
            if isinstance(value, dict):
                return {key: content_only(item) for key, item in value.items() if key not in {"uid", "gid"}}
            return value
        return content_only(actual) == content_only(snapshot)

    def restore(self, journal):
        transaction = journal.get("transaction", "")
        if not isinstance(transaction, str) or not TRANSACTION_NAME.fullmatch(transaction):
            raise UpdateError("invalid_transaction_name")
        folder = self.backup_dir / transaction
        if folder.is_symlink() or not folder.resolve().is_relative_to(self.backup_dir.resolve()):
            raise UpdateError("unsafe_backup_path")
        manifest = self.read_json(folder / "backup.json")
        entries = manifest.get("entries", {})
        order = manifest.get("path_order")
        if order is None:
            order = list(LEGACY_ALL_PATHS if set(entries) == set(LEGACY_ALL_PATHS) else ALL_PATHS)
        if (manifest.get("transaction") != transaction or tuple(order) not in (ALL_PATHS, LEGACY_ALL_PATHS)
                or set(entries) != set(order)):
            raise UpdateError("invalid_backup_manifest")
        for index, target in enumerate(order):
            before = entries[target]
            if before.get("exists") and not self.backup_matches(folder / str(index), before):
                raise UpdateError("backup_integrity_failed")
        old_timer = journal.get("timer_before", {})
        if old_timer.get("enabled") in {"disabled", "not-found"}:
            self.command(["systemctl", "disable", "--now", TIMER], check=False)
        old_network = journal.get("network_timer_before", {"enabled": "not-found", "active": "inactive"})
        if old_network.get("enabled") in {"disabled", "not-found"}:
            self.command(["systemctl", "disable", "--now", "huarun-network.timer"], check=False)
        for index, target in enumerate(order):
            destination = self.path(target, restore_leaf=True)
            before = manifest["entries"][target]
            try:
                unchanged = self.snapshot(destination) == before
            except UpdateError:
                unchanged = False
            if unchanged:
                continue
            if destination.exists() or destination.is_symlink():
                if destination.is_dir() and not destination.is_symlink():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            if before.get("exists"):
                destination.parent.mkdir(parents=True, exist_ok=True)
                backup_path = folder / str(index)
                if before["type"] == "directory":
                    shutil.copytree(backup_path, destination, copy_function=shutil.copy2)
                else:
                    shutil.copy2(backup_path, destination)
                self.restore_metadata(destination, before)
                self.sync_tree(destination)
            if self.snapshot(destination) != before:
                raise UpdateError("restore_verification_failed")
            self.sync_parent_chain(destination)
        self.sync_installed()
        self.command(["systemctl", "daemon-reload"])
        if old_timer.get("enabled") == "enabled":
            self.command(["systemctl", "enable", TIMER])
        elif old_timer.get("enabled") == "disabled":
            self.command(["systemctl", "disable", TIMER])
        if old_timer.get("enabled") != "not-found" and old_timer.get("active") in {"active", "inactive", "failed"}:
            self.command(["systemctl", "start" if old_timer["active"] == "active" else "stop", TIMER])
        actual_timer = self.timer_state()
        if old_timer.get("enabled") in {"enabled", "disabled"} and actual_timer["enabled"] != old_timer["enabled"]:
            raise UpdateError("timer_restore_failed")
        if old_timer.get("active") == "active" and actual_timer["active"] != "active":
            raise UpdateError("timer_restore_failed")
        if old_timer.get("active") in {"inactive", "failed"} and actual_timer["active"] == "active":
            raise UpdateError("timer_restore_failed")

        if old_network.get("enabled") in {"enabled", "disabled"}:
            self.command(["systemctl", "enable" if old_network["enabled"] == "enabled" else "disable", "huarun-network.timer"])
            self.command(["systemctl", "start" if old_network.get("active") == "active" else "stop", "huarun-network.timer"])
            actual_network = self.timer_state("huarun-network.timer")
            if actual_network["enabled"] != old_network["enabled"] or (actual_network["active"] == "active") != (old_network.get("active") == "active"):
                raise UpdateError("network_timer_restore_failed")
        elif old_network.get("enabled") == "not-found":
            # A 1.2 journal cannot enumerate newly introduced 1.3 programs. Keep
            # those files (they may be user-owned), but prove their timer stopped.
            actual_network = self.timer_state("huarun-network.timer")
            if actual_network["enabled"] not in {"not-found", "disabled", "masked"} or actual_network["active"] not in {"inactive", "failed"}:
                raise UpdateError("network_timer_restore_failed")
        else:
            raise UpdateError("network_timer_restore_state_unknown")

    def health(self):
        manager = self.path("/usr/local/bin/huarun")
        try:
            doctor = object_json(self.command([manager, "doctor", "--json"], timeout=30).stdout)
            status_value = object_json(self.command([manager, "status", "--json"], timeout=20).stdout)
            checks = doctor["checks"]
            if not isinstance(checks, dict) or not checks or not isinstance(doctor["all_ok"], bool):
                raise ValueError()
            result = {"doctor": {}, "all_ok": doctor["all_ok"], "status": {}}
            for name, check in checks.items():
                if not isinstance(check, dict) or not isinstance(check.get("ok"), bool):
                    raise ValueError()
                result["doctor"][name] = check["ok"]
            for name in ("xray", "nginx"):
                if not isinstance(status_value.get(name), str) or not status_value[name]:
                    raise ValueError()
                result["status"][name] = status_value[name] == "active"
            for name in ("port443", "renew_cron", "assistant"):
                if not isinstance(status_value.get(name), bool):
                    raise ValueError()
                result["status"][name] = status_value[name]
            return result
        except (KeyError, ValueError, TypeError, Defer):
            raise UpdateError("invalid_health_json") from None

    @staticmethod
    def nonregression(before, after):
        if before["all_ok"] and not after["all_ok"]:
            raise UpdateError("health_regression")
        for section in ("doctor", "status"):
            if any(value and after[section].get(name) is not True for name, value in before[section].items()):
                raise UpdateError("health_regression")

    def validate_installed(self, candidate, manifest, before, network_timer_before=None):
        for target in PROTECTED_PATHS:
            if self.snapshot(self.path(target)) != manifest["entries"][target]:
                raise UpdateError("protected_file_changed")
        for target in ("/etc/huarun/assistant/gate.py", "/etc/huarun/assistant/research.py", *[
                "/usr/local/lib/huarun/" + name for name in
                ("auto_update.py", "network.py", "ip_provider.py", "aws_provider.py", "egress.py", "network_setup.py")]):
            path = self.path(target)
            try:
                compile(path.read_bytes(), target, "exec")
            except (SyntaxError, UnicodeError, OSError):
                raise UpdateError("installed_python_invalid") from None
        manager = self.path("/usr/local/bin/huarun")
        self.command(["bash", "-n", manager])
        current = self.command([manager, "version"]).stdout.strip()
        if current != candidate["version"]:
            raise UpdateError("installed_version_mismatch")
        self.nonregression(before, self.health())
        if network_timer_before is not None:
            actual = self.timer_state("huarun-network.timer")
            expected = ({"enabled": "enabled", "active": "active"}
                        if network_timer_before.get("enabled") == "not-found" else network_timer_before)
            if expected.get("enabled") not in {"enabled", "disabled"} or expected.get("active") not in {"active", "inactive", "failed"}:
                raise UpdateError("network_timer_baseline_unknown")
            if actual["enabled"] != expected["enabled"] or (actual["active"] == "active") != (expected["active"] == "active"):
                raise UpdateError("network_timer_changed_unexpectedly")

    def prune_backups(self):
        if not self.backup_dir.exists():
            return
        own = []
        for path in self.backup_dir.iterdir():
            if path.is_symlink() or not path.is_dir() or not TRANSACTION_NAME.fullmatch(path.name):
                continue
            try:
                marker = self.read_json(path / "owner.json")
            except (UpdateError, Defer):
                continue
            if marker.get("transaction") == path.name and marker.get("schema_version") == 1:
                own.append(path)
        for path in sorted(own, key=lambda p: p.name, reverse=True)[3:]:
            if path.parent == self.backup_dir and path.resolve().is_relative_to(self.backup_dir.resolve()):
                shutil.rmtree(path)

    def failure(self, journal, code):
        self.restore(journal)
        state = journal.get("previous_state", {})
        if code == "installer_busy":
            result = self.write_state(state, "deferred", reason=code)
            self.clear_journal()
            self.prune_backups()
            return result
        candidate = journal.get("candidate", {})
        failure = {"source_sha": candidate.get("source_sha"), "installer_sha256": candidate.get("installer_sha256"),
                   "at": int(self.clock()), "code": code}
        result = self.write_state(state, "rolled_back", last_failure=failure)
        self.clear_journal()
        self.prune_backups()
        return result

    def run(self):
        self.private_dir(self.state_dir)
        self.private_dir(self.backup_dir)
        lock_path = self.path(LOCK_PATH)
        self.private_dir(lock_path.parent)
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            if os.fstat(fd).st_uid != os.geteuid() or not stat.S_ISREG(os.fstat(fd).st_mode):
                raise UpdateError("unsafe_lock_file")
            os.fchmod(fd, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "busy"}
            self.lock_fd = fd
            if self.journal_path.exists():
                return self.failure(self.read_json(self.journal_path), "interrupted_update")
            state = self.read_json(self.state_path, {})
            if self.path(DISABLED_MARKER).exists():
                return self.write_state(state, "disabled")
            try:
                candidate = verify_release(self.fetch)
            except Defer as error:
                return self.write_state(state, "deferred", reason=str(error))
            public_candidate = {key: value for key, value in candidate.items() if key != "installer"}
            previous_good = (state.get("last_good") or {})
            if previous_good.get("installer_sha256") == candidate["installer_sha256"]:
                return self.write_state(state, "up_to_date")
            failure = (state.get("last_failure") or {})
            if failure.get("source_sha") == candidate["source_sha"] and self.clock() - failure.get("at", 0) < FAILURE_BACKOFF:
                return self.write_state(state, "backoff", reason="same_release_failed_recently")
            current = self.command([self.path("/usr/local/bin/huarun"), "version"]).stdout.strip()
            if semver(candidate["version"]) < semver(current):
                return self.write_state(state, "deferred", reason="downgrade_refused")
            baseline = self.health()
            transaction = "txn-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:16]
            folder, manifest = self.backup(transaction)
            verified_path = folder / "verified-installer.sh"
            descriptor = os.open(verified_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(candidate["installer"])
                stream.flush()
                os.fsync(stream.fileno())
            journal = {"schema_version": 1, "transaction": transaction, "phase": "prepared",
                       "candidate": public_candidate, "previous_state": state, "timer_before": self.timer_state(), "network_timer_before": self.timer_state("huarun-network.timer")}
            self.atomic_json(self.journal_path, journal)
            try:
                journal["phase"] = "applying"
                self.atomic_json(self.journal_path, journal)
                applied = self.command(["bash", verified_path, "--upgrade-assistant", "--yes"], timeout=900, check=False)
                if applied.returncode:
                    raise UpdateError("installer_busy" if applied.returncode == 75 else "installer_failed")
                journal["phase"] = "verifying"
                self.atomic_json(self.journal_path, journal)
                self.validate_installed(candidate, manifest, baseline, journal["network_timer_before"])
                self.sync_installed()
            except (UpdateError, OSError, ValueError, TypeError, KeyError) as error:
                code = str(error) if isinstance(error, UpdateError) else "local_update_failed"
                return self.failure(journal, code)
            good = {**public_candidate, "at": int(self.clock())}
            result = self.write_state(state, "updated", last_good=good, last_failure=None)
            self.clear_journal()
            self.prune_backups()
            return result
        finally:
            self.lock_fd = None
            os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise UpdateError("root_required")
    updater = Updater()
    print(json.dumps(updater.status() if args.status else updater.run(), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (UpdateError, OSError, ValueError, TypeError, KeyError) as error:
        code = str(error) if isinstance(error, UpdateError) else type(error).__name__
        print(json.dumps({"status": "failed", "code": code}))
        raise SystemExit(1) from None
