"""Offline tests of review boundaries, publisher failures, and cache freshness."""
import copy
import hashlib
from contextlib import redirect_stdout
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("router_watch", ROOT / "scripts/check_router_upstream.py")
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)
A, B = "a" * 40, "b" * 40


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class FakeCollector:
    def __init__(self, content, fail=()):
        self.content, self.fail = content, set(fail)

    def fetch(self, url, limit=2_000_000):
        if url in self.fail:
            raise ValueError("private-server-error-must-not-appear")
        return self.content[url]


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.raw = {
            "README.md": b"reviewed model table",
            "fancyss/install.sh": b"reviewed installer",
            "packages/version.json.js": json.dumps({"version": "3.5.30", "md5_arm_full": "1" * 32,
                                                      "md5_arm_lite": "2" * 32}).encode(),
        }
        self.matrix = {"fancyss_commit": A, "package_version": "3.5.30", "checked_at": "2026-11-02T00:00:00Z",
                       "not_device_tested": True, "packages": {"arm_full": {}, "arm_lite": {}}, "sources": {}}
        self.content = {}
        for key, path in (("fancyss-readme", "README.md"), ("fancyss-install", "fancyss/install.sh"),
                          ("fancyss-manifest", "packages/version.json.js")):
            url = "https://raw.githubusercontent.com/hq450/fancyss/" + A + "/" + path
            self.content[url] = self.raw[path]
            self.matrix["sources"][key] = {"url": url, "status": "retrieved", "sha256": digest(self.raw[path])}
        self.topic_url = "https://www.koolcenter.com/t/topic/31125.json"
        self.topic = {"title": "102.9_0 release", "views": 100,
                      "post_stream": {"posts": [{"post_number": 1, "updated_at": "2026-10-31T00:00:00Z", "cooked": "<p>Models</p>"}]}}
        self.matrix["sources"]["kool-102-current"] = {"url": self.topic_url, "status": "retrieved",
                                                       "title": self.topic["title"], "post_updated_at": self.topic["post_stream"]["posts"][0]["updated_at"]}
        self.content[self.topic_url] = json.dumps(self.topic).encode()
        self.root_url = "https://fw.koolcenter.com/"
        self.content[self.root_url] = b'<a href="MODEL/">MODEL</a>'
        self.matrix["sources"]["kool-mirror-root"] = {"url": self.root_url, "status": "retrieved", "sha256": digest(self.content[self.root_url])}
        self.tree = {"truncated": False, "tree": [{"path": path, "type": "blob", "sha": str(i + 1) * 40, "size": 100}
                                                  for i, path in enumerate(sorted(watch.CORE | {"packages/fancyss_arm_full.tar.gz", "packages/fancyss_arm_lite.tar.gz"}))]}
        self.current_tree = copy.deepcopy(self.tree)
        self.head = A

    def api(self, url):
        if url == watch.API:
            return {"default_branch": "3.0"}
        if url.endswith("/commits/3.0"):
            return {"sha": self.head}
        if url.endswith("/git/trees/" + self.head + "?recursive=1"):
            return self.current_tree
        if url.endswith("/git/trees/" + A + "?recursive=1"):
            return self.tree
        raise AssertionError(url)

    def run_watch(self, **kwargs):
        return watch.observe(self.matrix, FakeCollector(self.content, kwargs.pop("fail", ())),
                             api=kwargs.pop("api", self.api), checked_at="2026-11-03T00:00:00Z", **kwargs)

    def advance(self):
        self.head = B
        for url, raw in list(self.content.items()):
            if "/" + A + "/" in url:
                self.content[url.replace(A, B)] = raw

    def test_no_change_is_success_and_does_not_mutate_matrix(self):
        before = copy.deepcopy(self.matrix)
        result = self.run_watch()
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["change_count"], 0)
        self.assertFalse(result["review_required"])
        self.assertEqual(self.matrix, before)
        for key in ("device_tested", "compatibility_matrix_modified", "package_archives_downloaded"):
            self.assertFalse(result[key])

    def test_new_commit_and_changed_full_package_require_review(self):
        self.advance()
        full = next(v for v in self.current_tree["tree"] if v["path"].endswith("arm_full.tar.gz"))
        full["sha"] = "c" * 40
        result = self.run_watch()
        self.assertEqual(result["status"], "changes_pending_review")
        self.assertEqual({v["category"] for v in result["changes"]}, {"upstream_commit", "package_blob"})
        self.assertTrue(all(v["status"] == "pending_manual_review" for v in result["changes"]))
        self.assertEqual(self.matrix["fancyss_commit"], A)

    def test_added_and_removed_package_are_visible(self):
        self.advance()
        self.current_tree["tree"] = [v for v in self.current_tree["tree"] if not v["path"].endswith("arm_lite.tar.gz")]
        self.current_tree["tree"].append({"path": "packages/fancyss_newarch_lite.tar.gz", "type": "blob", "sha": "d" * 40, "size": 50})
        changes = self.run_watch()["changes"]
        self.assertEqual(sum(v["category"] == "package_blob" for v in changes), 2)

    def test_readme_manifest_and_release_edits_are_not_compatibility(self):
        self.advance()
        url = next(u for u in self.content if B in u and u.endswith("README.md"))
        self.content[url] = b"new model table"
        self.topic["post_stream"]["posts"][0]["updated_at"] = "2026-11-03T00:00:00Z"
        self.content[self.topic_url] = json.dumps(self.topic).encode()
        result = self.run_watch()
        ids = {v["source_id"] for v in result["changes"]}
        self.assertTrue({"fancyss-readme", "kool-102-current"} <= ids)
        self.assertFalse(result["device_tested"])

    def test_topic_reply_or_view_changes_do_not_alert(self):
        self.topic["views"] = 10000
        self.topic["post_stream"]["posts"].append({"post_number": 2, "cooked": "new reply"})
        self.content[self.topic_url] = json.dumps(self.topic).encode()
        self.assertEqual(self.run_watch()["status"], "unchanged")

    def test_model_root_change_is_pending_even_without_auto_model_join(self):
        self.content[self.root_url] += b'<a href="NEW_MODEL/">NEW_MODEL</a>'
        result = self.run_watch()
        self.assertEqual(result["changes"][0]["source_id"], "kool-mirror-root")
        self.assertEqual(result["changes"][0]["status"], "pending_manual_review")

    def test_publisher_failure_is_unknown_and_preserves_other_results(self):
        result = self.run_watch(fail={self.topic_url})
        self.assertEqual(result["status"], "partial_failure")
        self.assertEqual(result["failed_source_count"], 1)
        self.assertIn("fancyss-manifest", result["observations"])
        self.assertNotIn("private-server-error", json.dumps(result) + watch.render_summary(result))
        self.assertIn("unknown", watch.render_summary(result))

    def test_github_failure_never_claims_stale_head_is_fresh(self):
        def broken(url):
            raise URLError("private-token-in-upstream-error")
        result = self.run_watch(api=broken)
        self.assertEqual(result["status"], "partial_failure")
        self.assertNotIn("fancyss-upstream", result["observations"])
        self.assertNotIn("fancyss-readme", result["observations"])
        self.assertIn("kool-102-current", result["observations"])
        self.assertNotIn("private-token", json.dumps(result))

    def test_truncated_tree_and_invalid_manifest_fail_closed(self):
        self.current_tree["truncated"] = True
        self.assertEqual(self.run_watch()["status"], "partial_failure")
        self.current_tree["truncated"] = False
        url = next(u for u in self.content if u.endswith("version.json.js"))
        self.content[url] = b'{"version":"3.6.0","md5_arm_full":"bad"}'
        result = self.run_watch()
        self.assertEqual(result["status"], "partial_failure")
        self.assertNotIn("fancyss-manifest", result["observations"])

    def test_missing_reviewed_package_tree_fails_instead_of_unchanged(self):
        self.current_tree["tree"] = [v for v in self.current_tree["tree"] if not v["path"].endswith("arm_lite.tar.gz")]
        self.assertEqual(self.run_watch()["status"], "partial_failure")

    def test_cli_writes_failure_artifacts_and_preserves_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "matrix.json"
            base.write_text(json.dumps(self.matrix))
            original = base.read_bytes()
            report = self.run_watch(fail={self.topic_url})
            out = Path(temp) / "report"
            with patch.object(watch, "observe", return_value=report), patch.dict(watch.os.environ, {}, clear=True), redirect_stdout(io.StringIO()) as captured:
                code = watch.main(["--baseline", str(base), "--output-dir", str(out)])
            self.assertEqual(code, 1)
            self.assertEqual(base.read_bytes(), original)
            self.assertEqual(json.loads((out / "router-upstream-observation.json").read_text())["status"], "partial_failure")
            self.assertIn("unknown", (out / "router-upstream-summary.md").read_text())
            self.assertNotIn("private-server-error", captured.getvalue())

    def test_topic_missing_first_post_is_failure(self):
        self.topic["post_stream"]["posts"][0]["post_number"] = 2
        self.content[self.topic_url] = json.dumps(self.topic).encode()
        self.assertEqual(self.run_watch()["status"], "partial_failure")


class FakeResponse:
    def __init__(self, raw, url):
        self.raw, self.url = raw, url
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, limit):
        return self.raw[:limit]


class CacheTests(unittest.TestCase):
    def test_online_refreshes_existing_cache_offline_keeps_observation(self):
        url = "https://fw.koolcenter.com/"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / (digest(url.encode()) + ".bin")
            path.write_bytes(b"old")
            with patch.object(watch.evidence, "urlopen", return_value=FakeResponse(b"fresh", url)) as opening:
                self.assertEqual(watch.evidence.Collector(temp).fetch(url), b"fresh")
                opening.assert_called_once()
            stamp = watch.evidence.OBSERVED_AT[url]
            with patch.object(watch.evidence, "urlopen", side_effect=AssertionError("offline network")):
                self.assertEqual(watch.evidence.Collector(temp, offline=True).fetch(url), b"fresh")
            self.assertEqual(watch.evidence.OBSERVED_AT[url], stamp)

    def test_online_failure_does_not_claim_cached_bytes_are_current(self):
        url = "https://fw.koolcenter.com/"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / (digest(url.encode()) + ".bin")
            path.write_bytes(b"old")
            with patch.object(watch.evidence, "urlopen", side_effect=URLError("offline")):
                with self.assertRaisesRegex(ValueError, "Source unavailable"):
                    watch.evidence.Collector(temp).fetch(url)
            self.assertEqual(path.read_bytes(), b"old")

    def test_github_rejects_other_hosts_and_redirects(self):
        with self.assertRaises(ValueError):
            watch.github_json("https://example.com/token-sink")
        with self.assertRaises(ValueError):
            watch.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com")


if __name__ == "__main__":
    unittest.main()
