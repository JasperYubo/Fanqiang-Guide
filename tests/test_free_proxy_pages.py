"""Reader-page boundaries: dated archives, source identity, and stale observations."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_free_proxy_pages as pages


def fixture():
    url = "https://raw.githubusercontent.com/Example/Feed/main/sub"
    now = "2026-09-11T18:00:00Z"
    manifest = {"schema_version": 1, "sources": [{
        "id": "example", "name": "Example", "repository": "https://github.com/Example/Feed",
        "category": "subscription", "description": "Public subscriptions.",
        "feeds": [{"id": "example-sub", "label": "订阅文件", "format": "plain_uri", "url": url}]}]}
    row = {"source_id": "example", "url": url, "format": "plain_uri", "checked_at": now,
           "status": "ok", "last_success_at": now, "content_changed_at": now,
           "sha256": "a" * 64, "byte_count": 100, "valid_count": 3, "unique_count": 2,
           "duplicate_count": 1, "rejected_count": 0, "protocol_counts": {"vless": 2}, "error_code": None}
    state = {"schema_version": 1, "last_run": {"checked_at": now, "feed_count": 1, "ok_count": 1, "error_count": 0},
             "feeds": {"example-sub": row}}
    return manifest, state


class DatedPagesTests(unittest.TestCase):
    def test_day_uses_beijing_date_and_preserves_source_links(self):
        manifest, state = fixture()
        date, page = pages.render_day(manifest, state)
        self.assertEqual(date, "2026-09-12")
        self.assertIn("2026-09-12 02:00", page)
        self.assertIn(manifest["sources"][0]["feeds"][0]["url"], page)
        self.assertIn("| 2 |", page)
        for internal in ("GITHUB_TOKEN", "Run workflow", "Actions", "sha256"):
            self.assertNotIn(internal, page)
        self.assertIn("尚未实测", page)

    def test_index_is_newest_first_and_ignores_unrelated_names(self):
        names = ["2026-09-11.md", "2025-12-31.md", "2026-09-12.md", "README.md", "2026-02-30.md", "notes.md"]
        self.assertEqual(pages.valid_dates(names), ["2026-09-12", "2026-09-11", "2025-12-31"])
        rendered = pages.render_index(names)
        self.assertLess(rendered.index("- [2026-09-12]"), rendered.index("- [2026-09-11]"))

    def test_new_day_keeps_old_files_and_same_day_does_not_duplicate(self):
        manifest, state = fixture()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            prior = folder / "2026-09-11.md"
            prior.write_text("Existing historical page", encoding="utf-8")
            pages.write_pages(manifest, state, folder)
            saved = (folder / "2026-09-12.md").read_bytes()
            pages.write_pages(manifest, state, folder)
            self.assertEqual(prior.read_text(encoding="utf-8"), "Existing historical page")
            self.assertEqual((folder / "2026-09-12.md").read_bytes(), saved)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["2026-09-11.md", "2026-09-12.md", "README.md"])

    def test_changed_source_url_is_rejected_before_writing(self):
        manifest, state = fixture()
        state["feeds"]["example-sub"]["url"] = "https://raw.githubusercontent.com/Example/Other/main/sub"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                pages.write_pages(manifest, state, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_all_failed_sources_do_not_create_a_fresh_day(self):
        manifest, state = fixture()
        state["last_run"].update(ok_count=0, error_count=1)
        state["feeds"]["example-sub"].update(status="error", error_code="network_error")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                pages.write_pages(manifest, state, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_partial_failure_is_not_listed_as_a_current_subscription(self):
        manifest, state = fixture()
        source = copy.deepcopy(manifest["sources"][0])
        source.update(id="failed", name="Failed source", repository="https://github.com/Example/Failed")
        source["feeds"][0]["id"] = "failed-sub"
        source["feeds"][0]["url"] = "https://raw.githubusercontent.com/Example/Failed/main/sub"
        manifest["sources"].append(source)
        row = copy.deepcopy(state["feeds"]["example-sub"])
        row["url"] = source["feeds"][0]["url"]
        row.update(source_id="failed", status="error", error_code="network_error", last_success_at="2026-09-10T18:00:00Z",
                   content_changed_at="2026-09-10T18:00:00Z")
        state["feeds"]["failed-sub"] = row
        state["last_run"].update(feed_count=2, error_count=1)
        date, page = pages.render_day(manifest, state)
        self.assertEqual(page.count("[订阅文件]("), 1)
        self.assertIn("2026-09-11 02:00", page)
        self.assertIn("本次暂未更新的来源", page)

    def test_cell_escapes_markdown_and_html(self):
        text = pages.cell('Name | [fake](https://evil.test)\n<img src="x">')
        self.assertNotIn("|", text)
        self.assertNotIn("[fake]", text)
        self.assertNotIn("<img", text)
        self.assertNotIn("\n", text)


if __name__ == "__main__":
    unittest.main()
