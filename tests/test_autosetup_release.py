"""A release cannot mix an old downloadable book with a new MCP contract."""
import importlib.util
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("setup_release_checks", ROOT / "developer/check_apps.py")
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)

class SetupReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.release=Path(self.temp.name)
        contract=runpy.run_path(str(ROOT/"apps/lookup/runtime/setup_book.py"))
        self.manifest=contract["setup_book_manifest"]()
        raw=contract["BOOK_PATH"].read_bytes()
        for relative in ("lookup/books/fanqiang-autosetup-v2.1.ilang.md","site/ai/books/fanqiang-autosetup-v2.1.ilang.md"):
            p=self.release/relative
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(raw)
        (self.release/"site/ai/books/autosetup.json").write_text(json.dumps(self.manifest))
        for relative in ("site/ai/index.html","site/ai/index.md","site/ai/index.ilang","site/ai/skills/library-lookup/SKILL.md","site/llms.txt"):
            p=self.release/relative
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text("fanqiang://books/autosetup fanqiang-autosetup-v2.1.ilang.md")
        for relative in ("lookup/server-card.json","site/.well-known/mcp/server-card.json"):
            p=self.release/relative
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps({"serverInfo":{"version":"2.1.0"},"capabilities":{"tools":{},"resources":{},"prompts":{}},"setupBook":self.manifest,"books":contract["book_catalog"](),"answerRules":contract["answer_rules_manifest"]()}))


        def put(relative, raw):
            path = self.release / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        for book_id, entry in contract["BOOK_REGISTRY"].items():
            put("site/ai/books/" + book_id + ".json", json.dumps(contract["book_manifest"](book_id)).encode())
            for prefix in ("lookup/books/", "site/ai/books/"):
                put(prefix + entry["evidence_path"].name, entry["evidence_path"].read_bytes())
                put(prefix + entry["path"].name, entry["path"].read_bytes())
        legacy = ROOT / "apps/lookup/runtime/books/fanqiang-autosetup-v1.1.ilang.md"
        put("site/ai/books/" + legacy.name, legacy.read_bytes())
        legacy_v2 = ROOT / "apps/lookup/runtime/books/fanqiang-autosetup-v2.0.ilang.md"
        put("site/ai/books/" + legacy_v2.name, legacy_v2.read_bytes())
        legacy_v2_evidence = legacy_v2.with_name("fanqiang-autosetup-v2.0.evidence.json")
        put("site/ai/books/" + legacy_v2_evidence.name, legacy_v2_evidence.read_bytes())
        put("site/ai/books/index.json", json.dumps(contract["book_catalog"]()).encode())
        rules = contract["answer_rules_text"]()
        for relative in ("lookup/answer-rules.ilang", "site/ai/answer-rules.ilang"):
            put(relative, rules.encode())
        for ext in ("html", "md", "ilang"):
            path = self.release / ("site/ai/index." + ext)
            path.write_text(path.read_text() + "\n" + rules)
        for target, source in {
            "lookup/source-freshness.json": "data/source-freshness.json",
            "lookup/library.json": "apps/lookup/runtime/library.json",
            "lookup/router-compatibility.json": "data/router-compatibility.json",
            "site/data/router-compatibility.json": "data/router-compatibility.json",
            "site/data/source-freshness.json": "data/source-freshness.json",
            "lookup/client-comparison.json": "apps/site/content/client-comparison-v1.3-2026-09-12.json",
            "lookup/sync_source_freshness.py": "developer/sync_source_freshness.py",
        }.items():
            put(target, (ROOT / source).read_bytes())

    def test_consistent_package_passes(self):
        self.assertEqual(checks.validate_autosetup_release(ROOT,self.release),[])

    def test_snapshot_must_bind_packaged_library_bytes(self):
        path=self.release/"lookup/library.json"
        path.write_bytes(path.read_bytes().replace(b"\n",b"\r\n"))
        self.assertIn("lookup/source-freshness.json:invalid_or_wrong_library_binding",
                      checks.validate_autosetup_release(ROOT,self.release))

    def test_stale_download_is_rejected(self):
        (self.release/"site/ai/books/fanqiang-autosetup-v2.1.ilang.md").write_text("old book")
        self.assertIn("site/ai/books/fanqiang-autosetup-v2.1.ilang.md:canonical_book_mismatch",checks.validate_autosetup_release(ROOT,self.release))

    def test_metadata_cannot_claim_execution(self):
        self.manifest["execution_status"]="complete"
        (self.release/"site/ai/books/autosetup.json").write_text(json.dumps(self.manifest))
        self.assertIn("site/ai/books/autosetup.json:contract_mismatch",checks.validate_autosetup_release(ROOT,self.release))

    def test_missing_runtime_book_is_rejected(self):
        (self.release/"lookup/books/fanqiang-autosetup-v2.1.ilang.md").unlink()
        self.assertIn("autosetup:invalid_release_contract",checks.validate_autosetup_release(ROOT,self.release))

    def test_old_discovery_is_rejected(self):
        (self.release/"site/llms.txt").write_text("lookup only")
        self.assertIn("site/llms.txt:setup_discovery_missing",checks.validate_autosetup_release(ROOT,self.release))

    def test_wrong_discovery_fingerprint_is_rejected(self):
        for relative in ("lookup/server-card.json","site/.well-known/mcp/server-card.json"):
            p=self.release/relative
            card=json.loads(p.read_text())
            card["setupBook"]["sha256"]="0"*64
            p.write_text(json.dumps(card))
        failures=checks.validate_autosetup_release(ROOT,self.release)
        self.assertIn("lookup/server-card.json:setup_capabilities_missing",failures)
        self.assertIn("site/.well-known/mcp/server-card.json:setup_capabilities_missing",failures)

    def test_truncated_visible_answer_rules_are_rejected(self):
        path = self.release / "site/ai/index.html"
        path.write_text(path.read_text().replace("Do not request passwords", "Truncated"))
        self.assertIn("site/ai/index.html:answer_rules_incomplete", checks.validate_autosetup_release(ROOT, self.release))

    def test_old_version_download_must_remain_exact(self):
        path = self.release / "site/ai/books/fanqiang-autosetup-v1.1.ilang.md"
        path.write_text("replaced old book")
        self.assertIn("autosetup:legacy_download_mismatch", checks.validate_autosetup_release(ROOT, self.release))

    def test_freshness_runtime_copy_must_match_reviewed_input(self):
        (self.release / "lookup/source-freshness.json").write_text("{}")
        self.assertIn("lookup/source-freshness.json:source_input_mismatch", checks.validate_autosetup_release(ROOT, self.release))

    def test_router_matrix_copy_must_match_source(self):
        (self.release / "lookup/router-compatibility.json").write_text("{}")
        self.assertIn("lookup/router-compatibility.json:source_input_mismatch", checks.validate_autosetup_release(ROOT,self.release))

    def test_merlin_book_cannot_be_truncated(self):
        (self.release / "site/ai/books/fanqiang-merlin-v1.0.ilang.md").write_text("partial")
        self.assertIn("site/ai/books/fanqiang-merlin-v1.0.ilang.md:canonical_book_mismatch", checks.validate_autosetup_release(ROOT,self.release))

    def test_previous_v2_download_must_remain_exact(self):
        (self.release / "site/ai/books/fanqiang-autosetup-v2.0.ilang.md").write_text("new book at old URL")
        self.assertIn("autosetup:legacy_v2_download_mismatch", checks.validate_autosetup_release(ROOT,self.release))
        (self.release / "site/ai/books/fanqiang-autosetup-v2.0.evidence.json").write_text("{}")
        self.assertIn("autosetup:legacy_v2_evidence_mismatch", checks.validate_autosetup_release(ROOT,self.release))
