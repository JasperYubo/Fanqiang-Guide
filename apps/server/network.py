#!/usr/bin/env python3
"""Cloudflare domain maintenance, authenticated reachability and bounded recovery.

Cloudflare account tokens use Full account and zone access as selected by the
owner. Secrets stay in the local private configuration, never in model output.
This module never rewrites Xray, Nginx, node identity, whitelist or DeepSeek keys.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import copy
import fcntl
import getpass
import hashlib
import hmac
import http.client
import http.server
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

CONFIG = "/etc/huarun/network.json"
STATE_DIR = "/var/lib/huarun-network"
LOCK = "/run/huarun/maintenance.lock"
NETWORK_LOCK = "/run/huarun/network.lock"
CF = "https://api.cloudflare.com/client/v4"
MAX_BYTES = 256 * 1024
MAX_CONFIG = 64 * 1024
HEX32 = re.compile(r"[a-f0-9]{32}\Z")
DOCTOR_CHECKS = ("xray", "nginx", "port443", "xray_config", "nginx_config",
                 "cert", "cron", "firewall", "dns", "disk")
IP_SERVICES = ("https://api.ipify.org", "https://checkip.amazonaws.com")
HEALTH_FAILURES = 3


class NetworkError(Exception):
    """A fixed, public code. Never include HTTP bodies or secret-bearing URLs."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise NetworkError("redirect_rejected")


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def hostname(value):
    if not isinstance(value, str):
        raise NetworkError("invalid_domain")
    value = value.lower().rstrip(".")
    if len(value) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value):
        raise NetworkError("invalid_domain")
    return value


def address(value, kind=None):
    try:
        parsed = ipaddress.ip_address(value)
    except (TypeError, ValueError):
        raise NetworkError("invalid_ip") from None
    if not parsed.is_global or parsed.is_multicast or parsed.is_unspecified:
        raise NetworkError("non_public_ip")
    if kind is not None and parsed.version != {"A": 4, "AAAA": 6}.get(kind):
        raise NetworkError("ip_family_mismatch")
    return str(parsed)


def addresses(value):
    if not isinstance(value, dict) or not value or set(value) - {"A", "AAAA"}:
        raise NetworkError("invalid_addresses")
    return {kind: address(ip, kind) for kind, ip in value.items()}


def secret_string(value, name, minimum=12):
    if not isinstance(value, str) or not minimum <= len(value) <= 4096 or any(c.isspace() for c in value):
        raise NetworkError("invalid_" + name)
    return value


def private_file(path, limit=MAX_CONFIG):
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise NetworkError("private_file_permissions")
    if info.st_size > limit:
        raise NetworkError("private_file_too_large")
    return path


def load_private(path, default=None, limit=MAX_CONFIG):
    path = private_file(path, limit)
    if path is None:
        return copy.deepcopy(default)
    try:
        value = json.loads(path.read_bytes())
    except (ValueError, UnicodeError):
        raise NetworkError("private_json_invalid") from None
    if not isinstance(value, dict):
        raise NetworkError("private_json_invalid")
    return value


def atomic_private(path, value):
    path = Path(path)
    if path.is_symlink():
        raise NetworkError("private_path_symlink")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.is_symlink():
        raise NetworkError("private_parent_symlink")
    # Do not change the modes of an existing owner-managed parent.
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(encoded(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def public_probe_url(value, resolve=False):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.fragment or parsed.query):
            raise ValueError()
        hostname(parsed.hostname)
        if resolve:
            found = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
            if not found:
                raise ValueError()
            for item in found:
                address(item[4][0])
    except (TypeError, ValueError, OSError, NetworkError):
        raise NetworkError("invalid_probe_url") from None
    return value


def request(method, url, payload=None, headers=None, timeout=12, probe=False):
    """Fixed credential origins; authenticated probe URLs are owner configured."""
    parsed = urlsplit(url)
    allowed = (url.startswith(CF + "/") or
               (parsed.scheme == "https" and parsed.hostname == "api.telegram.org"
                and re.fullmatch(r"/bot[0-9]+:[A-Za-z0-9_-]+/sendMessage", parsed.path)) or
               url in IP_SERVICES)
    if not allowed:
        if not probe:
            raise NetworkError("upstream_not_allowed")
        public_probe_url(url, resolve=True)
    raw = None if payload is None else encoded(payload)
    supplied = {"User-Agent": "HuaRun-Network/1.0", "Accept": "application/json"}
    supplied.update(headers or {})
    if raw is not None:
        supplied["Content-Type"] = "application/json"
    req = Request(url, data=raw, headers=supplied, method=method)
    try:
        with build_opener(NoRedirect).open(req, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise NetworkError("response_too_large")
    except HTTPError as error:
        raise NetworkError("upstream_http_" + str(error.code)) from None
    except (URLError, TimeoutError, OSError, ssl.SSLError):
        raise NetworkError("upstream_unavailable") from None
    if url in IP_SERVICES:
        return body.decode("ascii").strip()
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise NetworkError("upstream_invalid_json") from None
    if not isinstance(result, dict):
        raise NetworkError("upstream_invalid_json")
    return result


def validate_config(value):
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise NetworkError("configuration_schema_invalid")
    result = copy.deepcopy(value)
    result["domain"] = hostname(result.get("domain"))
    cf = result.get("cloudflare")
    if not isinstance(cf, dict):
        raise NetworkError("cloudflare_configuration_missing")
    for name in ("account_id", "zone_id"):
        if not isinstance(cf.get(name), str) or not HEX32.fullmatch(cf[name]):
            raise NetworkError("invalid_" + name)
    secret_string(cf.get("api_token"), "cloudflare_token")
    if type(cf.get("proxied", False)) is not bool:
        raise NetworkError("invalid_proxy_setting")
    source = result.get("address_source")
    if not isinstance(source, dict) or source.get("mode") not in ("static", "consensus", "provider", "digitalocean", "hetzner_floating"):
        raise NetworkError("address_source_required")
    if source["mode"] == "static":
        source["addresses"] = addresses(source.get("addresses"))
    if source["mode"] == "consensus" and source.get("no_nat_confirmed") is not True:
        raise NetworkError("inbound_ip_confirmation_required")
    notification = result.get("notification", {"kind": "none"})
    if not isinstance(notification, dict) or notification.get("kind") not in ("telegram", "none"):
        raise NetworkError("notification_kind_invalid")
    if notification["kind"] == "telegram":
        if not re.fullmatch(r"[0-9]{5,20}:[A-Za-z0-9_-]{20,120}", str(notification.get("bot_token", ""))):
            raise NetworkError("telegram_token_invalid")
        if not re.fullmatch(r"-?[0-9]{1,20}", str(notification.get("chat_id", ""))):
            raise NetworkError("telegram_chat_invalid")
    result["notification"] = notification
    provider = result.get("provider", {})
    if not isinstance(provider, dict):
        raise NetworkError("provider_configuration_invalid")
    if provider.get("auto_rotate") is True and source["mode"] not in ("provider", "digitalocean", "hetzner_floating"):
        raise NetworkError("automatic_rotation_requires_provider_address_source")
    probes = result.get("probes", [])
    if not isinstance(probes, list) or len(probes) > 8:
        raise NetworkError("probes_invalid")
    names = set()
    for probe in probes:
        if not isinstance(probe, dict):
            raise NetworkError("probe_invalid")
        public_probe_url(probe.get("url"))
        secret_string(probe.get("key"), "probe_key", minimum=32)
        region = probe.get("region")
        if not isinstance(region, str) or not re.fullmatch(r"[a-z0-9-]{2,32}", region):
            raise NetworkError("probe_region_invalid")
        endpoint = urlsplit(probe["url"]).hostname
        if endpoint in names:
            raise NetworkError("probe_hosts_must_be_independent")
        names.add(endpoint)
    result["probes"] = probes
    return result


class MaintenanceLock:
    """Shared with chat, exclusive against updates; serialize network mutations.

    The inherited descriptors must actually reference the expected local locks.
    Only an inherited verified exclusive maintenance descriptor may be forwarded
    as HUARUN_UPDATE_LOCK_FD to existing updater-aware subprocesses.
    """
    def __init__(self, path=LOCK, network_path=NETWORK_LOCK):
        self.path, self.network_path = Path(path).absolute(), Path(network_path).absolute()
        self.fd = self.network_fd = None
        self.inherited = self.network_inherited = False

    @staticmethod
    def _acquire(path, variable, mode):
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink():
            raise NetworkError("maintenance_lock_symlink")
        inherited = os.environ.get(variable, "")
        if inherited.isdigit() and 3 <= int(inherited) <= 65535:
            try:
                fd = int(inherited)
                info = os.fstat(fd)
                if (os.readlink("/proc/self/fd/" + inherited) == str(path)
                        and stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                        and not stat.S_IMODE(info.st_mode) & 0o077):
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return fd, True
            except (OSError, ValueError):
                pass
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise NetworkError("maintenance_lock_permissions")
            fcntl.flock(fd, mode | fcntl.LOCK_NB)
        except Exception as error:
            os.close(fd)
            if isinstance(error, BlockingIOError):
                raise NetworkError("maintenance_busy") from None
            raise
        return fd, False

    def __enter__(self):
        try:
            self.fd, self.inherited = self._acquire(self.path, "HUARUN_UPDATE_LOCK_FD", fcntl.LOCK_SH)
            self.network_fd, self.network_inherited = self._acquire(
                self.network_path, "HUARUN_NETWORK_LOCK_FD", fcntl.LOCK_EX)
        except Exception:
            self.__exit__()
            raise
        return self

    def __exit__(self, *unused):
        if self.network_fd is not None and not self.network_inherited:
            os.close(self.network_fd)
            self.network_fd = None
        if self.fd is not None and not self.inherited:
            os.close(self.fd)
            self.fd = None


class Cloudflare:
    def __init__(self, config, transport=request):
        self.config, self.transport = config, transport
        self.cf = config["cloudflare"]

    def api(self, method, path, payload=None):
        result = self.transport(method, CF + path, payload,
                                {"Authorization": "Bearer " + self.cf["api_token"]})
        if result.get("success") is not True or "result" not in result:
            raise NetworkError("cloudflare_request_failed")
        return result

    def verify(self):
        token = self.api("GET", "/accounts/" + self.cf["account_id"] + "/tokens/verify")["result"]
        if not isinstance(token, dict) or token.get("status") != "active":
            raise NetworkError("cloudflare_token_inactive")
        zone = self.api("GET", "/zones/" + self.cf["zone_id"])["result"]
        if (not isinstance(zone, dict) or zone.get("id") != self.cf["zone_id"] or
                zone.get("account", {}).get("id") != self.cf["account_id"]):
            raise NetworkError("cloudflare_zone_account_mismatch")
        if zone.get("status") != "active":
            raise NetworkError("cloudflare_zone_not_active")
        zone_name = hostname(zone.get("name"))
        domain = self.config["domain"]
        if domain != zone_name and not domain.endswith("." + zone_name):
            raise NetworkError("domain_outside_selected_zone")
        return {"zone_name": zone_name, "token_active": True}

    @property
    def prefix(self):
        return "/zones/" + self.cf["zone_id"] + "/dns_records"

    def records(self, name):
        if name not in (self.config["domain"], "_acme-challenge." + self.config["domain"]):
            raise NetworkError("record_name_not_selected")
        result = self.api("GET", self.prefix + "?" + urlencode({"name": name, "per_page": 100}))
        items = result["result"]
        pages = result.get("result_info", {}).get("total_pages", 1)
        if not isinstance(items, list) or pages not in (0, 1) or (pages == 0 and items):
            raise NetworkError("dns_records_ambiguous")
        for item in items:
            if not isinstance(item, dict) or item.get("name", "").lower().rstrip(".") != name:
                raise NetworkError("dns_record_identity_mismatch")
            if not HEX32.fullmatch(str(item.get("id", ""))):
                raise NetworkError("dns_record_id_invalid")
        return items

    def read_record(self, ident, kind, name):
        if not HEX32.fullmatch(str(ident)):
            raise NetworkError("dns_record_id_invalid")
        value = self.api("GET", self.prefix + "/" + ident)["result"]
        if not isinstance(value, dict) or value.get("id") != ident or value.get("type") != kind or value.get("name", "").lower().rstrip(".") != name:
            raise NetworkError("dns_record_identity_mismatch")
        return value

    def sync(self, wanted):
        wanted = addresses(wanted)
        name = self.config["domain"]
        rows = self.records(name)
        if any(r.get("type") == "CNAME" for r in rows):
            raise NetworkError("domain_has_cname")
        # Validate the complete selection before the first mutation.
        matches_by_kind = {kind: [r for r in rows if r.get("type") == kind] for kind in wanted}
        if any(len(matches) > 1 for matches in matches_by_kind.values()):
            raise NetworkError("multiple_address_records_require_owner_selection")
        proxy_active = any(row.get("type") in ("A", "AAAA") and row.get("proxied") is True for row in rows)
        proxy_new = self.cf.get("proxied") is True and any(not matches for matches in matches_by_kind.values())
        if proxy_active or proxy_new:
            setting = self.api("GET", "/zones/" + self.cf["zone_id"] + "/settings/ssl")["result"]
            if not isinstance(setting, dict) or setting.get("value") != "strict":
                # Never change the whole zone's TLS mode on behalf of one node.
                raise NetworkError("cloudflare_full_strict_required")
        changes, selected = [], {}
        for kind, ip in wanted.items():
            matches = matches_by_kind[kind]
            if matches:
                record = matches[0]
                ident = record["id"]
                if record.get("content") != ip:
                    # Only content changes. Keep existing TTL/proxy/comment/tags.
                    self.api("PATCH", self.prefix + "/" + ident, {"content": ip})
                    changes.append(kind)
            else:
                record = self.api("POST", self.prefix, {"type": kind, "name": name, "content": ip,
                                    "ttl": 1 if self.cf.get("proxied", False) else 300,
                                    "proxied": self.cf.get("proxied", False)})["result"]
                ident = record.get("id") if isinstance(record, dict) else None
                changes.append(kind)
            observed = self.read_record(ident, kind, name)
            if observed.get("content") != ip:
                raise NetworkError("dns_write_readback_mismatch")
            selected[kind] = {"record_id": ident, "content": ip, "proxied": observed.get("proxied") is True}
        return {"changed": changes, "records": selected}

    def dns_add(self, name, value, state):
        if name != "_acme-challenge." + self.config["domain"] or not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", value):
            raise NetworkError("dns_challenge_invalid")
        fingerprint = hashlib.sha256((name + "\0" + value).encode()).hexdigest()
        entries = state.setdefault("challenges", {})
        prior = entries.get(fingerprint)
        if prior:
            observed = self.read_record(prior["id"], "TXT", name)
            if observed.get("content") != value:
                raise NetworkError("challenge_record_changed")
            return fingerprint
        # A matching foreign TXT is never adopted or deleted during cleanup.
        matches = [r for r in self.records(name) if r.get("type") == "TXT" and r.get("content") == value]
        if matches:
            entries[fingerprint] = {"id": matches[0]["id"], "owned": False, "name": name, "value": value}
            return fingerprint
        created = self.api("POST", self.prefix, {"type": "TXT", "name": name, "content": value, "ttl": 120})["result"]
        ident = created.get("id") if isinstance(created, dict) else None
        if self.read_record(ident, "TXT", name).get("content") != value:
            raise NetworkError("challenge_write_readback_mismatch")
        entries[fingerprint] = {"id": ident, "owned": True, "name": name, "value": value}
        return fingerprint

    def dns_remove(self, name, value, state):
        fingerprint = hashlib.sha256((name + "\0" + value).encode()).hexdigest()
        entry = state.get("challenges", {}).get(fingerprint)
        if not entry:
            return False
        if entry.get("name") != name or entry.get("value") != value:
            raise NetworkError("challenge_identity_mismatch")
        if entry.get("owned") is True:
            rows = self.records(name)
            if not any(row["id"] == entry["id"] for row in rows):
                del state["challenges"][fingerprint]
                return True
            observed = self.read_record(entry["id"], "TXT", name)
            if observed.get("content") != value:
                raise NetworkError("challenge_record_changed")
            self.api("DELETE", self.prefix + "/" + entry["id"])
            if any(row["id"] == entry["id"] for row in self.records(name)):
                raise NetworkError("challenge_cleanup_readback_failed")
        del state["challenges"][fingerprint]
        return True

def probe_signature(key, value):
    return hmac.new(key.encode(), encoded(value), hashlib.sha256).hexdigest()


class PinnedHTTPS(http.client.HTTPSConnection):
    """Resolve once, reject private destinations, retain certificate/SNI checks."""
    def __init__(self, host, ip, timeout):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self.pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self.pinned_ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def probe_request(url, payload, key, timeout=12):
    public_probe_url(url)
    parsed = urlsplit(url)
    try:
        resolved = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        ips = sorted({address(row[4][0]) for row in resolved})
        if not ips:
            raise NetworkError("probe_dns_empty")
        connection = PinnedHTTPS(parsed.hostname, ips[0], timeout)
        try:
            connection.request("POST", parsed.path or "/", encoded(payload),
                               {"Content-Type": "application/json", "X-HuaRun-Signature": probe_signature(key, payload)})
            response = connection.getresponse()
            if response.status != 200:
                raise NetworkError("probe_http_failed")
            raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise NetworkError("probe_response_too_large")
        finally:
            connection.close()
        data = json.loads(raw)
    except (OSError, ValueError, ssl.SSLError, http.client.HTTPException):
        raise NetworkError("probe_unavailable") from None
    if not isinstance(data, dict):
        raise NetworkError("probe_invalid_json")
    return data


def probe_results(config, connect_ip=None, path="/", transport=probe_request, now=time.time):
    output = []
    for probe in config.get("probes", []):
        payload = {"schema_version": 1, "nonce": secrets.token_hex(16), "domain": config["domain"],
                   "connect_ip": connect_ip, "path": path, "at": int(now())}
        try:
            data = transport(probe["url"], payload, probe["key"])
            observed = data.get("result")
            if (not isinstance(observed, dict) or
                    not hmac.compare_digest(str(data.get("signature", "")), probe_signature(probe["key"], observed))):
                raise NetworkError("probe_signature_invalid")
            if (observed.get("nonce") != payload["nonce"] or observed.get("domain") != payload["domain"]
                    or observed.get("connect_ip") != connect_ip or type(observed.get("at")) is not int
                    or abs(now() - observed["at"]) > 90):
                raise NetworkError("probe_response_not_bound")
            checks = ("tcp_ok", "tls_ok", "websocket_ok")
            if any(type(observed.get(name)) is not bool for name in checks):
                raise NetworkError("probe_result_invalid")
            output.append({"region": probe["region"], "host": urlsplit(probe["url"]).hostname,
                           "verified": True, "reachable": all(observed[name] for name in checks)})
        except NetworkError as error:
            output.append({"region": probe["region"], "host": urlsplit(probe["url"]).hostname,
                           "verified": False, "reachable": None, "code": str(error)})
    return output


def doctor(lock_fd=None, runner=subprocess.run):
    env = dict(os.environ)
    passed = ()
    if lock_fd is not None:
        env["HUARUN_UPDATE_LOCK_FD"] = str(lock_fd)
        passed = (lock_fd,)
    try:
        result = runner(["/usr/local/bin/huarun", "doctor", "--json"], capture_output=True,
                        text=True, timeout=45, env=env, pass_fds=passed)
        body = json.loads(result.stdout)
        checks = body.get("checks", {})
        return (result.returncode == 0 and body.get("all_ok") is True and
                all(isinstance(checks.get(key), dict) and checks[key].get("ok") is True for key in DOCTOR_CHECKS)
                and local_node_healthy())
    except (OSError, ValueError, subprocess.TimeoutExpired, TypeError):
        return False


class Network:
    def __init__(self, config_path=CONFIG, state_dir=STATE_DIR, transport=request,
                 probe_transport=probe_request, clock=time.time, doctor_fn=doctor, provider_factory=None):
        self.config_path, self.state_dir = Path(config_path), Path(state_dir)
        self.state_path = self.state_dir / "state.json"
        self.transport, self.probe_transport, self.clock = transport, probe_transport, clock
        self.doctor_fn, self.provider_factory = doctor_fn, provider_factory
        self.lock_fd = None

    def config(self):
        value = load_private(self.config_path)
        return None if value is None else validate_config(value)

    def state(self):
        return load_private(self.state_path, {"schema_version": 1, "status": "not_configured", "failures": 0,
                                              "events": [], "outbox": [], "challenges": {}}, limit=MAX_BYTES)

    def save(self, state):
        state["updated_at"] = int(self.clock())
        if len(encoded(state)) > MAX_BYTES:
            raise NetworkError("state_too_large")
        atomic_private(self.state_path, state)

    def provider(self, config):
        settings = config.get("provider", {"kind": "manual"})
        factory = self.provider_factory
        if factory is None:
            try:
                from ip_provider import get_provider
            except ImportError:
                raise NetworkError("provider_module_unavailable") from None
            factory = get_provider
        return factory(settings, self.state_dir / "provider")

    def inbound(self, config):
        source = config["address_source"]
        if source["mode"] == "static":
            return source["addresses"]
        if source["mode"] in ("provider", "digitalocean", "hetzner_floating"):
            try:
                return addresses(self.provider(config).get_inbound_addresses())
            except Exception as error:
                if isinstance(error, NetworkError):
                    raise
                raise NetworkError("provider_address_unavailable") from None
        observed = [address(self.transport("GET", url), "A") for url in IP_SERVICES]
        if len(set(observed)) != 1:
            raise NetworkError("public_ip_sources_disagree")
        return {"A": observed[0]}

    def status(self):
        config = self.config()
        state = self.state()
        if config is None:
            return {"configured": False, "status": "not_configured", "notification": "not_configured"}
        return {"configured": True, "domain": config["domain"], "status": state.get("status", "configured"),
                "address_source": config["address_source"]["mode"],
                "cloudflare": {"account_id": config["cloudflare"]["account_id"],
                               "zone_id": config["cloudflare"]["zone_id"], "credential": "stored",
                               "requested_permissions": "Full account and zone access"},
                "notification": "configured" if config["notification"]["kind"] == "telegram" else "not_configured",
                "pending_notifications": len(state.get("outbox", [])),
                "probe_count": len(config["probes"]), "failures": state.get("failures", 0),
                "provider": config.get("provider", {}).get("kind", "manual"),
                "last_check": state.get("last_check"), "last_error": state.get("last_error"),
                "last_notification": state.get("last_notification"),
                "provider_result": state.get("provider_result"),
                "notification_status": state.get("notification_status", "not_configured"),
                "addresses": {k: v.get("content") for k, v in state.get("records", {}).items()}}

    def event(self, state, code, text, force=False):
        # One notification per incident/code. Time-bounded non-incident events
        # (DNS/probe setup/errors) remain useful without flooding every timer tick.
        stamp = str(state.get("incident_id", "none")) + ":" + code
        seen = state.setdefault("event_seen", {})
        previous = seen.get(stamp)
        if not force and previous is not None and self.clock() - previous < 21600:
            return
        seen[stamp] = int(self.clock())
        state["event_seen"] = dict(sorted(seen.items(), key=lambda item: item[1])[-128:])
        item = {"id": secrets.token_hex(8), "at": int(self.clock()), "code": code, "text": text[:1500],
                "attempts": 0, "next_attempt": 0}
        state.setdefault("events", []).append({k: item[k] for k in ("id", "at", "code")})
        state["events"] = state["events"][-100:]
        state.setdefault("outbox", []).append(item)
        state["outbox"] = state["outbox"][-100:]
        state["last_event"] = code
        self.save(state)

    def deliver(self, config, state):
        notification = config["notification"]
        if notification["kind"] != "telegram":
            state["notification_status"] = "not_configured"
            return
        state["notification_status"] = "configured"
        for item in list(state.get("outbox", [])):
            if item.get("next_attempt", 0) > self.clock():
                continue
            try:
                result = self.transport("POST", "https://api.telegram.org/bot" + notification["bot_token"] + "/sendMessage",
                                        {"chat_id": str(notification["chat_id"]), "text": item["text"],
                                         "disable_web_page_preview": True})
                if result.get("ok") is not True or not isinstance(result.get("result", {}).get("message_id"), int):
                    raise NetworkError("notification_delivery_unconfirmed")
            except NetworkError:
                item["attempts"] = item.get("attempts", 0) + 1
                item["next_attempt"] = int(self.clock()) + min(21600, 60 * 2 ** min(item["attempts"], 8))
                state["last_notification"] = {"status": "retry_pending", "at": int(self.clock())}
                self.save(state)
                break
            state["outbox"].remove(item)
            state["last_notification"] = {"status": "delivered", "at": int(self.clock()), "event_id": item["id"]}
            self.save(state)

    def configure(self, value, allow_domain_change=False, info_path="/etc/huarun/info.json"):
        config = validate_config(value)
        info = Path(info_path)
        if info.exists():
            try:
                old_domain = json.loads(info.read_bytes())["domain"]
            except (ValueError, KeyError):
                raise NetworkError("installed_domain_unreadable") from None
            if old_domain != config["domain"] and not allow_domain_change:
                raise NetworkError("domain_change_requires_migration")
        cf = Cloudflare(config, self.transport)
        cf.verify()
        # Only validate addresses here; prepare performs the explicitly selected DNS operation.
        self.inbound(config)
        atomic_private(self.config_path, config)
        state = self.state()
        state["status"], state["last_error"] = "configured", None
        self.save(state)
        if config["notification"]["kind"] == "telegram":
            self.notify_test()
        return self.status()

    def prepare(self, expected_domain=None):
        config = self.config()
        if config is None:
            raise NetworkError("configuration_required")
        if expected_domain is not None and hostname(expected_domain) != config["domain"]:
            raise NetworkError("configured_domain_mismatch")
        cf = Cloudflare(config, self.transport)
        cf.verify()
        observed = cf.sync(self.inbound(config))
        state = self.state()
        state["records"] = observed["records"]
        state["status"] = "dns_ready"
        self.save(state)
        return {"domain": config["domain"], "status": "dns_ready", "changed": observed["changed"]}

    def challenge(self, operation, name, value):
        config = self.config()
        if config is None:
            raise NetworkError("configuration_required")
        cf = Cloudflare(config, self.transport)
        cf.verify()
        state = self.state()
        if operation == "dns-add":
            cf.dns_add(name, value, state)
        else:
            cf.dns_remove(name, value, state)
        self.save(state)
        return {"status": "created" if operation == "dns-add" else "removed"}

    def notify_test(self):
        config = self.config()
        if config is None or config["notification"]["kind"] != "telegram":
            raise NetworkError("notification_not_configured")
        state = self.state()
        self.event(state, "notification_test", "华润网络助手：" + config["domain"] + " 的故障与恢复通知已连接。", force=True)
        self.deliver(config, state)
        self.save(state)
        return {"status": state.get("last_notification", {}).get("status", "pending")}

    def _path(self):
        try:
            data = json.loads(Path("/etc/huarun/info.json").read_bytes())
            value = data.get("wsPath", "/")
            if isinstance(value, str) and re.fullmatch(r"/[A-Za-z0-9/_-]{0,160}", value):
                return value
        except (OSError, ValueError):
            pass
        return "/"

    def observations(self, config, connect_ip=None):
        return probe_results(config, connect_ip, self._path(), self.probe_transport, self.clock)

    @staticmethod
    def confirmed(results, reachable):
        # Mixed evidence cannot authorize an automatic origin change.
        if reachable is False and any(r.get("verified") is True and r.get("reachable") is True for r in results):
            return False
        rows = [r for r in results if r.get("verified") is True and r.get("reachable") is reachable]
        return len({r["host"] for r in rows}) >= 2 and len({r["region"] for r in rows}) >= 2

    def run(self):
        config = self.config()
        if config is None:
            return {"status": "not_configured"}
        state = self.state()
        state["last_check"] = int(self.clock())
        cf = Cloudflare(config, self.transport)
        try:
            cf.verify()
            provider = None
            if config.get("provider", {}).get("kind") not in (None, "manual", "none"):
                provider = self.provider(config)
                if hasattr(provider, "restore_local_address"):
                    provider.restore_local_address()

            def commit(ip):
                result = cf.sync({"A": address(ip, "A")})
                state.setdefault("records", {}).update(result["records"])
                self.save(state)
                return True

            def verify(ip):
                return self.confirmed(self.observations(config, address(ip, "A")), True)

            # A running provider transaction must finish/recover before routine DDNS.
            if provider is not None and provider.pending():
                result = provider.rotate(state.get("incident_id", "recovery"), verify, commit)
                state["provider_result"] = {k: result.get(k) for k in ("status", "code")}
                state["status"] = "recovery_" + result.get("status", "failed")
                if result.get("status") == "rotated":
                    state["failures"] = 0
                    state["dns_settle_until"] = int(self.clock()) + 900
                    self.event(state, "ip_recovered", "华润网络助手：" + config["domain"] + " 已自动更换 IP，DNS 与双地区连接复查通过。")
                elif result.get("status") in ("deferred", "failed", "rolled_back"):
                    self.event(state, "provider_action_required", "华润网络助手：" + config["domain"] + " 自动换 IP 未完成，请查看 huarun network status，并到 VPS 面板处理；原配置与 Key 保留。")
                state["last_error"] = None
                self.deliver(config, state)
                self.save(state)
                return self.status()
            synced = cf.sync(self.inbound(config))
            state["records"] = synced["records"]
            if synced["changed"]:
                self.event(state, "dns_changed", "华润网络助手：" + config["domain"] + " 已同步新的入站 IP，原节点配置和 Key 保留。")
            healthy = self.doctor_fn(self.lock_fd)
            results = self.observations(config)
            state["probes"] = results
            if not healthy:
                state["failures"], state["status"] = 0, "local_service_fault"
                self.event(state, "local_service_fault", "华润网络助手：" + config["domain"] + " 本机服务或证书检查异常，未将它判定为 IP 封锁，也未更换 IP。请查看 huarun doctor。")
            elif self.confirmed(results, True):
                was_fault = state.get("status") not in ("healthy", "configured", "dns_ready", "not_configured")
                state["failures"], state["status"] = 0, "healthy"
                if was_fault:
                    self.event(state, "recovered", "华润网络助手：" + config["domain"] + " 已恢复，服务、TLS 和双地区连接检查通过。")
                state.pop("incident_id", None)
            elif self.confirmed(results, False) and self.clock() < state.get("dns_settle_until", 0):
                state["failures"], state["status"] = 0, "dns_propagating"
            elif self.confirmed(results, False):
                state["failures"] = state.get("failures", 0) + 1
                state["status"] = "regional_access_suspected"
                if state["failures"] >= HEALTH_FAILURES:
                    if not state.get("incident_id"):
                        state["incident_id"] = secrets.token_hex(12)
                    self.event(state, "regional_access_failure", "华润网络助手：" + config["domain"] + " 本机服务正常，但两个独立地区连续访问失败；疑似入口线路受阻。将按已配置的厂商恢复策略处理。")
                    # An edge outage cannot be fixed by rotating a healthy origin.
                    proxied = any(v.get("proxied") is True for v in state["records"].values())
                    if proxied:
                        state["status"] = "cdn_path_fault_manual_review"
                        self.event(state, "cdn_path_fault", "华润网络助手：" + config["domain"] + " 的 Cloudflare 入口持续异常；已暂停自动更换源站 IP，避免把 CDN 故障误判为源站 IP 故障。")
                    elif provider is not None:
                        result = provider.rotate(state["incident_id"], verify, commit)
                        state["provider_result"] = {k: result.get(k) for k in ("status", "code")}
                        state["status"] = "recovery_" + result.get("status", "failed")
                        if result.get("status") == "rotated":
                            state["failures"] = 0
                            state["dns_settle_until"] = int(self.clock()) + 900
                            self.event(state, "ip_recovered", "华润网络助手：" + config["domain"] + " 已自动更换 IP，DNS 与双地区连接复查通过。")
                        elif result.get("status") in ("deferred", "failed", "rolled_back"):
                            self.event(state, "provider_action_required", "华润网络助手：" + config["domain"] + " 无法按当前厂商授权完成自动换 IP，请查看 huarun network status，并到 VPS 面板处理；新 IP 就绪后会继续同步 DNS。")
                    else:
                        state["status"] = "manual_ip_change_required"
                        self.event(state, "manual_ip_change_required", "华润网络助手：" + config["domain"] + " 持续访问异常，当前厂商未接入自动换 IP。请到 VPS 面板或联系厂商更换 IP；系统会继续检测并同步 DNS。")
            else:
                state["failures"], state["status"] = 0, "reachability_unconfirmed"
                self.event(state, "probe_setup_required", "华润网络助手：" + config["domain"] + " 尚缺两个独立地区的有效探针结果；本机检查正常，无法据此认定被墙，未自动更换 IP。")
            state["last_error"] = None
        except Exception as error:
            # Provider exceptions may contain URLs or credentials: only expose our fixed codes.
            code = str(error) if isinstance(error, NetworkError) else "provider_or_runtime_failed"
            state["status"], state["last_error"] = "error", code
            self.event(state, "maintenance_error_" + code, "华润网络助手：" + config["domain"] + " 网络维护未完成（" + code + "）。原节点和 Key 保留，请查看 network status。")
        self.deliver(config, state)
        self.save(state)
        return self.status()

def discover_zone(token, domain, transport=request):
    parts = hostname(domain).split(".")
    for offset in range(len(parts) - 1):
        suffix = ".".join(parts[offset:])
        data = transport("GET", CF + "/zones?" + urlencode({"name": suffix, "per_page": 50}),
                         None, {"Authorization": "Bearer " + token})
        if data.get("success") is not True:
            raise NetworkError("cloudflare_zone_discovery_failed")
        matches = [item for item in data.get("result", []) if isinstance(item, dict) and item.get("name") == suffix]
        if len(matches) > 1:
            raise NetworkError("cloudflare_zone_ambiguous")
        if matches:
            return matches[0].get("account", {}).get("id"), matches[0].get("id")
    raise NetworkError("domain_not_in_cloudflare_account")


def provider_choices():
    """Only advertise implemented provider adapters in terminal onboarding."""
    labels = {"digitalocean": "DigitalOcean Reserved IPv4",
              "hetzner_floating": "Hetzner Floating IPv4",
              "vultr": "Vultr Reserved IPv4", "aws_eip": "AWS EC2 Elastic IPv4"}
    try:
        from ip_provider import capabilities
        available = {row["kind"] for row in capabilities() if row.get("automatic_rotation") is True}
    except (ImportError, KeyError, TypeError):
        available = set()
    return [(kind, label) for kind, label in labels.items() if kind in available]


def interactive_provider(kind):
    if kind == "aws_eip":
        provider = {"kind": kind, "account_id": input("AWS Account ID（12 位）: ").strip(),
                    "region": input("AWS Region（如 us-east-1）: ").strip(),
                    "instance_id": input("EC2 Instance ID（i-...）: ").strip(),
                    "access_key_id": getpass.getpass("AWS Access Key ID（隐藏输入）: ").strip(),
                    "secret_access_key": getpass.getpass("AWS Secret Access Key（隐藏输入）: ").strip(),
                    "auto_rotate": False, "cleanup_owned_old_ip": False}
        session = getpass.getpass("AWS Session Token（长期凭据可留空，隐藏输入）: ").strip()
        if session:
            provider["session_token"] = session
        interface = input("Network Interface ID（空则唯一主 ENI）: ").strip()
        private_ip = input("Private IPv4（空则主私网地址）: ").strip()
        if interface:
            provider["network_interface_id"] = interface
        if private_ip:
            provider["private_ip_address"] = private_ip
        if input("授权已绑定 EIP 的实例自动申请并切换 EIP（可能短暂中断及产生 IPv4 费用）？[y/N]: ").strip().lower() == "y":
            provider.update(auto_rotate=True, allow_reserved_ip_allocation=True, allow_downtime=True,
                            max_attempts_per_day=int(input("每日最多换 IP 次数 [1]: ").strip() or "1"),
                            max_elastic_ips=5,
                            max_monthly_ipv4_usd=float(input("公网 IPv4 预计月费上限（美元）[20]: ").strip() or "20"))
            provider["cleanup_owned_old_ip"] = input("新入口验证后回收本工具创建的旧 EIP（保留原有地址）？[Y/n]: ").strip().lower() != "n"
        return provider
    if kind not in ("digitalocean", "hetzner_floating", "vultr"):
        raise NetworkError("provider_interactive_setup_unavailable")
    provider = {"kind": kind, "token": getpass.getpass("厂商 API Token（隐藏输入）: ").strip(),
                "auto_rotate": False, "cleanup_owned_old_ip": False}
    instance = input("实例 ID（Vultr 为 UUID，其余为数字）: ").strip()
    provider["instance_id"] = instance if kind == "vultr" else int(instance)
    provider["region"] = input("实例地域标识（如 nyc3 / fsn1 / sea）: ").strip()
    if kind in ("hetzner_floating", "vultr"):
        provider["interface"] = input("公网接口名称（如 eth0 / ens3）: ").strip()
        selected = input("已在使用的 Floating / Reserved IPv4（无则留空）: ").strip()
        if selected:
            provider["managed_ip"] = address(selected, "A")
    wording = ("授权故障时自动分配并切换 Reserved IPv4（可能短暂中断及产生闲置 IP 费用）？[y/N]: "
               if kind == "digitalocean" else
               "授权故障时自动申请新 IPv4 并添加本机 /32 地址（保留主 IP，可能产生地址费用）？[y/N]: ")
    if input(wording).strip().lower() == "y":
        provider["auto_rotate"] = True
        provider["max_attempts_per_day"] = int(input("每日最多换 IP 次数 [1]: ").strip() or "1")
        if kind == "digitalocean":
            provider.update(allow_reserved_ip_allocation=True, allow_downtime=True, max_unassigned_ips=2,
                            max_monthly_unassigned_usd=float(input("闲置 IPv4 预计月费上限（美元）[10]: ").strip() or "10"))
        elif kind == "hetzner_floating":
            provider.update(allow_floating_ip_allocation=True, allow_guest_network_changes=True, max_floating_ips=2,
                            max_monthly_floating_eur=float(input("Floating IPv4 预计月费上限（欧元）[6]: ").strip() or "6"))
        else:
            provider.update(allow_reserved_ip_allocation=True, allow_guest_network_changes=True, max_reserved_ips=2,
                            max_monthly_reserved_usd=float(input("Reserved IPv4 预计月费上限（美元）[6]: ").strip() or "6"))
        provider["cleanup_owned_old_ip"] = input("新入口验证后回收本工具创建的旧 IP（保留原有地址）？[Y/n]: ").strip().lower() != "n"
    return provider


def interactive_config(domain=None):
    if not sys.stdin.isatty():
        raise NetworkError("terminal_required")
    domain = hostname(domain or input("固定节点域名（已接入 Cloudflare 的自有域名）: ").strip())
    token = getpass.getpass("Cloudflare Full account and zone access 账户令牌（隐藏输入）: ").strip()
    secret_string(token, "cloudflare_token")
    account, zone = discover_zone(token, domain)
    options = provider_choices()
    available = {str(index + 3): kind for index, (kind, label) in enumerate(options)}
    menu = "入站地址来源：1 固定 IP，2 本机动态公网 IP（无 NAT）"
    menu += "".join("，" + str(index + 3) + " " + label for index, (_, label) in enumerate(options))
    choice = input(menu + " [2]: ").strip() or "2"
    value = {"schema_version": 1, "domain": domain,
             "cloudflare": {"account_id": account, "zone_id": zone, "api_token": token,
                            "proxied": input("新建 DNS 记录是否启用 Cloudflare 代理？[y/N]: ").strip().lower() == "y"},
             "probes": [], "notification": {"kind": "none"}}
    if choice == "1":
        ipv4 = input("入站公网 IPv4（可留空）: ").strip()
        ipv6 = input("入站公网 IPv6（可留空）: ").strip()
        value["address_source"] = {"mode": "static", "addresses": {k: ip for k, ip in (("A", ipv4), ("AAAA", ipv6)) if ip}}
    elif choice == "2":
        yes = input("确认出口公网 IPv4 就是此 VPS 的可访问入站 IPv4（无 NAT / Reserved IP）？[y/N]: ").strip().lower()
        if yes != "y":
            raise NetworkError("inbound_ip_confirmation_required")
        value["address_source"] = {"mode": "consensus", "no_nat_confirmed": True}
    elif choice in available:
        value["address_source"] = {"mode": "provider"}
        value["provider"] = interactive_provider(available[choice])
    else:
        raise NetworkError("address_source_invalid")
    if input("配置 Telegram 故障及恢复通知？[Y/n]: ").strip().lower() != "n":
        value["notification"] = {"kind": "telegram",
                                 "bot_token": getpass.getpass("Telegram Bot Token（隐藏输入）: ").strip(),
                                 "chat_id": input("接收通知的 Chat ID: ").strip()}
    if input("现在配置两个独立地区的自有 HTTPS 探针？[y/N]: ").strip().lower() == "y":
        for number in (1, 2):
            value["probes"].append({"url": input("探针 " + str(number) + " HTTPS URL: ").strip(),
                                    "region": input("地区标识（如 cn-telecom）: ").strip().lower(),
                                    "key": getpass.getpass("探针 HMAC Key（至少 32 字符，隐藏输入）: ").strip()})
    return value


def local_node_healthy(info_path="/etc/huarun/info.json"):
    """Check the installed TLS/WS path before blaming an external route."""
    try:
        value = json.loads(Path(info_path).read_bytes())
        domain, path = hostname(value.get("domain")), value.get("wsPath")
        if not isinstance(path, str) or not re.fullmatch(r"/[A-Za-z0-9/_-]{0,160}", path):
            return False
        result = _observe_connection(domain, "127.0.0.1", path)
        return all(result.get(name) is True for name in ("tcp_ok", "tls_ok", "websocket_ok"))
    except (OSError, ValueError, NetworkError, AttributeError):
        return False


def observe_target(domain, connect_ip, path):
    """Public probes reject private targets and verify TCP, TLS and WS."""
    try:
        if connect_ip is not None:
            ips = [address(connect_ip)]
        else:
            ips = sorted({address(row[4][0]) for row in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)})
        if not ips:
            raise NetworkError("target_dns_empty")
    except (OSError, NetworkError):
        return {"tcp_ok": False, "tls_ok": False, "websocket_ok": False}
    return _observe_connection(domain, ips[0], path)


def _observe_connection(domain, ip, path):
    result = {"tcp_ok": False, "tls_ok": False, "websocket_ok": False}
    sock = None
    try:
        sock = socket.create_connection((ip, 443), timeout=7)
        result["tcp_ok"] = True
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=domain)
        result["tls_ok"] = True
        ws_key = base64.b64encode(secrets.token_bytes(16)).decode()
        request_bytes = ("GET " + path + " HTTP/1.1\r\nHost: " + domain +
                         "\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: " +
                         ws_key + "\r\n\r\n").encode()
        sock.sendall(request_bytes)
        response = http.client.HTTPResponse(sock)
        response.begin()
        expected = base64.b64encode(hashlib.sha1((ws_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        result["websocket_ok"] = response.status == 101 and hmac.compare_digest(response.getheader("Sec-WebSocket-Accept", ""), expected)
    except (OSError, ssl.SSLError, NetworkError, http.client.HTTPException):
        pass
    finally:
        if sock is not None:
            sock.close()
    return result


def make_probe_handler(config, observer=observe_target, clock=time.time):
    domain = hostname(config.get("domain"))
    key = secret_string(config.get("key"), "probe_key", 32)
    path = config.get("path")
    if not isinstance(path, str) or not re.fullmatch(r"/[A-Za-z0-9/_-]{0,160}", path):
        raise NetworkError("probe_target_path_invalid")
    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/probe":
                self.send_error(404)
                return
            try:
                self.connection.settimeout(10)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise NetworkError("invalid_request")
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise NetworkError("invalid_request")
                if not hmac.compare_digest(self.headers.get("X-HuaRun-Signature", ""), probe_signature(key, value)):
                    raise NetworkError("unauthorized")
                nonce = value.get("nonce")
                if (value.get("schema_version") != 1 or value.get("domain") != domain or value.get("path") != path
                        or type(value.get("at")) is not int or abs(clock() - value["at"]) > 90
                        or not isinstance(nonce, str) or not re.fullmatch(r"[a-f0-9]{32}", nonce)):
                    raise NetworkError("request_not_bound")
                for old, timestamp in list(seen.items()):
                    if timestamp < clock() - 180:
                        del seen[old]
                if nonce in seen or len(seen) > 1000:
                    raise NetworkError("replayed_request")
                ip = value.get("connect_ip")
                if ip is not None:
                    ip = address(ip)
                seen[nonce] = clock()
                result = {"nonce": nonce, "domain": domain, "connect_ip": ip, "at": int(clock()),
                          **observer(domain, ip, path)}
                raw = encoded({"result": result, "signature": probe_signature(key, result)})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except (NetworkError, ValueError, OSError):
                self.send_error(403, "Rejected")

        def log_message(self, *unused):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("configure", "prepare", "status", "run", "config-domain",
                                           "dns-add", "dns-remove", "notify-test", "probe-server"), nargs="?")
    parser.add_argument("challenge_name", nargs="?")
    parser.add_argument("challenge_value", nargs="?")
    parser.add_argument("--domain")
    parser.add_argument("--configure-stdin", action="store_true")
    parser.add_argument("--allow-domain-change", action="store_true")
    parser.add_argument("--probe-config", type=Path)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9077)
    args = parser.parse_args()
    operation = "configure" if args.configure_stdin else args.command
    if operation is None:
        parser.error("command required")
    if os.geteuid() != 0:
        raise NetworkError("root_required")
    network = Network()
    if operation == "status":
        result = network.status()
    elif operation == "config-domain":
        config = network.config()
        if config is None:
            raise NetworkError("configuration_required")
        print(config["domain"])
        return 0
    elif operation == "probe-server":
        if not args.probe_config or args.listen != "127.0.0.1" or not 1024 <= args.port <= 65535:
            raise NetworkError("probe_listener_invalid")
        handler = make_probe_handler(load_private(args.probe_config))
        http.server.ThreadingHTTPServer((args.listen, args.port), handler).serve_forever()
        return 0
    else:
        with MaintenanceLock() as lock:
            network.lock_fd = lock.fd if lock.inherited else None
            if operation == "configure":
                if args.configure_stdin:
                    raw = sys.stdin.buffer.read(MAX_CONFIG + 1)
                    if len(raw) > MAX_CONFIG:
                        raise NetworkError("configuration_too_large")
                    try:
                        config = json.loads(raw)
                    except (ValueError, UnicodeError):
                        raise NetworkError("configuration_json_invalid") from None
                    if args.allow_domain_change and os.environ.get("HUARUN_DOMAIN_MIGRATION") != "1":
                        raise NetworkError("domain_migration_wrapper_required")
                else:
                    config = interactive_config(args.domain)
                if args.domain and hostname(args.domain) != config.get("domain"):
                    raise NetworkError("configured_domain_mismatch")
                result = network.configure(config, args.allow_domain_change)
            elif operation == "prepare":
                result = network.prepare(args.domain)
            elif operation in ("dns-add", "dns-remove"):
                if args.challenge_name is None or args.challenge_value is None:
                    raise NetworkError("challenge_arguments_required")
                result = network.challenge(operation, args.challenge_name, args.challenge_value)
            elif operation == "notify-test":
                result = network.notify_test()
            else:
                result = network.run()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NetworkError as error:
        print(json.dumps({"status": "error", "code": str(error)}, ensure_ascii=False))
        raise SystemExit(75 if str(error) == "maintenance_busy" else 1) from None
    except (OSError, ValueError, TypeError, KeyError, KeyboardInterrupt):
        print('{"status":"error","code":"network_operation_failed"}')
        raise SystemExit(1) from None
