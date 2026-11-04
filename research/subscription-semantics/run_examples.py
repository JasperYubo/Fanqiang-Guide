#!/usr/bin/env python3
"""Run authored fixture cases through the actual CLI and record reproducible evidence."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads((ROOT / "fixtures/cases.json").read_text())["cases"]
    outcomes = []
    for case in cases:
        result = subprocess.run([sys.executable, str(ROOT / "checker.py"),
                                 "--source", str(ROOT / case["source"]),
                                 "--target", str(ROOT / case["target"]),
                                 "--mapping", str(ROOT / case["mapping"])],
                                text=True, capture_output=True, check=False)
        report = json.loads(result.stdout)
        expected_code = 0 if case["expected_verdict"] == "projection-equivalent" else 1
        expected = {s: case["expected_statuses"].get(s, 0) for s in report["summary"]["statuses"]}
        if (result.returncode != expected_code or report["summary"]["verdict"] != case["expected_verdict"]
                or report["summary"]["statuses"] != expected or result.stderr):
            raise RuntimeError("fixture_expectation_failed: " + case["id"])
        outcomes.append({"case": case["id"], "exit_code": result.returncode, **report["summary"]})
    test_result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(str(ROOT), pattern="test_checker.py"))
    if not test_result.wasSuccessful():
        return 1
    inputs = {}
    for path in sorted([ROOT / "checker.py", ROOT / "test_checker.py", ROOT / "run_examples.py", *ROOT.glob("fixtures/**/*.json")]):
        raw = path.read_bytes()
        inputs[path.relative_to(ROOT).as_posix()] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    evidence = {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"system": platform.system(), "python": platform.python_version()},
        "scope": "Manually authored synthetic local fixtures; CLI differential checks only.",
        "third_party_converter_executed": False, "network_or_connectivity_tested": False,
        "fixture_cases": len(cases), "fixture_passed": len(outcomes),
        "unit_tests": test_result.testsRun, "unit_test_failures": len(test_result.failures),
        "unit_test_errors": len(test_result.errors),
        "verdict_counts": dict(Counter(x["verdict"] for x in outcomes)),
        "outcomes": outcomes, "inputs": inputs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: evidence[k] for k in ("fixture_cases", "fixture_passed", "unit_tests", "verdict_counts")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
