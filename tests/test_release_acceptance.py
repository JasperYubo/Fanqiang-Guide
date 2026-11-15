"""Release acceptance must fail closed for incomplete or unrelated evidence."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("release_acceptance", Path(__file__).resolve().parents[1] / "developer/release_acceptance.py")
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)


def accepted_fixture():
    expected = {"source_sha": "a" * 40, "installer_sha256": "b" * 64, "candidate_version": "1.2.0",
                "run_id": "123456789", "run_attempt": 1}
    previous = {"source_sha": "c" * 40, "installer_sha256": "d" * 64, "version": "1.2.0", "release_id": 45}
    report = {"schema_version": 1, "kind": a.KIND, **expected, "platform": "linux", "passed": True,
              "skipped": 0, "fresh_install": {**{field: True for field in a.FRESH_CHECKS},
                  "doctor_checks": {**{field: True for field in a.DOCTOR_REQUIRED_CHECKS}, "swap": False}}, "upgrades": []}
    for role, baseline in {**a.LEGACY_BASELINES, "previous-stable": previous}.items():
        report["upgrades"].append({**{field: True for field in a.UPGRADE_CHECKS},
                                  "doctor_checks": {**{field: True for field in a.DOCTOR_REQUIRED_CHECKS}, "swap": False},
                                  "preserved": {field: True for field in a.PRESERVED_CHECKS},
                                  "roles": [role], "baseline_source_sha": baseline["source_sha"],
                                  "baseline_installer_sha256": baseline["installer_sha256"],
                                  "from_version": baseline["version"], "to_version": expected["candidate_version"],
                                  **({"baseline_release_id": previous["release_id"]} if role == "previous-stable" else {})})
    return report, expected, previous


class ReleaseAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.report, self.expected, self.previous = accepted_fixture()

    def validate(self, report=None, expected=None, previous=None):
        return a.validate_report(self.report if report is None else report,
                                 self.expected if expected is None else expected,
                                 self.previous if previous is None else previous)

    def test_complete_linux_report_passes_without_mutating_input(self):
        before = copy.deepcopy((self.report, self.expected, self.previous))
        summary = self.validate()
        self.assertEqual(summary["upgrade_cases"], 3)
        self.assertEqual(set(summary["upgrade_roles"]), a.REQUIRED_ROLES)
        self.assertEqual(summary["previous_stable"], self.previous)
        self.assertEqual(summary["source_sha"], self.expected["source_sha"])
        self.assertEqual(before, (self.report, self.expected, self.previous))

    def test_every_root_identity_is_mandatory_and_bound(self):
        for name in self.expected:
            for value in (None, "unrelated", True):
                with self.subTest(name=name, value=value):
                    report = copy.deepcopy(self.report)
                    report[name] = value
                    with self.assertRaises(a.AcceptanceError):
                        self.validate(report)

    def test_stale_report_for_same_installer_is_rejected(self):
        expected = dict(self.expected, source_sha="f" * 40)
        with self.assertRaisesRegex(a.AcceptanceError, "source_sha_mismatch"):
            self.validate(expected=expected)

    def test_expected_identity_is_strictly_typed(self):
        for name, values in {"run_id": [123, "0", "01", "1.0", "local"],
                             "run_attempt": [0, True, "1", 1.0],
                             "source_sha": ["A" * 40, "a" * 39, None],
                             "installer_sha256": ["g" * 64, "b" * 63, None],
                             "candidate_version": ["v1.2.0", "01.2.0", "1.2", "1.2.0-beta"]}.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    expected = dict(self.expected, **{name: value})
                    with self.assertRaises(a.AcceptanceError):
                        self.validate(expected=expected)

    def test_root_status_schema_platform_and_skipped_must_pass(self):
        for name, values in {"passed": [False, 1, "true", None], "schema_version": [True, "1", 2, None],
                             "kind": ["fixture", None], "platform": ["windows", None],
                             "skipped": [True, False, "0", 0.0, 1, None]}.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    report = copy.deepcopy(self.report)
                    report[name] = value
                    with self.assertRaises(a.AcceptanceError):
                        self.validate(report)

    def test_development_report_cannot_be_published(self):
        for value in (True, "false", 0, 1, None):
            with self.subTest(value=value):
                report = dict(self.report, development_only=value)
                with self.assertRaisesRegex(a.AcceptanceError, "development_only"):
                    self.validate(report)
        self.assertTrue(self.validate(dict(self.report, development_only=False))["passed"])

    def test_every_fresh_install_observation_is_required(self):
        for name in a.FRESH_CHECKS:
            for value in (False, 1, "true", None):
                with self.subTest(name=name, value=value):
                    report = copy.deepcopy(self.report)
                    report["fresh_install"][name] = value
                    with self.assertRaises(a.AcceptanceError):
                        self.validate(report)
        with self.assertRaisesRegex(a.AcceptanceError, "fresh_install_missing"):
            self.validate(dict(self.report, fresh_install=None))

    def test_failed_or_wrong_version_fresh_install_rejected_even_when_upgrades_pass(self):
        report = copy.deepcopy(self.report)
        report["fresh_install"]["installed_version"] = "1.1.0"
        with self.assertRaisesRegex(a.AcceptanceError, "fresh_install_version_mismatch"):
            self.validate(report)

    def test_every_upgrade_observation_is_required_for_every_baseline(self):
        for index in range(3):
            for name in a.UPGRADE_CHECKS:
                for value in (False, 1, "true", None):
                    with self.subTest(index=index, name=name, value=value):
                        report = copy.deepcopy(self.report)
                        report["upgrades"][index][name] = value
                        with self.assertRaises(a.AcceptanceError):
                            self.validate(report)

    def test_each_protected_file_must_be_preserved_for_every_baseline(self):
        for index in range(3):
            for name in a.PRESERVED_CHECKS:
                for value in (False, 1, "true", None):
                    with self.subTest(index=index, name=name, value=value):
                        report = copy.deepcopy(self.report)
                        report["upgrades"][index]["preserved"][name] = value
                        with self.assertRaises(a.AcceptanceError):
                            self.validate(report)

    def test_doctor_must_have_all_required_checks_true_for_every_case(self):
        for index in range(-1, 3):
            for name in a.DOCTOR_REQUIRED_CHECKS:
                for value in (False, 1, "true", None):
                    with self.subTest(index=index, name=name, value=value):
                        report = copy.deepcopy(self.report)
                        case = report["fresh_install"] if index == -1 else report["upgrades"][index]
                        case["doctor_checks"][name] = value
                        with self.assertRaises(a.AcceptanceError):
                            self.validate(report)

    def test_missing_or_empty_doctor_checks_cannot_be_masked_by_services_healthy(self):
        for index in range(-1, 3):
            for value in (None, {}, [], True):
                with self.subTest(index=index, value=value):
                    report = copy.deepcopy(self.report)
                    case = report["fresh_install"] if index == -1 else report["upgrades"][index]
                    case["doctor_checks"] = value
                    with self.assertRaises(a.AcceptanceError):
                        self.validate(report)

    def test_no_swap_is_allowed_but_optional_doctor_status_still_must_be_boolean(self):
        self.assertTrue(self.validate()["passed"])
        report = copy.deepcopy(self.report)
        report["fresh_install"]["doctor_checks"]["swap"] = "false"
        with self.assertRaisesRegex(a.AcceptanceError, "doctor_check_type_invalid"):
            self.validate(report)

    def test_missing_upgrade_or_preserved_object_rejected(self):
        for value in ([], None, {}, "passed"):
            with self.subTest(value=value):
                with self.assertRaises(a.AcceptanceError):
                    self.validate(dict(self.report, upgrades=value))
        report = copy.deepcopy(self.report)
        del report["upgrades"][1]["preserved"]
        with self.assertRaises(a.AcceptanceError):
            self.validate(report)

    def test_roles_must_cover_all_supported_baselines_exactly_once(self):
        for roles in ([], "legacy-1.0", ["other"], ["legacy-1.0", "legacy-1.0"], [None], [{}], ["legacy-1.1"]):
            with self.subTest(roles=roles):
                report = copy.deepcopy(self.report)
                report["upgrades"][0]["roles"] = roles
                with self.assertRaises(a.AcceptanceError):
                    self.validate(report)
        for index in range(3):
            report = copy.deepcopy(self.report)
            del report["upgrades"][index]
            with self.assertRaisesRegex(a.AcceptanceError, "roles_incomplete"):
                self.validate(report)

    def test_all_baseline_source_digest_and_versions_are_pinned(self):
        for index in range(3):
            for name, value in (("baseline_source_sha", "f" * 40), ("baseline_installer_sha256", "f" * 64),
                                ("from_version", "1.0.1"), ("to_version", "1.3.0")):
                with self.subTest(index=index, name=name):
                    report = copy.deepcopy(self.report)
                    report["upgrades"][index][name] = value
                    with self.assertRaises(a.AcceptanceError):
                        self.validate(report)

    def test_previous_release_id_is_bound_and_not_a_boolean(self):
        for value in (True, "45", None, 0, 46):
            with self.subTest(value=value):
                report = copy.deepcopy(self.report)
                report["upgrades"][-1]["baseline_release_id"] = value
                with self.assertRaises(a.AcceptanceError):
                    self.validate(report)

    def test_previous_baseline_must_come_from_caller(self):
        for previous in (None, {}, [], {**self.previous, "release_id": True},
                         {**self.previous, "version": "invalid"}, {**self.previous, "source_sha": "invalid"}):
            with self.subTest(previous=previous):
                with self.assertRaises(a.AcceptanceError):
                    a.validate_report(self.report, self.expected, previous)

    def test_previous_release_moving_during_publication_rejects_old_report(self):
        previous = {**self.previous, "release_id": 46, "source_sha": "e" * 40}
        with self.assertRaises(a.AcceptanceError):
            self.validate(previous=previous)

    def test_shared_role_case_allowed_only_when_sources_are_identical(self):
        previous = {**a.LEGACY_BASELINES["legacy-1.1"], "release_id": 45}
        report = copy.deepcopy(self.report)
        report["upgrades"].pop()
        report["upgrades"][-1]["roles"].append("previous-stable")
        report["upgrades"][-1]["baseline_release_id"] = 45
        self.assertEqual(self.validate(report, previous=previous)["upgrade_cases"], 2)
        with self.assertRaisesRegex(a.AcceptanceError, "baseline_identity_mismatch"):
            self.validate(report)

    def test_case_skip_is_rejected_even_when_root_claims_zero(self):
        for value in (1, True, False, "0"):
            for slot in ("fresh_install", "upgrades"):
                with self.subTest(slot=slot, value=value):
                    report = copy.deepcopy(self.report)
                    case = report[slot] if slot == "fresh_install" else report[slot][0]
                    case["skipped"] = value
                    with self.assertRaises(a.AcceptanceError):
                        self.validate(report)

    def test_version_downgrade_is_rejected(self):
        report = copy.deepcopy(self.report)
        previous = {**self.previous, "version": "2.0.0"}
        report["upgrades"][-1]["from_version"] = previous["version"]
        with self.assertRaisesRegex(a.AcceptanceError, "version_downgrade"):
            self.validate(report, previous=previous)

    def test_malformed_inputs_raise_controlled_errors(self):
        for report in (None, [], True, "report"):
            with self.subTest(report=report):
                with self.assertRaises(a.AcceptanceError):
                    a.validate_report(report, self.expected, self.previous)
        for expected in (None, [], True, "expected"):
            with self.subTest(expected=expected):
                with self.assertRaises(a.AcceptanceError):
                    a.validate_report(self.report, expected, self.previous)


if __name__ == "__main__":
    unittest.main()
