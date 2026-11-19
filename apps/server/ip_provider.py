#!/usr/bin/env python3
"""Bounded, crash-aware DigitalOcean Reserved IPv4 replacement.

The caller holds the HuaRun maintenance lock. It supplies independent reachability
verification and an idempotent DNS write/read-back callback. No server, disk, or
foreign IP is deleted. A lost allocation response requires reconciliation rather
than another potentially billable POST. Provider API contract verified 2026-11-18:
https://docs.digitalocean.com/products/networking/reserved-ips/how-to/modify/
https://docs.digitalocean.com/products/networking/reserved-ips/details/limits/
https://github.com/digitalocean/openapi/tree/master/specification/resources/reserved_ips
"""
from __future__ import annotations
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.digitalocean.com/v2"
UNASSIGNED_MONTHLY_USD = 5.0
PRICE_VERIFIED_ON = "2026-11-18"
MAX_RESPONSE = 2 * 1024 * 1024


class ProviderError(Exception):
    """Only a controlled nonsecret code crosses this boundary."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _ipv4(value):
    try:
        ip = ipaddress.ip_address(value)
        if ip.version != 4 or not ip.is_global:
            raise ValueError()
        return str(ip)
    except (ValueError, TypeError):
        raise ProviderError("provider_ipv4_invalid") from None


def _integer(value, lower, upper, code):
    if type(value) is not int or not lower <= value <= upper:
        raise ProviderError(code)
    return value


def _safe_id(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 256:
        raise ProviderError("incident_id_invalid")
    return hashlib.sha256(value.encode()).hexdigest()


def capabilities():
    tested = {"validation": "official_contract_tested", "live_verified": False, "address_family": "ipv4"}
    return [
        {**tested, "kind": "digitalocean", "automatic_rotation": True, "mechanism": "new_reserved_ipv4",
         "requires": ["provider_token", "instance_id", "region", "allocation_and_interruption_authorization", "independent_candidate_verification"],
         "source": "https://docs.digitalocean.com/products/networking/reserved-ips/details/limits/"},
        {**tested, "kind": "hetzner_floating", "automatic_rotation": True, "mechanism": "new_floating_ipv4",
         "requires": ["provider_token", "instance_id", "region", "interface", "allocation_and_guest_alias_authorization", "independent_candidate_verification"],
         "source": "https://docs.hetzner.com/cloud/floating-ips/overview/"},
        {**tested, "kind": "vultr", "automatic_rotation": True, "mechanism": "new_reserved_ipv4_cloud_compute",
         "requires": ["provider_token", "instance_id", "region", "interface", "allocation_and_guest_alias_authorization", "independent_candidate_verification"],
         "source": "https://docs.vultr.com/products/network/reserved-ips/management/attachment"},
        {**tested, "kind": "aws_eip", "automatic_rotation": True, "mechanism": "new_elastic_ipv4_online",
         "requires": ["aws_credentials", "account_id", "instance_id", "region", "existing_elastic_ip_for_rollback",
                      "allocation_and_interruption_authorization", "independent_candidate_verification"],
         "source": "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-eips.html"},
        {"kind": "aws_primary", "automatic_rotation": False, "reason": "external_controller_required",
         "mechanism": "stop_start_dynamic_public_ipv4", "live_verified": False,
         "source": "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/working-with-ip-addresses.html"},
        {"kind": "hetzner_primary", "automatic_rotation": False, "reason": "external_controller_required",
         "live_verified": False, "source": "https://docs.hetzner.com/cloud/servers/primary-ips/faq/"},
        {"kind": "vultr_bare_metal", "automatic_rotation": False, "reason": "external_controller_required",
         "live_verified": False, "source": "https://docs.vultr.com/products/compute/instances/bare-metal/networking/reserved-ips"},
        {"kind": "bandwagonhost", "automatic_rotation": "after_official_discovery_and_validation", "reason": "official_discovery_required",
         "validation": "official_documentation_unavailable", "live_verified": False, "source": "https://kiwivm.64clouds.com/api/"},
        {"kind": "auto", "automatic_rotation": "after_official_discovery_and_validation", "mechanism": "official_documentation_generated_http_contract", "reason": "provider_documentation_discovery", "live_verified": False},
    ]


class DigitalOceanAPI:
    origin = API
    patterns = {
        "GET": r"(?:/droplets/[1-9][0-9]*|/reserved_ips\?per_page=200&page=[1-9][0-9]*|/reserved_ips/[0-9.]+(?:/actions/[1-9][0-9]*)?)",
        "POST": r"(?:/reserved_ips|/reserved_ips/[0-9.]+/actions)",
        "DELETE": r"/reserved_ips/[0-9.]+",
    }
    missing_pattern = r"/reserved_ips/[0-9.]+"
    missing_key = "reserved_ip"
    def __init__(self, token):
        if not isinstance(token, str) or not 8 <= len(token) <= 512 or any(c.isspace() for c in token):
            raise ProviderError("provider_token_invalid")
        self._token = token
        self._opener = build_opener(NoRedirect)

    def __call__(self, method, path, data=None):
        patterns = self.patterns
        if method not in patterns or not isinstance(path, str) or not re.fullmatch(patterns[method], path):
            raise ProviderError("provider_api_path_invalid")
        raw = None if data is None else json.dumps(data, separators=(",", ":")).encode()
        request = Request(self.origin + path, data=raw, method=method, headers={
            "Authorization": "Bearer " + self._token, "Accept": "application/json",
            "Content-Type": "application/json", "User-Agent": "HuaRun-IP-Recovery/1.0"})
        try:
            with self._opener.open(request, timeout=20) as response:
                body = response.read(MAX_RESPONSE + 1)
        except HTTPError as error:
            if error.code == 404 and method == "GET" and re.fullmatch(self.missing_pattern, path):
                return {self.missing_key: None}
            if error.code == 404 and method == "DELETE":
                return {}
            raise ProviderError("provider_http_" + str(error.code)) from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("provider_network_unavailable") from None
        if len(body) > MAX_RESPONSE:
            raise ProviderError("provider_response_too_large")
        try:
            result = json.loads(body) if body else {}
        except (ValueError, UnicodeError):
            raise ProviderError("provider_invalid_json") from None
        if not isinstance(result, dict):
            raise ProviderError("provider_invalid_response")
        return result


class _Store:
    def __init__(self, root):
        self.root = Path(root)
        if any(part.is_symlink() for part in (self.root, *self.root.parents)):
            raise ProviderError("provider_state_symlink")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.stat().st_uid != os.geteuid():
            raise ProviderError("provider_state_owner_mismatch")
        self.root.chmod(0o700)

    def read(self, name, default):
        path = self.root / name
        if path.is_symlink():
            raise ProviderError("provider_state_symlink")
        if not path.exists():
            return default
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > MAX_RESPONSE:
            raise ProviderError("provider_state_permissions_invalid")
        try:
            value = json.loads(path.read_bytes())
        except (ValueError, OSError):
            raise ProviderError("provider_state_invalid") from None
        if not isinstance(value, dict):
            raise ProviderError("provider_state_invalid")
        return value

    def write(self, name, value):
        path = self.root / name
        if path.is_symlink():
            raise ProviderError("provider_state_symlink")
        tmp = self.root / (name + ".tmp." + str(os.getpid()) + "." + secrets.token_hex(4))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write((json.dumps(value, sort_keys=True) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
            descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            tmp.unlink(missing_ok=True)

    def remove(self, name):
        path = self.root / name
        if path.is_symlink():
            raise ProviderError("provider_state_symlink")
        path.unlink(missing_ok=True)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class DigitalOceanRotator:
    """No mutation occurs until rotate() has checked saved authorization/budgets."""
    def __init__(self, config, state_dir, request=None, clock=time.time):
        self.config = dict(config)
        self.instance = _integer(config.get("instance_id", config.get("droplet_id")), 1, 2**63-1, "provider_instance_invalid")
        self.region = config.get("region", "")
        if not isinstance(self.region, str) or not re.fullmatch(r"[a-z]{2,8}[1-9][0-9]?", self.region):
            raise ProviderError("provider_region_invalid")
        self.request = request if request is not None else DigitalOceanAPI(config.get("token"))
        self.clock = clock
        self.scope = "digitalocean:" + str(self.instance) + ":" + self.region
        self.store = _Store(Path(state_dir) / "digitalocean")

    def _ledger(self):
        ledger = self.store.read("ledger.json", {"scope": self.scope, "attempts": [], "owned": {}, "finished": {}})
        if ledger.get("scope") != self.scope:
            raise ProviderError("provider_state_scope_mismatch")
        if not isinstance(ledger.get("attempts"), list) or not isinstance(ledger.get("owned"), dict) or not isinstance(ledger.get("finished"), dict):
            raise ProviderError("provider_ledger_invalid")
        return ledger

    def _journal(self):
        journal = self.store.read("transaction.json", {})
        if journal and journal.get("scope") != self.scope:
            raise ProviderError("provider_state_scope_mismatch")
        return journal

    def pending(self):
        return bool(self._journal())

    def _save(self, journal):
        journal["updated_at"] = int(self.clock())
        self.store.write("transaction.json", journal)

    def _droplet(self):
        d = self.request("GET", "/droplets/" + str(self.instance)).get("droplet")
        if (not isinstance(d, dict) or d.get("id") != self.instance or d.get("region", {}).get("slug") != self.region
                or d.get("status") != "active"):
            raise ProviderError("provider_instance_identity_or_state_mismatch")
        return d

    def _ips(self):
        result = []
        for page in range(1, 11):
            data = self.request("GET", "/reserved_ips?per_page=200&page=" + str(page))
            rows = data.get("reserved_ips")
            if not isinstance(rows, list):
                raise ProviderError("provider_ip_list_invalid")
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("region"), dict):
                    raise ProviderError("provider_ip_list_invalid")
                _ipv4(row.get("ip"))
                assigned = row.get("droplet")
                if assigned is not None and (not isinstance(assigned, dict) or type(assigned.get("id")) is not int):
                    raise ProviderError("provider_ip_assignment_invalid")
            result.extend(rows)
            if not data.get("links", {}).get("pages", {}).get("next"):
                return result
        raise ProviderError("provider_ip_list_limit")

    def _get(self, ip):
        ip = _ipv4(ip)
        value = self.request("GET", "/reserved_ips/" + ip).get("reserved_ip")
        if value is None:
            return None
        if (not isinstance(value, dict) or value.get("ip") != ip
                or value.get("region", {}).get("slug") != self.region):
            raise ProviderError("provider_ip_identity_mismatch")
        assigned = value.get("droplet")
        if assigned is not None and (not isinstance(assigned, dict) or type(assigned.get("id")) is not int):
            raise ProviderError("provider_ip_assignment_invalid")
        return value

    @staticmethod
    def _assigned(value):
        return None if value is None or value.get("droplet") is None else value["droplet"]["id"]

    def get_inbound_addresses(self):
        droplet = self._droplet()
        bound = [row for row in self._ips() if self._assigned(row) == self.instance]
        if len(bound) > 1:
            raise ProviderError("provider_multiple_inbound_addresses")
        if bound:
            if bound[0].get("region", {}).get("slug") != self.region:
                raise ProviderError("provider_ip_region_mismatch")
            return {"A": _ipv4(bound[0].get("ip"))}
        values = [v.get("ip_address") for v in droplet.get("networks", {}).get("v4", []) if v.get("type") == "public"]
        if len(values) != 1:
            raise ProviderError("provider_public_ipv4_ambiguous")
        return {"A": _ipv4(values[0])}

    def current_ip(self):
        return self.get_inbound_addresses()["A"]

    def _authorization(self, ledger, rows):
        for key in ("auto_rotate", "allow_reserved_ip_allocation", "allow_downtime"):
            if self.config.get(key) is not True:
                raise ProviderError("provider_" + key + "_not_authorized")
        maximum = _integer(self.config.get("max_attempts_per_day", 1), 1, 3, "provider_attempt_limit_invalid")
        limit = _integer(self.config.get("max_unassigned_ips", 2), 1, 3, "provider_unassigned_limit_invalid")
        budget = self.config.get("max_monthly_unassigned_usd", 10)
        if type(budget) not in (int, float) or not math.isfinite(budget) or not 0 < budget <= 100:
            raise ProviderError("provider_budget_invalid")
        recent = [t for t in ledger["attempts"] if type(t) in (int, float) and t > self.clock() - 86400]
        if len(recent) >= maximum:
            raise ProviderError("provider_daily_attempt_limit")
        unassigned = sum(self._assigned(row) is None for row in rows)
        peak = unassigned + 1 + int(any(self._assigned(row) == self.instance for row in rows))
        if peak > limit or peak * UNASSIGNED_MONTHLY_USD > budget:
            raise ProviderError("provider_unassigned_budget_exceeded")
        ledger["attempts"] = recent + [int(self.clock())]

    def _start(self, incident, ledger):
        droplet = self._droplet()
        rows = self._ips()
        bound = [row for row in rows if self._assigned(row) == self.instance]
        if len(bound) > 1:
            raise ProviderError("provider_multiple_inbound_addresses")
        if bound:
            old = _ipv4(bound[0].get("ip"))
            if bound[0].get("region", {}).get("slug") != self.region:
                raise ProviderError("provider_ip_region_mismatch")
        else:
            public = [v.get("ip_address") for v in droplet.get("networks", {}).get("v4", []) if v.get("type") == "public"]
            if len(public) != 1:
                raise ProviderError("provider_public_ipv4_ambiguous")
            old = _ipv4(public[0])
        self._authorization(ledger, rows)
        journal = {"scope": self.scope, "incident": incident, "phase": "allocating", "created_at": int(self.clock()),
                   "old_ip": old, "old_reserved": bool(bound), "old_owned": old in ledger["owned"],
                   "before_ips": [row.get("ip") for row in rows], "dns_attempted": False, "new_ip": None}
        self.store.write("ledger.json", ledger)
        self._save(journal)  # Never repeat an allocation whose acknowledgement was lost.
        try:
            answer = self.request("POST", "/reserved_ips", {"region": self.region}).get("reserved_ip")
            if not isinstance(answer, dict):
                raise ProviderError("provider_allocation_response_invalid")
            new = _ipv4(answer.get("ip"))
            if (new == old or new in journal["before_ips"] or answer.get("region", {}).get("slug") != self.region
                    or self._assigned(answer) is not None):
                raise ProviderError("provider_allocation_identity_invalid")
            journal.update(new_ip=new, new_owned=True, phase="detach_old")
            self._save(journal)
            ledger["owned"][new] = {"created_at": journal["created_at"], "incident": incident}
            self.store.write("ledger.json", ledger)
        except Exception:
            journal.update(phase="allocation_unknown", code="provider_allocation_requires_reconciliation")
            self._save(journal)
        return journal

    def _assignment(self, journal, ip, target, label):
        value = self._get(ip)
        if value is None:
            raise ProviderError("provider_reserved_ip_disappeared")
        current = self._assigned(value)
        if current not in (None, self.instance):
            raise ProviderError("provider_ip_assigned_elsewhere")
        action = journal.get("action")
        if action:
            if action.get("ip") != ip or action.get("target") != target:
                raise ProviderError("provider_action_conflict")
            ident = action.get("id")
            if ident:
                result = self.request("GET", "/reserved_ips/" + ip + "/actions/" + str(ident)).get("action", {})
                if result.get("id") != ident:
                    raise ProviderError("provider_action_identity_mismatch")
                if result.get("status") == "errored":
                    journal.pop("action", None); self._save(journal)
                    raise ProviderError("provider_action_failed")
                if result.get("status") != "completed":
                    if self.clock() - action["started_at"] > 900:
                        journal["code"] = "provider_action_requires_reconciliation"; self._save(journal)
                    return False
            elif current != target:
                journal["code"] = "provider_action_requires_reconciliation"; self._save(journal)
                return False
            if current == target:
                journal.pop("action", None); self._save(journal)
                return True
            if self.clock() - action["started_at"] > 900:
                journal["code"] = "provider_action_requires_reconciliation"; self._save(journal)
            return False
        if current == target:
            return True
        journal["action"] = {"ip": ip, "target": target, "label": label, "started_at": int(self.clock())}
        self._save(journal)
        data = {"type": "assign", "droplet_id": target} if target is not None else {"type": "unassign"}
        try:
            action = self.request("POST", "/reserved_ips/" + ip + "/actions", data).get("action")
            if not isinstance(action, dict) or type(action.get("id")) is not int or action["id"] < 1:
                raise ProviderError("provider_action_response_invalid")
            journal["action"]["id"] = action["id"]; self._save(journal)
        except Exception:
            journal["code"] = "provider_action_requires_reconciliation"; self._save(journal)
        return False

    def _delete_created(self, journal, ip):
        ledger = self._ledger()
        owned = ip in ledger["owned"] or (ip == journal.get("new_ip") and journal.get("new_owned") is True)
        if not owned:
            raise ProviderError("provider_delete_not_owned")
        current = self._get(ip)
        if current is not None and self._assigned(current) is not None:
            raise ProviderError("provider_delete_still_assigned")
        if current is not None:
            self.request("DELETE", "/reserved_ips/" + ip)
            if self._get(ip) is not None:
                return False
        ledger["owned"].pop(ip, None); self.store.write("ledger.json", ledger)
        return True

    def _finish(self, journal, status, code):
        ip = journal["new_ip"] if status == "rotated" else journal["old_ip"]
        result = {"status": status, "code": code, "addresses": {"A": ip}, "incident": journal["incident"],
                  "old_reserved_ip_retained": bool(journal["old_reserved"] and not journal.get("old_deleted"))}
        ledger = self._ledger()
        if status == "rotated" and journal.get("new_owned") is True:
            ledger["owned"].setdefault(ip, {"created_at": journal["created_at"], "incident": journal["incident"]})
        ledger["finished"][journal["incident"]] = result
        ledger["finished"] = dict(list(ledger["finished"].items())[-100:])
        self.store.write("ledger.json", ledger)
        self.store.remove("transaction.json")
        return result

    def _prepare_old(self, journal):
        return not journal["old_reserved"] or self._assignment(journal, journal["old_ip"], None, "detach_old")

    def _prepare_candidate(self, journal):
        pass

    def _remove_candidate_local(self, journal):
        pass

    def _rollback(self, journal, update_dns):
        new = journal.get("new_ip")
        if not new:
            return {"status": "deferred", "code": "provider_allocation_requires_reconciliation"}
        if journal["phase"] == "rollback_detach":
            self._remove_candidate_local(journal)
            if not self._assignment(journal, new, None, "rollback_detach_new"):
                return {"status": "pending", "code": journal.get("code", "provider_rollback_in_progress")}
            journal["phase"] = "rollback_old"; self._save(journal)
        if journal["phase"] == "rollback_old":
            if journal["old_reserved"] and not self._assignment(journal, journal["old_ip"], self.instance, "rollback_restore_old"):
                return {"status": "pending", "code": journal.get("code", "provider_rollback_in_progress")}
            journal["phase"] = "rollback_dns"; self._save(journal)
        if journal["phase"] == "rollback_dns":
            if journal["dns_attempted"]:
                try:
                    if update_dns(journal["old_ip"]) is not True:
                        return {"status": "pending", "code": "provider_dns_rollback_pending"}
                except Exception:
                    return {"status": "pending", "code": "provider_dns_rollback_pending"}
            journal["phase"] = "rollback_cleanup"; self._save(journal)
        if not self._delete_created(journal, new):
            return {"status": "pending", "code": "provider_cleanup_pending"}
        return self._finish(journal, "rolled_back", journal.get("failure", "provider_recovery_failed"))

    def rotate(self, incident_id, verify_ip, update_dns):
        """Advance a durable transaction; callbacks must not echo credentials.

        Call on subsequent timer ticks while pending() is true. Do not publish
        get_inbound_addresses() to DNS during a pending transaction: that address
        may be a candidate awaiting independent verification.
        """
        try:
            verified_now = False
            incident = _safe_id(incident_id)
            ledger = self._ledger(); journal = self._journal()
            if not journal:
                if incident in ledger["finished"]:
                    return ledger["finished"][incident]
                journal = self._start(incident, ledger)
            if journal["phase"] in ("allocating", "allocation_unknown"):
                return {"status": "deferred", "code": "provider_allocation_requires_reconciliation"}
            if journal["phase"].startswith("rollback_"):
                return self._rollback(journal, update_dns)
            if journal["phase"] == "detach_old":
                if not self._prepare_old(journal):
                    return {"status": "pending", "code": journal.get("code", "provider_action_pending")}
                journal["phase"] = "assign_new"; self._save(journal)
            if journal["phase"] == "assign_new":
                if not self._assignment(journal, journal["new_ip"], self.instance, "assign_new"):
                    return {"status": "pending", "code": journal.get("code", "provider_action_pending")}
                journal["phase"] = "verify_new"; self._save(journal)
            if journal["phase"] == "verify_new":
                self._prepare_candidate(journal)
                if self.clock() < journal.get("next_verify_at", 0):
                    return {"status": "pending", "code": "provider_candidate_verification_pending"}
                try:
                    verified = verify_ip(journal["new_ip"]) is True
                except Exception:
                    verified = False
                if not verified:
                    journal["verify_failures"] = journal.get("verify_failures", 0) + 1
                    journal["next_verify_at"] = int(self.clock()) + 30
                    self._save(journal)
                    if journal["verify_failures"] < 3:
                        return {"status": "pending", "code": "provider_candidate_verification_pending"}
                    raise ProviderError("provider_candidate_unreachable")
                verified_now = True
                journal["phase"] = "commit_dns"; self._save(journal)
            if journal["phase"] == "commit_dns":
                if not verified_now:
                    self._prepare_candidate(journal)
                    try:
                        verified_now = verify_ip(journal["new_ip"]) is True
                    except Exception:
                        verified_now = False
                    if not verified_now:
                        raise ProviderError("provider_candidate_unreachable")
                journal["dns_attempted"] = True; self._save(journal)
                try:
                    committed = update_dns(journal["new_ip"]) is True
                except Exception:
                    committed = False
                if not committed:
                    raise ProviderError("provider_dns_commit_failed")
                journal["phase"] = "cleanup_old"; self._save(journal)
            if journal["phase"] == "cleanup_old":
                if journal["old_reserved"] and journal["old_owned"] and self.config.get("cleanup_owned_old_ip") is True:
                    if not self._delete_created(journal, journal["old_ip"]):
                        return {"status": "pending", "code": "provider_old_ip_cleanup_pending"}
                    journal["old_deleted"] = True; self._save(journal)
                return self._finish(journal, "rotated", "provider_ip_rotated")
            raise ProviderError("provider_transaction_phase_invalid")
        except ProviderError as error:
            code = str(error)
            try:
                journal = self._journal()
            except ProviderError:
                return {"status": "failed", "code": code}
            if journal and journal.get("new_ip") and not journal.get("action") and not journal.get("phase", "").startswith("rollback_") and journal.get("phase") != "cleanup_old":
                journal.update(phase="rollback_detach", failure=code); self._save(journal)
                return {"status": "pending", "code": "provider_rollback_required"}
            return {"status": "deferred" if journal else "failed", "code": code}
        except Exception:
            # A provider or callback may include a Key in its exception. Do not echo it.
            return {"status": "deferred", "code": "provider_operation_failed"}


class HetznerAPI(DigitalOceanAPI):
    origin = "https://api.hetzner.cloud/v1"
    patterns = {
        "GET": r"(?:/servers/[1-9][0-9]*|/floating_ips\?per_page=50&page=[1-9][0-9]*|/floating_ips/[1-9][0-9]*|/actions/[1-9][0-9]*)",
        "POST": r"(?:/floating_ips|/floating_ips/[1-9][0-9]*/actions/(?:assign|unassign))",
        "DELETE": r"/floating_ips/[1-9][0-9]*",
    }
    missing_pattern = r"/floating_ips/[1-9][0-9]*"
    missing_key = "floating_ip"


class LocalIPv4Alias:
    """Only /32 aliases on an explicitly selected interface; never restart networking."""
    def __init__(self, interface, run=None):
        if not isinstance(interface, str) or not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,15}", interface) or interface.startswith("-"):
            raise ProviderError("provider_interface_invalid")
        self.interface = interface
        self.run = run or subprocess.run
        self.executable = next((x for x in ("/usr/sbin/ip", "/sbin/ip", "/usr/bin/ip", "/bin/ip") if Path(x).is_file()), "/usr/sbin/ip")

    def _command(self, args):
        try:
            result = self.run([self.executable, *args], check=False, capture_output=True, text=True, timeout=10)
        except Exception:
            raise ProviderError("provider_guest_network_command_failed") from None
        if result.returncode != 0:
            raise ProviderError("provider_guest_network_command_failed")
        return result.stdout

    def addresses(self):
        try:
            data = json.loads(self._command(["-j", "-4", "address", "show", "dev", self.interface]))
            if len(data) != 1 or data[0].get("ifname") != self.interface:
                raise ValueError()
            return {x["local"]: x["prefixlen"] for x in data[0]["addr_info"] if x.get("family") == "inet"}
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("provider_guest_network_response_invalid") from None

    def ensure(self, ip):
        ip = _ipv4(ip)
        values = self.addresses()
        if ip in values:
            if values[ip] != 32:
                raise ProviderError("provider_guest_address_conflict")
            return
        self._command(["-4", "address", "add", ip + "/32", "dev", self.interface])
        if self.addresses().get(ip) != 32:
            raise ProviderError("provider_guest_address_not_installed")

    def remove(self, ip):
        ip = _ipv4(ip)
        values = self.addresses()
        if ip not in values:
            return
        if values[ip] != 32:
            raise ProviderError("provider_guest_address_conflict")
        self._command(["-4", "address", "del", ip + "/32", "dev", self.interface])
        if ip in self.addresses():
            raise ProviderError("provider_guest_address_not_removed")


class HetznerFloatingRotator(DigitalOceanRotator):
    """Online replacement, preserving primary and existing Floating IP bindings.

    Official contract: https://github.com/hetznercloud/hcloud-python/blob/main/hcloud/floating_ips/client.py
    Guest setup: https://docs.hetzner.com/cloud/floating-ips/persistent-configuration/
    The maintenance timer calls restore_local_address() after reboot. Only a new
    /32 address owned by this transaction is ever added/removed locally.
    """
    def __init__(self, config, state_dir, request=None, clock=time.time, local=None):
        self.config = dict(config)
        self.instance = _integer(config.get("instance_id"), 1, 2**63-1, "provider_instance_invalid")
        self.region = config.get("region", "")
        if not isinstance(self.region, str) or not re.fullmatch(r"[a-z]{2,8}[1-9][0-9]?", self.region):
            raise ProviderError("provider_region_invalid")
        self.request = request if request is not None else HetznerAPI(config.get("token"))
        self.clock = clock
        self.scope = "hetzner_floating:" + str(self.instance) + ":" + self.region
        self.store = _Store(Path(state_dir) / "hetzner-floating")
        self.local = local if local is not None else LocalIPv4Alias(config.get("interface"))

    def _droplet(self):
        value = self.request("GET", "/servers/" + str(self.instance)).get("server")
        if (not isinstance(value, dict) or value.get("id") != self.instance or value.get("status") != "running"
                or value.get("datacenter", {}).get("location", {}).get("name") != self.region):
            raise ProviderError("provider_instance_identity_or_state_mismatch")
        primary = _ipv4(value.get("public_net", {}).get("ipv4", {}).get("ip"))
        return {"id": self.instance, "status": "active", "region": {"slug": self.region},
                "networks": {"v4": [{"type": "public", "ip_address": primary}]}}

    def _normalize(self, row):
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 1 or row.get("type") != "ipv4":
            raise ProviderError("provider_ip_identity_mismatch")
        ip = _ipv4(row.get("ip")); server = row.get("server")
        if server is not None and (type(server) is not int or server < 1):
            raise ProviderError("provider_ip_assignment_invalid")
        location = row.get("home_location", {}).get("name")
        labels = row.get("labels", {})
        if not isinstance(location, str) or not isinstance(labels, dict):
            raise ProviderError("provider_ip_identity_mismatch")
        return {"id": row["id"], "ip": ip, "region": {"slug": location},
                "droplet": None if server is None else {"id": server}, "labels": labels}

    def _ips(self):
        rows = []
        for page in range(1, 21):
            data = self.request("GET", "/floating_ips?per_page=50&page=" + str(page))
            values = data.get("floating_ips")
            if not isinstance(values, list):
                raise ProviderError("provider_ip_list_invalid")
            rows.extend(self._normalize(row) for row in values if isinstance(row, dict) and row.get("type") == "ipv4")
            if not data.get("meta", {}).get("pagination", {}).get("next_page"):
                return rows
        raise ProviderError("provider_ip_list_limit")

    def _get(self, ip):
        rows = [row for row in self._ips() if row["ip"] == _ipv4(ip)]
        if len(rows) > 1:
            raise ProviderError("provider_ip_identity_mismatch")
        return rows[0] if rows else None

    def get_inbound_addresses(self):
        d = self._droplet(); ledger = self._ledger()
        selected = ledger.get("active_ip") or self.config.get("managed_ip")
        if selected:
            selected = _ipv4(selected); row = self._get(selected)
            if not row or self._assigned(row) != self.instance:
                raise ProviderError("provider_managed_ip_binding_mismatch")
            return {"A": selected}
        return {"A": d["networks"]["v4"][0]["ip_address"]}

    def _authorization(self, ledger, rows):
        for key in ("auto_rotate", "allow_floating_ip_allocation", "allow_guest_network_changes"):
            if self.config.get(key) is not True:
                raise ProviderError("provider_" + key + "_not_authorized")
        maximum = _integer(self.config.get("max_attempts_per_day", 1), 1, 3, "provider_attempt_limit_invalid")
        limit = _integer(self.config.get("max_floating_ips", 2), 1, 20, "provider_floating_limit_invalid")
        budget = self.config.get("max_monthly_floating_eur", 6)
        if type(budget) not in (int, float) or not math.isfinite(budget) or not 0 < budget <= 300:
            raise ProviderError("provider_budget_invalid")
        recent = [t for t in ledger["attempts"] if type(t) in (int, float) and t > self.clock() - 86400]
        if len(recent) >= maximum:
            raise ProviderError("provider_daily_attempt_limit")
        # EUR 3/month excluding tax, price verified 2026-11-18. Count every
        # project IPv4, including unrelated ones; this is a conservative estimate.
        if len(rows) + 1 > limit or (len(rows) + 1) * 3 > budget:
            raise ProviderError("provider_floating_budget_exceeded")
        ledger["attempts"] = recent + [int(self.clock())]

    def _adopt_allocation(self, journal, answer):
        return self._adopt_normalized(journal, self._normalize(answer))

    def _adopt_normalized(self, journal, new):
        labels = {"huarun-instance": str(self.instance), "huarun-operation": journal["incident"][:32]}
        if (new["ip"] == journal["old_ip"] or new["ip"] in journal["before_ips"]
                or new["region"]["slug"] != self.region or self._assigned(new) is not None
                or any(new["labels"].get(k) != v for k, v in labels.items())):
            raise ProviderError("provider_allocation_identity_invalid")
        journal.update(new_ip=new["ip"], new_id=new["id"], new_owned=True, phase="detach_old")
        self._save(journal)
        ledger = self._ledger()
        ledger["owned"][new["ip"]] = {"id": new["id"], "incident": journal["incident"], "created_at": journal["created_at"]}
        self.store.write("ledger.json", ledger)
        return journal

    def _start(self, incident, ledger):
        self._droplet(); rows = self._ips(); old = self.current_ip()
        self._authorization(ledger, rows)
        journal = {"scope": self.scope, "incident": incident, "phase": "allocating", "created_at": int(self.clock()),
                   "old_ip": old, "old_reserved": any(r["ip"] == old for r in rows), "old_owned": old in ledger["owned"],
                   "before_ips": [r["ip"] for r in rows], "dns_attempted": False, "new_ip": None}
        self.store.write("ledger.json", ledger); self._save(journal)
        labels = {"huarun-instance": str(self.instance), "huarun-operation": incident[:32]}
        try:
            answer = self.request("POST", "/floating_ips", {"type": "ipv4", "home_location": self.region,
                "name": "huarun-" + incident[:16], "labels": labels}).get("floating_ip")
            return self._adopt_allocation(journal, answer)
        except Exception:
            journal.update(phase="allocation_unknown", code="provider_allocation_requires_reconciliation"); self._save(journal)
            return journal

    def _prepare_old(self, journal):
        return True  # Multiple Floating IPs coexist; primary/old remain reachable.

    def _prepare_candidate(self, journal):
        if self.config.get("allow_guest_network_changes") is not True:
            raise ProviderError("provider_allow_guest_network_changes_not_authorized")
        if not journal.get("local_add_intent"):
            if journal["new_ip"] in self.local.addresses():
                raise ProviderError("provider_guest_address_conflict")
            journal["local_add_intent"] = True; self._save(journal)
        self.local.ensure(journal["new_ip"])
        ledger = self._ledger()
        ledger["owned"].setdefault(journal["new_ip"], {"id": journal["new_id"], "incident": journal["incident"], "created_at": journal["created_at"]})["alias_owned"] = True
        self.store.write("ledger.json", ledger)

    def _remove_candidate_local(self, journal):
        if journal.get("local_add_intent"):
            self.local.remove(journal["new_ip"])

    def restore_local_address(self):
        journal = self._journal()
        if journal:
            if journal.get("phase") in ("verify_new", "commit_dns", "cleanup_old") and journal.get("new_owned") and journal.get("local_add_intent"):
                row = self._get(journal["new_ip"])
                if not row or row["id"] != journal.get("new_id") or self._assigned(row) != self.instance:
                    raise ProviderError("provider_managed_ip_binding_mismatch")
                self._prepare_candidate(journal)
            return {"status": "pending"}
        ledger = self._ledger(); ip = ledger.get("active_ip")
        if not ip:
            return {"status": "not_needed"}
        if self.config.get("allow_guest_network_changes") is not True:
            raise ProviderError("provider_allow_guest_network_changes_not_authorized")
        owned = ledger["owned"].get(ip)
        if not owned:
            raise ProviderError("provider_active_address_not_owned")
        row = self._get(ip)
        if not row or row["id"] != owned.get("id") or self._assigned(row) != self.instance:
            raise ProviderError("provider_managed_ip_binding_mismatch")
        self.local.ensure(ip)
        return {"status": "restored", "addresses": {"A": ip}}

    def _assignment(self, journal, ip, target, label):
        value = self._get(ip)
        if value is None:
            raise ProviderError("provider_reserved_ip_disappeared")
        current = self._assigned(value)
        if current not in (None, self.instance):
            raise ProviderError("provider_ip_assigned_elsewhere")
        action = journal.get("action")
        if action:
            if action.get("ip") != ip or action.get("target") != target:
                raise ProviderError("provider_action_conflict")
            if action.get("id"):
                result = self.request("GET", "/actions/" + str(action["id"])).get("action", {})
                if result.get("id") != action["id"]:
                    raise ProviderError("provider_action_identity_mismatch")
                if result.get("status") == "error":
                    journal.pop("action", None); self._save(journal)
                    raise ProviderError("provider_action_failed")
                if result.get("status") != "success":
                    if self.clock() - action["started_at"] > 900:
                        journal["code"] = "provider_action_requires_reconciliation"; self._save(journal)
                    return False
            if current != target:
                if not action.get("id") or self.clock() - action["started_at"] > 900:
                    journal["code"] = "provider_action_requires_reconciliation"; self._save(journal)
                return False
            journal.pop("action", None); self._save(journal)
            return True
        if current == target:
            return True
        journal["action"] = {"ip": ip, "target": target, "label": label, "started_at": int(self.clock())}; self._save(journal)
        action_name = "assign" if target is not None else "unassign"
        data = {"server": target} if target is not None else None
        try:
            action = self.request("POST", "/floating_ips/" + str(value["id"]) + "/actions/" + action_name, data).get("action")
            if not isinstance(action, dict) or type(action.get("id")) is not int or action["id"] < 1:
                raise ProviderError("provider_action_response_invalid")
            journal["action"]["id"] = action["id"]; self._save(journal)
        except Exception:
            journal["code"] = "provider_action_requires_reconciliation"; self._save(journal)
        return False

    def _delete_created(self, journal, ip):
        ledger = self._ledger(); owned = ledger["owned"].get(ip)
        if owned is None and ip == journal.get("new_ip") and journal.get("new_owned"):
            owned = {"id": journal["new_id"], "incident": journal["incident"]}
        if not owned:
            raise ProviderError("provider_delete_not_owned")
        row = self._get(ip)
        if row:
            if row["id"] != owned["id"] or row["labels"].get("huarun-instance") != str(self.instance) or row["labels"].get("huarun-operation") != owned["incident"][:32]:
                raise ProviderError("provider_delete_identity_mismatch")
            if self._assigned(row) is not None:
                if ip == journal.get("old_ip") and journal.get("old_owned") and self.config.get("cleanup_owned_old_ip") is True:
                    if not self._assignment(journal, ip, None, "cleanup_old"):
                        return False
                    row = self._get(ip)
                else:
                    raise ProviderError("provider_delete_still_assigned")
            if owned.get("alias_owned") or (ip == journal.get("new_ip") and journal.get("local_add_intent")):
                self.local.remove(ip)
            self._release_resource(row)
            if self._get(ip) is not None:
                return False
        ledger["owned"].pop(ip, None); self.store.write("ledger.json", ledger)
        return True

    def _release_resource(self, row):
        self.request("DELETE", "/floating_ips/" + str(row["id"]))

    def _finish(self, journal, status, code):
        ledger = self._ledger()
        if status == "rotated":
            ledger["active_ip"] = journal["new_ip"]
            ledger["owned"].setdefault(journal["new_ip"], {"id": journal["new_id"], "incident": journal["incident"], "created_at": journal["created_at"]})
            self.store.write("ledger.json", ledger)
        return super()._finish(journal, status, code)

    def rotate(self, incident_id, verify_ip, update_dns):
        try:
            journal = self._journal()
            if journal.get("phase") in ("allocating", "allocation_unknown"):
                # The label was part of allocation itself; recover a lost response
                # without issuing a second billable POST or adopting unrelated IPs.
                matching = [r for r in self._ips() if r["labels"].get("huarun-instance") == str(self.instance)
                            and r["labels"].get("huarun-operation") == journal["incident"][:32]]
                if len(matching) == 1:
                    row = matching[0]
                    self._adopt_normalized(journal, row)
            return super().rotate(incident_id, verify_ip, update_dns)
        except ProviderError as error:
            return {"status": "deferred", "code": str(error)}
        except Exception:
            return {"status": "deferred", "code": "provider_operation_failed"}


_UUID_PATTERN = r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}"


def _uuid(value):
    if not isinstance(value, str) or not re.fullmatch(_UUID_PATTERN, value):
        raise ProviderError("provider_resource_id_invalid")
    return value


class VultrAPI(DigitalOceanAPI):
    origin = "https://api.vultr.com/v2"
    patterns = {
        "GET": r"(?:/instances/" + _UUID_PATTERN + r"|/reserved-ips\?per_page=100|/reserved-ips/" + _UUID_PATTERN + r")",
        "POST": r"(?:/reserved-ips|/reserved-ips/" + _UUID_PATTERN + r"/(?:attach|detach))",
        "DELETE": r"/reserved-ips/" + _UUID_PATTERN,
    }
    missing_pattern = r"/reserved-ips/" + _UUID_PATTERN
    missing_key = "reserved_ip"


class VultrReservedRotator(HetznerFloatingRotator):
    """Cloud Compute additional Reserved IPv4; no reboot or primary-IP replacement.

    https://docs.vultr.com/products/network/reserved-ips/management/attachment
    https://github.com/vultr/govultr/blob/master/reserved_ip.go
    Bare Metal is intentionally excluded: its documented attach requires reboot.
    """
    def __init__(self, config, state_dir, request=None, clock=time.time, local=None):
        self.config = dict(config)
        self.instance = _uuid(config.get("instance_id"))
        self.region = config.get("region", "")
        if not isinstance(self.region, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,15}", self.region):
            raise ProviderError("provider_region_invalid")
        self.request = request if request is not None else VultrAPI(config.get("token"))
        self.clock = clock
        self.scope = "vultr:" + self.instance + ":" + self.region
        self.store = _Store(Path(state_dir) / "vultr")
        self.local = local if local is not None else LocalIPv4Alias(config.get("interface"))

    def _droplet(self):
        value = self.request("GET", "/instances/" + self.instance).get("instance")
        if (not isinstance(value, dict) or value.get("id") != self.instance or value.get("region") != self.region
                or value.get("status") != "active" or value.get("power_status") != "running"):
            raise ProviderError("provider_instance_identity_or_state_mismatch")
        primary = _ipv4(value.get("main_ip"))
        return {"id": self.instance, "status": "active", "region": {"slug": self.region},
                "networks": {"v4": [{"type": "public", "ip_address": primary}]}}

    def _normalize(self, row):
        if not isinstance(row, dict) or row.get("ip_type") != "v4" or row.get("subnet_size") != 32:
            raise ProviderError("provider_ip_identity_mismatch")
        ident = _uuid(row.get("id")); ip = _ipv4(row.get("subnet"))
        target = row.get("instance_id") or None
        if target is not None:
            _uuid(target)
        region = row.get("region")
        if not isinstance(region, str):
            raise ProviderError("provider_ip_identity_mismatch")
        labels = {}; label = row.get("label", "")
        if isinstance(label, str) and label.startswith("huarun:"):
            bits = label.split(":")
            if len(bits) == 3:
                labels = {"huarun-instance": bits[1], "huarun-operation": bits[2]}
        return {"id": ident, "ip": ip, "region": {"slug": region},
                "droplet": None if target is None else {"id": target}, "labels": labels}

    def _ips(self):
        data = self.request("GET", "/reserved-ips?per_page=100")
        values = data.get("reserved_ips")
        if not isinstance(values, list):
            raise ProviderError("provider_ip_list_invalid")
        # Reject incomplete inventory before billable operations. This adapter is
        # bounded to <=100 project IPs; no provider-supplied URL is followed.
        if data.get("meta", {}).get("links", {}).get("next"):
            raise ProviderError("provider_ip_list_limit")
        return [self._normalize(row) for row in values if isinstance(row, dict) and row.get("ip_type") == "v4"]

    def _authorization(self, ledger, rows):
        for key in ("auto_rotate", "allow_reserved_ip_allocation", "allow_guest_network_changes"):
            if self.config.get(key) is not True:
                raise ProviderError("provider_" + key + "_not_authorized")
        maximum = _integer(self.config.get("max_attempts_per_day", 1), 1, 3, "provider_attempt_limit_invalid")
        limit = _integer(self.config.get("max_reserved_ips", 2), 1, 20, "provider_reserved_limit_invalid")
        budget = self.config.get("max_monthly_reserved_usd", 6)
        if type(budget) not in (int, float) or not math.isfinite(budget) or not 0 < budget <= 300:
            raise ProviderError("provider_budget_invalid")
        recent = [t for t in ledger["attempts"] if type(t) in (int,float) and t > self.clock()-86400]
        if len(recent) >= maximum:
            raise ProviderError("provider_daily_attempt_limit")
        # USD 3/month per Reserved IP, whether attached or idle, snapshot 2026-11-18.
        if len(rows)+1 > limit or (len(rows)+1)*3 > budget:
            raise ProviderError("provider_reserved_budget_exceeded")
        ledger["attempts"] = recent + [int(self.clock())]

    def _start(self, incident, ledger):
        self._droplet(); rows=self._ips(); old=self.current_ip()
        self._authorization(ledger,rows)
        journal={"scope":self.scope,"incident":incident,"phase":"allocating","created_at":int(self.clock()),
                 "old_ip":old,"old_reserved":any(r["ip"]==old for r in rows),"old_owned":old in ledger["owned"],
                 "before_ips":[r["ip"] for r in rows],"dns_attempted":False,"new_ip":None}
        self.store.write("ledger.json",ledger); self._save(journal)
        try:
            answer=self.request("POST","/reserved-ips",{"region":self.region,"ip_type":"v4",
                "label":"huarun:"+self.instance+":"+incident[:32]}).get("reserved_ip")
            return self._adopt_allocation(journal,answer)
        except Exception:
            journal.update(phase="allocation_unknown",code="provider_allocation_requires_reconciliation"); self._save(journal)
            return journal

    def _assignment(self,journal,ip,target,label):
        value=self._get(ip)
        if value is None:
            raise ProviderError("provider_reserved_ip_disappeared")
        current=self._assigned(value)
        if current not in (None,self.instance):
            raise ProviderError("provider_ip_assigned_elsewhere")
        action=journal.get("action")
        if action:
            if action.get("ip")!=ip or action.get("target")!=target:
                raise ProviderError("provider_action_conflict")
            if current==target:
                journal.pop("action",None); self._save(journal); return True
            if not action.get("acknowledged") or self.clock()-action["started_at"]>900:
                journal["code"]="provider_action_requires_reconciliation"; self._save(journal)
            return False
        if current==target:
            return True
        journal["action"]={"ip":ip,"target":target,"label":label,"started_at":int(self.clock())}; self._save(journal)
        try:
            if target is None:
                self.request("POST","/reserved-ips/"+value["id"]+"/detach")
            else:
                self.request("POST","/reserved-ips/"+value["id"]+"/attach",{"instance_id":target})
            journal["action"]["acknowledged"]=True; self._save(journal)
        except Exception:
            journal["code"]="provider_action_requires_reconciliation"; self._save(journal)
        return False

    def _release_resource(self,row):
        self.request("DELETE","/reserved-ips/"+row["id"])


class UnsupportedProvider:
    def __init__(self, kind):
        self.kind = kind
    def pending(self):
        return False
    def get_inbound_addresses(self):
        raise ProviderError("provider_adapter_unavailable")
    def rotate(self, incident_id, verify_ip, update_dns):
        external = self.kind in ("aws_primary", "hetzner_primary", "vultr_bare_metal")
        return {"status": "unsupported", "code": "external_controller_required" if external else "provider_adapter_unavailable"}


def get_provider(config, state_dir, request=None, clock=time.time):
    if config.get("kind", config.get("provider")) == "digitalocean":
        return DigitalOceanRotator(config, state_dir, request=request, clock=clock)
    if config.get("kind", config.get("provider")) == "hetzner_floating":
        return HetznerFloatingRotator(config, state_dir, request=request, clock=clock)
    if config.get("kind", config.get("provider")) == "vultr":
        return VultrReservedRotator(config, state_dir, request=request, clock=clock)
    if config.get("kind", config.get("provider")) == "aws_eip":
        from aws_provider import AWSElasticRotator
        return AWSElasticRotator(config, state_dir, request=request, clock=clock)
    kind=config.get("kind", config.get("provider", "other"))
    if kind in ("manual", "none"):
        return UnsupportedProvider(kind)
    from provider_discovery import DiscoveryProvider
    return DiscoveryProvider(config,state_dir,request=request,clock=clock)
