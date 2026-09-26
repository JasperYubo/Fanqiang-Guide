"""Release knowledge checks preserve records and match actual served input bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
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
