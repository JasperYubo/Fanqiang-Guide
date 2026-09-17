"""End-to-end offline checks of the maintainer's full snapshot rebuild."""

from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rebuild_library", ROOT / "tools/rebuild_library.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
STAMP = builder.STAMP
FAKE_ID = "zz-rebuild-fixture"


def file_hashes(root):
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def fake_entity():
    url = "https://github.com/example/rebuild-fixture"
    return {
        "id": FAKE_ID, "name": "Temporary rebuild fixture", "aliases": [], "kind": "client",
        "summary": "Synthetic offline reconstruction fixture.", "platforms": [], "ecosystems": [],
        "official_urls": [url], "repository": url, "discovery_sources": [], "tags": [],
        "verification": {"status": "primary_reviewed", "checked_at": "2026-09-12",
                         "notes": "Synthetic test only.", "reviewed_fields": ["name", "kind", "summary", "official_urls"],
                         "evidence_urls": [url]},
        "relations": [{"predicate": "uses_core", "target_name": "Mihomo", "evidence_url": url}],
    }


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fanqiang-rebuild-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        shutil.copytree(ROOT / "tools/source", self.source)
        self.output = self.base / "output"
        self.output.mkdir()
        self.state = self.base / "upstream.json"
        shutil.copyfile(ROOT / "data/upstream.json", self.state)

    def rebuild(self):
        return builder.rebuild(self.source, self.output, self.state)

    def seed_published_outputs(self):
        for name in ("export", "knowledge"):
            shutil.copytree(ROOT / name, self.output / name)
        for name in ("CATALOG.md", "UPDATES.md", "config/upstream-repositories.json"):
            target = self.output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)

    def source_rows(self):
        return read_json(self.source / "github-extra.json")

    def write_source_rows(self, rows):
        (self.source / "github-extra.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def test_current_snapshot_rebuild_is_exact_and_database_is_not_replaced(self):
        self.seed_published_outputs()
        before = file_hashes(self.output)
        database = self.output / "export" / ("library-" + STAMP + ".sqlite")
        original_time = database.stat().st_mtime_ns
        state_before = self.state.read_bytes()
        report = self.rebuild()
        self.assertEqual(report["entity_count"], 310)
        self.assertEqual(report["repository_count"], 212)
        self.assertEqual(report["excluded_count"], 98)
        self.assertEqual(report["changed"], [])
        self.assertEqual(report["removed_cards"], [])
        self.assertEqual(file_hashes(self.output), before)
        self.assertEqual(database.stat().st_mtime_ns, original_time)
        self.assertEqual(self.state.read_bytes(), state_before)
        self.assertEqual(builder.database_snapshot(database), builder.database_snapshot(ROOT / "export" / database.name))

    def test_add_then_remove_entity_updates_every_relevant_view(self):
        self.rebuild()
        baseline = file_hashes(self.output)
        baseline_database = builder.database_snapshot(self.output / "export" / ("library-" + STAMP + ".sqlite"))
        original = self.source_rows()
        self.write_source_rows(original + [fake_entity()])
        added = self.rebuild()
        self.assertEqual((added["entity_count"], added["repository_count"]), (311, 213))
        export = self.output / "export"
        library = read_json(export / ("library-" + STAMP + ".json"))
        self.assertIn(FAKE_ID, {row["id"] for row in library})
        for filename in ("rag-all", "rag-reviewed"):
            self.assertIn(FAKE_ID, {row["entity_id"] for row in builder.jsonl(export / (filename + "-" + STAMP + ".jsonl"))})
        self.assertNotIn(FAKE_ID, {row["entity_id"] for row in builder.jsonl(export / ("review-queue-" + STAMP + ".jsonl"))})
        relations = [row for row in builder.jsonl(export / ("relationships-" + STAMP + ".jsonl")) if row["source_id"] == FAKE_ID]
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["target_id"], "mihomo")
        self.assertTrue(any(FAKE_ID in row["referenced_by"] for row in builder.jsonl(export / ("sources-" + STAMP + ".jsonl"))))
        for name in ("CATALOG.md", "UPDATES.md", "export/INDEX-" + STAMP + ".md"):
            self.assertIn(FAKE_ID, (self.output / name).read_text(encoding="utf-8"))
        card = export / "cards" / (FAKE_ID + "-" + STAMP + ".md")
        self.assertTrue(card.is_file())
        mapping = read_json(self.output / "config/upstream-repositories.json")
        self.assertTrue(any(FAKE_ID in row["entity_ids"] for row in mapping["repositories"]))
        with closing(sqlite3.connect((export / ("library-" + STAMP + ".sqlite")).as_uri() + "?mode=ro", uri=True)) as connection:
            self.assertIn((FAKE_ID,), connection.execute("SELECT id FROM search WHERE search MATCH 'rebuild'").fetchall())
        # A reference-only addition must move to the review queue, not remain reviewed.
        reference = fake_entity()
        reference["verification"]["status"] = "reference_only"
        self.write_source_rows(original + [reference])
        self.rebuild()
        self.assertIn(FAKE_ID, {row["entity_id"] for row in builder.jsonl(export / ("review-queue-" + STAMP + ".jsonl"))})
        self.assertNotIn(FAKE_ID, {row["entity_id"] for row in builder.jsonl(export / ("rag-reviewed-" + STAMP + ".jsonl"))})
        self.write_source_rows(original)
        removed = self.rebuild()
        self.assertEqual(removed["entity_count"], 310)
        self.assertEqual(removed["removed_cards"], [card.name])
        after = file_hashes(self.output)
        db_name = "export/library-" + STAMP + ".sqlite"
        self.assertEqual({k: v for k, v in baseline.items() if k != db_name}, {k: v for k, v in after.items() if k != db_name})
        self.assertEqual(builder.database_snapshot(export / ("library-" + STAMP + ".sqlite")), baseline_database)

    def test_missing_each_required_input_fails_before_touching_output(self):
        self.seed_published_outputs()
        before = file_hashes(self.output)
        for name in list(builder.ENTITY_INPUTS) + [builder.MODEL_INPUT] + ["knowledge/" + name for name in builder.KNOWLEDGE_INPUTS]:
            path = self.source / name
            original = path.read_bytes()
            with self.subTest(name=name):
                path.unlink()
                try:
                    with self.assertRaisesRegex(ValueError, "missing_required_input"):
                        self.rebuild()
                    self.assertEqual(file_hashes(self.output), before)
                finally:
                    path.write_bytes(original)

    def test_invalid_source_or_missing_observation_preserves_outputs(self):
        self.seed_published_outputs()
        before = file_hashes(self.output)
        path = self.source / "github-extra.json"
        original = path.read_bytes()
        path.write_bytes(b'[{"id":"one","id":"two"}]')
        with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
            self.rebuild()
        self.assertEqual(file_hashes(self.output), before)
        path.write_bytes(original)
        self.state.unlink()
        with self.assertRaises(FileNotFoundError):
            self.rebuild()
        self.assertEqual(file_hashes(self.output), before)

    def test_bannedbook_card_keeps_two_named_sources_after_full_rebuild(self):
        self.rebuild()
        path = self.output / "export/cards" / ("bannedbook-fanqiang-" + STAMP + ".md")
        sources = path.read_text(encoding="utf-8").split("## 来源\n\n", 1)[1]
        self.assertEqual(sources, "- [官方仓库 · bannedbook/fanqiang](https://github.com/bannedbook/fanqiang)\n"
                         "- [已阅读的 README](https://raw.githubusercontent.com/bannedbook/fanqiang/HEAD/README.md)\n")
        self.assertEqual(path.read_bytes(), (ROOT / "export/cards" / path.name).read_bytes())

    def test_current_manuscripts_are_the_only_knowledge_inputs(self):
        note = self.source / "knowledge" / builder.KNOWLEDGE_INPUTS[0]
        revised = note.read_bytes() + "\n维护者增加的离线测试段落。\n".encode("utf-8")
        note.write_bytes(revised)
        (self.source / "knowledge/not-an-input.md").write_text("Do not publish arbitrary files.", encoding="utf-8")
        self.rebuild()
        self.assertEqual((self.output / "knowledge" / note.name).read_bytes(), revised)
        self.assertEqual({p.name for p in (self.output / "knowledge").iterdir()}, set(builder.KNOWLEDGE_INPUTS))

    def test_resolved_source_path_cannot_escape_input_directory(self):
        outside = self.base / "outside.json"
        outside.write_bytes((self.source / "baseline.json").read_bytes())
        target = self.source / "baseline.json"
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            # Simulate a symlink/reparse target without requiring Windows link privileges.
            return outside if path == target else original_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", autospec=True, side_effect=resolve):
            with self.assertRaisesRegex(ValueError, "input_outside_source"):
                self.rebuild()
        self.assertEqual(list(self.output.iterdir()), [])

    def test_cli_is_cwd_independent_and_leaves_daily_pages_and_state_untouched(self):
        protected = {"README.md": b"reader-entry\n", "free-proxies/2030-01-01.md": b"day-one\n", "free-proxies/README.md": b"date-index\n",
                     "data/upstream.json": b"must-not-write\n", "data/free-proxy-sources.json": b"must-not-write-feeds\n"}
        for name, content in protected.items():
            path = self.output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        result = subprocess.run([sys.executable, str(ROOT / "tools/rebuild_library.py"), "--source-dir", str(self.source),
                                 "--output-dir", str(self.output), "--state", str(self.state)],
                                cwd=self.base, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["entity_count"], 310)
        for name, content in protected.items():
            self.assertEqual((self.output / name).read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
