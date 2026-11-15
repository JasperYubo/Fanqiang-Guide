"""Release gate and resumable draft behavior; no external writes or network."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import io
from unittest.mock import patch
from urllib.error import HTTPError
import unittest
from urllib.parse import urlsplit

SPEC = importlib.util.spec_from_file_location("github_release", Path(__file__).resolve().parents[1] / "developer/publish_github_release.py")
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


class FakeGitHub:
    def __init__(self):
        self.release = None
        self.target = None
        self.data = {}
        self.events = []
        self.next_id = 1
        self.fail_upload = None
        self.no_digest = False

    def tag_commit(self, tag):
        return self.target

    def find_release(self, tag):
        return copy.deepcopy(self.release)

    def create(self, payload):
        self.events.append(("create", payload["draft"]))
        self.release = {"id": 20, **copy.deepcopy(payload)}
        return copy.deepcopy(self.release)

    def get(self, release_id):
        return copy.deepcopy(self.release)

    def assets(self, release_id):
        result = []
        for name, item in self.data.items():
            metadata = {"id": item["id"], "name": name, "size": len(item["raw"]), "state": item.get("state", "uploaded")}
            if not self.no_digest:
                metadata["digest"] = "sha256:" + r.digest(item["raw"])
            result.append(metadata)
        return result

    def read_asset(self, asset):
        return next(item["raw"] for item in self.data.values() if item["id"] == asset["id"])

    def upload(self, release_id, name, raw):
        self.events.append(("upload", name))
        if name == self.fail_upload:
            raise r.ReleaseError("fixture_upload_failure")
        self.data[name] = {"id": self.next_id, "raw": raw}
        self.next_id += 1
        return next(asset for asset in self.assets(release_id) if asset["name"] == name)

    def delete_asset(self, asset):
        self.events.append(("delete", asset["name"]))
        del self.data[asset["name"]]

    def publish(self, release_id):
        self.events.append(("publish", release_id))
        self.release["draft"] = False
        self.target = self.release["target_commitish"]
        return self.get(release_id)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.installer = b'#!/bin/bash\nVERSION="1.1.0"\n'
        self.index = b'<h1>Fanqiang Guide</h1>'
        self.contract = {"version": "fixture"}
        self.expected = {"schema_version": 1, "source_sha": "a" * 40, "sync_id": "linux-test-1",
                         "contract_sha256": "c" * 64, "installer_sha256": r.digest(self.installer),
                         "run_id": "12345", "run_attempt": 1, "index_sha256": r.digest(self.index)}
        origin = {key: self.expected[key] for key in ("schema_version", "source_sha", "sync_id", "contract_sha256", "installer_sha256")}
        self.public = {
            r.ORIGIN + "data/site-release.json": r.encoded(origin),
            r.PAGES + "deployment.json": r.encoded(self.expected),
            r.ORIGIN + "data/product-contract.json": r.encoded(self.contract),
            r.ORIGIN + "server/install.sh": self.installer,
            r.PAGES: self.index,
        }
        self.proof = r.verify_live(self.expected, self.contract, fetch=self.fetch, attempts=1)
        self.static = {"huarun-install.sh": self.installer, "SOUL.ilang.md": b'::ILANG::v5.0\n',
                       "huarun.SKILL.ilang.md": b'::ILANG::v5.0\n::STATE{@SKILL}\n'}
        self.api = FakeGitHub()

    def fetch(self, url):
        return self.public[url.split("?", 1)[0]]

    def publish(self, **kwargs):
        return r.publish_release(self.api, self.expected, self.proof, self.static, "华润助手 v1.1.0 · MCP", "body", **kwargs)

    def test_public_identity_all_fields_are_checked(self):
        for field in ("source_sha", "sync_id", "contract_sha256", "installer_sha256", "run_id", "run_attempt", "index_sha256"):
            with self.subTest(field=field):
                original = self.public[r.PAGES + "deployment.json"]
                bad = dict(self.expected)
                bad[field] = "wrong"
                self.public[r.PAGES + "deployment.json"] = r.encoded(bad)
                with self.assertRaisesRegex(r.ReleaseError, "pages_identity_mismatch"):
                    r.verify_live(self.expected, self.contract, fetch=self.fetch, attempts=1)
                self.public[r.PAGES + "deployment.json"] = original

    def test_live_installer_index_and_contract_bytes_are_verified(self):
        for url, raw, reason in [(r.ORIGIN + "server/install.sh", b'old', "installer"), (r.PAGES, b'old', "index"),
                                 (r.ORIGIN + "data/product-contract.json", b'{}', "contract")]:
            with self.subTest(url=url):
                original = self.public[url]
                self.public[url] = raw
                with self.assertRaisesRegex(r.ReleaseError, reason):
                    r.verify_live(self.expected, self.contract, fetch=self.fetch, attempts=1)
                self.public[url] = original

    def test_stale_public_receipts_retry_bounded_and_then_pass(self):
        seen = []
        sleeps = []
        def fetch(url):
            seen.append(url)
            if len(seen) == 1:
                raise r.ReleaseError("temporary_cache")
            return self.fetch(url)
        proof = r.verify_live(self.expected, self.contract, fetch=fetch, attempts=2, sleep=sleeps.append)
        self.assertEqual(proof["run_id"], "12345")
        self.assertEqual(sleeps, [5])
        self.assertEqual(len(seen), 6)

    def test_failed_public_verification_stops_after_limit(self):
        attempts = []
        def fetch(url):
            attempts.append(url)
            raise r.ReleaseError("fixture_unavailable")
        with self.assertRaisesRegex(r.ReleaseError, "public_verification_failed"):
            r.verify_live(self.expected, self.contract, fetch=fetch, attempts=3, sleep=lambda _: None)
        self.assertEqual(len(attempts), 3)

    def test_draft_first_every_asset_verified_then_publish(self):
        result = self.publish()
        self.assertEqual(result["status"], "published")
        self.assertEqual(result["tag"], "release-" + "a" * 12)
        self.assertEqual(self.api.events[0], ("create", True))
        self.assertEqual(self.api.events[-1][0], "publish")
        self.assertEqual(set(self.api.data), set(self.static) | {"SHA256SUMS", "deployment-proof.json"})
        self.assertFalse(self.api.release["draft"])
        self.assertEqual(self.api.target, self.expected["source_sha"])

    def test_incomplete_upload_keeps_draft_then_resumes_without_duplicate(self):
        self.api.fail_upload = "SOUL.ilang.md"
        with self.assertRaisesRegex(r.ReleaseError, "fixture_upload_failure"):
            self.publish()
        self.assertTrue(self.api.release["draft"])
        self.assertFalse(any(event[0] == "publish" for event in self.api.events))
        self.api.fail_upload = None
        self.publish()
        self.assertEqual(sum(event[0] == "create" for event in self.api.events), 1)
        self.assertEqual(sum(event == ("upload", "huarun-install.sh") for event in self.api.events), 1)

    def test_wrong_existing_tag_prevents_creation(self):
        self.api.target = "b" * 40
        with self.assertRaisesRegex(r.ReleaseError, "existing_tag_wrong_source"):
            self.publish()
        self.assertEqual(self.api.events, [])

    def test_existing_release_target_cannot_be_rewritten(self):
        self.api.release = {"id": 20, "tag_name": "release-" + "a" * 12, "target_commitish": "b" * 40, "draft": True}
        with self.assertRaisesRegex(r.ReleaseError, "existing_release_wrong_source"):
            self.publish()
        self.assertEqual(self.api.events, [])

    def test_published_release_rerun_is_read_only_and_preserves_original_proof(self):
        self.publish()
        previous = copy.deepcopy(self.api.data)
        events = list(self.api.events)
        # Same code may be verified by a later full workflow rerun.
        self.expected["run_attempt"] = 2
        self.proof = {**self.proof, "run_attempt": 2,
                      "pages_receipt": {**self.proof["pages_receipt"], "run_attempt": 2}}
        result = self.publish()
        self.assertEqual(result["status"], "already_published")
        self.assertEqual(self.api.data, previous)
        self.assertEqual(self.api.events, events)

    def test_published_wrong_asset_is_rejected_never_overwritten(self):
        self.publish()
        self.api.data["SOUL.ilang.md"]["raw"] = b'wrong source'
        events = list(self.api.events)
        with self.assertRaisesRegex(r.ReleaseError, "published_assets_mismatch"):
            self.publish()
        self.assertEqual(self.api.events, events)

    def test_corrupt_published_deployment_proof_is_rejected(self):
        self.publish()
        proof = json.loads(self.api.data["deployment-proof.json"]["raw"])
        proof["pages_receipt"]["sync_id"] = "some-other-transaction"
        self.api.data["deployment-proof.json"]["raw"] = r.encoded(proof)
        with self.assertRaisesRegex(r.ReleaseError, "published_pages_proof_identity_mismatch"):
            self.publish()

    def test_draft_wrong_source_asset_is_not_silently_replaced(self):
        self.api.fail_upload = "SOUL.ilang.md"
        with self.assertRaises(r.ReleaseError):
            self.publish()
        self.api.fail_upload = None
        self.api.data["huarun-install.sh"]["raw"] = b'wrong installer'
        events = list(self.api.events)
        with self.assertRaisesRegex(r.ReleaseError, "draft_source_asset_mismatch"):
            self.publish()
        self.assertEqual(self.api.events, events)

    def test_draft_receipt_refreshes_for_new_run_but_source_assets_stay(self):
        with self.assertRaises(r.ReleaseError):
            self.publish(before_publish=lambda: (_ for _ in ()).throw(r.ReleaseError("stale_live")))
        self.expected["run_attempt"] = 2
        self.proof = {**self.proof, "run_attempt": 2,
                      "pages_receipt": {**self.proof["pages_receipt"], "run_attempt": 2}}
        self.publish()
        self.assertEqual(json.loads(self.api.data["deployment-proof.json"]["raw"])["run_attempt"], 2)
        self.assertEqual(sum(event == ("upload", "huarun-install.sh") for event in self.api.events), 1)
        self.assertIn(("delete", "deployment-proof.json"), self.api.events)

    def test_recheck_before_publication_prevents_stale_release(self):
        def stale():
            raise r.ReleaseError("origin_changed")
        with self.assertRaisesRegex(r.ReleaseError, "origin_changed"):
            self.publish(before_publish=stale)
        self.assertTrue(self.api.release["draft"])
        self.assertFalse(any(event[0] == "publish" for event in self.api.events))

    def test_missing_github_asset_digest_uses_bytes(self):
        self.api.no_digest = True
        self.assertEqual(self.publish()["status"], "published")
        self.assertEqual(self.publish()["status"], "already_published")

    def test_checksums_cover_every_other_asset_and_exact_bytes(self):
        files = r.complete_assets(self.static, self.proof)
        for line in files["SHA256SUMS"].decode().splitlines():
            checksum, name = line.split("  ", 1)
            self.assertEqual(checksum, r.digest(files[name]))
        self.assertNotIn("SHA256SUMS", files["SHA256SUMS"].decode())
        self.assertEqual(len(files["SHA256SUMS"].decode().splitlines()), len(files) - 1)

    def test_source_assets_follow_canonical_books_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = ["apps/server/install.sh", "apps/server/assistant/AGENT.md", "apps/server/assistant/SOUL.md", "apps/server/assistant/skills/huarun/SKILL.md"]
            for path in paths:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'fixture')
            books = []
            for book_id in ("server", "troubleshooting"):
                name = "fanqiang-" + book_id + "-v2.0.ilang.md"
                path = root / "apps/lookup/runtime/books" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'book')
                books.append({"book_id": book_id, "download_url": r.ORIGIN + "ai/books/" + name, "sha256": r.digest(b'book')})
            self.assertEqual(len(r.source_assets(root, {"books": books})), 6)
            books[0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(r.ReleaseError, "release_book_hash_mismatch"):
                r.source_assets(root, {"books": books})

    def test_github_error_response_does_not_expose_token_or_provider_body(self):
        secret = "ghp-private-test-token"
        class Opener:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 422, "body " + secret, {}, io.BytesIO(secret.encode()))
        with patch.object(r, "build_opener", return_value=Opener()):
            with self.assertRaises(r.ReleaseError) as caught:
                r.GitHub(secret).request("POST", "/repos/" + r.REPOSITORY + "/releases", {})
        self.assertEqual(str(caught.exception), "github_http_422")
        self.assertNotIn(secret, str(caught.exception))

    def test_binary_asset_redirect_never_accepts_unapproved_host(self):
        class Opener:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 302, "redirect", {"Location": "https://credential-collector.example/file"}, io.BytesIO())
        with patch.object(r, "build_opener", return_value=Opener()):
            with self.assertRaisesRegex(r.ReleaseError, "public_host_not_allowed"):
                r.GitHub("secret").request("GET", "/repos/" + r.REPOSITORY + "/releases/assets/1", binary=True)

    def test_failed_starter_asset_is_replaced_only_while_draft(self):
        self.api.fail_upload = "SOUL.ilang.md"
        with self.assertRaises(r.ReleaseError):
            self.publish()
        self.api.fail_upload = None
        self.api.data["SOUL.ilang.md"] = {"id": 90, "raw": b"", "state": "starter"}
        self.assertEqual(self.publish()["status"], "published")
        self.assertIn(("delete", "SOUL.ilang.md"), self.api.events)

    def test_workflow_release_job_is_after_deploy_and_token_step_scoped(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pages.yml").read_text()
        deploy, release = workflow.split("\n  release:\n")
        self.assertNotIn("contents: write", deploy)
        self.assertIn("needs: deploy", release)
        self.assertIn("if: ${{ inputs.source_sha != '270c81ba257398004ecf992d2cde2d3029d981de' }}", release)
        self.assertNotIn("hashFiles(", release)
        self.assertIn("contents: write", release)
        self.assertIn("ref: ${{ inputs.source_sha }}", release)
        self.assertIn("persist-credentials: false", release)
        self.assertEqual(release.count("GITHUB_TOKEN:"), 1)
        self.assertNotIn("on:\n  push:", workflow)


if __name__ == "__main__":
    unittest.main()
