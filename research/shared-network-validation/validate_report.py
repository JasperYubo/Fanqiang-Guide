#!/usr/bin/env python3
"""Offline evaluator for scoped shared-network observations; never probes a device."""
from __future__ import annotations
import argparse
import json
import re
import os
import stat
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

CHANNELS = ("dns_ipv4", "dns_ipv6", "tcp_ipv4", "tcp_ipv6", "udp_ipv4", "udp_ipv6")
PHASES = ("normal", "disconnected", "reconnected", "sleep", "restored")
STATES = {"observed", "not_tested", "unknown", "not_applicable"}
METHODS = {"official_support_review", "host_interface_observation", "controlled_dns_query",
           "resolver_path_observation", "transport_probe", "route_observation",
           "working_control_probe", "transition_observation", "exit_ip"}
REASONS = {"none", "not_performed", "insufficient_evidence", "conflicting_evidence",
           "predeclared_out_of_scope", "not_supported"}
OBS_KEYS = {"state", "observed", "methods", "evidence_id", "observed_at", "reason"}
EXIT = {"pass": 0, "fail": 1, "incomplete": 2}
MAX_BYTES = 2_000_000

class InvalidReport(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise InvalidReport(message)

def keys(value, expected, name):
    require(isinstance(value, dict) and set(value) == set(expected), name + ": unexpected or missing fields")

def alias(value, prefix):
    require(isinstance(value, str) and re.fullmatch(prefix + r"-[1-9][0-9]{0,5}", value),
            "Use a local alias, not an actual device, app, address or endpoint identifier")

def timestamp(value):
    require(isinstance(value, str), "Timestamp must be UTC text")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InvalidReport("Invalid timestamp") from None
    require(value.endswith("Z") and moment.utcoffset().total_seconds() == 0, "UTC Z timestamp required")

def observation(value, accepted):
    keys(value, OBS_KEYS, "observation")
    require(value["state"] in STATES, "Unknown observation state")
    require(value["observed"] is None or value["observed"] in accepted, "Unknown observed outcome")
    methods = value["methods"]
    require(isinstance(methods, list) and len(methods) == len(set(methods))
            and set(methods) <= METHODS, "Invalid observation methods")
    require(value["reason"] in REASONS, "Invalid reason code")
    if value["state"] == "observed":
        require(value["observed"] is not None and value["reason"] == "none",
                "Observed state requires an outcome and no exception reason")
        alias(value["evidence_id"], "evidence")
        timestamp(value["observed_at"])
    elif value["state"] == "not_tested":
        require(value["observed"] is None and not methods and value["evidence_id"] is None
                and value["observed_at"] is None and value["reason"] == "not_performed",
                "Untested rows cannot contain fabricated observations")
    elif value["state"] == "not_applicable":
        require(value["observed"] is None and value["reason"] == "predeclared_out_of_scope",
                "Not applicable requires the predeclared scope reason")
        alias(value["evidence_id"], "evidence")
        timestamp(value["observed_at"])
        require(not methods, "Not applicable is a scope decision, not a network observation")
    else:
        require(value["observed"] is None and value["reason"] in
                {"insufficient_evidence", "conflicting_evidence", "not_supported"},
                "Unknown observations need a specific unresolved reason")
        if value["evidence_id"] is not None:
            alias(value["evidence_id"], "evidence")
        if value["observed_at"] is not None:
            timestamp(value["observed_at"])

def outcomes(channel):
    return {"proxy_resolver", "approved_direct_resolver", "blocked"} if channel.startswith("dns") else {"proxy", "direct", "blocked"}

def expected(policy, channel, phase):
    entry = policy["channels"][channel]
    if not entry["required"]:
        return None
    if phase == "restored":
        return entry["baseline"]
    if phase == "disconnected":
        return "blocked" if policy["disconnect"] == "block" else (
            "approved_direct_resolver" if channel.startswith("dns") else "direct")
    if phase == "sleep" and policy["sleep"] == "block":
        return "blocked"
    return entry["normal"]

def required_methods(channel, phase, outcome):
    value = {"controlled_dns_query", "resolver_path_observation"} if channel.startswith("dns") else {
        "transport_probe", "route_observation"}
    if phase != "normal":
        value.add("transition_observation")
    if outcome == "blocked":
        value.add("working_control_probe")
    return value

def status(obs, needed, expected_value, methods):
    if not needed:
        # Observed activity outside the agreed scope is not silently accepted.
        return ("not_applicable", "predeclared_out_of_scope") if obs["state"] == "not_applicable" else (
            "unknown", "scope_observation_mismatch")
    if obs["state"] == "not_applicable":
        return "unknown", "required_check_cannot_be_excluded"
    if obs["state"] != "observed":
        return obs["state"], obs["reason"]
    if not methods <= set(obs["methods"]):
        return "unknown", "insufficient_observation_methods"
    if obs["observed"] != expected_value:
        return "fail", "observed_policy_mismatch"
    return "pass", "scoped_evidence_matches_policy"

def evaluate(report):
    keys(report, {"schema_version", "evidence_kind", "session_alias", "conditions", "topology", "host_readiness", "targets"}, "report")
    require(type(report["schema_version"]) is int and report["schema_version"] == 1, "Unsupported schema version")
    require(report["evidence_kind"] in {"synthetic", "device_observation"}, "Invalid evidence kind")
    alias(report["session_alias"], "session")
    conditions = report["conditions"]
    keys(conditions, {"sleep_seconds", "transition_window_seconds", "max_probes_per_cell",
                       "data_budget_bytes", "charging_state", "thermal_state"}, "conditions")
    for field, maximum in (("sleep_seconds", 86400), ("transition_window_seconds", 3600),
                            ("max_probes_per_cell", 1000), ("data_budget_bytes", 1000000000)):
        require(type(conditions[field]) is int and 0 <= conditions[field] <= maximum,
                "Invalid observation condition")
    require(conditions["charging_state"] in {"plugged", "unplugged", "unknown"}, "Invalid charging state")
    require(conditions["thermal_state"] in {"no_warning_observed", "warning_observed", "unknown"},
            "Invalid thermal observation")
    topology = report["topology"]
    keys(topology, {"host", "host_model_alias", "host_platform", "host_os_version", "client_version",
                    "core_version", "downstream", "upstream", "sharing_link", "mode"}, "topology")
    alias(topology["host"], "host")
    alias(topology["host_model_alias"], "model")
    require(topology["host_platform"] in {"android", "ios", "linux", "unknown"}, "Invalid platform")
    for field in ("host_os_version", "client_version", "core_version"):
        require(isinstance(topology[field], str) and (topology[field] == "unknown" or
                (field == "core_version" and topology[field] == "not_exposed") or
                re.fullmatch(r"[0-9][0-9A-Za-z.+_-]{0,63}", topology[field])),
                "Versions must be bounded version text or unknown")
    require(isinstance(topology["downstream"], list) and 0 < len(topology["downstream"]) <= 64,
            "One to 64 downstream aliases required")
    require(len(set(topology["downstream"])) == len(topology["downstream"]), "Duplicate downstream alias")
    for device in topology["downstream"]:
        alias(device, "device")
    require(topology["upstream"] in {"wifi", "cellular", "ethernet", "unknown"}, "Invalid upstream")
    require(topology["sharing_link"] in {"wifi", "usb", "bluetooth", "ethernet"}, "Invalid sharing link")
    require(topology["mode"] in {"explicit_proxy", "gateway"}, "Invalid sharing mode")
    readiness = report["host_readiness"]
    observation(readiness, {"supported", "unsupported"})
    rows = []
    ready_status, reason = status(readiness, True, "supported",
                                 {"official_support_review", "host_interface_observation"})
    if ready_status == "pass" and any(topology[f] == "unknown" for f in
        ("host_platform", "host_os_version", "client_version", "core_version", "upstream")):
        ready_status, reason = "unknown", "host_environment_incomplete"
    if ready_status == "pass":
        if conditions["thermal_state"] == "warning_observed":
            ready_status, reason = "fail", "thermal_warning_stop_and_reassess"
        elif any(conditions[f] == 0 for f in ("sleep_seconds", "transition_window_seconds",
                 "max_probes_per_cell", "data_budget_bytes")) or any(
                 conditions[f] == "unknown" for f in ("charging_state", "thermal_state")):
            ready_status, reason = "unknown", "observation_conditions_incomplete"
    rows.append({"check": "host_readiness", "status": ready_status, "reason": reason, "required": True})
    targets = report["targets"]
    require(isinstance(targets, list) and 0 < len(targets) <= 256, "One to 256 application targets required")
    seen, covered = set(), set()
    for target in targets:
        keys(target, {"device", "application", "policy", "observations"}, "target")
        require(target["device"] in topology["downstream"], "Target is absent from downstream topology")
        alias(target["application"], "app")
        ident = (target["device"], target["application"])
        require(ident not in seen, "Duplicate device/application target")
        seen.add(ident)
        covered.add(target["device"])
        policy = target["policy"]
        keys(policy, {"channels", "disconnect", "sleep"}, "policy")
        require(policy["disconnect"] in {"block", "allow_direct"}, "Declare intended disconnect policy")
        require(policy["sleep"] in {"maintain", "block"}, "Declare intended sleep policy")
        keys(policy["channels"], CHANNELS, "channels")
        for channel, entry in policy["channels"].items():
            keys(entry, {"required", "normal", "baseline", "scope_reason"}, "channel policy")
            require(type(entry["required"]) is bool, "required must be boolean")
            if entry["required"]:
                require(entry["normal"] in outcomes(channel) and entry["baseline"] in outcomes(channel)
                        and entry["scope_reason"] == "required_by_user", "Invalid required channel policy")
            else:
                require(entry["normal"] is None and entry["baseline"] is None
                        and entry["scope_reason"] == "predeclared_out_of_scope", "Invalid excluded channel policy")
        require(any(policy["channels"][c]["required"] and
                    policy["channels"][c]["normal"] in {"proxy", "direct"}
                    for c in ("tcp_ipv4", "tcp_ipv6")),
                "At least one required TCP family must permit normal application access")
        # DNS channel suffixes name the resolver connection's transport family,
        # not the address family returned by an A/AAAA query.
        require(any(policy["channels"][c]["required"] for c in ("dns_ipv4", "dns_ipv6")),
                "At least one declared DNS path must be assessed")
        keys(target["observations"], PHASES, "phases")
        for phase in PHASES:
            keys(target["observations"][phase], CHANNELS, "phase channels")
            for channel in CHANNELS:
                obs = target["observations"][phase][channel]
                observation(obs, outcomes(channel))
                outcome = expected(policy, channel, phase)
                needed = policy["channels"][channel]["required"]
                result, why = status(obs, needed, outcome, required_methods(channel, phase, outcome))
                rows.append({"device": ident[0], "application": ident[1], "phase": phase,
                             "channel": channel, "expected": outcome, "observed": obs["observed"],
                             "status": result, "reason": why, "required": needed})
    require(covered == set(topology["downstream"]), "Every declared downstream device needs an application target")
    counts = dict(Counter(row["status"] for row in rows))
    overall = "fail" if counts.get("fail") else (
        "incomplete" if any(counts.get(s) for s in ("unknown", "not_tested")) else "pass")
    actual = report["evidence_kind"] == "device_observation"
    return {"schema_version": 1, "session_alias": report["session_alias"], "overall": overall,
            "verification_scope": "declared_device_observations" if actual else "synthetic_logic_only",
            "device_acceptance": overall if actual else "not_tested",
            "counts": counts, "required_checks": sum(row["required"] for row in rows),
            "passed_required_checks": sum(row["required"] and row["status"] == "pass" for row in rows),
            "limitations": ["Structured observations are supplied by the operator; authenticity is not verified.",
                           "Results cover only listed devices, applications, channels, phases and conditions.",
                           "No raw logs, credentials, IP addresses or endpoint URLs are needed or emitted."],
            "checks": rows}

def no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise InvalidReport("Duplicate JSON key")
        value[key] = item
    return value

def reject_constant(value):
    raise InvalidReport("Non-finite JSON constant")

def bounded_json(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(descriptor, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Regular report file required")
        raw = stream.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "Report exceeds 2 MB")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                      parse_constant=reject_constant)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    try:
        report = bounded_json(args.report)
        result = evaluate(report)
    except (InvalidReport, OSError, UnicodeError, json.JSONDecodeError, TypeError, KeyError, AttributeError, RecursionError):
        # Do not echo malformed values, file paths or accidentally supplied secrets.
        print(json.dumps({"overall": "invalid", "error": "Report schema or evidence fields are invalid."}))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT[result["overall"]]

if __name__ == "__main__":
    raise SystemExit(main())
