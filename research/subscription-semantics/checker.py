#!/usr/bin/env python3
"""Local SIP008 -> sing-box field projection audit; never fetches or converts."""
from __future__ import annotations

import argparse
from collections import Counter
import ipaddress
import json
from pathlib import Path
import re
import sys
import uuid

VERSION = "0.1.0"
MAX_BYTES = 1024 * 1024
MISSING = object()
STATUSES = ("field-preserved", "transformed", "unsupported", "unknown", "changed")
SOURCE_KEYS = {"id", "remarks", "server", "server_port", "method", "password", "plugin", "plugin_opts"}
TARGET_KEYS = {"type", "tag", "server", "server_port", "method", "password", "plugin", "plugin_opts"}
ROOT_SOURCE_KEYS = {"version", "servers", "bytes_used", "bytes_remaining"}
SUPPORTED_PLUGINS = {"", "obfs-local", "v2ray-plugin"}
HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class InputError(ValueError):
    """Only constant error codes may cross the CLI boundary."""


def require(condition, code):
    if not condition:
        raise InputError(code)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def reject_constant(_):
    raise InputError("non_finite_json_number")


def load_json(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        require(len(raw) <= MAX_BYTES, "input_too_large")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_constant=reject_constant)
    except InputError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError):
        raise InputError("unreadable_or_invalid_json") from None


def host_normal_form(value):
    """Only literal IP equivalence or ASCII DNS case; no lookup/IDNA/trailing-dot guess."""
    if not isinstance(value, str) or not value or "%" in value:
        return None
    try:
        return ("ip", ipaddress.ip_address(value))
    except ValueError:
        if len(value) > 253 or value.endswith("."):
            return None
        labels = value.split(".")
        if all(HOST_LABEL.fullmatch(label) for label in labels):
            return ("ascii-dns", value.lower())
    return None


def validate_source(source):
    require(isinstance(source, dict), "source_object_required")
    require(type(source.get("version")) is int and source["version"] == 1, "unsupported_sip008_version")
    nodes = source.get("servers")
    require(isinstance(nodes, list) and 0 < len(nodes) <= 256, "source_servers_required")
    seen = set()
    for node in nodes:
        require(isinstance(node, dict), "source_server_object_required")
        for key in ("id", "remarks", "server", "method", "password"):
            require(isinstance(node.get(key), str), "invalid_source_required_field")
        require(bool(node["server"]) and bool(node["method"]) and bool(node["password"]), "empty_source_required_field")
        try:
            identity = str(uuid.UUID(node["id"]))
        except (ValueError, AttributeError):
            raise InputError("invalid_source_uuid") from None
        require(identity not in seen, "duplicate_source_uuid")
        seen.add(identity)
        require(type(node.get("server_port")) is int and 1 <= node["server_port"] <= 65535, "invalid_source_port")
        for key in ("plugin", "plugin_opts"):
            require(key not in node or isinstance(node[key], str), "invalid_source_plugin_field")
        require(bool(node.get("plugin")) or not node.get("plugin_opts"), "plugin_options_without_plugin")
        require(not node.get("plugin") or "plugin_opts" in node, "active_plugin_options_required")
    for key in ("bytes_used", "bytes_remaining"):
        if key in source:
            require(type(source[key]) is int and source[key] >= 0, "invalid_usage_metadata")
    require("bytes_remaining" not in source or "bytes_used" in source, "remaining_without_used")
    return nodes


def validate_target(target):
    require(isinstance(target, dict), "target_object_required")
    nodes = target.get("outbounds")
    require(isinstance(nodes, list) and len(nodes) <= 256, "target_outbounds_required")
    seen = set()
    for node in nodes:
        require(isinstance(node, dict), "target_outbound_object_required")
        require(isinstance(node.get("tag"), str) and bool(node["tag"]), "target_tag_required")
        require(node["tag"] not in seen, "duplicate_target_tag")
        seen.add(node["tag"])
    return nodes


def validate_mapping(mapping, sources, targets):
    require(isinstance(mapping, dict) and set(mapping) == {"pairs"}, "invalid_mapping_shape")
    require(isinstance(mapping["pairs"], list) and len(mapping["pairs"]) <= 256, "invalid_mapping_pairs")
    source_by_id = {str(uuid.UUID(n["id"])): i for i, n in enumerate(sources)}
    target_by_tag = {n["tag"]: i for i, n in enumerate(targets)}
    used_source, used_target, pairs = set(), set(), []
    for pair in mapping["pairs"]:
        require(isinstance(pair, dict) and set(pair) == {"source_id", "target_tag"}, "invalid_mapping_pair")
        require(isinstance(pair["source_id"], str) and isinstance(pair["target_tag"], str), "invalid_mapping_identity")
        try:
            identity = str(uuid.UUID(pair["source_id"]))
        except ValueError:
            raise InputError("invalid_mapping_uuid") from None
        require(identity in source_by_id and pair["target_tag"] in target_by_tag, "mapping_node_not_found")
        si, ti = source_by_id[identity], target_by_tag[pair["target_tag"]]
        require(si not in used_source and ti not in used_target, "mapping_not_one_to_one")
        used_source.add(si)
        used_target.add(ti)
        pairs.append((si, ti))
    return pairs, used_source, used_target


def compare(source, target, mapping):
    sources = validate_source(source)
    targets = validate_target(target)
    pairs, used_source, used_target = validate_mapping(mapping, sources, targets)
    fields = []

    def add(field, status, reason, si=None, ti=None, source_key=None, target_key=None, ordinal=None):
        row = {"field": field, "status": status, "reason": reason}
        if si is not None:
            row["source_node"] = si
        if ti is not None:
            row["target_node"] = ti
        if source_key:
            row["source_path"] = "/servers/" + str(si) + "/" + source_key
        if target_key:
            row["target_path"] = "/outbounds/" + str(ti) + "/" + target_key
        if ordinal is not None:
            row["extension_ordinal"] = ordinal
        fields.append(row)

    for si, ti in pairs:
        a, b = sources[si], targets[ti]
        add("node-binding", "transformed", "explicit_user_mapping_not_converter_provenance", si, ti, "id", "tag")
        add("label", "field-preserved" if a["remarks"] == b["tag"] else "transformed",
            "label_exact" if a["remarks"] == b["tag"] else "mapped_tag_renaming", si, ti, "remarks", "tag")
        add("protocol", "field-preserved" if b.get("type") == "shadowsocks" else "changed",
            "same_protocol" if b.get("type") == "shadowsocks" else "target_protocol_missing_or_changed",
            si, ti, target_key="type")
        for key in ("server", "server_port", "method", "password", "plugin", "plugin_opts"):
            av = a.get(key, MISSING)
            bv = b.get(key, MISSING)
            optional = key in ("plugin", "plugin_opts")
            aa = "" if optional and av is MISSING else av
            bb = "" if optional and bv is MISSING else bv
            status, reason = "changed", "value_changed"
            if key == "plugin" and aa not in SUPPORTED_PLUGINS:
                status, reason = "unsupported", "outside_documented_target_plugin_set"
            elif bv is MISSING and not optional:
                status, reason = "changed", "required_target_field_missing"
            elif type(aa) is not type(bb):
                status, reason = "changed", "target_type_changed"
            elif key == "server" and (host_normal_form(aa) is None or host_normal_form(bb) is None):
                status, reason = "unknown", "host_not_in_reviewed_normalization_domain"
            elif aa == bb:
                status, reason = ("field-preserved", "exact_value") if (av is MISSING) == (bv is MISSING) else ("transformed", "optional_empty_equivalence")
            elif key == "server" and host_normal_form(aa) == host_normal_form(bb):
                status, reason = "transformed", "ip_text_or_ascii_dns_case_equivalence"
            add(key, status, reason, si, ti, key, key)
        for ordinal, _ in enumerate(sorted(set(a) - SOURCE_KEYS)):
            add("source-extension", "unknown", "source_extension_semantics_not_modeled", si, ti, ordinal=ordinal)
        for ordinal, _ in enumerate(sorted(set(b) - TARGET_KEYS)):
            add("target-extension", "unknown", "target_extension_semantics_not_modeled", si, ti, ordinal=ordinal)

    for si in sorted(set(range(len(sources))) - used_source):
        add("source-node", "unknown", "source_node_not_mapped", si=si)
    for ti in sorted(set(range(len(targets))) - used_target):
        add("target-node", "unknown", "target_node_not_mapped", ti=ti)
    for key in ("bytes_used", "bytes_remaining"):
        if key in source:
            add(key, "unsupported", "usage_metadata_has_no_projection_in_this_adapter")
    for ordinal, _ in enumerate(sorted(set(source) - ROOT_SOURCE_KEYS)):
        add("source-global-extension", "unknown", "source_global_semantics_not_modeled", ordinal=ordinal)
    for ordinal, _ in enumerate(sorted(set(target) - {"outbounds"})):
        add("target-global-policy", "unknown", "target_global_semantics_not_compared", ordinal=ordinal)

    counts = Counter(row["status"] for row in fields)
    verdict = ("differences-detected" if counts["changed"] or counts["unsupported"]
               else "incomplete" if counts["unknown"] else "projection-equivalent")
    return {
        "schema_version": 1, "checker_version": VERSION,
        "source_format": "sip008-v1", "target_projection": "sing-box-shadowsocks-2026-11-04",
        "scope": {
            "mapping_origin": "explicit-user-declaration",
            "third_party_conversion_executed": False,
            "network_or_connectivity_tested": False,
            "client_schema_or_cipher_key_validity_certified": False,
            "global_dns_routing_and_runtime_behavior_compared": False,
            "input_values_or_digests_in_report": False,
        },
        "summary": {"verdict": verdict, "mapped_nodes": len(pairs),
                    "source_nodes": len(sources), "target_nodes": len(targets),
                    "statuses": {key: counts[key] for key in STATUSES}},
        "fields": fields,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            require(args.output.resolve() not in {args.source.resolve(), args.target.resolve(), args.mapping.resolve()},
                    "output_would_overwrite_input")
        report = compare(load_json(args.source), load_json(args.target), load_json(args.mapping))
        raw = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            # Exclusive creation avoids replacing prior evidence.
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(raw)
        else:
            print(raw, end="")
        return 0 if report["summary"]["verdict"] == "projection-equivalent" else 1
    except InputError as exc:
        print(json.dumps({"error": str(exc), "input_values_included": False}), file=sys.stderr)
        return 2
    except (OSError, RecursionError):
        print('{"error":"local_io_or_depth_error","input_values_included":false}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
