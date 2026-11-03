#!/usr/bin/env python3
"""Observe router upstream changes; never promote or rewrite compatibility facts.

Every run compares live, bounded primary-source observations with the reviewed
matrix. A change means pending manual review, not confirmed compatibility.
No package is downloaded, extracted, installed or executed by this watcher.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("router_evidence_builder", ROOT / "developer/update_router_compatibility.py")
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)
API = "https://api.github.com/repos/hq450/fancyss"
SHA = re.compile(r"[0-9a-f]{40}\Z")
PACKAGE = re.compile(r"packages/fancyss_([a-z0-9_]+)_(full|lite)[.]tar[.]gz\Z")
CORE = {"README.md", "fancyss/install.sh", "packages/version.json.js"}
API_ERRORS = (OSError, URLError, ValueError, KeyError, TypeError, UnicodeError)


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A GitHub token is never forwarded to any redirect target.
        raise ValueError("unexpected_api_redirect")


def github_json(url):
    if not (url == API or url.startswith(API + "/")) or urlsplit(url).hostname != "api.github.com":
        raise ValueError("unexpected_api_url")
    headers = {"User-Agent": "Fanqiang-Guide-RouterWatch/1.0", "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(url, headers=headers)
    with build_opener(NoRedirect()).open(request, timeout=25) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError("api_response_too_large")
    return json.loads(raw)


def tracked_tree(obj):
    if obj.get("truncated") is not False or not isinstance(obj.get("tree"), list):
        raise ValueError("incomplete_git_tree")
    result = {}
    for item in obj["tree"]:
        path = item.get("path", "")
        if path not in CORE and not PACKAGE.fullmatch(path):
            continue
        if item.get("type") != "blob" or not SHA.fullmatch(item.get("sha", "")):
            raise ValueError("invalid_git_blob")
        if path in result:
            raise ValueError("duplicate_git_path")
        result[path] = {"git_blob_sha": item["sha"], "bytes": item.get("size")}
    if not CORE <= result.keys() or len(result) > 100:
        raise ValueError("unexpected_git_tree_layout")
    return result


def source_value(source_id, source, content=None):
    if source_id in evidence.TOPICS:
        if content is None:
            if not source.get("title") or not source.get("post_updated_at"):
                raise ValueError("reviewed_topic_metadata_missing")
            return {key: source[key] for key in ("title", "post_updated_at")}
        obj = json.loads(content)
        first = obj["post_stream"]["posts"][0]
        if first.get("post_number") != 1 or not isinstance(first.get("cooked"), str):
            raise ValueError("release_first_post_missing")
        if not obj.get("title") or not first.get("updated_at"):
            raise ValueError("release_metadata_missing")
        # Reply/view counters do not create a release-change alert. A first-post
        # edit is observable even when version/model text remains the same.
        return {"title": obj["title"], "post_updated_at": first["updated_at"]}
    if content is None:
        return {"sha256": source["sha256"]}
    if not content or re.search(br"<title>\s*(?:Just a moment|Access denied|Attention Required)", content, re.I):
        raise ValueError("source_not_readable")
    return {"sha256": hashlib.sha256(content).hexdigest()}


def change(category, key, before, after):
    return {"category": category, "source_id": key, "status": "pending_manual_review",
            "before": before, "observed": after}


def observe(matrix, collector, *, api=github_json, checked_at=None):
    checked_at = checked_at or utc()
    reviewed = matrix["fancyss_commit"]
    if not SHA.fullmatch(reviewed) or matrix.get("not_device_tested") is not True:
        raise ValueError("invalid_reviewed_matrix")
    report = {"schema_version": "1.0", "checked_at": checked_at,
              "reviewed_baseline": {"commit": reviewed, "package_version": matrix["package_version"],
                                    "matrix_checked_at": matrix["checked_at"]},
              "scope": "upstream_observation_only_pending_manual_review",
              "compatibility_matrix_modified": False, "device_tested": False,
              "package_archives_downloaded": False,
              "observations": {}, "changes": [], "failures": []}
    observations, changes, failures = report["observations"], report["changes"], report["failures"]
    current = None
    try:
        repository = api(API)
        branch = repository["default_branch"]
        if not isinstance(branch, str) or not branch or len(branch) > 200:
            raise ValueError("invalid_default_branch")
        commit = api(API + "/commits/" + quote(branch, safe=""))
        current = commit["sha"]
        if not SHA.fullmatch(current):
            raise ValueError("invalid_commit")
        current_tree = tracked_tree(api(API + "/git/trees/" + current + "?recursive=1"))
        reviewed_tree = current_tree if current == reviewed else tracked_tree(api(API + "/git/trees/" + reviewed + "?recursive=1"))
        expected_packages = {"packages/fancyss_" + name + ".tar.gz" for name in matrix["packages"]}
        if not expected_packages <= reviewed_tree.keys():
            raise ValueError("reviewed_packages_missing_from_git_tree")
        observations["fancyss-upstream"] = {"url": "https://github.com/hq450/fancyss", "default_branch": branch,
                                             "commit": current, "tracked_files": current_tree}
        if current != reviewed:
            changes.append(change("upstream_commit", "fancyss-upstream", reviewed, current))
        for path in sorted(set(reviewed_tree) | set(current_tree)):
            if reviewed_tree.get(path) != current_tree.get(path):
                changes.append(change("package_blob" if PACKAGE.fullmatch(path) else "upstream_file",
                                      path, reviewed_tree.get(path), current_tree.get(path)))
    except API_ERRORS:
        failures.append({"source_id": "fancyss-upstream", "error_code": "github_metadata_unavailable_or_invalid"})
        current = None

    def check_source(pair):
        key, baseline = pair
        url = baseline["url"]
        try:
            if baseline.get("status") != "retrieved":
                raise ValueError("reviewed_source_missing")
            if key.startswith("fancyss-"):
                if current is None:
                    raise ValueError("upstream_commit_unavailable")
                url = url.replace("/" + reviewed + "/", "/" + current + "/")
            content = collector.fetch(url, 3_000_000)
            old, new = source_value(key, baseline), source_value(key, baseline, content)
            observation = {"url": url, "observed_at": checked_at, "status": "observed", "value": new}
            if key == "fancyss-manifest":
                manifest = json.loads(content)
                version = manifest["version"]
                if not re.fullmatch(r"[0-9]+[.][0-9]+[.][0-9]+", version):
                    raise ValueError("invalid_advertised_version")
                checksums = {k: v for k, v in manifest.items() if k.startswith("md5_")}
                expected = {"md5_" + name for name in matrix["packages"]}
                if not expected <= checksums.keys() or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", v) for v in checksums.values()):
                    raise ValueError("invalid_advertised_checksums")
                observation["advertised_package_version"] = version
                observation["advertised_md5"] = checksums
                observation["archive_bytes_not_reverified"] = True
            return key, observation, change("publisher_source", key, old, new) if old != new else None, None
        except API_ERRORS + (IndexError,):
            return key, None, None, {"source_id": key, "error_code": "source_unavailable_or_invalid"}

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(check_source, sorted(matrix["sources"].items())))
    for key, observation, changed, failure in results:
        if observation:
            observations[key] = observation
        if changed:
            changes.append(changed)
        if failure:
            failures.append(failure)
    report["status"] = "partial_failure" if failures else "changes_pending_review" if changes else "unchanged"
    report["change_count"] = len(changes)
    report["failed_source_count"] = len(failures)
    report["review_required"] = bool(changes)
    return report


def render_summary(report):
    lines = ["# Router upstream observation", "", "Status: **" + report["status"] + "**", "",
             "Compared with reviewed fancyss commit `" + report["reviewed_baseline"]["commit"] + "`.", "",
             "Detected changes: " + str(report["change_count"]) + "; unavailable sources: " + str(report["failed_source_count"]) + ".", "",
             "All detected changes require manual review. The compatibility matrix and reviewed pin remain unchanged.",
             "No new package was downloaded or installed; no hardware compatibility was tested.", ""]
    if report["failures"]:
        lines += ["An unavailable check is unknown, not evidence of no change. See the JSON artifact for source IDs.", ""]
    if report["changes"]:
        lines += ["| Kind | Source |", "| --- | --- |"]
        for item in report["changes"]:
            # Only identifiers are shown, never arbitrary upstream prose or errors.
            key = re.sub(r"[^a-zA-Z0-9_./-]", "", item["source_id"])
            lines.append("| " + item["category"] + " | `" + key + "` |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "data/router-compatibility.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    opts = parser.parse_args(argv)
    opts.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        matrix = json.loads(opts.baseline.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="router-watch-") as cache:
            report = observe(matrix, evidence.Collector(cache))
        (opts.output_dir / "router-upstream-observation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary = render_summary(report)
        (opts.output_dir / "router-upstream-summary.md").write_text(summary, encoding="utf-8")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
                handle.write(summary + "\n")
        print(json.dumps({key: report[key] for key in ("status", "change_count", "failed_source_count")}))
        return 1 if report["failures"] else 0
    except API_ERRORS:
        print('{"status":"failed","error_code":"invalid_baseline_or_output"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
