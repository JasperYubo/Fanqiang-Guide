"""Run public project tests and an isolated build from any working directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NODE_TESTS = ("worker-intake.test.mjs", "intake-integration-review.test.mjs", "intake.test.mjs",
              "intake-artifact.test.mjs", "retrieval.test.mjs", "cases.test.mjs",
              "faq-cache.test.mjs", "worker-faq-cache.test.mjs")


def validate_generated_answers(source: Path, public: Path) -> dict:
    spec = importlib.util.spec_from_file_location("check_faq_pages", ROOT / "apps/site/faq_pages_v10.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries, _ = module.load_answers(source)
    representatives, failures = {}, []
    mapping = json.loads((public / "data/faq-pages.json").read_text(encoding="utf-8"))
    mapped = {e["faq_id"]: e for e in mapping["entries"]}
    if len(mapped) != len(entries) or mapping["pages"] != len(entries) or mapping["source_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest():
        failures.append("data/faq-pages.json:source_mapping_mismatch")
    for entry in entries:
        ident = representatives.setdefault(module.equivalent_key(entry), entry["faq_id"])
        relative = "answers/" + entry["faq_id"] + "/"
        canonical = module.SITE + "/answers/" + ident + "/"
        try:
            raw = (public / relative / "index.html").read_text(encoding="utf-8")
            markdown = (public / relative / "index.md").read_text(encoding="utf-8")
            if raw.count('rel="canonical" href="' + canonical + '"') != 1:
                failures.append(relative + "canonical_mismatch")
            if mapped[entry["faq_id"]]["canonical"] != canonical or mapped[entry["faq_id"]]["url"] != module.SITE + "/" + relative or "<h1>" + html.escape(mapped[entry["faq_id"]]["title"]) + "</h1>" not in raw:
                failures.append(relative + "deployment_mapping_mismatch")
            for fact in [entry["short_answer"], *[s["content"] for s in entry["sections"]]]:
                if html.escape(fact) not in raw or module.mdtext(fact) not in markdown:
                    failures.append(relative + "approved_fact_missing")
            graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S)[1])["@graph"]
            article = next(s for s in graph if s["@type"] == "Article")
            if article["dateModified"] != entry["checked_at_utc"] or article["mainEntityOfPage"] != canonical:
                failures.append(relative + "article_metadata_mismatch")
            if any(s["@type"] == "FAQPage" for s in graph) or not any(s["@type"] == "BreadcrumbList" for s in graph):
                failures.append(relative + "structured_data_mismatch")
            if raw.count('/assets/external-browser-v1.0.js') != 1 or raw.count('googletagmanager.com/gtag/js?id=G-V0RLGGS7FB') != 1:
                failures.append(relative + "template_guard_or_analytics_missing")
            for source_item in entry["sources"]:
                if html.escape(source_item["url"], quote=True) not in raw or source_item["url"] not in markdown:
                    failures.append(relative + "approved_source_missing")
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            failures.append(relative + "invalid_page")
    namespace = {"s": module.NS}
    urls = [n.text for n in ET.parse(public / "sitemap-answers.xml").findall("s:url/s:loc", namespace)]
    expected = {module.SITE + "/answers/" + ident + "/" for ident in representatives.values()}
    if len(urls) != len(set(urls)) or not expected <= set(urls):
        failures.append("sitemap-answers.xml:canonical_coverage_mismatch")
    if mapping["canonical_pages"] != len(representatives) or mapping["sitemap_urls"] != len(urls):
        failures.append("data/faq-pages.json:canonical_count_mismatch")
    for ident in {e["faq_id"] for e in entries} - set(representatives.values()):
        if module.SITE + "/answers/" + ident + "/" in urls:
            failures.append("sitemap-answers.xml:duplicate_canonical_page")
    actual_pages = len(list((public / "answers").glob("faq-*/index.html")))
    if actual_pages != len(entries):
        failures.append("answers:page_count_mismatch")
    return {"pages": actual_pages, "canonical_pages": len(representatives), "sitemap_urls": len(urls), "failures": failures}


def validate_generated_knowledge(source: Path, generated: Path, public: Path) -> list[str]:
    """Compare all records, then verify rebuilt hashes against actual release bytes.

    Git can check inherited JSON out as CRLF on Windows. Hashes describe the
    bytes actually packaged; an EOL-only input change must not hide record drift.
    """
    def exports(path):
        values = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.fullmatch(r"export const ([A-Z_]+) = (.+);", line)
            if match:
                values[match[1]] = json.loads(match[2])
        if set(values) != {"KNOWLEDGE_META", "GUIDES", "MODELS", "LIBRARY"}:
            raise ValueError("unexpected_knowledge_exports")
        return values
    try:
        expected, actual = exports(source), exports(generated)
        hashes = actual["KNOWLEDGE_META"].pop("sha256")
        expected["KNOWLEDGE_META"].pop("sha256")
        if expected != actual:
            return ["worker/src/knowledge.mjs:generated_records_mismatch"]
        if set(hashes) != {"guides", "library", "merlin-models"}:
            return ["worker/src/knowledge.mjs:input_hash_keys_mismatch"]
        return ["worker/src/knowledge.mjs:" + name + ":published_input_hash_mismatch"
                for name, digest in hashes.items()
                if hashlib.sha256((public / "data" / (name + ".json")).read_bytes()).hexdigest() != digest]
    except (OSError, ValueError, KeyError, TypeError):
        return ["worker/src/knowledge.mjs:invalid_generated_contract"]

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
        ("case-page-tests", [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "apps/site"), "-p", "test_cases*.py", "-v"], ROOT / "apps/site"),
        ("faq-page-tests", [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "apps/site"), "-p", "test_faq_pages*.py", "-v"], ROOT / "apps/site"),
        ("case-pipeline-tests", [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "apps/case-pipeline"), "-p", "test_*.py", "-v"], ROOT / "apps/case-pipeline"),
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
        for name in ("worker.mjs", "intake.mjs", "ilang.mjs", "retrieval.mjs", "cases.mjs", "openapi.mjs", "faq-cache.mjs"):
            if (release / "worker/src" / name).read_bytes() != (ROOT / "apps/worker/src" / name).read_bytes():
                failures.append("worker/src/" + name + ":generated_source_mismatch")
        failures.extend(validate_generated_knowledge(ROOT / "apps/worker/src/knowledge.mjs", release / "worker/src/knowledge.mjs", release / "site"))
        faq_bytes = (ROOT / "data/faq-cache.json").read_bytes()
        if (release / "site/data/faq-cache.json").read_bytes() != faq_bytes:
            failures.append("site/data/faq-cache.json:source_mismatch")
        faq_module = (release / "worker/src/faq-cache-data.mjs").read_text(encoding="utf-8")
        if ("SHA256: " + hashlib.sha256(faq_bytes).hexdigest()) not in faq_module:
            failures.append("worker/src/faq-cache-data.mjs:source_hash_mismatch")
        report["faq_pages"] = validate_generated_answers(ROOT / "data/faq-cache.json", release / "site")
        failures.extend(report["faq_pages"]["failures"])
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
