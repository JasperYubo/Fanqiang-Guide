"""Offline freshness semantics and failure preservation; no network requests."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("refresh_knowledge_sources", ROOT / "developer/refresh_knowledge_sources.py")
freshness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freshness)
NOW = "2026-11-03T00:00:00Z"
OLD = "2026-10-30T00:00:00Z"
SLUG = "2dust/v2rayNG"


def fixture():
    library = [{"id": "v2rayng", "verification": {"checked_at": "2026-09-11", "status": "primary_reviewed"},
                "compatibility": {"supported_models": None}, "source_claims": {"version": "2.2.6"}},
               {"id": "no-repository", "verification": {"checked_at": "2026-09-11"}}]
    manifest = {"schema_version": 1, "repositories": [{"full_name": SLUG, "entity_ids": ["v2rayng"]}],
                "excluded": [{"entity_id": "no-repository", "reason": "missing_repository"}]}
    entry = {"checked_at": NOW, "repository_status": "ok", "release_status": "ok", "error_code": None,
             "repository_last_success_at": NOW, "release_last_success_at": NOW,
             "repository": {"full_name": SLUG, "html_url": "https://github.com/" + SLUG, "archived": False,
                            "disabled": False, "pushed_at": "2026-11-01T06:59:31Z", "default_branch": "master"},
             "release": {"tag_name": "2.3.14", "html_url": "https://github.com/" + SLUG + "/releases/tag/2.3.14",
                         "published_at": "2026-10-28T03:06:38Z"}}
    state = {"schema_version": 1, "last_run": {"checked_at": NOW, "repository_count": 1, "ok_count": 1, "error_count": 0},
             "repositories": {SLUG: entry}}
    return library, manifest, state


def failed(state):
    state["last_run"].update(ok_count=0, error_count=1)
    return state["repositories"][SLUG]


class ProjectionTests(unittest.TestCase):
    def build(self, values=None, now=NOW):
        return freshness.build_projection(*(values or fixture()), as_of=now)

    def test_distinct_dates_and_authored_facts_are_unchanged(self):
        values = fixture(); before = deepcopy(values)
        result = self.build(values); row = result["records"]["v2rayng"]
        self.assertEqual(values, before)
        self.assertEqual(row["knowledge_checked_at"], "2026-09-11")
        self.assertEqual(row["source_checked_at"], NOW)
        self.assertEqual(row["last_attempt_at"], NOW)
        self.assertEqual(row["latest_release"]["published_at"], "2026-10-28T03:06:38Z")
        self.assertEqual(row["repository"]["pushed_at"], "2026-11-01T06:59:31Z")
        self.assertEqual(result["generated_at"], NOW)
        self.assertEqual(row["scope"], "repository_metadata_only")
        self.assertNotIn("compatibility", row)
        self.assertEqual(row["status"], "current")
        self.assertEqual(row["expires_at"], "2026-11-05T00:00:00Z")

    def test_deterministic_given_as_of(self):
        self.assertEqual(self.build(), self.build())

    def test_expired_metadata_is_stale_without_changing_observation_time(self):
        row = self.build(now="2026-11-05T00:00:00Z")["records"]["v2rayng"]
        self.assertEqual(row["status"], "stale")
        self.assertEqual(row["source_checked_at"], NOW)

    def test_failed_repository_keeps_old_success_without_false_refresh(self):
        values = fixture(); entry = failed(values[2])
        entry.update(repository_status="error", release_status="not_checked", error_code="network_error",
                     repository_last_success_at=OLD, release_last_success_at=OLD)
        previous_repo, previous_release = deepcopy(entry["repository"]), deepcopy(entry["release"])
        row = self.build(values)["records"]["v2rayng"]
        self.assertEqual((row["status"], row["source_checked_at"], row["last_attempt_at"]), ("stale", OLD, NOW))
        self.assertEqual(row["repository"]["checked_at"], OLD)
        self.assertEqual(row["latest_release"]["checked_at"], OLD)
        self.assertEqual(row["latest_release"]["tag_name"], previous_release["tag_name"])
        self.assertEqual(row["repository"]["pushed_at"], previous_repo["pushed_at"])

    def test_partial_release_failure_retains_its_own_old_timestamp(self):
        values = fixture(); entry = failed(values[2])
        entry.update(release_status="error", release_last_success_at=OLD, error_code="rate_limited")
        row = self.build(values)["records"]["v2rayng"]
        self.assertEqual(row["status"], "stale")
        self.assertEqual(row["repository"]["checked_at"], NOW)
        self.assertEqual(row["latest_release"]["checked_at"], OLD)
        self.assertEqual(row["source_checked_at"], OLD)

    def test_first_failure_is_unknown_not_absent_repository_claim(self):
        values = fixture(); entry = failed(values[2])
        entry.update(repository_status="unavailable", repository=None, repository_last_success_at=None,
                     release_status="not_checked", release=None, release_last_success_at=None, error_code="repository_not_found")
        row = self.build(values)["records"]["v2rayng"]
        self.assertEqual(row["status"], "unknown")
        self.assertIsNone(row["source_checked_at"])
        self.assertIsNone(row["expires_at"])
        self.assertIsNone(row["repository"])

    def test_missing_repository_withholds_installation_but_preserves_previous_release(self):
        values = fixture(); entry = failed(values[2])
        entry.update(repository_status="unavailable", release_status="not_checked", error_code="repository_not_found",
                     repository_last_success_at=OLD, release_last_success_at=OLD)
        result = self.build(values); row = result["records"]["v2rayng"]
        self.assertEqual(row["status"], "stale")
        self.assertEqual(row["repository_availability"], "unavailable")
        self.assertEqual(row["installation_source_status"], "withheld")
        self.assertEqual(row["latest_release"]["tag_name"], "2.3.14")
        self.assertEqual(row["latest_release"]["checked_at"], OLD)
        self.assertEqual(row["availability_checked_at"], NOW)
        self.assertEqual(result["availability_counts"]["unavailable"], 1)
        entry.update(repository_status="ok", release_status="ok", error_code=None,
                     repository_last_success_at=NOW, release_last_success_at=NOW)
        values[2]["last_run"].update(ok_count=1,error_count=0)
        recovered = self.build(values)["records"]["v2rayng"]
        self.assertEqual(recovered["repository_availability"], "available")
        self.assertEqual(recovered["installation_source_status"], "requires_release_verification")
        self.assertIsNone(recovered["availability_notice"])

    def test_network_error_does_not_claim_repository_unavailable(self):
        values = fixture(); entry = failed(values[2])
        entry.update(repository_status="error", release_status="not_checked", error_code="network_error")
        row = self.build(values)["records"]["v2rayng"]
        self.assertEqual(row["repository_availability"], "unknown")
        self.assertEqual(row["installation_source_status"], "not_verified")

    def test_confirmed_no_release_is_different_from_failed_release(self):
        values = fixture(); entry = values[2]["repositories"][SLUG]
        entry.update(release_status="none", release=None)
        row = self.build(values)["records"]["v2rayng"]
        self.assertEqual(row["status"], "current")
        self.assertIsNone(row["latest_release"])
        self.assertEqual(row["source_checked_at"], NOW)

    def test_fresh_archived_metadata_does_not_mean_project_is_active(self):
        values = fixture(); values[2]["repositories"][SLUG]["repository"]["archived"] = True
        row = self.build(values)["records"]["v2rayng"]
        self.assertEqual(row["status"], "current")
        self.assertTrue(row["repository"]["archived"])
        self.assertNotIn("maintained", row)

    def test_upstream_rejects_new_private_metadata_and_preserves_last_public_success(self):
        previous = fixture()[2]["repositories"][SLUG]
        for flags in ({"private": True}, {"visibility": "private"}, {"visibility": "internal"}):
            with self.subTest(flags=flags):
                raw = dict(previous["repository"], **flags)
                class Client:
                    def fetch(self, slug, release=False):
                        if release:
                            raise AssertionError("must not query release of a private repository")
                        return raw
                result = freshness.upstream.update_repository(SLUG, previous, "2026-11-04T00:00:00Z", Client())
                self.assertEqual(result["repository_status"], "error")
                self.assertEqual(result["error_code"], "invalid_repository_response")
                self.assertEqual(result["repository"], previous["repository"])
                self.assertEqual(result["repository_last_success_at"], NOW)
                self.assertEqual(result["release"], previous["release"])
        self.assertEqual(freshness.upstream.repository_payload(previous["repository"], SLUG), previous["repository"])

    def test_unmonitored_record_does_not_receive_checked_today(self):
        row = self.build()["records"]["no-repository"]
        self.assertEqual(row["status"], "unmonitored")
        self.assertIsNone(row["last_attempt_at"])
        self.assertIsNone(row["source_checked_at"])
        self.assertEqual(row["knowledge_checked_at"], "2026-09-11")

    def test_unknown_repository_or_entity_mapping_is_rejected(self):
        for mutation in ("repository", "entity"):
            with self.subTest(mutation=mutation):
                values = fixture()
                if mutation == "repository":
                    values[2]["repositories"]["other/unknown"] = values[2]["repositories"].pop(SLUG)
                else:
                    values[1]["repositories"][0]["entity_ids"] = ["unreviewed-entity"]
                with self.assertRaises(freshness.upstream.ValidationError):
                    self.build(values)

    def test_arbitrary_release_url_and_future_observation_rejected(self):
        for mutation in ("url", "future"):
            with self.subTest(mutation=mutation):
                values = fixture(); entry = values[2]["repositories"][SLUG]
                if mutation == "url":
                    entry["release"]["html_url"] = "https://attacker.invalid/payload"
                else:
                    entry["repository_last_success_at"] = "2027-01-01T00:00:00Z"
                with self.assertRaises(freshness.upstream.ValidationError):
                    self.build(values)

    def test_verified_migration_keeps_provenance(self):
        values = fixture(); entry = values[2]["repositories"][SLUG];new = "official/new-name"
        entry["repository"].update(full_name=new, html_url="https://github.com/" + new)
        entry["release"]["html_url"] = "https://github.com/" + new + "/releases/tag/2.3.14"
        evidence = {"full_name": new, "checked_at": NOW, "api_redirect_chain":
                    ["https://api.github.com/repos/" + SLUG, "https://api.github.com/repos/" + new]}
        entry.update(repository_resolution=evidence, release_resolution=evidence)
        row = self.build(values)["records"]["v2rayng"]
        self.assertEqual(row["requested_repository"], SLUG)
        self.assertEqual(row["repository"]["full_name"], new)
        self.assertEqual(row["status"], "current")
        self.assertEqual(row["repository_resolution"], evidence)


class CLITests(unittest.TestCase):
    def write_inputs(self, root):
        result = []
        for name, value in zip(("library", "manifest", "state"), fixture()):
            path = root / (name + ".json"); path.write_text(json.dumps(value)); result.extend(["--" + name, str(path)])
        return result

    def test_failed_projection_keeps_previous_success_file_and_sanitizes_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); args = self.write_inputs(root)
            output = root / "freshness.json"; output.write_bytes(b"previous successful snapshot")
            (root / "state.json").write_text('{"secret":"DO-NOT-LOG-THIS"}')
            stream = io.StringIO()
            with redirect_stderr(stream), patch.dict("os.environ", {"GITHUB_TOKEN": "DO-NOT-LOG-TOKEN"}):
                code = freshness.main(args + ["--output", str(output), "--as-of", NOW])
            self.assertEqual(code, 1)
            self.assertEqual(output.read_bytes(), b"previous successful snapshot")
            self.assertEqual(json.loads(stream.getvalue()), {"ok": False, "error_code": "freshness_projection_failed"})

    def test_cannot_overwrite_authored_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); args = self.write_inputs(root); library = root / "library.json"; before = library.read_bytes()
            with redirect_stderr(io.StringIO()):
                self.assertEqual(freshness.main(args + ["--output", str(library), "--as-of", NOW]), 1)
            self.assertEqual(library.read_bytes(), before)

    def test_cli_success_does_not_need_network_or_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); args = self.write_inputs(root); output = root / "freshness.json"
            with patch.object(freshness.upstream.APIClient, "fetch", side_effect=AssertionError("network access")), redirect_stdout(io.StringIO()):
                self.assertEqual(freshness.main(args + ["--output", str(output), "--as-of", NOW]), 0)
            result = json.loads(output.read_text())
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(set(result["input_sha256"]), {"library", "manifest", "upstream"})


if __name__ == "__main__":
    unittest.main()
