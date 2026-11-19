"""Validate Linux installation evidence before a public assistant release.

The caller supplies trusted checkout/workflow identity and the prior stable
release resolved from GitHub. This module does not run tests or infer a pass
from repository fixtures. The original report bytes must be hashed separately
and shipped unchanged by the release publisher.
"""
from __future__ import annotations

import hashlib
import json
import re

KIND = "huarun-linux-release-e2e"
ASSET_NAME = "linux-install-upgrade-proof.json"
LEGACY_BASELINES = {
    "legacy-1.0": {
        "source_sha": "c89b724428683237d037239fd17f8a08473d16a1",
        "installer_sha256": "0a8dd67be1838b0fe674edc51ed75636bd41843e6b9ece8cf26ba38ba380e7c1",
        "version": "1.0.0",
    },
    "legacy-1.1": {
        "source_sha": "e3d9a186ce961fb12c3b3401e00bc22621fe7242",
        "installer_sha256": "cdb22951eb5c34053fd99863e1d38bafec200217cdc426adfb8c3b7f5b368f6c",
        "version": "1.1.0",
    },
}
REQUIRED_ROLES = frozenset((*LEGACY_BASELINES, "previous-stable"))
FRESH_CHECKS = ("passed", "timer_enabled", "timer_active", "services_healthy", "proxy_allowed",
                "proxy_blocked", "tls_verified", "blocked_target_reachable")
DOCTOR_REQUIRED_CHECKS = ("xray", "nginx", "port443", "xray_config", "nginx_config",
                          "cert", "cron", "firewall", "dns", "disk")
UPGRADE_CHECKS = FRESH_CHECKS + ("network_processes_unchanged",)
PRESERVED_CHECKS = ("node_config", "whitelist", "key", "memory")
NETWORK_FAULT_SUITES = ('test_network.py','test_ip_provider.py','test_aws_provider.py','test_egress.py','test_network_setup.py')
GENERIC_FAULT_SUITES = NETWORK_FAULT_SUITES + ('test_generic_provider.py', 'test_provider_discovery.py', 'test_network_discovery.py', 'test_generic_updater.py')
ASSISTED_FAULT_SUITES = GENERIC_FAULT_SUITES + ('test_provider_readiness.py',)
GENERIC_PROVIDER_CHECKS = (
    'passed', 'unknown_json_provider_auto_connected', 'unknown_query_provider_auto_connected',
    'official_docs_read', 'official_docs_digest_bound', 'read_only_probe_before_activation',
    'generated_adapter_validated', 'provider_credentials_not_sent_to_model',
    'ip_replacement_verified', 'dns_readback_verified', 'no_api_notified',
    'docs_unavailable_distinguished', 'missing_credentials_distinguished',
    'malicious_document_rejected', 'ambiguous_replace_not_repeated',
    'failed_replacement_rolled_back', 'no_vendor_allowlist',
)
ASSISTED_RECOVERY_CHECKS = (
    'passed', 'manual_ip_validated', 'static_address_persisted',
    'dns_readback_verified', 'next_timer_keeps_new_ip', 'unverified_ip_rejected',
    'pending_setup_rejected', 'pending_provider_rejected',
    'api_binding_cannot_be_bypassed', 'configuration_and_keys_preserved',
    'dns_failure_keeps_new_ip', 'dns_retry_recovers_new_ip',
)
NETWORK_FEATURE_CHECKS = (
    "passed", "cloudflare_dns01", "cloudflare_txt_created", "cloudflare_txt_removed", "dns01_leading_dash_value",
    "ddns_address_changed", "ddns_readback_verified", "notification_retry_queued",
    "notification_recovered_delivered", "domain_migration_verified", "domain_identity_preserved",
    "domain_migration_rollback", "socks5_chain_verified", "http_connect_chain_verified",
    "chain_whitelist_enforced", "chain_failure_closed", "network_timer_enabled", "network_timer_active",
    "fixture_unknown_ca_rejected", "fixture_wrong_san_rejected",
)
NETWORK_PRESERVED_CHECKS = PRESERVED_CHECKS + ("nginx_config", "connection_info", "network_config", "egress_config")
GENERIC_PRESERVED_CHECKS = NETWORK_PRESERVED_CHECKS + ("generic_provider_state",)
NETWORK_TIMER_CHECKS = ("network_timer_enabled", "network_timer_active")
UNCONFIGURED_CHECKS = ("network_config_absent", "egress_config_absent", "network_status_not_configured")
HEX = {40: re.compile(r"[0-9a-f]{40}"), 64: re.compile(r"[0-9a-f]{64}")}
SEMVER = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
RUN_ID = re.compile(r"[1-9][0-9]*")


class AcceptanceError(ValueError):
    """A controlled rejection code, safe to show without report contents."""


def _object(value, code):
    if not isinstance(value, dict):
        raise AcceptanceError(code)
    return value


def _digest(value, length, code):
    if not isinstance(value, str) or not HEX[length].fullmatch(value):
        raise AcceptanceError(code)
    return value


def _version(value, code):
    if not isinstance(value, str) or not SEMVER.fullmatch(value):
        raise AcceptanceError(code)
    return tuple(int(part) for part in value.split("."))


def _positive_integer(value, code):
    if type(value) is not int or value < 1:
        raise AcceptanceError(code)
    return value


def _checks(value, required, prefix):
    _object(value, prefix + "_missing")
    for name in required:
        if value.get(name) is not True:
            raise AcceptanceError(prefix + "_" + name + "_not_passed")
    # Optional per-case counters must never contradict the mandatory root count.
    if "skipped" in value and (type(value["skipped"]) is not int or value["skipped"] != 0):
        raise AcceptanceError(prefix + "_skipped")


def _doctor(value, prefix):
    _object(value, prefix + "_doctor_checks_missing")
    for name in DOCTOR_REQUIRED_CHECKS:
        if value.get(name) is not True:
            raise AcceptanceError(prefix + "_doctor_" + name + "_not_passed")
    # --no-swap is intentional in the disposable acceptance guest. Optional
    # diagnostic fields may be false, but a string/integer is never evidence.
    if any(type(status) is not bool for status in value.values()):
        raise AcceptanceError(prefix + "_doctor_check_type_invalid")


def _previous(value):
    _object(value, "previous_stable_missing")
    return {
        "release_id": _positive_integer(value.get("release_id"), "previous_stable_release_id_invalid"),
        "source_sha": _digest(value.get("source_sha"), 40, "previous_stable_source_invalid"),
        "installer_sha256": _digest(value.get("installer_sha256"), 64, "previous_stable_installer_invalid"),
        "version": value.get("version"),
    }


def _preservation_manifest(case, *, unconfigured=False, generic=False):
    manifest = _object(case.get("preservation_checks"), "preservation_manifest_missing")
    before = _object(manifest.get("before"), "preservation_before_missing")
    after = _object(manifest.get("after"), "preservation_after_missing")
    for name in (GENERIC_PRESERVED_CHECKS if generic else NETWORK_PRESERVED_CHECKS):
        left = _object(before.get(name), "preservation_before_item_missing")
        right = _object(after.get(name), "preservation_after_item_missing")
        absent = unconfigured and name in ("network_config", "egress_config", "generic_provider_state")
        if absent:
            if left != {"exists": False, "sha256": None, "mode": None, "uid": None, "gid": None}:
                raise AcceptanceError("unconfigured_file_existed")
        else:
            if left.get("exists") is not True:
                raise AcceptanceError("preserved_file_missing")
            _digest(left.get("sha256"), 64, "preserved_file_digest_invalid")
            mode = left.get("mode")
            if type(mode) is not int or not 0 <= mode <= 0o777:
                raise AcceptanceError("preserved_file_mode_invalid")
            if any(type(left.get(field)) is not int or left[field] < 0 for field in ("uid", "gid")):
                raise AcceptanceError("preserved_file_owner_invalid")
            if name in ("network_config", "egress_config", "generic_provider_state") and mode & 0o077:
                raise AcceptanceError("preserved_network_secret_permissions")
            if name == "generic_provider_state":
                entries=_object(left.get("entries"),"generic_state_entries_missing")
                if not entries:raise AcceptanceError("generic_state_entries_empty")
                for path, item in entries.items():
                    if not isinstance(path,str) or not path or path.startswith('/') or any(part in ('','..','.') for part in path.split('/')) or '\\' in path:
                        raise AcceptanceError("generic_state_path_invalid")
                    _object(item,"generic_state_entry_invalid")
                    if item.get('kind') not in ('file','directory'):raise AcceptanceError("generic_state_kind_invalid")
                    if type(item.get('mode')) is not int or not 0<=item['mode']<=0o700 or item['mode']&0o077:
                        raise AcceptanceError("generic_state_permissions_invalid")
                    if any(type(item.get(field)) is not int or item[field]<0 for field in ('uid','gid')):
                        raise AcceptanceError("generic_state_owner_invalid")
                    if item['kind']=='file':_digest(item.get('sha256'),64,"generic_state_file_digest_invalid")
                    elif item.get('sha256') is not None:raise AcceptanceError("generic_state_directory_digest_invalid")
                digest=hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                if left['sha256']!=digest:raise AcceptanceError("generic_state_digest_mismatch")
        if left != right:
            raise AcceptanceError("preserved_file_bytes_or_mode_changed")


def _unconfigured_case(case, candidate_version, *, generic=False):
    _checks(case, UPGRADE_CHECKS + NETWORK_TIMER_CHECKS + UNCONFIGURED_CHECKS, "unconfigured_upgrade")
    _doctor(case.get("doctor_checks"), "unconfigured_upgrade")
    _checks(case.get("preserved"), GENERIC_PRESERVED_CHECKS if generic else NETWORK_PRESERVED_CHECKS, "unconfigured_preserved")
    if generic:_checks(case,("generic_provider_state_absent",),"unconfigured_upgrade")
    _preservation_manifest(case, unconfigured=True, generic=generic)
    pin = LEGACY_BASELINES["legacy-1.0"]
    if (case.get("baseline_source_sha") != pin["source_sha"]
            or case.get("baseline_installer_sha256") != pin["installer_sha256"]
            or case.get("from_version") != pin["version"]
            or case.get("to_version") != candidate_version):
        raise AcceptanceError("unconfigured_baseline_identity_mismatch")

def _generic_provider_features(value):
    _checks(value, GENERIC_PROVIDER_CHECKS, "generic_provider_features")
    if value.get("scope") != "installed_runtime_http_fixtures" or value.get("live_cloud_rotation") is not False:
        raise AcceptanceError("generic_provider_scope_invalid")
    cases = value.get("providers")
    if not isinstance(cases, list) or len(cases) != 2:
        raise AcceptanceError("generic_provider_cases_missing")
    names, shapes = set(), set()
    for case in cases:
        _object(case, "generic_provider_case_invalid")
        name = case.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"qa-vps-[a-f0-9]{12}", name) or name in names:
            raise AcceptanceError("generic_provider_not_independent")
        names.add(name)
        shape = case.get("api_shape")
        if shape not in ("json_bearer", "query_key") or shape in shapes:
            raise AcceptanceError("generic_provider_shapes_incomplete")
        shapes.add(shape)
        _digest(case.get("document_sha256"), 64, "generic_provider_document_digest_invalid")
        _digest(case.get("profile_sha256"), 64, "generic_provider_profile_digest_invalid")
        _positive_integer(case.get("read_requests"), "generic_provider_read_probe_missing")
        _positive_integer(case.get("mutation_requests"), "generic_provider_mutation_missing")
        _checks(case, ("passed", "dns_readback_verified", "read_before_mutation"), "generic_provider_case")


def validate_report(report, expected, previous_stable=None):
    """Return a compact verified summary or raise :class:`AcceptanceError`.

    ``expected`` is trusted current checkout/workflow identity, with source_sha,
    installer_sha256, candidate_version, run_id (decimal string), run_attempt
    (positive integer). ``previous_stable`` is the separately verified GitHub
    stable release identity: release_id, source_sha, installer_sha256, version.
    A historical immutable release can be rechecked using its original workflow
    and prior release identity; callers must not substitute report assertions
    for freshly resolved identity when publishing a new release.
    """
    _object(expected, "expected_identity_missing")
    source = _digest(expected.get("source_sha"), 40, "expected_source_invalid")
    installer = _digest(expected.get("installer_sha256"), 64, "expected_installer_invalid")
    candidate_version = expected.get("candidate_version")
    candidate_parts = _version(candidate_version, "expected_version_invalid")
    run_id = expected.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise AcceptanceError("expected_run_id_invalid")
    run_attempt = _positive_integer(expected.get("run_attempt"), "expected_run_attempt_invalid")
    previous = _previous(previous_stable)
    _version(previous["version"], "previous_stable_version_invalid")

    _object(report, "acceptance_report_missing")
    if type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise AcceptanceError("acceptance_schema_invalid")
    if report.get("kind") != KIND or report.get("platform") != "linux":
        raise AcceptanceError("acceptance_kind_or_platform_invalid")
    if "development_only" in report and report["development_only"] is not False:
        raise AcceptanceError("acceptance_development_only")
    if report.get("passed") is not True:
        raise AcceptanceError("acceptance_not_passed")
    if type(report.get("skipped")) is not int or report["skipped"] != 0:
        raise AcceptanceError("acceptance_skipped")
    identities = {"source_sha": source, "installer_sha256": installer,
                  "candidate_version": candidate_version, "run_id": run_id, "run_attempt": run_attempt}
    for key, wanted in identities.items():
        actual = report.get(key)
        if type(actual) is not type(wanted) or actual != wanted:
            raise AcceptanceError("acceptance_" + key + "_mismatch")

    fresh = report.get("fresh_install")
    _checks(fresh, FRESH_CHECKS, "fresh_install")
    _doctor(fresh.get("doctor_checks"), "fresh_install")
    network_release = candidate_parts >= (1, 3, 0)
    generic_release = candidate_parts >= (1, 4, 0)
    assisted_release = candidate_parts >= (1, 4, 1)
    if network_release:
        _checks(fresh.get("network_features"), NETWORK_FEATURE_CHECKS, "network_features")
        _unconfigured_case(report.get("unconfigured_upgrade"), candidate_version, generic=generic_release)
        faults = _object(report.get("network_fault_tests"), "network_fault_tests_missing")
        _checks(faults, ("passed",), "network_fault_tests")
        _positive_integer(faults.get("tests"), "network_fault_tests_empty")
        if type(faults.get("skipped")) is not int or faults["skipped"] != 0:
            raise AcceptanceError("network_fault_tests_skipped")
        if faults.get("suites") != list(ASSISTED_FAULT_SUITES if assisted_release else GENERIC_FAULT_SUITES if generic_release else NETWORK_FAULT_SUITES):
            raise AcceptanceError("network_fault_suites_incomplete")
    if generic_release:
        _generic_provider_features(fresh.get("generic_provider_features"))
    if assisted_release:
        _checks(fresh["generic_provider_features"].get("assisted"), ASSISTED_RECOVERY_CHECKS, "assisted_recovery")
    if (network_release or "installed_version" in fresh) and fresh.get("installed_version") != candidate_version:
        raise AcceptanceError("fresh_install_version_mismatch")
    upgrades = report.get("upgrades")
    if not isinstance(upgrades, list) or not 1 <= len(upgrades) <= len(REQUIRED_ROLES):
        raise AcceptanceError("upgrade_cases_missing_or_invalid")
    covered = set()
    summary_cases = []
    for case in upgrades:
        _checks(case, UPGRADE_CHECKS, "upgrade")
        _doctor(case.get("doctor_checks"), "upgrade")
        _checks(case.get("preserved"), GENERIC_PRESERVED_CHECKS if generic_release else NETWORK_PRESERVED_CHECKS if network_release else PRESERVED_CHECKS, "preserved")
        if network_release:
            _checks(case, NETWORK_TIMER_CHECKS, "network_upgrade")
            _preservation_manifest(case, generic=generic_release)
        roles = case.get("roles")
        if (not isinstance(roles, list) or not roles or any(not isinstance(role, str) for role in roles)
                or len(roles) != len(set(roles)) or not set(roles) <= REQUIRED_ROLES):
            raise AcceptanceError("upgrade_roles_invalid")
        if covered.intersection(roles):
            raise AcceptanceError("upgrade_roles_duplicate")
        covered.update(roles)
        baseline_source = _digest(case.get("baseline_source_sha"), 40, "baseline_source_invalid")
        baseline_installer = _digest(case.get("baseline_installer_sha256"), 64, "baseline_installer_invalid")
        before_version = case.get("from_version")
        before_parts = _version(before_version, "baseline_version_invalid")
        if case.get("to_version") != candidate_version:
            raise AcceptanceError("upgrade_target_version_mismatch")
        if before_parts > candidate_parts:
            raise AcceptanceError("upgrade_version_downgrade")
        for role in roles:
            pin = previous if role == "previous-stable" else LEGACY_BASELINES[role]
            if (baseline_source != pin["source_sha"] or baseline_installer != pin["installer_sha256"]
                    or before_version != pin["version"]):
                raise AcceptanceError("upgrade_baseline_identity_mismatch")
            if role == "previous-stable":
                ident = _positive_integer(case.get("baseline_release_id"), "baseline_release_id_invalid")
                if ident != previous["release_id"]:
                    raise AcceptanceError("upgrade_previous_release_mismatch")
        summary_cases.append({"roles": sorted(roles), "source_sha": baseline_source,
                              "installer_sha256": baseline_installer, "from_version": before_version})
    if covered != REQUIRED_ROLES:
        raise AcceptanceError("upgrade_roles_incomplete")
    return {"schema_version": 1, "kind": KIND, **identities, "platform": "linux", "passed": True,
            "skipped": 0, "fresh_install": True, "doctor_checks": list(DOCTOR_REQUIRED_CHECKS),
            "upgrade_cases": len(upgrades),
            "upgrade_roles": sorted(covered), "preserved": list(GENERIC_PRESERVED_CHECKS if generic_release else NETWORK_PRESERVED_CHECKS if network_release else PRESERVED_CHECKS),
            **({"network_features": list(NETWORK_FEATURE_CHECKS), "unconfigured_upgrade": True} if network_release else {}),
            **({"generic_provider_features": list(GENERIC_PROVIDER_CHECKS)} if generic_release else {}),
            **({"assisted_recovery": list(ASSISTED_RECOVERY_CHECKS)} if assisted_release else {}),
            "baselines": sorted(summary_cases, key=lambda case: case["roles"]), "previous_stable": previous}
