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


def accepted_network_fixture():
    report, expected, previous = accepted_fixture()
    report['candidate_version'] = expected['candidate_version'] = '1.3.0'
    report['fresh_install']['installed_version'] = '1.3.0'
    report['fresh_install']['network_features'] = {field: True for field in a.NETWORK_FEATURE_CHECKS}
    for case in report['upgrades']:
        case['to_version'] = '1.3.0'
        case.update({field: True for field in a.NETWORK_TIMER_CHECKS})
        case['preserved'] = {field: True for field in a.NETWORK_PRESERVED_CHECKS}
        before = {field: {'exists': True, 'sha256': 'a'*64, 'mode': 0o600, 'uid':0, 'gid':0} for field in a.NETWORK_PRESERVED_CHECKS}
        case['preservation_checks'] = {'before': before, 'after': copy.deepcopy(before)}
    unconfigured = copy.deepcopy(report['upgrades'][0])
    unconfigured.update({field: True for field in a.UNCONFIGURED_CHECKS})
    for side in ('before', 'after'):
        for name in ('network_config','egress_config'):
            unconfigured['preservation_checks'][side][name] = {'exists':False, 'sha256':None, 'mode':None, 'uid':None, 'gid':None}
    report['unconfigured_upgrade'] = unconfigured
    report['network_fault_tests'] = {'passed':True,'tests':100,'skipped':0,'suites':list(a.NETWORK_FAULT_SUITES)}
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



class NetworkReleaseAcceptanceTests(unittest.TestCase):
    def setUp(self): self.report, self.expected, self.previous = accepted_network_fixture()
    def validate(self): return a.validate_report(self.report,self.expected,self.previous)
    def test_complete_network_matrix_passes(self):
        result=self.validate();self.assertTrue(result['unconfigured_upgrade']);self.assertEqual(result['network_features'],list(a.NETWORK_FEATURE_CHECKS))
    def test_every_network_feature_is_mandatory(self):
        for name in a.NETWORK_FEATURE_CHECKS:
            for value in (None,False,1,'true'):
                with self.subTest(name=name,value=value):
                    self.setUp();self.report['fresh_install']['network_features'][name]=value
                    with self.assertRaises(a.AcceptanceError):self.validate()
    def test_network_proof_cannot_reuse_old_12_matrix(self):
        del self.report['fresh_install']['network_features']
        with self.assertRaises(a.AcceptanceError):self.validate()
    def test_unconfigured_upgrade_is_mandatory_and_pinned(self):
        for mutation in ('missing','wrong-source','preexisting-config','disabled-timer','claimed-configured'):
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation=='missing':del self.report['unconfigured_upgrade']
                elif mutation=='wrong-source':self.report['unconfigured_upgrade']['baseline_source_sha']='f'*40
                elif mutation=='preexisting-config':self.report['unconfigured_upgrade']['preservation_checks']['before']['network_config']['exists']=True
                elif mutation=='disabled-timer':self.report['unconfigured_upgrade']['network_timer_active']=False
                else:self.report['unconfigured_upgrade']['network_status_not_configured']=False
                with self.assertRaises(a.AcceptanceError):self.validate()
    def test_network_secret_preservation_is_mandatory(self):
        for name in ('network_config','egress_config'):
            with self.subTest(name=name):
                self.setUp();self.report['upgrades'][0]['preserved'][name]=False
                with self.assertRaises(a.AcceptanceError):self.validate()
    def test_boolean_claim_cannot_hide_changed_bytes_or_mode(self):
        for field,value in [('sha256','b'*64),('mode',0o640),('exists',False),('uid',1000),('gid',1000)]:
            with self.subTest(field=field):
                self.setUp();self.report['upgrades'][0]['preservation_checks']['after']['network_config'][field]=value
                with self.assertRaises(a.AcceptanceError):self.validate()
    def test_shared_readable_network_credentials_are_rejected(self):
        for side in ('before','after'):self.report['upgrades'][1]['preservation_checks'][side]['egress_config']['mode']=0o644
        with self.assertRaises(a.AcceptanceError):self.validate()
    def test_fault_suite_missing_skipped_or_empty_fails(self):
        for change in ('missing','empty','skipped','incomplete','failed'):
            with self.subTest(change=change):
                self.setUp()
                if change=='missing':del self.report['network_fault_tests']
                elif change=='empty':self.report['network_fault_tests']['tests']=0
                elif change=='skipped':self.report['network_fault_tests']['skipped']=1
                elif change=='incomplete':self.report['network_fault_tests']['suites'].pop()
                else:self.report['network_fault_tests']['passed']=False
                with self.assertRaises(a.AcceptanceError):self.validate()
    def test_missing_preservation_hashes_are_rejected(self):
        del self.report['upgrades'][2]['preservation_checks']
        with self.assertRaises(a.AcceptanceError):self.validate()

if __name__ == "__main__":
    unittest.main()
