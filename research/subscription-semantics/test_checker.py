"""Contract tests: loss, uncertainty, identity, input ambiguity and report privacy."""
import copy
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import checker

ROOT = Path(__file__).resolve().parent
CASES = json.loads((ROOT / "fixtures/cases.json").read_text())["cases"]


class SemanticsTests(unittest.TestCase):
    def setUp(self):
        path = ROOT / "fixtures/01-preserved"
        self.source = checker.load_json(path / "source.json")
        self.target = checker.load_json(path / "target.json")
        self.mapping = checker.load_json(path / "mapping.json")

    def test_nineteen_reviewed_case_expectations(self):
        for case in CASES:
            with self.subTest(case=case["id"]):
                report = checker.compare(*(checker.load_json(ROOT / case[k]) for k in ("source", "target", "mapping")))
                self.assertEqual(case["expected_verdict"], report["summary"]["verdict"])
                expected = {s: case["expected_statuses"].get(s, 0) for s in checker.STATUSES}
                self.assertEqual(expected, report["summary"]["statuses"])

    def test_no_input_value_or_extension_key_in_report(self):
        sentinel = "SECRET-MARKER-DO-NOT-REPORT-7f934a"
        self.source["servers"][0]["password"] = sentinel
        self.source["servers"][0][sentinel] = {"secret": sentinel}
        self.target["outbounds"][0]["password"] = sentinel + "-changed"
        report = checker.compare(self.source, self.target, self.mapping)
        raw = json.dumps(report)
        for value in (sentinel, self.source["servers"][0]["server"], self.source["servers"][0]["id"], "synthetic-ss"):
            self.assertNotIn(value, raw)
        self.assertFalse(report["scope"]["network_or_connectivity_tested"])

    def test_duplicates_are_rejected_before_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "input.json"
            p.write_text('{"password":"secret-a","password":"secret-b"}')
            with self.assertRaisesRegex(checker.InputError, "^duplicate_json_key$"):
                checker.load_json(p)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "input.json"
            for word in ("NaN", "Infinity", "-Infinity"):
                p.write_text('{"x":' + word + '}')
                with self.assertRaisesRegex(checker.InputError, "^non_finite_json_number$"):
                    checker.load_json(p)

    def test_input_size_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "input.json"
            p.write_bytes(b" " * (checker.MAX_BYTES + 1))
            with self.assertRaisesRegex(checker.InputError, "^input_too_large$"):
                checker.load_json(p)

    def test_unsupported_version_rejected(self):
        self.source["version"] = 2
        with self.assertRaisesRegex(checker.InputError, "^unsupported_sip008_version$"):
            checker.compare(self.source, self.target, self.mapping)

    def test_boolean_is_not_a_port(self):
        self.source["servers"][0]["server_port"] = True
        with self.assertRaisesRegex(checker.InputError, "^invalid_source_port$"):
            checker.compare(self.source, self.target, self.mapping)

    def test_duplicate_source_uuid_rejected(self):
        self.source["servers"].append(copy.deepcopy(self.source["servers"][0]))
        with self.assertRaisesRegex(checker.InputError, "^duplicate_source_uuid$"):
            checker.compare(self.source, self.target, self.mapping)

    def test_duplicate_target_tag_rejected(self):
        self.target["outbounds"].append(copy.deepcopy(self.target["outbounds"][0]))
        with self.assertRaisesRegex(checker.InputError, "^duplicate_target_tag$"):
            checker.compare(self.source, self.target, self.mapping)

    def test_many_to_one_mapping_rejected(self):
        other = copy.deepcopy(self.source["servers"][0])
        other["id"] = "00000000-0000-4000-8000-000000000002"
        self.source["servers"].append(other)
        self.mapping["pairs"].append({"source_id": other["id"], "target_tag": "synthetic-ss"})
        with self.assertRaisesRegex(checker.InputError, "^mapping_not_one_to_one$"):
            checker.compare(self.source, self.target, self.mapping)

    def test_missing_mapping_reference_rejected(self):
        self.mapping["pairs"][0]["target_tag"] = "no-such-node"
        with self.assertRaisesRegex(checker.InputError, "^mapping_node_not_found$"):
            checker.compare(self.source, self.target, self.mapping)

    def test_empty_mapping_does_not_pass(self):
        report = checker.compare(self.source, self.target, {"pairs": []})
        self.assertEqual("incomplete", report["summary"]["verdict"])
        self.assertEqual(2, report["summary"]["statuses"]["unknown"])

    def test_plugin_options_without_plugin_rejected(self):
        self.source["servers"][0]["plugin_opts"] = "obfs=http"
        with self.assertRaisesRegex(checker.InputError, "^plugin_options_without_plugin$"):
            checker.compare(self.source, self.target, self.mapping)

    def test_active_plugin_requires_explicit_options(self):
        self.source["servers"][0]["plugin"] = "obfs-local"
        with self.assertRaisesRegex(checker.InputError, "^active_plugin_options_required$"):
            checker.compare(self.source, self.target, self.mapping)

    def test_trailing_dot_not_assumed_equivalent(self):
        self.target["outbounds"][0]["server"] += "."
        report = checker.compare(self.source, self.target, self.mapping)
        self.assertEqual("incomplete", report["summary"]["verdict"])

    def test_pure_comparison_opens_no_sockets(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            report = checker.compare(self.source, self.target, self.mapping)
        self.assertEqual("projection-equivalent", report["summary"]["verdict"])

    def test_cli_invalid_json_does_not_echo_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid.json"
            path.write_text('{"secret":"PRIVATE-NEVER-ECHO",broken}')
            case = CASES[0]
            result = subprocess.run([sys.executable, str(ROOT / "checker.py"), "--source", str(path),
                                     "--target", str(ROOT / case["target"]), "--mapping", str(ROOT / case["mapping"])],
                                    capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertNotIn("PRIVATE-NEVER-ECHO", result.stdout + result.stderr)
            self.assertEqual("unreadable_or_invalid_json", json.loads(result.stderr)["error"])

    def test_cli_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for name, data in (("source", self.source), ("target", self.target), ("mapping", self.mapping)):
                (p / (name + ".json")).write_text(json.dumps(data))
            before = (p / "source.json").read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / "checker.py"), "--source", str(p / "source.json"),
                                     "--target", str(p / "target.json"), "--mapping", str(p / "mapping.json"),
                                     "--output", str(p / "source.json")], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertEqual(before, (p / "source.json").read_bytes())

    def test_cli_does_not_replace_prior_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "report.json"
            p.write_text("prior-evidence")
            case = CASES[0]
            result = subprocess.run([sys.executable, str(ROOT / "checker.py"), "--source", str(ROOT / case["source"]),
                                     "--target", str(ROOT / case["target"]), "--mapping", str(ROOT / case["mapping"]),
                                     "--output", str(p)], capture_output=True, text=True)
            self.assertEqual(2, result.returncode)
            self.assertEqual("prior-evidence", p.read_text())


if __name__ == "__main__":
    unittest.main()
