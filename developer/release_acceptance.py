"""Validate Linux installation evidence before a public assistant release.

The caller supplies trusted checkout/workflow identity and the prior stable
release resolved from GitHub. This module does not run tests or infer a pass
from repository fixtures. The original report bytes must be hashed separately
and shipped unchanged by the release publisher.
"""
from __future__ import annotations

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
    if "installed_version" in fresh and fresh["installed_version"] != candidate_version:
        raise AcceptanceError("fresh_install_version_mismatch")
    upgrades = report.get("upgrades")
    if not isinstance(upgrades, list) or not 1 <= len(upgrades) <= len(REQUIRED_ROLES):
        raise AcceptanceError("upgrade_cases_missing_or_invalid")
    covered = set()
    summary_cases = []
    for case in upgrades:
        _checks(case, UPGRADE_CHECKS, "upgrade")
        _doctor(case.get("doctor_checks"), "upgrade")
        _checks(case.get("preserved"), PRESERVED_CHECKS, "preserved")
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
            "upgrade_roles": sorted(covered), "preserved": list(PRESERVED_CHECKS),
            "baselines": sorted(summary_cases, key=lambda case: case["roles"]), "previous_stable": previous}
