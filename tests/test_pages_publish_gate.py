"""The Pages publish gate must leave the old deployment intact on drift or outage."""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pages_publish_gate", ROOT / "developer/check_pages_live_contract.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class PagesPublishGateTests(unittest.TestCase):
    def test_identical_live_contract_allows_publish(self):
        expected = gate.expected_contract()
        with patch.object(gate, "fetch_contract", return_value=expected) as fetch:
            fingerprint = gate.require_live_contract(expected)
        self.assertEqual(len(fingerprint), 64)
        self.assertEqual(fetch.call_count, 1)
        self.assertIn("/data/product-contract.json?v=", fetch.call_args[0][0])

    def test_mismatched_model_or_book_version_blocks_publish(self):
        expected = gate.expected_contract()
        for target in ("model", "book"):
            actual = json.loads(json.dumps(expected))
            if target == "model":
                actual["server"]["assistant"]["model"] = "older-model"
            else:
                actual["books"][0]["version"] = "older-book"
            with self.subTest(target=target), patch.object(gate, "fetch_contract", return_value=actual) as fetch, patch.object(gate.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "Publish the matching main-site release first"):
                    gate.require_live_contract(expected)
                self.assertEqual(fetch.call_count, gate.MAX_ATTEMPTS)

    def test_network_failure_is_bounded_and_blocks_publish(self):
        with patch.object(gate, "fetch_contract", side_effect=URLError("fixture unavailable")) as fetch, patch.object(gate.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "Existing Pages remains deployed"):
                gate.require_live_contract(gate.expected_contract())
        self.assertEqual(fetch.call_count, 3)

    def test_fetch_enforces_timeout_response_size_and_json_object(self):
        response = io.BytesIO(b'{"schema_version":1}')
        with patch.object(gate, "urlopen", return_value=response) as open_url:
            self.assertEqual(gate.fetch_contract("https://fanqiang.guide/data/product-contract.json"), {"schema_version": 1})
        self.assertEqual(open_url.call_args.kwargs["timeout"], 8)
        for raw in (b" " * (gate.MAX_BYTES + 1), b"[]", b"not json"):
            with self.subTest(size=len(raw)), patch.object(gate, "urlopen", return_value=io.BytesIO(raw)):
                with self.assertRaises(ValueError):
                    gate.fetch_contract("https://fanqiang.guide/data/product-contract.json")


if __name__ == "__main__":
    unittest.main()
