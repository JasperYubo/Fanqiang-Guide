import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import os
import unittest

from fixtures import make_template, pending, synthetic_complete
from validate_report import CHANNELS, PHASES, InvalidReport, evaluate, expected, main, required_methods

class AcceptanceTests(unittest.TestCase):
    def test_synthetic_pass_is_not_phone_acceptance(self):
        result = evaluate(synthetic_complete())
        self.assertEqual(result["overall"], "pass")
        self.assertEqual(result["required_checks"], 31)
        self.assertEqual(result["device_acceptance"], "not_tested")
        self.assertEqual(result["verification_scope"], "synthetic_logic_only")

    def test_blank_template_never_passes(self):
        result = evaluate(make_template())
        self.assertEqual(result["overall"], "incomplete")
        self.assertEqual(result["counts"], {"not_tested": 31})

    def test_every_channel_phase_must_be_observed(self):
        for phase in PHASES:
            for channel in CHANNELS:
                with self.subTest(phase=phase, channel=channel):
                    report = synthetic_complete()
                    report["targets"][0]["observations"][phase][channel] = pending()
                    self.assertEqual(evaluate(report)["overall"], "incomplete")

    def test_exit_ip_does_not_prove_dns_or_other_coverage(self):
        for channel in CHANNELS:
            with self.subTest(channel=channel):
                report = synthetic_complete()
                report["targets"][0]["observations"]["normal"][channel]["methods"] = ["exit_ip"]
                self.assertEqual(evaluate(report)["overall"], "incomplete")

    def test_explicit_proxy_does_not_skip_udp(self):
        report = synthetic_complete()
        report["topology"]["mode"] = "explicit_proxy"
        report["targets"][0]["observations"]["normal"]["udp_ipv4"] = pending()
        self.assertEqual(evaluate(report)["overall"], "incomplete")

    def test_all_normal_business_blocked_cannot_pass(self):
        report = synthetic_complete()
        report["evidence_kind"] = "device_observation"
        target = report["targets"][0]
        for channel in CHANNELS:
            target["policy"]["channels"][channel]["normal"] = "blocked"
            target["policy"]["channels"][channel]["baseline"] = "blocked"
            for phase in PHASES:
                obs = target["observations"][phase][channel]
                obs["observed"] = expected(target["policy"], channel, phase)
                obs["methods"] = sorted(required_methods(channel, phase, obs["observed"]))
        with self.assertRaises(InvalidReport):
            evaluate(report)

    def test_policy_mismatch_fails(self):
        report = synthetic_complete()
        report["targets"][0]["observations"]["disconnected"]["tcp_ipv4"]["observed"] = "direct"
        self.assertEqual(evaluate(report)["overall"], "fail")

    def test_allow_direct_is_a_declared_policy_not_always_failure(self):
        report = synthetic_complete()
        target = report["targets"][0]
        target["policy"]["disconnect"] = "allow_direct"
        for channel in CHANNELS:
            obs = target["observations"]["disconnected"][channel]
            obs["observed"] = expected(target["policy"], channel, "disconnected")
            obs["methods"] = sorted(required_methods(channel, "disconnected", obs["observed"]))
        self.assertEqual(evaluate(report)["overall"], "pass")

    def test_missing_control_cannot_prove_blocking(self):
        report = synthetic_complete()
        report["targets"][0]["observations"]["disconnected"]["tcp_ipv4"]["methods"].remove("working_control_probe")
        self.assertEqual(evaluate(report)["overall"], "incomplete")

    def test_required_not_applicable_never_passes(self):
        report = synthetic_complete()
        report["targets"][0]["observations"]["normal"]["dns_ipv6"] = {
            "state": "not_applicable", "observed": None, "methods": [], "evidence_id": "evidence-100",
            "observed_at": "2026-11-04T00:00:00Z", "reason": "predeclared_out_of_scope"}
        self.assertEqual(evaluate(report)["overall"], "incomplete")

    def test_predeclared_ipv4_only_scope_can_exclude_ipv6(self):
        report = synthetic_complete()
        target = report["targets"][0]
        for channel in CHANNELS:
            if channel.endswith("ipv6"):
                target["policy"]["channels"][channel] = {
                    "required": False, "normal": None, "baseline": None, "scope_reason": "predeclared_out_of_scope"}
                for phase in PHASES:
                    target["observations"][phase][channel] = {
                        "state": "not_applicable", "observed": None, "methods": [],
                        "evidence_id": "evidence-100", "observed_at": "2026-11-04T00:00:00Z",
                        "reason": "predeclared_out_of_scope"}
        result = evaluate(report)
        self.assertEqual(result["overall"], "pass")
        self.assertEqual(result["counts"]["not_applicable"], 15)
        self.assertEqual(result["required_checks"], 16)

    def test_unknown_remains_unknown(self):
        report = synthetic_complete()
        report["targets"][0]["observations"]["sleep"]["tcp_ipv4"] = {
            "state": "unknown", "observed": None, "methods": [], "evidence_id": None,
            "observed_at": None, "reason": "conflicting_evidence"}
        result = evaluate(report)
        self.assertEqual(result["overall"], "incomplete")
        self.assertEqual(result["counts"]["unknown"], 1)

    def test_missing_matrix_row_is_invalid(self):
        report = synthetic_complete()
        del report["targets"][0]["observations"]["normal"]["dns_ipv6"]
        with self.assertRaises(InvalidReport):
            evaluate(report)

    def test_uncovered_downstream_is_invalid(self):
        report = synthetic_complete()
        report["topology"]["downstream"].append("device-2")
        with self.assertRaises(InvalidReport):
            evaluate(report)

    def test_transport_cannot_drop_all_dns_paths(self):
        report = synthetic_complete()
        for channel in ("dns_ipv4", "dns_ipv6"):
            report["targets"][0]["policy"]["channels"][channel] = {
                "required": False, "normal": None, "baseline": None, "scope_reason": "predeclared_out_of_scope"}
        with self.assertRaises(InvalidReport):
            evaluate(report)

    def test_ipv6_business_can_use_ipv4_dns_transport(self):
        report = synthetic_complete()
        target = report["targets"][0]
        target["policy"]["channels"]["dns_ipv6"] = {
            "required": False, "normal": None, "baseline": None, "scope_reason": "predeclared_out_of_scope"}
        for phase in PHASES:
            target["observations"][phase]["dns_ipv6"] = {
                "state": "not_applicable", "observed": None, "methods": [],
                "evidence_id": "evidence-100", "observed_at": "2026-11-04T00:00:00Z",
                "reason": "predeclared_out_of_scope"}
        self.assertTrue(target["policy"]["channels"]["tcp_ipv6"]["required"])
        self.assertEqual(evaluate(report)["overall"], "pass")

    def test_unpublished_core_version_differs_from_unknown(self):
        report = synthetic_complete()
        report["topology"]["host_platform"] = "ios"
        report["topology"]["core_version"] = "not_exposed"
        self.assertEqual(evaluate(report)["overall"], "pass")
        report["topology"]["client_version"] = "not_exposed"
        with self.assertRaises(InvalidReport):
            evaluate(report)

    def test_unknown_host_environment_prevents_pass(self):
        report = synthetic_complete()
        report["topology"]["client_version"] = "unknown"
        self.assertEqual(evaluate(report)["overall"], "incomplete")

    def test_raw_log_or_url_cannot_enter_closed_schema(self):
        for change in ("extra", "url", "forged"):
            with self.subTest(change=change):
                report = synthetic_complete()
                if change == "extra":
                    report["raw_log"] = "secret-marker"
                elif change == "url":
                    report["host_readiness"]["evidence_id"] = "https://example.com/?secret=secret-marker"
                else:
                    report["targets"][0]["observations"]["normal"]["tcp_ipv4"] = pending()
                    report["targets"][0]["observations"]["normal"]["tcp_ipv4"]["observed"] = "proxy"
                with self.assertRaises(InvalidReport):
                    evaluate(report)

    def test_observation_conditions_cannot_be_missing(self):
        report = synthetic_complete()
        report["conditions"]["sleep_seconds"] = 0
        self.assertEqual(evaluate(report)["overall"], "incomplete")

    def test_thermal_warning_prevents_acceptance(self):
        report = synthetic_complete()
        report["conditions"]["thermal_state"] = "warning_observed"
        self.assertEqual(evaluate(report)["overall"], "fail")

    def test_bounded_reader_rejects_oversize_nonfinite_deep_and_fifo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            for raw in (b" " * 2_000_001, b'{"schema_version":NaN}',
                        b'{"schema_version":Infinity}', b"[" * 2000 + b"]" * 2000):
                path.write_bytes(raw)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main([str(path)]), 3)
            path.unlink()
            os.mkfifo(path)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(path)]), 3)

    def test_cli_codes_and_no_secret_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            cases = [(synthetic_complete(), 0), (make_template(), 2)]
            mismatch = synthetic_complete()
            mismatch["targets"][0]["observations"]["normal"]["tcp_ipv4"]["observed"] = "direct"
            cases.append((mismatch, 1))
            invalid = synthetic_complete()
            invalid["secret"] = "do-not-echo-this-value"
            cases.append((invalid, 3))
            for report, code in cases:
                path.write_text(json.dumps(report))
                capture = io.StringIO()
                with contextlib.redirect_stdout(capture):
                    self.assertEqual(main([str(path)]), code)
                self.assertNotIn("do-not-echo-this-value", capture.getvalue())
            path.write_text('{"schema_version":1,"schema_version":1}')
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(path)]), 3)

if __name__ == "__main__":
    unittest.main()
