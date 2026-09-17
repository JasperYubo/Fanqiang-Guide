"""Offline tests of coverage, observation semantics, and safe public rendering."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_catalog", ROOT / "scripts/build_catalog.py")
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


def entity(entity_id="example", repository="https://github.com/Example/project"):
    return {
        "id": entity_id, "name": "Example", "kind": "client", "repository": repository,
        "platforms": ["Windows"], "verification": {"status": "reference_only"},
        "source_claims": {"version": "UNVERIFIED-SOURCE-VERSION"},
    }


def observation(repository_status="ok", release_status="ok"):
    return {
        "checked_at": "2026-09-12T01:00:00Z", "repository_status": repository_status,
        "repository": {"full_name": "Example/project", "html_url": "https://github.com/Example/project",
                       "archived": False, "disabled": False, "pushed_at": "2026-09-01T00:00:00Z", "default_branch": "main"},
        "repository_last_success_at": "2026-09-01T00:00:00Z",
        "release_status": release_status,
        "release": {"tag_name": "v1.0+test", "html_url": "https://github.com/Example/project/releases/tag/v1.0%2Btest",
                    "published_at": "2026-08-31T00:00:00Z"},
        "release_last_success_at": "2026-09-01T00:00:00Z", "error_code": None,
    }


def state(row=None):
    return {"schema_version": 1, "last_run": {"checked_at": "2026-09-12T01:00:00Z",
            "repository_count": 1, "ok_count": 1, "error_count": 0},
            "repositories": {"Example/project": row or observation()}}


def render_one(row=None):
    library = [entity()]
    return catalog.render(library, catalog.make_manifest(library), state(row))


class ManifestTests(unittest.TestCase):
    def test_strict_roots_and_optional_suffixes(self):
        for url in ("https://github.com/Owner/project", "https://github.com/Owner/project/",
                    "https://github.com/Owner/project.git", "https://github.com/Owner/project.git/"):
            with self.subTest(url=url):
                self.assertEqual(catalog.github_root(url), "Owner/project")
        invalid = ["http://github.com/o/r", "https://github.com/o/r/tree/main", "https://github.com/o/r?x=1",
                   "https://github.com/o/r#readme", "https://u@github.com/o/r", "https://github.com:443/o/r",
                   "https://github.com.evil/o/r", "https://github.com/o/r\n", "https://github.com/o/r\\x",
                   "https://github.com/o/r%2Fs", "https://github.com/o/.git", "https://github.com/o/..",
                   "https://github.com/-bad/r", "https://github.com/a_b/r", " github.com/o/r", None, 7]
        for url in invalid:
            with self.subTest(url=url):
                self.assertIsNone(catalog.github_root(url))
        self.assertEqual(catalog.github_root("https://github.com/wangyu-/udp2raw"), "wangyu-/udp2raw")

    def test_deduplicates_case_insensitively_and_preserves_ids(self):
        library = [entity("two", "https://github.com/example/PROJECT.git/"), entity("one")]
        manifest = catalog.make_manifest(library)
        self.assertEqual(len(manifest["repositories"]), 1)
        self.assertEqual(manifest["repositories"][0]["entity_ids"], ["one", "two"])
        catalog.validate_manifest(library, manifest)

    def test_no_inference_from_other_urls(self):
        library = [entity("missing", None), entity("subtree", "https://github.com/o/r/tree/main"),
                   entity("gitlab", "https://gitlab.com/o/r")]
        library[0]["official_urls"] = ["https://github.com/o/r"]
        library[0]["discovery_sources"] = ["https://github.com/o/r"]
        manifest = catalog.make_manifest(library)
        self.assertEqual(manifest["repositories"], [])
        self.assertEqual({x["entity_id"]: x["reason"] for x in manifest["excluded"]}, {
            "missing": "missing_repository", "subtree": "invalid_repository_mapping", "gitlab": "non_github_repository"})

    def test_exact_coverage_rejects_missing_duplicate_extra_or_wrong_mapping(self):
        library = [entity()]
        base = catalog.make_manifest(library)
        variants = []
        missing = copy.deepcopy(base)
        missing["repositories"] = []
        variants.append(missing)
        duplicate = copy.deepcopy(base)
        duplicate["repositories"][0]["entity_ids"].append("example")
        variants.append(duplicate)
        extra = copy.deepcopy(base)
        extra["excluded"].append({"entity_id": "other", "reason": "missing_repository"})
        variants.append(extra)
        wrong = copy.deepcopy(base)
        wrong["repositories"][0]["full_name"] = "Other/project"
        variants.append(wrong)
        for manifest in variants:
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                catalog.validate_manifest(library, manifest)


class ObservationTests(unittest.TestCase):
    def test_stale_values_are_dated_and_not_silently_current(self):
        row = observation("error", "error")
        row["repository"]["archived"] = True
        row["error_code"] = "network_error"
        first, second = render_one(row)
        for text in (first, second):
            self.assertIn("本次未能取得项目信息", text)
            self.assertIn("本次版本查询失败；以下为旧版本信息", text)
            self.assertIn("以下为旧信息：已归档", text)
            self.assertIn("上次查到 2026-09-01 08:00（北京时间）", text)
            self.assertIn("2026-09-12 09:00（北京时间）", text)
            self.assertNotIn("GitHub 未查到正式发布版", text)

    def test_none_is_not_fetch_failure_and_does_not_display_retained_release(self):
        text = catalog.release_observation(observation(release_status="none"))
        self.assertIn("GitHub 未查到正式发布版", text)
        self.assertNotIn("v1.0", text)
        self.assertNotIn("失败", text)

    def test_no_previous_release_and_not_checked_are_explicit(self):
        row = observation("unavailable", "not_checked")
        row["repository"] = row["release"] = None
        row["repository_last_success_at"] = row["release_last_success_at"] = None
        text = "\n".join(render_one(row))
        self.assertIn("暂时无法查看项目（未确认是否删除）", text)
        self.assertIn("本次未查询版本；暂无旧版本记录", text)
        row["release_status"] = "error"
        self.assertIn("本次版本查询失败；暂无旧版本记录", catalog.release_observation(row))

    def test_success_never_promotes_review_or_imports_source_version(self):
        text = "\n".join(render_one())
        self.assertIn("仅有目录介绍，来源待核实", text)
        self.assertNotIn("UNVERIFIED-SOURCE-VERSION", text)
        self.assertIn("未归档", text)
        self.assertIn("v1.0%2Btest", text)

    def test_updates_show_renamed_returned_repository_and_push_time(self):
        row = observation()
        row["repository"]["html_url"] = "https://github.com/NewOwner/new-project"
        updates = render_one(row)[1]
        self.assertIn("项目来源：[NewOwner/new-project](<https://github.com/NewOwner/new-project>)", updates)
        self.assertIn("最近提交代码 2026-09-01 08:00（北京时间）", updates)
        row["repository_status"] = "error"
        updates = render_one(row)[1]
        self.assertIn("旧信息来源", updates)
        self.assertIn("旧信息中的代码提交时间", updates)
        row["repository"]["html_url"] = "https://evil.test/payload"
        self.assertNotIn("https://evil.test", render_one(row)[1])

    def test_empty_platforms_do_not_claim_unsupported(self):
        library = [entity()]
        library[0]["platforms"] = []
        text = catalog.render(library, catalog.make_manifest(library), state())[0]
        self.assertIn("未记录或不适用", text)
        self.assertNotIn("不支持", text)

    def test_markdown_injection_stays_plain_single_cell_text(self):
        payload = 'x|y\n[click](javascript:alert(1)) <script>bad</script> `code` ![img](evil)'
        library = [entity()]
        library[0]["name"] = payload
        library[0]["platforms"] = [payload]
        row = observation("error", "error")
        row["release"]["tag_name"] = payload
        row["release"]["html_url"] = "javascript:alert(1)"
        row["error_code"] = payload
        row["checked_at"] = payload
        first, second = catalog.render(library, catalog.make_manifest(library), state(row))
        for text in (first, second):
            self.assertNotIn("<script>", text)
            self.assertNotIn("`code`", text)
            self.assertNotIn("](javascript:", text)
            self.assertNotIn("[img](evil)", text)
            self.assertIn("&#124;", text)
            self.assertIn("&lt;script&gt;", text)
            self.assertIn("版本链接暂不可用", text)
        rows = [line for line in first.splitlines() if line.startswith("| ")]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(line.count("|") == 6 for line in rows))

    def test_release_link_validation(self):
        valid = "https://github.com/Owner/repo/releases/tag/v1.0%2B1"
        self.assertEqual(catalog.release_url(valid), valid)
        for url in ("http://github.com/o/r/releases/tag/v1", "https://evil.test/o/r/releases/tag/v1",
                    "https://github.com@evil.test/o/r/releases/tag/v1", "https://github.com/o/r/releases/tag/v1%0Aevil",
                    "https://github.com/o/r/releases/tag/v1\n", "https://github.com/o/r/releases/tag/<script>",
                    "https://github.com/o/r/releases/tag/v1?x=1", "https://github.com/o/r", "javascript:alert(1)"):
            with self.subTest(url=url):
                self.assertIsNone(catalog.release_url(url))

    def test_invalid_schemas_fail_before_rendering(self):
        library = [entity()]
        manifest = catalog.make_manifest(library)
        cases = [{"schema_version": True, "repositories": {}}, {"schema_version": 1, "repositories": []}]
        bad = state()
        bad["repositories"]["Example/project"]["release_status"] = "unknown"
        cases.append(bad)
        bad_count = state()
        bad_count["last_run"]["error_count"] = 2
        cases.append(bad_count)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                catalog.render(library, manifest, value)
        with self.assertRaises(ValueError):
            catalog.make_manifest([entity(), entity()])


class FullCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = catalog.read_json(ROOT / catalog.LIBRARY_PATH)
        cls.manifest = catalog.read_json(ROOT / catalog.MANIFEST_PATH)
        cls.empty_state = {"schema_version": 1, "last_run": None, "repositories": {}}

    def test_all_310_cards_and_known_exclusions(self):
        catalog.validate_manifest(self.library, self.manifest)
        self.assertEqual(len(self.library), 310)
        self.assertEqual(len(self.manifest["repositories"]), 212)
        self.assertEqual(len(self.manifest["excluded"]), 98)
        first, second = catalog.render(self.library, self.manifest, self.empty_state)
        self.assertEqual(first.count("](export/cards/"), 310)
        for item in self.library:
            path = "export/cards/" + item["id"] + catalog.CARD_SUFFIX
            self.assertTrue((ROOT / path).is_file())
            self.assertEqual(first.count("](" + path + ")"), 1)
        reasons = {x["entity_id"]: x["reason"] for x in self.manifest["excluded"]}
        self.assertEqual(reasons["mwan3"], "invalid_repository_mapping")
        self.assertEqual(reasons["ouinet"], "non_github_repository")
        self.assertEqual(reasons["clash-net"], "missing_repository")
        self.assertIn("暂未取得版本信息", second)

    def test_reader_navigation_has_stable_category_anchors(self):
        first, second = catalog.render(self.library, self.manifest, self.empty_state)
        for anchor in ("clients", "cores", "protocols", "concepts", "router-firmware", "router-plugins", "dns", "rules"):
            self.assertEqual(first.count('<a id="' + anchor + '"></a>'), 1)
        for text in (first, second):
            for internal_term in ("元数据", "根仓库", "映射", "状态文件", "repository", "JSON", "SQLite", "Actions"):
                self.assertNotIn(internal_term, text)

    def test_determinism_including_input_order(self):
        original = catalog.render(self.library, self.manifest, self.empty_state)
        reordered = copy.deepcopy(self.manifest)
        reordered["repositories"].reverse()
        reordered["excluded"].reverse()
        for row in reordered["repositories"]:
            row["entity_ids"].reverse()
        self.assertEqual(original, catalog.render(list(reversed(self.library)), reordered, self.empty_state))
        self.assertEqual(self.manifest, catalog.make_manifest(list(reversed(self.library))))

    def test_cli_missing_state_and_deterministic_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            command = [sys.executable, str(ROOT / "scripts/build_catalog.py"), "--state", str(base / "absent.json"),
                       "--catalog-output", str(base / "catalog.md"), "--updates-output", str(base / "updates.md")]
            first = subprocess.run(command, cwd=directory, check=True, capture_output=True)
            saved = [(base / name).read_bytes() for name in ("catalog.md", "updates.md")]
            second = subprocess.run(command, cwd=directory, check=True, capture_output=True)
            self.assertEqual(first.stdout, second.stdout)
            self.assertEqual(saved, [(base / name).read_bytes() for name in ("catalog.md", "updates.md")])
            self.assertNotIn(b"\r\n", saved[0])
            self.assertIn("暂无版本记录", saved[0].decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
