"""Evidence-scoped, offline fancyss package matching. Never operates a router."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

ROUTER_QUERY_FIELDS = frozenset({
    "router_model", "device_model_id", "hardware_revision", "firmware_family", "firmware_branch",
    "firmware_version", "architecture", "kernel", "package_variant",
})
# Router-specific inputs are separate from the protocol shared with general queries.
FAMILIES = ("koolcenter-merlin-mod", "koolcenter-asuswrt-mod", "asuswrt-merlin",
            "asuswrt-merlin-gnuton", "asuswrt", "other")
ROUTER_QUERY_PROPERTIES = {
    "router_model": {"type": ["string", "null"], "maxLength": 64, "description": "Exact router model; preserve PRO, V2, separators and regional suffixes. No fuzzy matching."},
    "device_model_id": {"type": ["string", "null"], "maxLength": 64, "description": "Locally observed nonempty odmpid, otherwise productid. Never infer it from the marketing name."},
    "hardware_revision": {"type": ["string", "null"], "maxLength": 16, "description": "Locally observed hardware revision, e.g. V1. Bare numeric revisions 1/2 (or 1.0/2.0) normalize to V1/V2; never infer from another model."},
    "firmware_family": {"type": ["string", "null"], "enum": [None, *FAMILIES], "description": "Exact firmware project identity. Original Merlin is not KoolCenter modified firmware."},
    "firmware_branch": {"type": ["string", "null"], "maxLength": 24, "description": "Publisher firmware branch, e.g. 3004.388 or 3006.102, not the CPU platform."},
    "firmware_version": {"type": ["string", "null"], "maxLength": 64, "description": "Observed installed build, e.g. 388.12_2. Listing a newer build does not authorize flashing."},
    "architecture": {"type": ["string", "null"], "maxLength": 16, "description": "Actual uname -m, e.g. armv7l or aarch64; never infer from CPU bitness."},
    "kernel": {"type": ["string", "null"], "maxLength": 48, "description": "Actual uname -r. Package installer and documented model kernel are distinct evidence."},
    "package_variant": {"type": "string", "enum": ["auto", "full", "lite"], "default": "auto"},
}
ROUTER_QUERY_DESCRIPTION = (
    "Match an exact router model to documented KoolCenter firmware sources and pinned "
    "fancyss package candidates. Supply locally observed firmware family/branch/version, "
    "uname architecture and kernel. Preserve model revisions. Missing facts remain unknown. "
    "This selects plugin candidates only, never flashes firmware or claims device testing."
)
KNOWN_PROTOCOLS = frozenset({
    "shadowsocks", "ssr", "vmess", "vless", "trojan", "hysteria2",
    "xray-json", "naiveproxy", "tuic", "vless-reality", "wireguard",
    "hysteria1", "socks", "http-proxy", "anytls", "snell",
})
PROTOCOL_ALIASES = {"ss": "shadowsocks", "shadowsocksr": "ssr", "hy2": "hysteria2",
                    "naive": "naiveproxy", "vless+reality": "vless-reality"}
PATTERNS = {
    "router_model": r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}",
    "device_model_id": r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}",
    "hardware_revision": r"(?:[VvAaBbCcDd]?[0-9]{1,2}(?:[.][0-9]{1,2})?)",
    "firmware_branch": r"[0-9]{1,4}(?:[.][0-9]{1,4}){0,3}",
    "firmware_version": r"[0-9][A-Za-z0-9_.-]{0,63}",
    "architecture": r"[a-z0-9_]{1,16}",
    "kernel": r"[0-9]{1,3}[.][0-9]{1,3}(?:[.][0-9]{1,6})?(?:[-+._][A-Za-z0-9_.+-]{1,30})?",
    "protocol": r"[a-zA-Z0-9][a-zA-Z0-9+-]{0,31}",
}
class RouterValidationError(ValueError):
    code = "invalid_parameter"
    status = 400
    def __init__(self, field="router", reason="invalid_value"):
        # All interpolated labels are fixed schema identifiers, never user input.
        self.field = field if field in ROUTER_QUERY_FIELDS | {"protocol"} else "router"
        self.reason = reason if reason in {"invalid_value", "unknown_field", "invalid_type"} else "invalid_value"
        super().__init__("Invalid router query parameter: " + self.field + " (" + self.reason + ")")

def normalize_router_query(params=None):
    if params is None:
        params = {}
    if type(params) is not dict:
        raise RouterValidationError(reason="invalid_type")
    if set(params) - ROUTER_QUERY_FIELDS - {"protocol"}:
        raise RouterValidationError(reason="unknown_field")
    normalized = {key: None for key in sorted(ROUTER_QUERY_FIELDS | {"protocol"})}
    normalized["package_variant"] = "auto"
    for field, value in params.items():
        if value is None and field != "package_variant":
            continue
        if type(value) is not str:
            raise RouterValidationError(field, "invalid_type")
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise RouterValidationError(field)
        value = value.strip()
        if field == "firmware_family":
            if value not in FAMILIES:
                raise RouterValidationError(field)
        elif field == "package_variant":
            if value not in ("auto", "full", "lite"):
                raise RouterValidationError(field)
        elif not re.fullmatch(PATTERNS[field], value, flags=re.ASCII):
            raise RouterValidationError(field)
        if field in ("router_model", "hardware_revision"):
            value = value.upper()
            if field == "hardware_revision" and re.fullmatch(r"V?[0-9]{1,2}(?:[.]0{1,2})?", value):
                value = "V" + str(int(value.removeprefix("V").split(".")[0]))
        elif field == "protocol":
            value = PROTOCOL_ALIASES.get(value.lower(), value.lower())
        normalized[field] = value
    return normalized

def _source(source_id, data):
    return deepcopy(data["sources"][source_id])

def _issue(field, code, message):
    return {"field": field, "code": code, "message": message}

def _kernel_series(value):
    return ".".join(value.split(".")[:2]) if value else None

def _safe_filters(params, matched_model):
    result = dict(params)
    if not matched_model:
        result["router_model"] = None
    result["device_model_id"] = "provided_locally" if params.get("device_model_id") else None
    # Unrecognized public input is never reflected back into the model or logs.
    if result["protocol"] not in KNOWN_PROTOCOLS:
        result["protocol"] = None
    if result["architecture"] not in ("armv7l", "aarch64", "x86_64", "mips", "mipsel", "armv6l"):
        result["architecture"] = None
    return result

class RouterMatcher:
    def __init__(self, path=None):
        if path is None:
            path = Path(__file__).with_name("router-compatibility.json")
            if not path.exists():
                path = Path(__file__).resolve().parents[3] / "data/router-compatibility.json"
        raw = Path(path).read_bytes()
        if len(raw) > 3 * 1024 * 1024:
            raise ValueError("Router evidence exceeds size budget")
        data = json.loads(raw)
        if (type(data) is not dict or data.get("schema_version") != "1.0"
                or type(data.get("rows")) is not list or type(data.get("packages")) is not dict
                or type(data.get("sources")) is not dict):
            raise ValueError("Invalid router evidence")
        self.data = data
        self.digest = hashlib.sha256(raw).hexdigest()
        for row in data["rows"]:
            if (not isinstance(row.get("router_model"), str)
                    or row.get("firmware_family") not in FAMILIES
                    or row.get("package_platform") not in data["platforms"]):
                raise ValueError("Invalid router evidence row")
        for key, package in data["packages"].items():
            if (not re.fullmatch(r"[a-z0-9_]+_(?:full|lite)", key)
                    or not re.fullmatch(r"[a-f0-9]{64}", package.get("sha256", ""))
                    or not re.fullmatch(r"[a-f0-9]{32}", package.get("author_md5", ""))
                    or package.get("manifest_md5_matches") is not True
                    or package.get("archive_metadata_matches") is not True
                    or not re.fullmatch(r"https://raw\.githubusercontent\.com/hq450/fancyss/[a-f0-9]{40}/packages/fancyss_[a-z0-9_]+\.tar\.gz", package.get("download_url", ""))):
                raise ValueError("Invalid pinned package evidence")
    @classmethod
    def from_path(cls, path):
        return cls(path)

    def _prechecks(self):
        return [
            {"id": "identity", "required": True, "action": "Read the label and local productid/odmpid; keep PRO/V2 and regional or hardware suffixes.",
             "read_only_commands": ["nvram get productid", "nvram get odmpid"], "status": "not_observed_by_service"},
            {"id": "firmware", "required": True, "action": "Identify the installed publisher/family and exact branch/build from the router UI. A firmware source link is not a flashing instruction.",
             "read_only_commands": ["nvram get firmver", "nvram get buildno", "nvram get extendno"], "status": "not_observed_by_service"},
            {"id": "runtime", "required": True, "action": "Read actual running architecture and kernel. CPU capability is not the running ABI.",
             "read_only_commands": ["uname -m", "uname -r"], "status": "not_observed_by_service"},
            {"id": "software_center", "required": True, "action": "Confirm the existing supported software center and installer prerequisites locally.",
             "read_only_commands": ["test -d /koolshare", "test -x /koolshare/bin/httpdb", "test -x /usr/bin/skipd"],
             "source_id": "fancyss-install", "status": "not_observed_by_service"},
            {"id": "storage", "required": True, "action": "Check available JFFS and temporary space against the chosen extracted package and the publisher's current installer; reserve rollback space.",
             "read_only_commands": ["df -k /jffs", "df -k /tmp"], "status": "not_observed_by_service"},
            {"id": "recovery", "required": True, "action": "Keep a private local configuration backup, current plugin build and working management path. Do not flash or upgrade firmware as a side effect.",
             "read_only_commands": [], "status": "not_observed_by_service"},
            {"id": "acceptance", "required": True, "action": "After separately authorized installation, verify the router and each intended downstream client, DNS/IPv4/IPv6/TCP/UDP as applicable, and disconnect/reconnect. Never treat this match as a device test.",
             "read_only_commands": [], "status": "not_observed_by_service"},
        ]

    def query(self, params=None):
        p = normalize_router_query(params)
        data = self.data
        rows = [r for r in data["rows"] if p["router_model"] in
                {r["router_model"].upper(), *[x.upper() for x in r.get("aliases", [])]}] if p["router_model"] else []
        result = {
            "schema_version": "1.0", "query_mode": "router",
            "filters": _safe_filters(p, bool(rows)), "status": "insufficient_evidence",
            "candidates": [], "unknowns": [], "conflicts": [],
            "local_prechecks": self._prechecks(), "sources": [],
            "snapshot": {"sha256": self.digest, "checked_at": data["checked_at"],
                         "fancyss_commit": data["fancyss_commit"], "package_version": data["package_version"],
                         "scope": "publisher_documentation_and_offline_archive_integrity"},
            "combination_status": "not_tested",
            "last_updated": data["checked_at"], "source_checked_at": data["checked_at"],
            "date_semantics": {"last_updated": "router_evidence_snapshot_check_time_not_release_date"},
            "notices": [
                "A documented package candidate is not a tested router installation.",
                "Original Merlin, GNUton and stock ASUS firmware are not automatically KoolCenter modified firmware.",
                "Missing hardware revision in the source is not certification of all revisions.",
                "Official MD5 checks accidental corruption; computed SHA256 pins observed bytes. Neither is a publisher signature.",
                "Current-release posts, access-restricted downloads and public historical mirrors are distinct.",
            ],
        }
        if not p["router_model"]:
            result["unknowns"].append(_issue("router_model", "required", "Provide the exact model observed on the target; no fuzzy model lookup is performed."))
            return result
        if not rows:
            result["status"] = "no_record"
            result["unknowns"].append(_issue("router_model", "exact_model_not_documented", "No exact model row was found. Similar PRO/V2 names must not be substituted."))
            return result
        if p["firmware_family"]:
            family_rows = [r for r in rows if r["firmware_family"] == p["firmware_family"]]
            if not family_rows:
                documented_firmware = [f for f in data.get("firmware_catalog", []) if f["family"] == p["firmware_family"] and any(name.upper() == p["router_model"] for name in f["models"])]
                if documented_firmware:
                    result["status"] = "insufficient_evidence"
                    result["firmware_candidates"] = deepcopy(documented_firmware)
                    result["unknowns"].append(_issue("firmware_family", "plugin_family_not_documented", "The firmware publisher documents this exact model/family, but the pinned plugin table does not establish the combination. No plugin package is selected."))
                    result["sources"] = [_source(key, data) for key in sorted({f["source_id"] for f in documented_firmware} | {"fancyss-readme"})]
                    return result
                result["status"] = "conflict"
                result["conflicts"].append(_issue("firmware_family", "firmware_family_not_documented_for_plugin",
                    "The supplied firmware family is not the documented modified-firmware environment for this exact model. Do not install this plugin or flash another firmware automatically."))
                result["sources"] = [_source("fancyss-readme", data), _source("fancyss-install", data)]
                return result
            rows = family_rows
        source_ids = {"fancyss-readme", "fancyss-install", "fancyss-manifest"}
        for row in rows:
            unknowns, conflicts, criteria = [], [], []
            platform = data["platforms"][row["package_platform"]]
            firmware = deepcopy(row["firmware"])
            source_ids.update(row.get("source_ids", []))
            criteria.append({"field": "router_model", "state": "matched", "scope": "exact_publisher_model_row"})
            for field in ("firmware_family", "architecture", "kernel"):
                if not p[field]:
                    unknowns.append(_issue(field, "local_value_missing", "Read this value from the actual router before installation."))
            if not p["hardware_revision"]:
                unknowns.append(_issue("hardware_revision", "source_revision_scope_unspecified",
                    "The source does not certify every hardware revision. Check the label and any publisher exclusions; absence alone does not invent a different model."))
            elif row.get("hardware_revision") and p["hardware_revision"] != row["hardware_revision"]:
                conflicts.append(_issue("hardware_revision", "hardware_revision_mismatch", "The specified hardware revision differs from the documented row."))
            else:
                if p["hardware_revision"] and row.get("hardware_revision") is None:
                    unknowns.append(_issue("hardware_revision", "revision_not_documented", "This exact revision is not independently documented; do not assume all revisions are covered."))
            excluded_revisions = firmware.get("excluded_hardware_revisions", [])
            if p["hardware_revision"] in excluded_revisions or (p["hardware_revision"] and any(p["hardware_revision"].startswith(rev+".") for rev in excluded_revisions)):
                conflicts.append(_issue("hardware_revision", "publisher_excluded_revision", "The firmware publisher explicitly excludes this hardware revision from this branch."))
            if p["architecture"] and p["architecture"] not in platform["architectures"]:
                conflicts.append(_issue("architecture", "runtime_architecture_conflict", "The observed running ABI does not match the selected documented platform package. CPU bitness cannot override this."))
            expected_arch = {"armv7": "armv7l", "armv8": "aarch64"}.get(row["documented_architecture"])
            if p["architecture"] in platform["architectures"] and expected_arch and p["architecture"] != expected_arch:
                unknowns.append(_issue("architecture", "model_abi_differs_from_readme", "The installer permits this ABI, but the exact model row documents another. Verify the actual firmware rather than inferring from CPU bitness."))
            if p["kernel"]:
                if _kernel_series(p["kernel"]) not in platform["kernel_series"]:
                    conflicts.append(_issue("kernel", "installer_kernel_conflict", "The observed kernel series fails this package's documented installer gate."))
                elif _kernel_series(p["kernel"]) != _kernel_series(row["documented_kernel"]):
                    unknowns.append(_issue("kernel", "model_kernel_differs_from_readme", "The installer accepts this series, but the model table documents another series. Verify the actual firmware build separately."))
            unresolved_model = row.get("installer_model_status") == "unresolved_alias"
            if p["device_model_id"]:
                observed_id=p["device_model_id"]
                same_names={row["router_model"].upper(),*[v.upper() for v in row.get("aliases",[])]}
                installer_ids=platform.get("installer_models",[])
                if installer_ids and observed_id not in installer_ids:
                    conflicts.append(_issue("device_model_id", "installer_model_id_conflict", "The locally observed device identifier is not permitted by this platform installer."))
                elif observed_id.upper() not in same_names and not (unresolved_model and len(installer_ids)==1 and observed_id==installer_ids[0]):
                    conflicts.append(_issue("device_model_id", "device_identity_conflict", "The observed device identifier is a different or unverified model, even if it uses the same platform. Do not combine its package gate with another model's firmware evidence."))
                else:
                    unresolved_model = False
                    criteria.append({"field": "device_model_id", "state": "matched", "scope": "caller_reported_local_value_matches_exact_identity_or_single_installer_gate_not_service_measurement"})
            if unresolved_model:
                unknowns.append(_issue("router_model", "installer_model_alias_unverified",
                    "The README marketing model and the installer's local product identifier differ. Check productid/odmpid against the installer gate; no alias is guessed."))
            legacy_pattern = r"^(?:(?:3004[._])|(?:3[.]0[.]0[.]4[._]))?(?:3[0-7][0-9]|38[0-3])(?:[._-]|$)"
            if any(value and re.match(legacy_pattern, value) for value in (p["firmware_branch"], p["firmware_version"])):
                conflicts.append(_issue("firmware_branch", "below_documented_minimum", "The pinned plugin README requires the modified-firmware generation 384 or newer; this supplied legacy branch is below that prerequisite."))
            branches = firmware.get("branches", [])
            versions = firmware.get("versions", [])
            if not p["firmware_branch"]:
                unknowns.append(_issue("firmware_branch", "installed_branch_missing", "Confirm the installed branch; listed firmware sources are not an upgrade recommendation."))
            elif branches and p["firmware_branch"] not in branches:
                unknowns.append(_issue("firmware_branch", "published_branch_not_in_observed_scope", "The supplied branch is outside the collected current/historical branch evidence. This does not prove incompatibility or authorize upgrading."))
            elif not branches:
                unknowns.append(_issue("firmware_branch", "publisher_branch_not_verified", "The current exact-model publisher branch was not independently verified."))
            observed_builds = firmware.get("observed_builds", [])
            version_branches = {b["branch"] for b in observed_builds if b["version"] == p["firmware_version"]}
            if p["firmware_branch"] and version_branches and p["firmware_branch"] not in version_branches:
                conflicts.append(_issue("firmware_version", "known_build_branch_conflict", "This exact observed build belongs to a different documented branch. Correct the locally read identity before selecting a package."))
            elif p["firmware_version"] and version_branches:
                matching_builds = [b for b in observed_builds if b["version"] == p["firmware_version"] and (not p["firmware_branch"] or b["branch"] == p["firmware_branch"])]
                if matching_builds and all(b["historical"] for b in matching_builds):
                    unknowns.append(_issue("firmware_version", "historical_build_scope", "This build is evidenced by a historical release or mirror. It is a candidate for local verification, not a claim that it is the current release or a recommendation to upgrade."))
            if not p["firmware_version"]:
                unknowns.append(_issue("firmware_version", "installed_build_missing", "Record the installed build and compare the publisher's prerequisites and known issues."))
            elif p["firmware_version"] not in versions or (p["firmware_branch"] and not any(b["branch"] == p["firmware_branch"] and b["version"] == p["firmware_version"] for b in firmware.get("observed_builds", []))):
                unknowns.append(_issue("firmware_version", "exact_build_not_verified", "The installed build is not one of the observed publisher builds. This does not establish incompatibility or authorize upgrading."))
            if firmware["status"] != "publisher_documented":
                unknowns.append(_issue("firmware_family", "firmware_source_not_independently_verified", "The plugin author's model table is available, but its exact current firmware release source remains unverified."))
            protocol = p["protocol"]
            variant = p["package_variant"]
            full_only = data["variant_rules"]["full_only_protocols"]
            common = data["variant_rules"]["common_protocols"]
            if variant == "lite" and protocol in full_only:
                conflicts.append(_issue("package_variant", "protocol_excluded_from_lite", "The requested protocol requires the full package; lite removes its binaries and UI."))
            protocol_known = protocol in common or protocol in full_only
            if not protocol:
                unknowns.append(_issue("protocol", "protocol_missing", "Specify the existing source's public protocol name to choose between full and lite; never send subscription secrets."))
            elif not protocol_known:
                unknowns.append(_issue("protocol", "protocol_combination_not_documented", "This protocol or compound combination was not verified in this pinned source. VLESS alone does not certify VLESS-Reality."))
            variants = [variant] if variant != "auto" else (["full"] if protocol in full_only else ["lite"] if protocol in common else ["lite", "full"])
            blocked = bool(conflicts) or unresolved_model
            packages = [] if blocked else [deepcopy(data["packages"][row["package_platform"]+"_"+v]) for v in variants]
            # Firmware version, source and ABI gates remain visible. Revision absence alone is nonblocking.
            gate_unknowns = [u for u in unknowns if u["field"] != "hardware_revision"]
            status = "conflict" if conflicts else "insufficient_evidence" if blocked else "candidate" if gate_unknowns else "matched"
            candidate = {
                "id": row["id"], "router_model": row["router_model"],
                "hardware_revision": row.get("hardware_revision"), "firmware_family": row["firmware_family"],
                "status": status, "firmware": firmware,
                "fancyss": {"platform": row["package_platform"], "packages": packages,
                            "auto_variant_reason": "full_required_by_protocol" if protocol in full_only else "lite_saves_jffs_for_documented_protocols" if protocol in common else "protocol_choice_needed",
                            "installer_gate": deepcopy(platform)},
                "documented_hardware": {"cpu": row["cpu"], "platform_label": row["platform_label"],
                                        "architecture": row["documented_architecture"], "kernel": row["documented_kernel"]},
                "criteria": criteria, "unknowns": unknowns, "conflicts": conflicts,
                "source_ids": row.get("source_ids", []), "readme_line": row["readme_line"],
                "combination_status": "not_tested", "grants_device_authorization": False,
            }
            result["candidates"].append(candidate)
        usable = [c for c in result["candidates"] if c["status"] in ("matched", "candidate")]
        result["status"] = ("matched" if usable and all(c["status"] == "matched" for c in usable)
                            else "candidate" if usable else "conflict" if any(c["conflicts"] for c in result["candidates"])
                            else "insufficient_evidence")
        result["unknowns"] = [u for c in result["candidates"] for u in c["unknowns"]]
        result["conflicts"] = [u for c in result["candidates"] for u in c["conflicts"]]
        result["sources"] = [_source(key, data) for key in sorted(source_ids)]
        return result
