"""Offline behavior tests: no GitHub requests or real credentials are used."""

from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import update_upstream as updater


SLUG = "example/tool"
OLD = "2026-09-11T00:00:00Z"
NOW = "2026-09-12T00:00:00Z"
REPO = {"full_name": SLUG, "html_url": "https://github.com/" + SLUG,
        "archived": False, "disabled": False, "pushed_at": OLD, "default_branch": "main"}
RELEASE = {"tag_name": "v1.0", "html_url": "https://github.com/" + SLUG + "/releases/tag/v1.0", "published_at": OLD}
MANIFEST = {"schema_version": 1, "repositories": [{"full_name": SLUG, "entity_ids": ["tool"]}], "excluded": []}
API_URL = "https://api.github.com/repos/" + SLUG
CANONICAL = "moved/tool-new"
CANONICAL_API = "https://api.github.com/repos/" + CANONICAL
MOVED_REPO = dict(REPO, full_name=CANONICAL, html_url="https://github.com/" + CANONICAL)
MOVED_RELEASE = dict(RELEASE, html_url="https://github.com/" + CANONICAL + "/releases/tag/v1.0")


def redirect(target, source=API_URL, status=301):
    return urllib.error.HTTPError(source, status, "Moved", {"Location": target}, io.BytesIO(b"{}"))


def moved_response():
    return updater.APIResponse(MOVED_REPO, [API_URL, CANONICAL_API])


class StubClient:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def fetch(self, slug, release=False):
        self.calls.append((slug, release))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return deepcopy(result)


def old_entry():
    return updater.update_repository(SLUG, None, OLD, StubClient(REPO, RELEASE))


def state_for(entry):
    return {"schema_version": 1, "last_run": {"checked_at": entry["checked_at"], "repository_count": 1,
            "ok_count": int(updater.is_complete(entry)), "error_count": int(not updater.is_complete(entry))},
            "repositories": {SLUG: entry}}


class Response:
    status = 200

    def __init__(self, data, url="https://api.github.com/repos/" + SLUG):
        self.data, self.url = data, url

    def geturl(self):
        return self.url

    def read(self, limit):
        return json.dumps(self.data).encode()[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Opener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class UpstreamTests(unittest.TestCase):
    def setUp(self):
        # CLI tests must never consult the developer machine's token/summary environment.
        environment = patch.object(updater.os, "environ", {})
        environment.start()
        self.addCleanup(environment.stop)

    def test_transient_repository_failure_preserves_last_good_values(self):
        previous = old_entry()
        unchanged = deepcopy(previous)
        entry = updater.update_repository(SLUG, previous, NOW, StubClient(updater.FetchError("network_error")))
        self.assertEqual(previous, unchanged)
        self.assertEqual(entry["repository"], previous["repository"])
        self.assertEqual(entry["release"], previous["release"])
        self.assertEqual(entry["repository_last_success_at"], OLD)
        self.assertEqual(entry["release_last_success_at"], OLD)
        self.assertEqual(entry["repository_status"], "error")
        self.assertEqual(entry["release_status"], "not_checked")
        self.assertEqual(entry["checked_at"], NOW)

    def test_release_failure_keeps_release_while_repository_refreshes(self):
        repo = dict(REPO, pushed_at=NOW)
        entry = updater.update_repository(SLUG, old_entry(), NOW, StubClient(repo, updater.FetchError("network_error")))
        self.assertEqual(entry["repository"]["pushed_at"], NOW)
        self.assertEqual(entry["repository_status"], "ok")
        self.assertEqual(entry["release_status"], "error")
        self.assertEqual(entry["release"], RELEASE)
        self.assertEqual(entry["release_last_success_at"], OLD)

    def test_repository_404_is_unavailable_and_does_not_check_release(self):
        client = StubClient(updater.FetchError("not_found"))
        entry = updater.update_repository(SLUG, old_entry(), NOW, client)
        self.assertEqual(entry["repository_status"], "unavailable")
        self.assertEqual(entry["error_code"], "repository_not_found")
        self.assertEqual(entry["repository"], REPO)
        self.assertEqual(entry["release"], RELEASE)
        self.assertEqual(client.calls, [(SLUG, False)])

    def test_release_404_is_successful_none_not_stale_release(self):
        entry = updater.update_repository(SLUG, old_entry(), NOW, StubClient(REPO, updater.FetchError("not_found")))
        self.assertEqual(entry["repository_status"], "ok")
        self.assertEqual(entry["release_status"], "none")
        self.assertIsNone(entry["release"])
        self.assertIsNone(entry["error_code"])
        self.assertEqual(entry["release_last_success_at"], NOW)

    def test_manifest_rejects_paths_urls_duplicates_and_missing_ids(self):
        for slug in ("../tool", "https://github.com/example/tool", "example/tool/extra", "example/%2e%2e", "example/..", "example/tool?x=1"):
            with self.subTest(slug=slug):
                manifest = deepcopy(MANIFEST)
                manifest["repositories"][0]["full_name"] = slug
                with self.assertRaises(updater.ValidationError):
                    updater.validate_manifest(manifest)
        for row in ({"full_name": "EXAMPLE/TOOL", "entity_ids": ["second"]},
                    {"full_name": "example/another", "entity_ids": ["tool"]},
                    {"full_name": "example/another", "entity_ids": []}):
            manifest = deepcopy(MANIFEST)
            manifest["repositories"].append(row)
            with self.assertRaises(updater.ValidationError):
                updater.validate_manifest(manifest)

    def test_malicious_response_urls_and_identity_are_not_saved(self):
        for url in ("http://github.com/example/tool", "https://github.com.evil.test/example/tool",
                    "https://github.com@evil.test/example/tool", "https://github.com/example/tool?token=x",
                    "https://github.com/example/%2e%2e/tool", "https://github.com:443/example/tool"):
            with self.subTest(url=url):
                entry = updater.update_repository(SLUG, old_entry(), NOW, StubClient(dict(REPO, html_url=url)))
                self.assertEqual(entry["repository_status"], "error")
                self.assertEqual(entry["repository"], REPO)
        with self.assertRaises(updater.ValidationError):
            updater.repository_payload(dict(REPO, full_name="another/tool"), SLUG)
        with self.assertRaises(updater.ValidationError):
            updater.repository_payload(dict(REPO, archived="false"), SLUG)
        with self.assertRaises(updater.ValidationError):
            updater.release_payload(dict(RELEASE, tag_name="v2.0"), SLUG)

    def test_redirect_handler_never_implicitly_forwards_token(self):
        request = urllib.request.Request("https://api.github.com/repos/" + SLUG,
                                         headers={"Authorization": "Bearer test-token"})
        for target in ("https://attacker.test/collect", "https://api.github.com/repos/moved/tool"):
            with self.subTest(target=target):
                self.assertIsNone(updater.NoRedirects().redirect_request(request, None, 302, "Found", {}, target))

    def test_verified_rename_chain_keeps_manifest_key_and_uses_canonical_release(self):
        numeric = "https://api.github.com/repositories/12345"
        opener = Opener(redirect(numeric), redirect(CANONICAL_API, numeric),
                        Response(MOVED_REPO, CANONICAL_API),
                        Response(MOVED_RELEASE, CANONICAL_API + "/releases/latest"))
        client = updater.APIClient(token="fake-test-token", opener=opener)
        state = updater.build_state([SLUG], {"repositories": {}}, NOW, client)
        self.assertEqual(list(state["repositories"]), [SLUG])
        entry = state["repositories"][SLUG]
        self.assertEqual(entry["repository"], MOVED_REPO)
        self.assertEqual(entry["release"], MOVED_RELEASE)
        self.assertTrue(updater.is_complete(entry))
        self.assertEqual(entry["repository_resolution"]["api_redirect_chain"], [API_URL, numeric, CANONICAL_API])
        self.assertEqual(entry["release_resolution"]["full_name"], CANONICAL)
        self.assertEqual([request.full_url for request, _ in opener.requests],
                         [API_URL, numeric, CANONICAL_API, CANONICAL_API + "/releases/latest"])
        self.assertTrue(all(request.get_header("Authorization") == "Bearer fake-test-token" for request, _ in opener.requests))
        self.assertEqual(updater.validate_state(state), state)

    def test_canonical_release_may_redirect_to_numeric_release_endpoint(self):
        numeric = "https://api.github.com/repositories/12345/releases/latest"
        opener = Opener(redirect(CANONICAL_API), Response(MOVED_REPO, CANONICAL_API),
                        redirect(numeric, CANONICAL_API + "/releases/latest", 307),
                        Response(MOVED_RELEASE, numeric))
        entry = updater.update_repository(SLUG, None, NOW, updater.APIClient(opener=opener))
        self.assertEqual(entry["release_status"], "ok")
        self.assertEqual(entry["release"], MOVED_RELEASE)
        updater.validate_state(state_for(entry))

    def test_cross_origin_redirect_never_receives_token(self):
        targets = ("https://attacker.test/repos/moved/tool", "http://api.github.com/repos/moved/tool",
                   "https://api.github.com.attacker.test/repos/moved/tool", "https://api.github.com@attacker.test/repos/moved/tool",
                   "https://attacker@api.github.com/repos/moved/tool", "https://api.github.com:443/repos/moved/tool")
        for target in targets:
            with self.subTest(target=target):
                opener = Opener(redirect(target))
                client = updater.APIClient(token="fake-test-token", opener=opener)
                with self.assertRaises(updater.FetchError) as raised:
                    client.fetch(SLUG)
                self.assertEqual(raised.exception.code, "redirect_blocked")
                self.assertEqual([req.full_url for req, _ in opener.requests], [API_URL])

    def test_redirect_rejects_nonrepository_paths_queries_and_escaping(self):
        targets = ("https://api.github.com/user", "https://api.github.com/repos/moved/tool/contents",
                   "https://api.github.com/repos/moved/tool?token=not-real", "https://api.github.com/repos/moved/tool#fragment",
                   "https://api.github.com/repos/moved/%2e%2e", "https://api.github.com/repositories/not-a-number",
                   "https://api.github.com/repositories/0", "/repositories/12345",
                   "https://api.github.com/repos/moved/tool/releases/latest")
        for target in targets:
            with self.subTest(target=target):
                opener = Opener(redirect(target))
                with self.assertRaises(updater.FetchError) as raised:
                    updater.APIClient(opener=opener).fetch(SLUG)
                self.assertEqual(raised.exception.code, "redirect_blocked")
                self.assertEqual(len(opener.requests), 1)

    def test_redirect_loop_stops_before_repeating_request(self):
        opener = Opener(redirect(CANONICAL_API), redirect(API_URL, CANONICAL_API))
        with self.assertRaises(updater.FetchError) as raised:
            updater.APIClient(opener=opener).fetch(SLUG)
        self.assertEqual(raised.exception.code, "redirect_loop")
        self.assertEqual(len(opener.requests), 2)

    def test_at_most_three_redirects_are_followed(self):
        urls = [API_URL] + ["https://api.github.com/repositories/" + str(i) for i in range(1, 5)]
        opener = Opener(*(redirect(target, source) for source, target in zip(urls, urls[1:])))
        with self.assertRaises(updater.FetchError) as raised:
            updater.APIClient(opener=opener).fetch(SLUG)
        self.assertEqual(raised.exception.code, "redirect_limit")
        self.assertEqual([req.full_url for req, _ in opener.requests], urls[:4])

    def test_json_cannot_claim_transport_provenance_for_identity_change(self):
        forged = dict(MOVED_REPO, api_redirect_chain=[API_URL, CANONICAL_API])
        opener = Opener(Response(forged))
        entry = updater.update_repository(SLUG, old_entry(), NOW, updater.APIClient(opener=opener))
        self.assertEqual(entry["repository_status"], "error")
        self.assertEqual(entry["repository"], REPO)
        self.assertNotIn("repository_resolution", entry)
        self.assertEqual(len(opener.requests), 1)

    def test_redirected_named_endpoint_must_match_response_identity(self):
        wrong = dict(MOVED_REPO, full_name="unrelated/project", html_url="https://github.com/unrelated/project")
        opener = Opener(redirect(CANONICAL_API), Response(wrong, CANONICAL_API))
        entry = updater.update_repository(SLUG, old_entry(), NOW, updater.APIClient(opener=opener))
        self.assertEqual(entry["repository_status"], "error")
        self.assertEqual(entry["repository"], REPO)
        self.assertNotIn("repository_resolution", entry)

    def test_malformed_redirected_response_preserves_last_good_data(self):
        wrong = dict(MOVED_REPO, html_url="https://attacker.test/moved/tool-new")
        opener = Opener(redirect(CANONICAL_API), Response(wrong, CANONICAL_API))
        entry = updater.update_repository(SLUG, old_entry(), NOW, updater.APIClient(opener=opener))
        self.assertEqual(entry["repository_status"], "error")
        self.assertEqual(entry["repository"], REPO)
        self.assertEqual(entry["release"], RELEASE)

    def test_rename_with_release_failure_preserves_old_release_identity(self):
        entry = updater.update_repository(SLUG, old_entry(), NOW,
                                          StubClient(moved_response(), updater.FetchError("network_error")))
        self.assertEqual(entry["repository"], MOVED_REPO)
        self.assertEqual(entry["release"], RELEASE)
        self.assertEqual(entry["release_status"], "error")
        self.assertNotIn("release_resolution", entry)
        updater.validate_state(state_for(entry))

    def test_renamed_old_state_survives_a_later_network_failure(self):
        previous = updater.update_repository(SLUG, None, OLD, StubClient(moved_response(), MOVED_RELEASE))
        previous_bytes = json.dumps(state_for(previous), sort_keys=True)
        updater.validate_state(json.loads(previous_bytes))
        entry = updater.update_repository(SLUG, previous, NOW, StubClient(updater.FetchError("network_error")))
        self.assertEqual(entry["repository_resolution"], previous["repository_resolution"])
        self.assertEqual(entry["release_resolution"], previous["release_resolution"])
        self.assertEqual(entry["repository_last_success_at"], OLD)
        self.assertEqual(entry["release_last_success_at"], OLD)
        updater.validate_state(state_for(entry))
        self.assertEqual(json.dumps(state_for(previous), sort_keys=True), previous_bytes)

    def test_renamed_state_requires_valid_provenance(self):
        entry = updater.update_repository(SLUG, None, NOW, StubClient(moved_response(), MOVED_RELEASE))
        for key in ("repository_resolution", "release_resolution"):
            invalid = deepcopy(entry)
            del invalid[key]
            with self.subTest(key=key), self.assertRaises(updater.ValidationError):
                updater.validate_state(state_for(invalid))
        invalid = deepcopy(entry)
        invalid["repository_resolution"]["api_redirect_chain"][-1] = "https://attacker.test/repos/moved/tool-new"
        with self.assertRaises(updater.ValidationError):
            updater.validate_state(state_for(invalid))

    def test_invalid_slug_rejected_before_authenticated_request(self):
        opener = Opener()
        client = updater.APIClient(token="test-token", opener=opener)
        with self.assertRaises(updater.ValidationError):
            client.fetch("https://attacker.test/collect")
        self.assertEqual(opener.requests, [])

    def test_no_auth_header_without_token_and_timeout_is_bounded(self):
        opener = Opener(Response(REPO))
        client = updater.APIClient(opener=opener)
        self.assertEqual(client.fetch(SLUG), REPO)
        request, timeout = opener.requests[0]
        self.assertIsNone(request.get_header("Authorization"))
        self.assertLessEqual(timeout, updater.REQUEST_TIMEOUT)

    def test_transient_http_failure_retries_then_succeeds(self):
        error = urllib.error.HTTPError("https://api.github.com/repos/" + SLUG, 503, "Unavailable", {}, io.BytesIO(b"{}"))
        opener = Opener(error, Response(REPO))
        sleeps = []
        client = updater.APIClient(opener=opener, sleep=sleeps.append)
        self.assertEqual(client.fetch(SLUG), REPO)
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(sleeps, [1])

    def test_large_retry_after_stops_without_early_retry(self):
        error = urllib.error.HTTPError("https://api.github.com/repos/" + SLUG, 429, "Limit", {"Retry-After": "3600"}, io.BytesIO(b"{}"))
        opener, sleeps = Opener(error), []
        client = updater.APIClient(opener=opener, sleep=sleeps.append)
        with self.assertRaises(updater.FetchError) as raised:
            client.fetch(SLUG)
        self.assertEqual(raised.exception.code, "rate_limited")
        self.assertTrue(client.systemic.is_set())
        self.assertEqual(sleeps, [])
        self.assertEqual(len(opener.requests), 1)

    def test_streaming_response_is_cut_off_at_deadline(self):
        class Stream:
            def read1(self, limit):
                return b"x"
        moments = iter([0, 0, 1, 2])
        client = updater.APIClient(opener=Opener(), monotonic=lambda: next(moments))
        with self.assertRaises(TimeoutError):
            client._read_response(Stream(), request_deadline=2)

    def test_malformed_quota_delay_is_systemic_and_does_not_sleep(self):
        error = urllib.error.HTTPError("https://api.github.com/repos/" + SLUG, 429, "Limit", {"Retry-After": "not-a-date"}, io.BytesIO(b"{}"))
        client = updater.APIClient(opener=Opener(error), sleep=lambda delay: self.fail("must not sleep"))
        with self.assertRaises(updater.FetchError):
            client.fetch(SLUG)
        self.assertTrue(client.systemic.is_set())

    def test_summary_is_optional_and_summary_failure_is_nonfatal(self):
        with patch("builtins.open") as file_open, patch("sys.stdout", new=io.StringIO()):
            updater.summary("test result")
            file_open.assert_not_called()
        with patch.object(updater.os, "environ", {"GITHUB_STEP_SUMMARY": "test-summary"}), \
                patch("builtins.open", side_effect=OSError("unavailable")), \
                patch("sys.stdout", new=io.StringIO()), patch("sys.stderr", new=io.StringIO()) as stderr:
            updater.summary("test result")
        self.assertIn("metadata result is unaffected", stderr.getvalue())

    def test_authentication_failure_halts_other_requests(self):
        error = urllib.error.HTTPError("https://api.github.com/repos/" + SLUG, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        opener = Opener(error)
        client = updater.APIClient(token="fake-test-token", opener=opener)
        with self.assertRaises(updater.FetchError) as raised:
            client.fetch(SLUG)
        self.assertTrue(raised.exception.systemic)
        with self.assertRaises(updater.FetchError) as halted:
            client.fetch(SLUG)
        self.assertEqual(halted.exception.code, "run_halted")
        self.assertEqual(len(opener.requests), 1)

    def test_fixed_timestamp_and_unchanged_upstream_are_idempotent(self):
        first = updater.build_state([SLUG], {"repositories": {}}, NOW, StubClient(REPO, RELEASE))
        second = updater.build_state([SLUG], first, NOW, StubClient(REPO, RELEASE))
        self.assertEqual(first, second)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "upstream.json"
            self.assertTrue(updater.atomic_save(output, first))
            original, modified = output.read_bytes(), output.stat().st_mtime_ns
            self.assertFalse(updater.atomic_save(output, second))
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(output.stat().st_mtime_ns, modified)

    def test_atomic_replace_failure_retains_old_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "upstream.json"
            output.write_bytes(b"original")
            with patch.object(updater.os, "replace", side_effect=OSError("failure")):
                with self.assertRaises(OSError):
                    updater.atomic_save(output, state_for(old_entry()))
            self.assertEqual(output.read_bytes(), b"original")
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_invalid_previous_json_does_not_make_requests_or_replace_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, output = root / "manifest.json", root / "upstream.json"
            manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
            output.write_bytes(b"invalid old json")
            with patch.object(updater, "APIClient") as factory, patch("sys.stderr", new=io.StringIO()):
                result = updater.main(["--manifest", str(manifest), "--output", str(output), "--now", NOW])
            self.assertEqual(result, 2)
            factory.assert_not_called()
            self.assertEqual(output.read_bytes(), b"invalid old json")

    def test_zero_success_does_not_replace_last_good_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest, output = root / "manifest.json", root / "upstream.json"
            manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
            updater.atomic_save(output, state_for(old_entry()))
            previous = output.read_bytes()
            with patch.object(updater, "APIClient", return_value=StubClient(updater.FetchError("not_found"))), patch.object(updater, "summary"):
                result = updater.main(["--manifest", str(manifest), "--output", str(output), "--now", NOW])
            self.assertEqual(result, 1)
            self.assertEqual(output.read_bytes(), previous)

    def test_only_cannot_write_default_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.json"
            manifest.write_text(json.dumps(MANIFEST), encoding="utf-8")
            with patch.object(updater, "APIClient") as factory, patch("sys.stderr", new=io.StringIO()):
                result = updater.main(["--manifest", str(manifest), "--only", SLUG])
            self.assertEqual(result, 2)
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
