"""Offline regressions over the committed router evidence; no network/cache dependency."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import unittest
from unittest.mock import patch

from router_matching import RouterMatcher, RouterValidationError, normalize_router_query

class RouterMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matcher=RouterMatcher()
        cls.data=cls.matcher.data
    def base(self,**extra):
        values={"router_model":"RT-AX86U","firmware_family":"koolcenter-merlin-mod",
                "firmware_branch":"3004.388","firmware_version":"388.12_2",
                "architecture":"aarch64","kernel":"4.1.52","protocol":"trojan"}
        values.update(extra);return values
    def query(self,**extra):
        return self.matcher.query(self.base(**extra))
    def packages(self,result):
        return [p for c in result["candidates"] for p in c["fancyss"]["packages"]]

    def test_committed_primary_evidence_is_pinned_and_scoped(self):
        self.assertEqual(len(self.data["rows"]),56)
        self.assertEqual(len(self.data["packages"]),14)
        self.assertEqual(len(self.data["platforms"]),7)
        self.assertTrue(self.data["not_device_tested"])
        self.assertRegex(self.data["fancyss_commit"],r"^[a-f0-9]{40}$")
        for package in self.data["packages"].values():
            self.assertIn("/"+self.data["fancyss_commit"]+"/",package["download_url"])
            self.assertTrue(package["manifest_md5_matches"])
            self.assertTrue(package["archive_metadata_matches"])
            self.assertRegex(package["sha256"],r"^[a-f0-9]{64}$")
            self.assertRegex(package["author_md5"],r"^[a-f0-9]{32}$")
            self.assertFalse(package["executed"])
            self.assertFalse(package["device_tested"])
            self.assertGreater(package["unpacked_file_bytes"],package["bytes"])
    def test_evidence_timestamps_are_actual_not_future(self):
        now=datetime.now(timezone.utc)
        entries=[self.data,*self.data["sources"].values(),*self.data["packages"].values()]
        for entry in entries:
            self.assertLessEqual(datetime.fromisoformat(entry["checked_at"].replace("Z","+00:00")),now)
    def test_known_ordinary_protocol_prefers_lite(self):
        result=self.query()
        self.assertEqual(result["status"],"matched")
        self.assertEqual([(p["platform"],p["variant"]) for p in self.packages(result)],[("hnd_v8","lite")])
        self.assertEqual(result["combination_status"],"not_tested")
        self.assertTrue(any(u["code"]=="source_revision_scope_unspecified" for u in result["unknowns"]))
        self.assertTrue(all(c["status"]=="not_observed_by_service" for c in result["local_prechecks"]))
    def test_naiveproxy_and_tuic_require_full(self):
        for protocol in ("naiveproxy","tuic"):
            with self.subTest(protocol=protocol):
                result=self.query(protocol=protocol)
                self.assertEqual([p["variant"] for p in self.packages(result)],["full"])
                rejected=self.query(protocol=protocol,package_variant="lite")
                self.assertEqual(rejected["status"],"conflict")
                self.assertFalse(self.packages(rejected))
                self.assertIn("protocol_excluded_from_lite",[c["code"] for c in rejected["conflicts"]])
    def test_protocol_aliases_do_not_lose_specificity(self):
        for value,canonical in (("ss","shadowsocks"),("shadowsocksr","ssr"),("hy2","hysteria2"),("vless+reality","vless-reality")):
            self.assertEqual(normalize_router_query({"protocol":value})["protocol"],canonical)
    def test_unknown_or_compound_protocol_does_not_become_vless_match(self):
        for protocol in ("vless-reality","wireguard","synthetic-secret"):
            with self.subTest(protocol=protocol):
                result=self.query(protocol=protocol)
                self.assertEqual(result["status"],"candidate")
                self.assertIn("protocol_combination_not_documented",[u["code"] for u in result["unknowns"]])
                self.assertEqual({p["variant"] for p in self.packages(result)},{"full","lite"})
                if protocol=="synthetic-secret":self.assertNotIn(protocol,json.dumps(result))
    def test_missing_protocol_exposes_choice_without_choosing(self):
        result=self.query(protocol=None)
        self.assertEqual(result["status"],"candidate")
        self.assertEqual({p["variant"] for p in self.packages(result)},{"full","lite"})
    def test_model_pro_and_separator_are_not_fuzzy(self):
        result=self.matcher.query({"router_model":"RT-AX86U_PRO"})
        self.assertTrue(result["candidates"])
        self.assertEqual({c["router_model"] for c in result["candidates"]},{"RT-AX86U PRO"})
        for model in ("RTAX86UPRO","RT-AX86UPRO","RT-AX86U V2","synthetic-private-probe"):
            r=self.matcher.query({"router_model":model})
            self.assertEqual(r["status"],"no_record")
            self.assertFalse(r["candidates"])
            self.assertNotIn(model,json.dumps(r))
    def test_case_and_outer_whitespace_only(self):
        self.assertEqual(normalize_router_query({"router_model":"  rt-ax86u  "})["router_model"],"RT-AX86U")
        self.assertEqual(normalize_router_query({"router_model":"RT-AX86U  PRO"})["router_model"],"RT-AX86U  PRO")
        self.assertEqual(self.matcher.query({"router_model":"RT-AX86U  PRO"})["status"],"no_record")
    def test_explicit_v2_exclusion_cannot_be_bypassed_by_numeric_spelling(self):
        for revision in ("V2","2","2.0","V2.0","V02","V2.00"):
            r=self.query(router_model="RT-AX58U",hardware_revision=revision,architecture="armv7l")
            self.assertEqual(r["status"],"conflict",revision)
            self.assertFalse(self.packages(r),revision)
            self.assertIn("publisher_excluded_revision",[c["code"] for c in r["conflicts"]])
        self.assertEqual(normalize_router_query({"hardware_revision":"A2"})["hardware_revision"],"A2")
    def test_stock_original_and_gnuton_do_not_inherit_software_center(self):
        for family in ("asuswrt","asuswrt-merlin","asuswrt-merlin-gnuton"):
            r=self.query(firmware_family=family)
            self.assertEqual(r["status"],"conflict")
            self.assertFalse(r["candidates"])
    def test_known_firmware_without_plugin_row_is_missing_evidence(self):
        r=self.query(router_model="TUF-AX3000",firmware_version="388.10_2",architecture="armv7l")
        self.assertEqual(r["status"],"insufficient_evidence")
        self.assertFalse(self.packages(r))
        self.assertTrue(r["firmware_candidates"])
        self.assertIn("plugin_family_not_documented",[u["code"] for u in r["unknowns"]])
    def test_runtime_abi_and_kernel_gate_reject_wrong_package(self):
        for change in ({"architecture":"armv7l"},{"kernel":"5.4.213"},{"architecture":"x86_64"}):
            r=self.query(**change)
            self.assertEqual(r["status"],"conflict")
            self.assertFalse(self.packages(r))
    def test_unknown_branch_is_not_asserted_unsupported(self):
        r=self.query(firmware_branch="3004.384",firmware_version="384.13_0")
        self.assertEqual(r["status"],"candidate")
        self.assertFalse(r["conflicts"])
        self.assertIn("published_branch_not_in_observed_scope",[u["code"] for u in r["unknowns"]])
    def test_legacy_pre_384_firmware_is_not_a_candidate(self):
        for branch,version in (("380","380.70"),("3004.382","3.0.0.4_382_50010")):
            r=self.query(firmware_branch=branch,firmware_version=version)
            self.assertEqual(r["status"],"conflict")
            self.assertFalse(self.packages(r))
            self.assertIn("below_documented_minimum",[c["code"] for c in r["conflicts"]])
    def test_known_build_in_wrong_branch_blocks_package(self):
        r=self.query(router_model="RT-AX86U PRO",firmware_branch="3004.388",firmware_version="102.9_0",kernel="4.19.183",protocol="vless")
        self.assertEqual(r["status"],"conflict")
        self.assertFalse(self.packages(r))
        self.assertIn("known_build_branch_conflict",[c["code"] for c in r["conflicts"]])
    def test_matching_historical_build_remains_a_candidate(self):
        r=self.query(router_model="RT-AX86U PRO",firmware_branch="3004.388",firmware_version="388.8_4",kernel="4.19.183",protocol="vless")
        self.assertEqual(r["status"],"candidate")
        self.assertTrue(self.packages(r))
        self.assertFalse(r["conflicts"])
        self.assertIn("historical_build_scope",[u["code"] for u in r["unknowns"]])
    def test_missing_values_remain_unknown(self):
        r=self.matcher.query({"router_model":"RT-AX86U"})
        self.assertEqual(r["status"],"candidate")
        fields={u["field"] for u in r["unknowns"]}
        self.assertTrue({"architecture","kernel","firmware_family","firmware_branch","firmware_version"}.issubset(fields))
    def test_ipq_platforms_are_distinct(self):
        bd4=self.matcher.query({"router_model":"ZenWiFi_BD4","architecture":"armv7l","kernel":"5.4.213","protocol":"trojan"})
        self.assertEqual({p["platform"] for p in self.packages(bd4)},{"ipq32"})
        pending=self.matcher.query({"router_model":"TUF-BE6500","architecture":"aarch64","kernel":"5.4.213","protocol":"trojan"})
        self.assertEqual(pending["status"],"insufficient_evidence")
        self.assertFalse(self.packages(pending))
        observed=self.matcher.query({"router_model":"TUF-BE6500","device_model_id":"TUF_6500","architecture":"aarch64","kernel":"5.4.213","protocol":"trojan"})
        self.assertEqual({p["platform"] for p in self.packages(observed)},{"ipq64"})
        self.assertEqual(observed["status"],"candidate")
    def test_same_platform_different_actual_model_is_conflict(self):
        for marketing,observed in (("TX-AX6000","GS7"),("TX-AX6000","TUF-AX4200Q"),("ZenWiFi_BD4","TUF_6500"),("RT-AX86U","RT-AX86U_PRO")):
            r=self.matcher.query({"router_model":marketing,"device_model_id":observed,"protocol":"trojan"})
            self.assertEqual(r["status"],"conflict",(marketing,observed))
            self.assertFalse(self.packages(r))
    def test_missing_model_never_lists_all_devices(self):
        r=self.matcher.query({})
        self.assertEqual(r["status"],"insufficient_evidence")
        self.assertFalse(r["candidates"])
    def test_validation_is_fixed_and_does_not_echo_secret_values(self):
        cases=[{"subscription":"synthetic-private-probe"},{"router_model":"https://private.example/secret"},
               {"router_model":["synthetic-private-probe"]},{"kernel":"synthetic-private-probe"},
               {"firmware_family":"synthetic-private-probe"},{"firmware_branch":"3;synthetic-private-probe"},
               {"device_model_id":"synthetic-private-probe\nline"},{"architecture":True},
               {"package_variant":None},{"protocol":"a"*33},{"router_model":"a"*65}]
        for args in cases:
            with self.subTest(args=list(args)):
                with self.assertRaises(RouterValidationError) as caught:normalize_router_query(args)
                self.assertNotIn("synthetic-private-probe",str(caught.exception))
    def test_query_does_not_access_network_or_mutate_evidence(self):
        before=json.dumps(self.matcher.data,sort_keys=True)
        with patch.object(socket,"create_connection",side_effect=AssertionError("no network")):
            result=self.query()
        result["candidates"][0]["firmware"]["branches"].append("unexpected")
        result["candidates"][0]["fancyss"]["packages"][0]["sha256"]="changed"
        self.assertEqual(before,json.dumps(self.matcher.data,sort_keys=True))
    def test_current_release_and_historical_directory_are_distinguished(self):
        r=self.query()
        firm=r["candidates"][0]["firmware"]
        self.assertIn("3004.388",firm["current_branches"])
        self.assertIn("access_restricted",firm["download_visibility"])
        self.assertEqual(firm["branch_scope"],"observed_release_sources_not_exhaustive_compatibility_range")
        historical=[s for s in self.data["sources"].values() if s.get("scope")=="exact_model_public_mirror_directory"]
        self.assertTrue(historical)
        self.assertTrue(all(s["not_latest_release_guarantee"] for s in historical))
    def test_every_row_source_resolves(self):
        for row in self.data["rows"]:
            self.assertEqual(len(row["source_ids"]),len(set(row["source_ids"])))
            for key in row["source_ids"]:self.assertIn(key,self.data["sources"])
            self.assertIn(row["package_platform"],self.data["platforms"])

if __name__=="__main__":unittest.main()
