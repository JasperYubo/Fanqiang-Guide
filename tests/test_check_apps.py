"""Release knowledge checks preserve records and match actual served input bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_apps", ROOT / "developer/check_apps.py")
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


class GeneratedKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data").mkdir()
        self.values = {"KNOWLEDGE_META": {"counts": {"library": 1}, "sha256": {}}, "GUIDES": [], "MODELS": [], "LIBRARY": [{"id": "one", "verification": "unknown"}]}
        for name in ("guides", "library", "merlin-models"):
            raw = b'{\r\n  "items": []\r\n}\r\n'
            (self.root / "data" / (name + ".json")).write_bytes(raw)
            self.values["KNOWLEDGE_META"]["sha256"][name] = hashlib.sha256(raw).hexdigest()
        self.source = self.root / "source.mjs"
        self.generated = self.root / "generated.mjs"
        self.write(self.generated, self.values)
        source = json.loads(json.dumps(self.values))
        source["KNOWLEDGE_META"]["sha256"] = {name: "old-lf-input-hash" for name in self.values["KNOWLEDGE_META"]["sha256"]}
        self.write(self.source, source)

    def write(self, file, values):
        file.write_text("\n".join("export const " + key + " = " + json.dumps(value) + ";" for key, value in values.items()) + "\n", encoding="utf-8")

    def validate(self):
        return checks.validate_generated_knowledge(self.source, self.generated, self.root)

    def test_same_records_with_changed_input_eol_use_actual_published_byte_hash(self):
        self.assertEqual(self.validate(), [])

    def test_real_record_change_is_rejected(self):
        self.values["LIBRARY"][0]["verification"] = "tested"
        self.write(self.generated, self.values)
        self.assertIn("worker/src/knowledge.mjs:generated_records_mismatch", self.validate())

    def test_hash_not_matching_release_bytes_is_rejected(self):
        self.values["KNOWLEDGE_META"]["sha256"]["library"] = "fake"
        self.write(self.generated, self.values)
        self.assertIn("worker/src/knowledge.mjs:library:published_input_hash_mismatch", self.validate())


class GeneratedAnswerImportTests(unittest.TestCase):
    def test_validator_loads_faq_renderer_from_outside_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp)
            (public / "data").mkdir()
            source = public / "faq.json"
            source.write_text(json.dumps({"schema_version": 1, "entries": []}), encoding="utf-8")
            mapping = {"entries": [], "pages": 0, "canonical_pages": 0, "sitemap_urls": 0,
                       "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            (public / "data/faq-pages.json").write_text(json.dumps(mapping), encoding="utf-8")
            (public / "sitemap-answers.xml").write_text(
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>', encoding="utf-8")
            script = textwrap.dedent("""
                import importlib.util
                import json
                from pathlib import Path
                import sys

                original_path = list(sys.path)
                spec = importlib.util.spec_from_file_location("isolated_checks", sys.argv[1])
                checks = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(checks)
                report = checks.validate_generated_answers(Path("faq.json"), Path.cwd())
                assert sys.path == original_path, "Validator changed the module search path"
                print(json.dumps(report))
            """)
            result = subprocess.run(
                [sys.executable, "-I", "-c", script, str(ROOT / "developer/check_apps.py")],
                cwd=public, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout), {
                "pages": 0, "canonical_pages": 0, "sitemap_urls": 0, "failures": []})
