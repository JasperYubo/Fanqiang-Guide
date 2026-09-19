"""Run public project tests and an isolated build from any working directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
NODE_TESTS = ("worker-intake.test.mjs", "intake-integration-review.test.mjs", "intake.test.mjs",
              "intake-artifact.test.mjs", "retrieval.test.mjs")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = (options.output or ROOT / ".build" / ("checks-" + stamp)).resolve()
    if output == ROOT or output in ROOT.parents or output.exists():
        raise ValueError("Output must be a new directory separate from checkout root.")
    output.mkdir(parents=True)
    env = dict(os.environ, PYTHON=sys.executable, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js 24 is required.")
    exported = ROOT / "export/library-v0.1-2026-09-11.json"
    lookup_snapshot = ROOT / "apps/lookup/runtime/library.json"
    exported_bytes = exported.read_bytes()
    lookup_bytes = lookup_snapshot.read_bytes()
    snapshots_equal = json.loads(exported_bytes) == json.loads(lookup_bytes)
    snapshot_check = {"ok": snapshots_equal, "export_sha256": hashlib.sha256(exported_bytes).hexdigest(),
                      "lookup_sha256": hashlib.sha256(lookup_bytes).hexdigest()}
    if not snapshots_equal:
        report = {"version": "1.0", "ok": False, "knowledge_snapshot": snapshot_check,
                  "error": "Root library export and lookup library differ; coordinate source and application snapshot rebuilds."}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": False, "report": str(output / "report.json"), "error": report["error"]}))
        raise SystemExit(1)
    commands = [
        ("ilang-documents", [sys.executable, str(ROOT / "tools/ilang_grammar_validator.py"), "--lint",
                             str(ROOT / "CLAUDE.md"), str(ROOT / "developer/MAINTENANCE-v1.0-2026-09-17.ilang.md"), "--strict", "--json"], ROOT),
        ("knowledge-tests", [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"], ROOT),
        ("worker-tests", [node, "--test", "--test-reporter=tap", *[str(ROOT / "apps/worker/test" / name) for name in NODE_TESTS]], ROOT / "apps/worker"),
        ("lookup-tests", [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "apps/lookup/runtime"), "-p", "test_app.py", "-v"], ROOT / "apps/lookup/runtime"),
        ("build", [sys.executable, str(ROOT / "developer/build_apps.py"), "--output", str(output / "release")], output),
    ]
    report = {"version": "1.0", "checked_at": datetime.now(timezone.utc).isoformat(), "ok": False, "steps": [], "knowledge_snapshot": snapshot_check}
    for name, command, cwd in commands:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        log = result.stdout + result.stderr
        (output / (name + ".log")).write_text(log, encoding="utf-8")
        step = {"name": name, "exit_code": result.returncode, "log": name + ".log"}
        report["steps"].append(step)
        if name == "worker-tests":
            counts = {key: int(re.findall(r"^# " + key + r" (\d+)\s*$", log, re.M)[-1])
                      for key in ("tests", "pass", "fail", "skipped") if re.findall(r"^# " + key + r" (\d+)\s*$", log, re.M)}
            step["counts"] = counts
            if counts.get("fail", 1) != 0 or counts.get("skipped", 1) != 0 or not counts.get("tests"):
                step["validation_failed"] = True
        if result.returncode or step.get("validation_failed"):
            print(json.dumps({"failed_step": name, "log_tail": log.splitlines()[-80:]}, ensure_ascii=False))
            break
    else:
        release = output / "release"
        failures = []
        public_library = json.loads(
            (ROOT / "export/library-v0.1-2026-09-11.json").read_text(encoding="utf-8-sig")
        )
        lookup_library = json.loads(
            (ROOT / "apps/lookup/runtime/library.json").read_text(encoding="utf-8-sig")
        )
        if public_library != lookup_library:
            failures.append("apps/lookup/runtime/library.json:does_not_match_public_export")
        for file in sorted((release / "site").rglob("*")):
            if file.is_file() and file.suffix == ".gz":
                if gzip.decompress(file.read_bytes()) != file.with_suffix("").read_bytes():
                    failures.append(file.relative_to(release).as_posix() + ":gzip_mismatch")
        for name in ("worker.mjs", "intake.mjs", "ilang.mjs", "retrieval.mjs", "knowledge.mjs"):
            if (release / "worker/src" / name).read_bytes() != (ROOT / "apps/worker/src" / name).read_bytes():
                failures.append("worker/src/" + name + ":generated_source_mismatch")
        for file in sorted(release.rglob("*")):
            if file.is_file() and file.suffix.lower() in {".html", ".txt", ".md", ".json", ".mjs", ".js", ".py", ".ilang"}:
                if "github.com/mtmpss/Fanqiang-Guide" in file.read_text(encoding="utf-8"):
                    failures.append(file.relative_to(release).as_posix() + ":old_repository_reference")
        report["release_validation"] = {"failures": failures, "static_files": sum(p.is_file() for p in (release / "site").rglob("*"))}
        report["ok"] = not failures
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "report": str(output / "report.json"), "steps": report["steps"]}, ensure_ascii=False))
    raise SystemExit(0 if report["ok"] else 1)

if __name__ == "__main__":
    main()
