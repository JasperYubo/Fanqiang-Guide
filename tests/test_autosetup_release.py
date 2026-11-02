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
        for relative in ("lookup/books/fanqiang-autosetup-v1.1.ilang.md","site/ai/books/fanqiang-autosetup-v1.1.ilang.md"):
            p=self.release/relative
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(raw)
        (self.release/"site/ai/books/autosetup.json").write_text(json.dumps(self.manifest))
        for relative in ("site/ai/index.html","site/ai/index.md","site/ai/index.ilang","site/ai/skills/library-lookup/SKILL.md","site/llms.txt"):
            p=self.release/relative
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text("get_setup_book fanqiang-autosetup-v1.1.ilang.md")
        for relative in ("lookup/server-card.json","site/.well-known/mcp/server-card.json"):
            p=self.release/relative
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps({"serverInfo":{"version":"1.2.0"},"capabilities":{"tools":{},"resources":{},"prompts":{}},"setupBook":self.manifest}))

    def test_consistent_package_passes(self):
        self.assertEqual(checks.validate_autosetup_release(ROOT,self.release),[])

    def test_stale_download_is_rejected(self):
        (self.release/"site/ai/books/fanqiang-autosetup-v1.1.ilang.md").write_text("old book")
        self.assertIn("site/ai/books/fanqiang-autosetup-v1.1.ilang.md:canonical_book_mismatch",checks.validate_autosetup_release(ROOT,self.release))

    def test_metadata_cannot_claim_execution(self):
        self.manifest["execution_status"]="complete"
        (self.release/"site/ai/books/autosetup.json").write_text(json.dumps(self.manifest))
        self.assertIn("site/ai/books/autosetup.json:contract_mismatch",checks.validate_autosetup_release(ROOT,self.release))

    def test_missing_runtime_book_is_rejected(self):
        (self.release/"lookup/books/fanqiang-autosetup-v1.1.ilang.md").unlink()
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
