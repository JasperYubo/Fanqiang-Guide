import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from freshness import SourceFreshness

class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state.json"
        self.now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        self.data = {"schema_version": 1, "generated_at": "2026-11-02T10:00:00Z",
            "records": {"v2rayng": {"status": "current", "expires_at": "2026-11-04T10:00:00Z",
                "source_checked_at": "2026-11-02T10:00:00Z", "knowledge_checked_at": "2026-09-11",
                "latest_release": {"tag_name": "example-v1"}}}}
        self.write(self.data)
        self.source = SourceFreshness(self.path, clock=lambda: self.now)

    def write(self, value):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value))
        tmp.replace(self.path)

    def test_expires_without_a_restart_or_claiming_knowledge_was_updated(self):
        self.assertEqual(self.source.for_record("v2rayng")["status"], "current")
        self.now = datetime(2026, 11, 5, tzinfo=timezone.utc)
        result = self.source.for_record("v2rayng")
        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["knowledge_checked_at"], "2026-09-11")
        self.assertTrue(result["does_not_revalidate_compatibility"])

    def test_atomic_new_snapshot_is_visible_without_restarting(self):
        self.data["generated_at"] = "2026-11-02T11:00:00Z"
        self.data["records"]["v2rayng"]["latest_release"]["tag_name"] = "example-v2"
        self.write(self.data)
        self.assertEqual(self.source.for_record("v2rayng")["latest_release"]["tag_name"], "example-v2")

    def test_unavailable_snapshot_recovers_without_restart(self):
        row = self.data["records"]["v2rayng"]
        row.update(repository_availability="unavailable", installation_source_status="withheld")
        self.write(self.data)
        self.assertEqual(self.source.unavailable_ids(), frozenset({"v2rayng"}))
        row.update(repository_availability="available", installation_source_status="requires_release_verification")
        self.data["generated_at"] = "2026-11-02T11:00:00Z"
        self.write(self.data)
        self.assertEqual(self.source.unavailable_ids(), frozenset())

    def test_failed_probe_cannot_clear_reviewed_unavailable_source(self):
        reviewed={"v2rayng":"2026-11-01","missing":"2026-11-01"}
        row=self.data["records"]["v2rayng"]
        row.update(repository_status="error",error_code="network_error",repository_availability="unknown")
        self.write(self.data)
        self.assertEqual(self.source.unavailable_ids(reviewed),frozenset(reviewed))
        row.update(repository_status="ok",error_code=None,repository_availability="available",repository={"checked_at":"2026-11-02T11:00:00Z"})
        self.data["generated_at"]="2026-11-02T11:00:00Z";self.write(self.data)
        self.assertEqual(self.source.unavailable_ids(reviewed),frozenset({"missing"}))

    def test_old_success_or_missing_timestamp_cannot_override_later_unavailable_review(self):
        reviewed={"v2rayng":"2026-11-02"}
        row=self.data["records"]["v2rayng"]
        row.update(repository_status="ok",repository_availability="available")
        for checked in (None,"2026-11-01T11:00:00Z","2026-11-02T23:59:59Z"):
            with self.subTest(checked=checked):
                row["repository"]={"checked_at":checked};self.write(self.data)
                self.assertEqual(self.source.unavailable_ids(reviewed),frozenset({"v2rayng"}))
        row["repository"]={"checked_at":"2026-11-03T00:00:00Z"};self.write(self.data)
        self.assertEqual(self.source.unavailable_ids(reviewed),frozenset())
        precise={"v2rayng":"2026-11-03T00:00:00Z"}
        self.assertEqual(self.source.unavailable_ids(precise),frozenset({"v2rayng"}))
        row["repository"]={"checked_at":"2026-11-03T00:00:01Z"};self.write(self.data)
        self.assertEqual(self.source.unavailable_ids(precise),frozenset())

    def test_utc_success_must_follow_exact_review_observation_despite_local_date(self):
        reviewed={"v2rayng":"2026-11-09T00:05:04.443766+00:00"}
        row=self.data["records"]["v2rayng"]
        row.update(repository_status="ok",repository_availability="available")
        for checked in ("2026-11-09T00:01:00Z","2026-11-09T00:05:04.443766Z"):
            row["repository"]={"checked_at":checked};self.write(self.data)
            self.assertEqual(self.source.unavailable_ids(reviewed),frozenset({"v2rayng"}))
        row["repository"]={"checked_at":"2026-11-09T00:05:04.443767Z"};self.write(self.data)
        self.assertEqual(self.source.unavailable_ids(reviewed),frozenset())

    def test_bad_json_shapes_keep_last_success(self):
        for invalid in ([], "secret-probe", None, {}, {"schema_version": 1, "records": {}},
                {**self.data, "records": {"v2rayng": {"status": "invented"}}}):
            self.write(invalid)
            result = self.source.for_record("v2rayng")
            self.assertEqual(result["latest_release"]["tag_name"], "example-v1")
            self.assertIn("snapshot_load_status", result)
            self.assertNotIn("secret-probe", json.dumps(result))

    def test_older_snapshot_cannot_replace_newer_success(self):
        self.data["generated_at"] = "2026-11-01T10:00:00Z"
        self.data["records"]["v2rayng"]["latest_release"]["tag_name"] = "example-old"
        self.write(self.data)
        self.assertEqual(self.source.for_record("v2rayng")["latest_release"]["tag_name"], "example-v1")

    def test_missing_and_symlink_state_keep_last_success(self):
        self.path.unlink()
        self.assertEqual(self.source.summary()["snapshot_load_status"], "latest_snapshot_unavailable_using_last_valid")
        other = self.path.with_name("other.json")
        other.write_text(json.dumps(self.data))
        self.path.symlink_to(other)
        self.assertEqual(self.source.for_record("v2rayng")["latest_release"]["tag_name"], "example-v1")
        self.assertIn("snapshot_load_status", self.source.for_record("v2rayng"))

    def test_public_data_is_copied_and_unknown_is_explicit(self):
        result = self.source.public_snapshot()
        result["records"]["v2rayng"]["latest_release"].clear()
        self.assertEqual(self.source.for_record("v2rayng")["latest_release"]["tag_name"], "example-v1")
        self.assertEqual(self.source.for_record("not-monitored")["status"], "unmonitored")

if __name__ == "__main__":
    unittest.main()
