"""Commit/transaction receipts and stale-job rejection for serialized Linux sync."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


receipt = load("release_receipt_test", "developer/release_receipt.py")
gate = load("exact_release_gate_test", "developer/check_pages_live_contract.py")


class ReleaseReceiptTests(unittest.TestCase):
    def setUp(self):
        self.contract = receipt.product_contract()
        self.identity = receipt.identity("a" * 40, "linux-sync-test-01", receipt.contract_digest(self.contract))
        self.installer_sha = receipt.installer_digest()

    def test_rejects_branch_partial_sha_and_unsafe_transaction_ids(self):
        for source in ("main", "abcdef", "A" * 40):
            with self.subTest(source=source), self.assertRaises(ValueError):
                receipt.identity(source, "safe-id", "b" * 64)
        for sync_id in ("", "../escape", "with space", "with:colon", "x" * 97):
            with self.subTest(sync_id=sync_id), self.assertRaises(ValueError):
                receipt.identity("a" * 40, sync_id, "b" * 64)
        with patch.object(receipt.subprocess, "check_output", return_value="b" * 40):
            with self.assertRaisesRegex(ValueError, "Checkout HEAD differs"):
                receipt.verify_checkout("a" * 40)
        with patch.object(receipt.subprocess, "check_output", return_value="a" * 40), patch.object(receipt.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(ValueError, "Tracked source differs"):
                receipt.verify_checkout("a" * 40)
        with patch.object(receipt.subprocess, "check_output", side_effect=["a" * 40, "apps/site/untracked.py\n"]), patch.object(receipt.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
            with self.assertRaisesRegex(ValueError, "untracked files"):
                receipt.verify_checkout("a" * 40)
        with patch.object(receipt.subprocess, "check_output", side_effect=["a" * 40, "apps/pages/deployment.json\n"]), patch.object(receipt.subprocess, "run", return_value=SimpleNamespace(returncode=0)):
            receipt.verify_checkout("a" * 40)

    def test_exact_origin_transaction_passes(self):
        origin = {**self.identity, "installer_sha256": self.installer_sha}
        with patch.object(gate, "fetch_contract", side_effect=[self.contract, origin]) as fetch:
            actual = gate.require_live_release(self.contract, self.identity, self.installer_sha)
        self.assertEqual(actual, self.identity["contract_sha256"])
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("/data/site-release.json?", fetch.call_args[0][0])

    def test_stale_sha_sync_or_installer_is_rejected_even_with_identical_product_facts(self):
        for field, value in (("source_sha", "b" * 40), ("sync_id", "previous-cycle"), ("installer_sha256", "c" * 64)):
            origin = {**self.identity, "installer_sha256": self.installer_sha, field: value}
            responses = [self.contract, origin] * gate.MAX_ATTEMPTS
            with self.subTest(field=field), patch.object(gate, "fetch_contract", side_effect=responses), patch.object(gate.time, "sleep"):
                with self.assertRaisesRegex(RuntimeError, "release." + field):
                    gate.require_live_release(self.contract, self.identity, self.installer_sha)

    def test_dispatch_contract_mismatch_fails_before_any_network_request(self):
        wrong = {**self.identity, "contract_sha256": "f" * 64}
        with patch.object(gate, "fetch_contract") as fetch:
            with self.assertRaisesRegex(ValueError, "Dispatch contract_sha256"):
                gate.require_live_release(self.contract, wrong, self.installer_sha)
        fetch.assert_not_called()

    def test_pages_receipt_binds_actual_rendered_index_and_exact_run(self):
        sync = load("receipt_sync_fixture", "developer/sync_pages_contract.py")
        with tempfile.TemporaryDirectory() as directory, patch.object(receipt, "verify_checkout"):
            public = Path(directory)
            index = sync.render(sync.TEMPLATE.read_text()).encode()
            (public / "index.html").write_bytes(index)
            result = receipt.write_receipt("pages", public, self.identity, run_id="12345", run_attempt="2")
            self.assertEqual(result["index_sha256"], hashlib.sha256(index).hexdigest())
            self.assertEqual(result["installer_sha256"], self.installer_sha)
            self.assertEqual(result["run_id"], "12345")
            self.assertEqual(result["run_attempt"], 2)
            self.assertEqual(json.loads((public / "deployment.json").read_text()), result)
            (public / "index.html").write_text("stale page")
            with self.assertRaisesRegex(ValueError, "Pages index differs"):
                receipt.write_receipt("pages", public, self.identity, run_id="12345", run_attempt="2")

    def test_origin_receipt_is_idempotent_and_keeps_manifest_for_publisher_sealing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(receipt, "verify_checkout"), patch.object(receipt, "verify_origin_build"):
            public = Path(directory)
            (public / "server").mkdir()
            (public / "server/install.sh").write_bytes((ROOT / "apps/server/install.sh").read_bytes())
            first = receipt.write_receipt("origin", public, self.identity)
            path = public / "data/site-release.json"
            first_raw = path.read_bytes()
            first_gzip = path.with_suffix(".json.gz").read_bytes()
            self.assertEqual(first, {**self.identity, "installer_sha256": self.installer_sha})
            receipt.write_receipt("origin", public, self.identity)
            self.assertEqual(path.read_bytes(), first_raw)
            self.assertEqual(path.with_suffix(".json.gz").read_bytes(), first_gzip)
            self.assertEqual(gzip.decompress(first_gzip), first_raw)
            (public / "server/install.sh").write_text("old installer")
            with self.assertRaisesRegex(ValueError, "Origin installer differs"):
                receipt.write_receipt("origin", public, self.identity)

    def test_origin_build_must_match_inputs_contract_and_actual_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "developer").mkdir()
            (root / "developer/build_apps.py").write_text("def source_inputs(): return {'fixture': {'sha256': 'current'}}\n")
            public = root / "release/site"
            (public / "data").mkdir(parents=True)
            contract_raw = json.dumps(self.contract).encode()
            (public / "data/product-contract.json").write_bytes(contract_raw)
            metadata = {"bytes": len(contract_raw), "sha256": hashlib.sha256(contract_raw).hexdigest()}
            manifest = {"source_inputs": {"fixture": {"sha256": "current"}}, "files": {"site/data/product-contract.json": metadata}}
            path = public.parent / "release-manifest.json"
            path.write_text(json.dumps(manifest))
            with patch.object(receipt, "ROOT", root):
                self.assertEqual(receipt.verify_origin_build(public, self.contract), path)
                manifest["source_inputs"]["fixture"]["sha256"] = "stale"
                path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, "current source inputs"):
                    receipt.verify_origin_build(public, self.contract)
                manifest["source_inputs"]["fixture"]["sha256"] = "current"
                manifest["files"]["site/data/product-contract.json"]["sha256"] = "0" * 64
                path.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, "differs from its build manifest"):
                    receipt.verify_origin_build(public, self.contract)


if __name__ == "__main__":
    unittest.main()
