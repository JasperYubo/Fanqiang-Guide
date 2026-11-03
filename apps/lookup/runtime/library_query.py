"""Evidence-scoped AND queries over the public library; no network or MCP dependency.

A match means a documented field/relation, never successful installation or a
certified platform/protocol/feature combination. Core capabilities are hints
for clients using that core, not inherited support assertions.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

TOOL_KINDS = frozenset({"client", "core", "router_plugin", "vpn", "mesh", "browser_extension"})
PLATFORMS = {
    "android": "Android", "windows": "Windows", "macos": "macOS", "linux": "Linux",
    "ios": "iOS", "ipados": "iPadOS", "tvos": "tvOS", "visionos": "visionOS",
    "harmonyos": "HarmonyOS", "openwrt": "OpenWrt", "router": "Router",
    "freebsd": "FreeBSD", "openbsd": "OpenBSD", "chrome": "Chrome",
    "edge": "Edge", "firefox": "Firefox",
}
PROTOCOLS = tuple("anytls doh doq dot http-proxy hysteria1 hysteria2 shadowsocks snell socks trojan tuic vless vmess wireguard".split())
FEATURE_RECORDS = {
    "tun": "concept-tun", "fake-ip": "concept-fakeip", "tproxy": "concept-tproxy",
    "redirect": "concept-redirect", "url-test": "concept-urltest",
    "rule-set": "concept-ruleset", "clash-api": "concept-clash-api",
    "reality": "transport-reality",
}
PROTOCOL_ALIASES = {"ss": "shadowsocks", "hy2": "hysteria2", "http": "http-proxy"}
FEATURE_ALIASES = {"fakeip": "fake-ip", "urltest": "url-test", "ruleset": "rule-set"}
COMPOUND_PROTOCOLS = frozenset({"vless-reality", "vless+reality"})
INPUT_FIELDS = frozenset({"kind", "platform", "protocol", "feature", "os_version", "include_unknown", "limit", "offset"})
QUERY_INPUT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "kind": {"type": ["string", "null"], "enum": [None, *sorted(TOOL_KINDS)], "description": "Exact tool category; use client to return client applications only."},
        "platform": {"type": ["string", "null"], "maxLength": 32, "description": "Platform family, e.g. android; put the OS version in os_version."},
        "protocol": {"type": ["string", "null"], "maxLength": 32, "description": "Protocol name; vless-reality expands to VLESS AND the Reality transport."},
        "feature": {"type": ["string", "null"], "maxLength": 32, "description": "One documented feature, e.g. tun. All requested conditions are AND."},
        "os_version": {"type": ["string", "null"], "maxLength": 32, "description": "Numeric dotted OS version. Current data has no exact-version matrix; results remain unknown."},
        "include_unknown": {"type": "boolean", "default": False},
        "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
        "offset": {"type": "integer", "minimum": 0, "maximum": 10000, "default": 0},
    },
}

# Public alias used by the MCP/HTTP wiring layer.
QUERY_SCHEMA = QUERY_INPUT_SCHEMA
QUERY_DESCRIPTION = "::ILANG::v5.0\n[TYPE:tool][SCOPE:public_knowledge_query]\n::MODULE{QUERY}\n  [MUST] Query the requested tool kind and documented platform, protocol and feature evidence with AND semantics. Use existing get with returned record IDs for full public context.\n  [MUST] Separate platform from os_version. Android support is not proof that Android 14 or a particular protocol and feature combination was tested.\n  [MUST] VLESS-Reality means VLESS AND the Reality transport; an additional feature such as TUN remains a separate AND condition.\n  [MUST] Treat unknown as unknown. include_unknown returns candidates for further checking; a core capability does not prove that every client using the core exposes it.\n  [MUST] Zero results do not establish lack of support. Inspect excluded_unknown and request include_unknown when appropriate.\n  [MUST] Preserve source URLs, review dates and combination_status. last_updated describes the knowledge record, not the latest software release.\n  [MUST] This read-only query neither operates devices nor tests connectivity. Send only public filter values; never credentials, subscription links or private logs.\n::ILANG::COMPLETE::"

NOTICES = [
    "筛选匹配表示资料中有相应字段或实现文档，不表示安装成功、安全认证或网络实测。",
    "零结果不等于不支持。可设置 include_unknown=true 查看待核验候选；未知不会当作已支持。",
    "平台、协议与功能分别有资料，也不能证明该具体组合已兼容；须按版本和目标设备验证。",
    "last_updated 是知识记录的 updated_at；checked_at 是所引资料的核对日期，均不是软件最新发布或实时状态。",
]


class QueryValidationError(ValueError):
    """Fixed messages: never include rejected input values in public errors."""
    code = "invalid_parameter"
    status = 400

    def __init__(self, field="query", reason="invalid_value"):
        self.field, self.reason = field, reason
        super().__init__("Invalid structured query parameter: " + field + " (" + reason + ")")
        self.message = str(self)


def _date(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        if len(value) == 10:
            date.fromisoformat(value)
        else:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                return None
    except ValueError:
        return None
    return value


def _url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or any(ord(char) <= 32 for char in value)):
            return None
    except ValueError:
        return None
    return value


def _key(value, field):
    if type(value) is not str or not value.strip() or len(value) > 32:
        raise QueryValidationError(field)
    value = value.strip().casefold().replace("_", "-").replace(" ", "-")
    if not re.fullmatch(r"[a-z0-9+.-]+", value):
        raise QueryValidationError(field)
    return value


def normalize_query(params):
    if params is None:
        params = {}
    if type(params) is not dict:
        raise QueryValidationError()
    if set(params) - INPUT_FIELDS:
        raise QueryValidationError("query", "unknown_field")
    result = {key: None for key in ("kind", "platform", "protocol", "feature", "os_version")}
    kind = params.get("kind")
    if kind is not None:
        if type(kind) is not str or kind not in TOOL_KINDS:
            raise QueryValidationError("kind", "unknown_tool_kind")
        result["kind"] = kind
    for field in ("platform", "protocol", "feature"):
        value = params.get(field)
        if value is not None:
            result[field] = _key(value, field)
    if result["platform"] is not None and result["platform"] not in PLATFORMS:
        raise QueryValidationError("platform", "unknown_platform_use_os_version_separately")
    required_features = []
    if result["protocol"] in COMPOUND_PROTOCOLS:
        result["protocol"] = "vless"
        required_features.append("reality")
    result["protocol"] = PROTOCOL_ALIASES.get(result["protocol"], result["protocol"])
    if result["protocol"] is not None and result["protocol"] not in PROTOCOLS:
        raise QueryValidationError("protocol", "unknown_protocol_reality_is_a_feature")
    result["feature"] = FEATURE_ALIASES.get(result["feature"], result["feature"])
    if result["feature"] is not None:
        if result["feature"] not in FEATURE_RECORDS:
            raise QueryValidationError("feature", "unknown_feature")
        required_features.append(result["feature"])
    version = params.get("os_version")
    if version is not None:
        if not result["platform"]:
            raise QueryValidationError("os_version", "platform_required")
        if result["platform"] in {"chrome", "edge", "firefox", "router"}:
            raise QueryValidationError("os_version", "os_platform_required")
        if (type(version) is not str or len(version) > 32 or
                not re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,6}){0,3}", version)):
            raise QueryValidationError("os_version", "numeric_dotted_version_required")
        result["os_version"] = version
    for field, default, minimum, maximum in (("limit", 10, 1, 20), ("offset", 0, 0, 10000)):
        value = params.get(field, default)
        if type(value) is not int or not minimum <= value <= maximum:
            raise QueryValidationError(field, "integer_out_of_range")
        result[field] = value
    unknown = params.get("include_unknown", False)
    if type(unknown) is not bool:
        raise QueryValidationError("include_unknown", "boolean_required")
    result["include_unknown"] = unknown
    result["required_features"] = sorted(set(required_features))
    return result


def _sources(record, field):
    verification = record.get("verification") or {}
    if (verification.get("status") != "primary_reviewed" or
            field not in verification.get("reviewed_fields", []) or
            not _date(verification.get("checked_at"))):
        return []
    return [{"record_id": record["id"], "url": url, "checked_at": verification["checked_at"],
             "field": field, "level": "primary_documented"}
            for value in verification.get("evidence_urls", [])
            if (url := _url(value))]


def _dedupe(sources):
    seen, result = set(), []
    for source in sources:
        key = json.dumps(source, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            result.append(source)
            seen.add(key)
    return result


def _criterion(field, value, state, reason, sources=None):
    return {"field": field, "value": value, "state": state, "reason": reason,
            "sources": _dedupe(sources or [])}


class LibraryQuery:
    """A fixed snapshot of deployable tools, linked to existing get(id) records."""

    def __init__(self, records, comparison=None):
        if type(records) is not list:
            raise ValueError("Invalid library query input")
        self.records = deepcopy(records)
        self.by_id, self.names = {}, {}
        for record in self.records:
            if (type(record) is not dict or not isinstance(record.get("id"), str)
                    or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", record["id"])
                    or record["id"] in self.by_id or not isinstance(record.get("name"), str)
                    or not isinstance(record.get("kind"), str)
                    or type(record.get("platforms", [])) is not list
                    or type(record.get("relations", [])) is not list
                    or type(record.get("verification", {})) is not dict):
                raise ValueError("Invalid library query record")
            self.by_id[record["id"]] = record
            for name in {record["id"].casefold(), record["name"].casefold()}:
                self.names.setdefault(name, set()).add(record["id"])
        self.comparison = deepcopy(comparison)
        self.packages = {}
        if comparison is not None:
            if type(comparison) is not dict or type(comparison.get("rows")) is not list:
                raise ValueError("Invalid client comparison input")
            for row in comparison["rows"]:
                if (type(row) is not dict or type(row.get("source_urls")) is not list
                        or not _date(row.get("checked_at")) or not _url(row.get("release_url"))
                        or not isinstance(row.get("client"), str)
                        or not isinstance(row.get("platform"), str)):
                    raise ValueError("Invalid client comparison row")
                ident = self._resolve(row["client"])
                if not ident:
                    raise ValueError("Unknown client comparison identity")
                platform = row["platform"].casefold()
                platforms = ["ios", "ipados"] if platform == "iphone / ipad" else [platform]
                if any(value not in PLATFORMS for value in platforms):
                    raise ValueError("Unknown client comparison platform")
                sources = [{"record_id": ident, "url": url, "checked_at": row["checked_at"],
                            "field": "package_platform", "level": "primary_documented"}
                           for raw in row["source_urls"] if (url := _url(raw))]
                if not sources:
                    raise ValueError("Client comparison requires sources")
                for value in platforms:
                    self.packages.setdefault((ident, value), []).extend(sources)
        self.capabilities = {}
        topics = [(f"protocol-{value}", "protocol", value) for value in PROTOCOLS]
        topics += [(ident, "feature", value) for value, ident in FEATURE_RECORDS.items()]
        for ident, field, value in topics:
            topic = self.by_id.get(ident)
            if not topic:
                continue
            for relation in topic.get("relations", []):
                if not isinstance(relation, dict) or relation.get("predicate") != "documented_implementation":
                    continue
                target = self._resolve(relation.get("target_name"))
                sources = self._relation_sources(topic, relation)
                if target and sources:
                    self.capabilities.setdefault((target, field, value), []).extend(sources)
        self.candidates = sorted((record for record in self.records if record["kind"] in TOOL_KINDS),
                                 key=lambda record: record["id"])
        canonical = json.dumps({"records": self.records, "comparison": comparison},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.snapshot = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def from_paths(cls, library_path, comparison_path=None):
        records = json.loads(Path(library_path).read_text(encoding="utf-8-sig"))
        comparison = (json.loads(Path(comparison_path).read_text(encoding="utf-8-sig"))
                      if comparison_path is not None else None)
        return cls(records, comparison)

    def _resolve(self, name):
        ids = self.names.get(name.casefold(), set()) if isinstance(name, str) else set()
        return next(iter(ids)) if len(ids) == 1 else None

    @staticmethod
    def _relation_sources(record, relation):
        verification = record.get("verification") or {}
        documented = (relation.get("verification_status") == "primary_reviewed" or
                      bool(_sources(record, "relations")))
        url, checked = _url(relation.get("evidence_url")), _date(verification.get("checked_at"))
        if not documented or not url or not checked:
            return []
        return [{"record_id": record["id"], "url": url, "checked_at": checked,
                 "field": "relations", "relation": relation["predicate"],
                 "level": "primary_documented"}]

    def _platform(self, record, value):
        platforms = {p.casefold() for p in record.get("platforms", []) if isinstance(p, str)}
        sources = _sources(record, "platforms")
        packages = self.packages.get((record["id"], value), [])
        if packages or (value in platforms and sources):
            return _criterion("platform", value, "matched", "documented_platform_family",
                              (sources if value in platforms else []) + packages)
        if sources and platforms:
            return _criterion("platform", value, "not_listed", "not_in_documented_platform_list", sources)
        claims = record.get("source_claims") or {}
        reference = []
        if isinstance(claims, dict) and (url := _url(claims.get("source_url"))):
            reference = [{"record_id": record["id"], "url": url, "checked_at": _date(claims.get("captured_at")),
                          "field": "source_claims.platforms", "level": "reference_only"}]
        return _criterion("platform", value, "unknown", "platform_field_not_independently_reviewed", reference)

    def _capability(self, record, field, value):
        direct = self.capabilities.get((record["id"], field, value), [])
        if direct:
            return _criterion(field, value, "matched", "direct_implementation_documentation", direct)
        hints = []
        for relation in record.get("relations", []):
            if not isinstance(relation, dict) or relation.get("predicate") != "uses_core":
                continue
            core = self._resolve(relation.get("target_name"))
            relation_sources = self._relation_sources(record, relation)
            core_sources = self.capabilities.get((core, field, value), [])
            if relation_sources and core_sources:
                hints.extend(relation_sources + core_sources)
        reason = "core_documentation_does_not_verify_client_capability" if hints else "no_direct_capability_evidence"
        return _criterion(field, value, "unknown", reason, hints)

    def query(self, params=None):
        filters = normalize_query(params)
        matches, unknown_count, not_listed_count = [], 0, 0
        for record in self.candidates:
            if filters["kind"] is not None and record["kind"] != filters["kind"]:
                continue
            criteria = []
            if filters["kind"]:
                criteria.append(_criterion("kind", filters["kind"], "matched", "record_kind_classification"))
            if filters["platform"]:
                criteria.append(self._platform(record, filters["platform"]))
            if filters["protocol"]:
                criteria.append(self._capability(record, "protocol", filters["protocol"]))
            for feature in filters["required_features"]:
                criteria.append(self._capability(record, "feature", feature))
            if filters["os_version"]:
                criteria.append(_criterion("os_version", filters["os_version"], "unknown",
                                           "exact_os_version_not_structured_or_tested"))
            if any(item["state"] == "not_listed" for item in criteria):
                not_listed_count += 1
                continue
            has_unknown = any(item["state"] == "unknown" for item in criteria)
            if has_unknown:
                unknown_count += 1
                if not filters["include_unknown"]:
                    continue
            sources = _dedupe([source for item in criteria for source in item["sources"]])
            verification = record.get("verification") or {}
            matches.append({
                "id": record["id"], "name": record["name"], "kind": record["kind"],
                "match_status": "unknown" if has_unknown else "matched" if criteria else "not_filtered",
                "criteria": criteria, "sources": sources,
                "matched_condition_count": sum(item["state"] == "matched" for item in criteria),
                "verification": verification.get("status", "unknown"),
                "checked_at": _date(verification.get("checked_at")),
                "last_updated": _date(record.get("updated_at")),
                "combination_status": "not_tested",
                "compatibility_notes": (record.get("compatibility") or {}).get("notes"),
            })
        ordering = ["id_asc"]
        if filters["include_unknown"]:
            if filters["platform"]:
                matches.sort(key=lambda item: (
                    -int(any(c["field"] == "platform" and c["state"] == "matched"
                             for c in item["criteria"])),
                    -item["matched_condition_count"], item["id"]))
                ordering = ["platform_matched_first", "matched_condition_count_desc", "id_asc"]
            else:
                matches.sort(key=lambda item: (-item["matched_condition_count"], item["id"]))
                ordering = ["matched_condition_count_desc", "id_asc"]
        offset, limit = filters["offset"], filters["limit"]
        page = deepcopy(matches[offset:offset + limit])
        total = len(matches)
        return {
            "schema_version": "1.0", "snapshot_sha256": self.snapshot,
            "scope": {"kinds": sorted(TOOL_KINDS), "eligible_records": len(self.candidates)},
            "filters": filters, "filter_operator": "AND", "ordering": ordering,
            "total": total, "limit": limit, "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None,
            "unknown_candidates": unknown_count,
            "excluded_unknown": 0 if filters["include_unknown"] else unknown_count,
            "excluded_not_listed_platform": not_listed_count,
            "items": page, "notices": list(NOTICES),
            "available_filters": {"kind": sorted(TOOL_KINDS), "platform": list(PLATFORMS), "protocol": list(PROTOCOLS),
                                  "feature": list(FEATURE_RECORDS),
                                  "protocol_aliases": {**PROTOCOL_ALIASES, "vless-reality": "vless AND feature=reality"}},
            "date_semantics": {"last_updated": "knowledge_record_updated_at",
                               "checked_at": "record_source_review_date",
                               "sources_checked_at": "specific_evidence_review_date"},
        }
