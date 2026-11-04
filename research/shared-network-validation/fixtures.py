"""Synthetic, non-network test data. These functions make no device claims."""
from copy import deepcopy
from validate_report import CHANNELS, PHASES, expected, required_methods

def pending():
    return {"state": "not_tested", "observed": None, "methods": [], "evidence_id": None,
            "observed_at": None, "reason": "not_performed"}

def make_template():
    channels = {}
    for channel in CHANNELS:
        channels[channel] = {"required": True,
            "normal": "proxy_resolver" if channel.startswith("dns") else "proxy",
            "baseline": "approved_direct_resolver" if channel.startswith("dns") else "direct",
            "scope_reason": "required_by_user"}
    return {"schema_version": 1, "evidence_kind": "device_observation", "session_alias": "session-1",
            "conditions": {"sleep_seconds": 0, "transition_window_seconds": 0,
                           "max_probes_per_cell": 0, "data_budget_bytes": 0,
                           "charging_state": "unknown", "thermal_state": "unknown"},
            "topology": {"host": "host-1", "host_model_alias": "model-1", "host_platform": "unknown",
                         "host_os_version": "unknown", "client_version": "unknown", "core_version": "unknown",
                         "downstream": ["device-1"], "upstream": "unknown", "sharing_link": "wifi",
                         "mode": "gateway"},
            "host_readiness": pending(),
            "targets": [{"device": "device-1", "application": "app-1",
                         "policy": {"channels": channels, "disconnect": "block", "sleep": "maintain"},
                         "observations": {phase: {channel: pending() for channel in CHANNELS} for phase in PHASES}}]}

def synthetic_complete():
    report = make_template()
    report["evidence_kind"] = "synthetic"
    report["conditions"].update(sleep_seconds=600, transition_window_seconds=60,
                                max_probes_per_cell=3, data_budget_bytes=1000000,
                                charging_state="unplugged", thermal_state="no_warning_observed")
    report["topology"].update(host_platform="android", host_os_version="0.0", client_version="0.0",
                              core_version="0.0", upstream="wifi")
    report["host_readiness"] = {"state": "observed", "observed": "supported",
        "methods": ["official_support_review", "host_interface_observation"],
        "evidence_id": "evidence-1", "observed_at": "2026-11-04T00:00:00Z", "reason": "none"}
    i = 1
    target = report["targets"][0]
    for phase in PHASES:
        for channel in CHANNELS:
            i += 1
            value = expected(target["policy"], channel, phase)
            target["observations"][phase][channel] = {
                "state": "observed", "observed": value,
                "methods": sorted(required_methods(channel, phase, value)),
                "evidence_id": "evidence-" + str(i), "observed_at": "2026-11-04T00:00:00Z", "reason": "none"}
    return report

def synthetic_cases():
    complete = synthetic_complete()
    fail = deepcopy(complete)
    fail["targets"][0]["observations"]["disconnected"]["tcp_ipv4"]["observed"] = "direct"
    incomplete = deepcopy(complete)
    incomplete["targets"][0]["observations"]["sleep"]["dns_ipv6"] = pending()
    exit_ip = deepcopy(complete)
    exit_ip["targets"][0]["observations"]["normal"]["dns_ipv4"]["methods"] = ["exit_ip"]
    return {"complete": complete, "disconnect_mismatch": fail,
            "sleep_not_tested": incomplete, "exit_ip_insufficient": exit_ip}
