"""Offline regression tests for evidence-scoped public structured queries."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from library_query import LibraryQuery, QueryValidationError, normalize_query


URL = "https://example.org/documentation"


def record(ident, kind="client", platforms=None, reviewed=True, relations=None):
    return {"id": ident, "name": ident, "kind": kind, "platforms": platforms or [],
            "relations": relations or [], "updated_at": "2026-01-01",
            "verification": {"status": "primary_reviewed" if reviewed else "reference_only",
                             "checked_at": "2026-01-02",
                             "reviewed_fields": ["platforms", "relations"],
                             "evidence_urls": [URL]},
            "source_claims": {"source_url": "https://directory.example/entry",
                              "captured_at": "2026-01-01", "lastUpdated": "2026-10-01"},
            "compatibility": {"notes": None}}


def relation(predicate, target, reviewed=True):
    value = {"predicate": predicate, "target_name": target, "evidence_url": URL}
    if reviewed:
        value["verification_status"] = "primary_reviewed"
    return value


def fixture():
    return [
        record("engine", "core", ["Android"], relations=[]),
        record("reality-engine", "core", ["Windows"], relations=[]),
        record("android-client", platforms=["Android"],
               relations=[relation("uses_core", "engine")]),
        record("windows-client", platforms=["Windows"]),
        record("reference-client", platforms=["Android"], reviewed=False),
        record("no-platform-client"),
        record("protocol-vless", "protocol",
               relations=[relation("documented_implementation", "engine")]),
        record("concept-tun", "concept",
               relations=[relation("documented_implementation", "engine")]),
        record("transport-reality", "transport",
               relations=[relation("documented_implementation", "reality-engine")]),
        record("not-a-client", "directory", ["Android"]),
    ]


def comparison(client="reference-client"):
    return {"version": "1", "checked_at": "2026-01-03", "rows": [
        {"client": client, "platform": "Android", "architecture": "arm64",
         "release_url": "https://example.org/releases/latest",
         "source_urls": ["https://example.org/releases/1"],
         "checked_at": "2026-01-03", "package_note": "Recheck selected release."}
    ]}


class StructuredQueryTests(unittest.TestCase):
    def setUp(self):
        self.records = fixture()
        self.query = LibraryQuery(self.records)

    def ids(self, params):
        return [row["id"] for row in self.query.query(params)["items"]]

    def test_unavailable_repository_is_withheld_before_pagination_and_can_be_inspected(self):
        missing = frozenset({"android-client"})
        default = self.query.query({"kind":"client", "platform":"Android", "limit":1}, unavailable_ids=missing)
        self.assertNotIn("android-client", [x["id"] for x in default["items"]])
        inspected = self.query.query({"kind":"client", "platform":"Android", "include_unknown":True, "limit":20}, unavailable_ids=missing)
        item = next(x for x in inspected["items"] if x["id"] == "android-client")
        self.assertEqual(item["match_status"], "unknown")
        self.assertTrue(any(c["reason"] == "original_repository_unavailable_do_not_install" for c in item["criteria"]))
        recovered = self.query.query({"kind":"client", "platform":"Android"}, unavailable_ids=frozenset())
        self.assertIn("android-client", [x["id"] for x in recovered["items"]])

    def test_scope_does_not_return_protocols_as_installable_tools(self):
        result = self.query.query({"limit": 20})
        self.assertEqual(result["total"], 6)
        self.assertNotIn("protocol-vless", self.ids({"limit": 20}))
        self.assertNotIn("not-a-client", self.ids({"limit": 20}))

    def test_kind_is_an_exact_and_filter_not_a_core_inheritance_shortcut(self):
        clients = self.query.query({"kind": "client", "limit": 20})
        self.assertEqual(clients["total"], 4)
        self.assertTrue(all(row["kind"] == "client" for row in clients["items"]))
        self.assertTrue(all(row["match_status"] == "matched" for row in clients["items"]))
        self.assertEqual(self.ids({"kind": "client", "platform": "android"}), ["android-client"])
        self.assertEqual(self.ids({"kind": "core", "platform": "android",
                                   "protocol": "vless", "feature": "tun"}), ["engine"])
        strict = self.query.query({"kind": "client", "platform": "android",
                                   "protocol": "vless", "feature": "tun"})
        self.assertEqual(strict["total"], 0)
        self.assertEqual(strict["excluded_unknown"], 3)
        expanded = self.query.query({"kind": "client", "platform": "android",
                                     "protocol": "vless", "feature": "tun",
                                     "include_unknown": True, "limit": 20})
        self.assertEqual(expanded["total"], 3)
        self.assertTrue(all(row["kind"] == "client" and row["match_status"] == "unknown"
                            for row in expanded["items"]))
        self.assertEqual(expanded["filters"]["kind"], "client")
        self.assertIn("router_plugin", expanded["available_filters"]["kind"])

    def test_kind_rejects_non_tool_kinds_and_private_values_safely(self):
        for value in ("protocol", "concept", "directory", "CLIENT", "client_app",
                      "synthetic-private-kind", ["client"], {"private": "synthetic-private-kind"}, True, 1):
            with self.subTest(kind=value):
                with self.assertRaises(QueryValidationError) as caught:
                    self.query.query({"kind": value})
                self.assertEqual(caught.exception.field, "kind")
                self.assertNotIn("synthetic-private-kind", str(caught.exception))
        self.assertEqual(self.ids({"kind": None}), self.ids({}))

    def test_platform_is_case_insensitive_but_not_version_inference(self):
        self.assertEqual(self.ids({"platform": "Android"}), ["android-client", "engine"])
        with self.assertRaises(QueryValidationError):
            self.query.query({"platform": "Android14"})

    def test_three_conditions_are_and(self):
        self.assertEqual(self.ids({"platform": "android", "protocol": "vless", "feature": "tun"}),
                         ["engine"])
        self.assertEqual(self.ids({"platform": "windows", "protocol": "vless", "feature": "tun"}), [])

    def test_core_capabilities_are_not_inherited_as_client_matches(self):
        strict = self.query.query({"protocol": "vless", "feature": "tun", "limit": 20})
        self.assertEqual([row["id"] for row in strict["items"]], ["engine"])
        expanded = self.query.query({"platform": "android", "protocol": "vless",
                                    "feature": "tun", "include_unknown": True, "limit": 20})
        client = next(row for row in expanded["items"] if row["id"] == "android-client")
        self.assertEqual(client["match_status"], "unknown")
        self.assertEqual([c["state"] for c in client["criteria"]], ["matched", "unknown", "unknown"])
        self.assertIn("core_documentation", client["criteria"][1]["reason"])
        self.assertEqual({s["record_id"] for s in client["criteria"][1]["sources"]},
                         {"android-client", "protocol-vless"})

    def test_unknown_is_opt_in_and_counts_are_reported(self):
        strict = self.query.query({"feature": "tun"})
        expanded = self.query.query({"feature": "tun", "include_unknown": True, "limit": 20})
        self.assertEqual(strict["total"], 1)
        self.assertEqual(strict["excluded_unknown"], 5)
        self.assertEqual(expanded["total"], 6)
        self.assertEqual(expanded["unknown_candidates"], 5)
        self.assertEqual(expanded["excluded_unknown"], 0)

    def test_documented_platform_omission_is_not_an_unsupported_claim(self):
        result = self.query.query({"platform": "android", "include_unknown": True, "limit": 20})
        self.assertNotIn("windows-client", [row["id"] for row in result["items"]])
        self.assertEqual(result["excluded_not_listed_platform"], 2)
        self.assertTrue(any("零结果不等于不支持" in note for note in result["notices"]))
        self.assertFalse(any("unsupported" in json.dumps(row) for row in result["items"]))

    def test_reference_platform_is_unknown(self):
        result = self.query.query({"platform": "android", "include_unknown": True, "limit": 20})
        row = next(row for row in result["items"] if row["id"] == "reference-client")
        self.assertEqual(row["criteria"][0]["state"], "unknown")
        self.assertEqual(row["criteria"][0]["sources"][0]["level"], "reference_only")

    def test_os_version_is_always_unknown_even_for_documented_platform(self):
        strict = self.query.query({"platform": "android", "os_version": "14"})
        self.assertEqual(strict["total"], 0)
        expanded = self.query.query({"platform": "android", "os_version": "14",
                                    "include_unknown": True, "limit": 20})
        for row in expanded["items"]:
            self.assertEqual(row["criteria"][-1]["state"], "unknown")
            self.assertEqual(row["combination_status"], "not_tested")

    def test_os_version_requires_platform_and_numeric_components(self):
        for params in ({"os_version": "14"}, {"platform": "android", "os_version": "Android 14"},
                       {"platform": "chrome", "os_version": "123"},
                       {"platform": "android", "os_version": 14},
                       {"platform": "android", "os_version": ""}):
            with self.subTest(params=params), self.assertRaises(QueryValidationError):
                self.query.query(params)

    def test_vless_reality_is_two_requirements_with_explicit_feature_preserved(self):
        result = self.query.query({"protocol": "VLESS-Reality", "feature": "tun",
                                   "include_unknown": True, "limit": 20})
        self.assertEqual(result["filters"]["protocol"], "vless")
        self.assertEqual(result["filters"]["required_features"], ["reality", "tun"])
        row = next(row for row in result["items"] if row["id"] == "engine")
        self.assertEqual([(c["field"], c["value"], c["state"]) for c in row["criteria"]],
                         [("protocol", "vless", "matched"), ("feature", "reality", "unknown"),
                          ("feature", "tun", "matched")])
        self.assertEqual(self.query.query({"protocol": "VLESS-Reality"})["total"], 0)

    def test_no_protocol_guessing_from_names_or_unreviewed_tags(self):
        data = fixture()
        data[2]["name"] = "VLESS TUN Android"
        data[2]["tags"] = ["vless", "tun"]
        query = LibraryQuery(data)
        self.assertEqual([row["id"] for row in query.query({"protocol": "vless"})["items"]], ["engine"])

    def test_invalid_enums_and_unknown_fields_have_safe_errors(self):
        for params in ({"protocol": "secret-token-not-a-protocol"}, {"feature": "secret-token"},
                       {"private_subscription": "secret-token"}, {"platform": "secret-token"}):
            with self.subTest(params=params):
                with self.assertRaises(QueryValidationError) as caught:
                    self.query.query(params)
                self.assertNotIn("secret-token", str(caught.exception))
                self.assertNotIn("private_subscription", str(caught.exception))

    def test_limit_offset_and_boolean_type_validation(self):
        for params in ({"limit": True}, {"limit": 0}, {"limit": 21}, {"limit": "10"},
                       {"offset": -1}, {"offset": 10001}, {"offset": False},
                       {"include_unknown": 1}, {"include_unknown": "true"}, [], "query"):
            with self.subTest(params=params), self.assertRaises(QueryValidationError):
                self.query.query(params)

    def test_stable_pagination_and_out_of_range_page(self):
        all_rows = self.ids({"limit": 20})
        paged = []
        for offset in (0, 2, 4):
            result = self.query.query({"limit": 2, "offset": offset})
            self.assertEqual(result["total"], len(all_rows))
            paged.extend(row["id"] for row in result["items"])
        self.assertEqual(all_rows, sorted(all_rows))
        self.assertEqual(paged, all_rows)
        last = self.query.query({"limit": 2, "offset": 4})
        self.assertIsNone(last["next_offset"])
        beyond = self.query.query({"offset": 1000})
        self.assertEqual(beyond["items"], [])
        self.assertEqual(beyond["total"], 6)

    def test_unknown_candidates_prioritize_documented_matches_then_id(self):
        params = {"platform": "android", "protocol": "vless", "feature": "tun",
                  "include_unknown": True, "limit": 20}
        result = self.query.query(params)
        self.assertEqual(result["ordering"], ["platform_matched_first", "matched_condition_count_desc", "id_asc"])
        self.assertEqual([row["id"] for row in result["items"][:2]], ["engine", "android-client"])
        self.assertEqual([row["matched_condition_count"] for row in result["items"][:2]], [3, 1])
        pages = []
        for offset in range(0, result["total"], 2):
            pages.extend(self.query.query({**params, "limit": 2, "offset": offset})["items"])
        self.assertEqual(pages, result["items"])

    def test_known_platform_precedes_more_capabilities_with_unknown_platform(self):
        records = fixture()
        records[0]["platforms"] = []
        query = LibraryQuery(records)
        result = query.query({"platform": "android", "protocol": "vless", "feature": "tun",
                              "include_unknown": True, "limit": 20})
        self.assertEqual([row["id"] for row in result["items"][:2]], ["android-client", "engine"])
        self.assertEqual([row["matched_condition_count"] for row in result["items"][:2]], [1, 2])
        result = query.query({"protocol": "vless", "feature": "tun", "include_unknown": True})
        self.assertEqual(result["items"][0]["id"], "engine")
        self.assertEqual(result["ordering"], ["matched_condition_count_desc", "id_asc"])

    def test_input_order_does_not_change_query_order(self):
        self.assertEqual(self.ids({"limit": 20}),
                         [row["id"] for row in LibraryQuery(list(reversed(self.records))).query({"limit": 20})["items"]])

    def test_result_and_constructor_inputs_are_isolated(self):
        self.records[0]["platforms"].append("Windows")
        result = self.query.query({"platform": "android"})
        result["items"][0]["criteria"][0]["sources"][0]["url"] = "https://changed.example"
        self.assertNotIn("https://changed.example", json.dumps(self.query.query({"platform": "android"})))
        self.assertNotIn("engine", self.ids({"platform": "windows"}))

    def test_comparison_adds_only_documented_platform_not_protocol_or_version(self):
        query = LibraryQuery(fixture(), comparison())
        result = query.query({"platform": "android"})
        row = next(row for row in result["items"] if row["id"] == "reference-client")
        self.assertEqual(row["criteria"][0]["state"], "matched")
        self.assertEqual(row["criteria"][0]["sources"][0]["checked_at"], "2026-01-03")
        self.assertEqual(query.query({"platform": "android", "protocol": "vless"})["total"], 1)

    def test_iphone_ipad_comparison_is_two_platform_families(self):
        table = comparison()
        table["rows"][0]["platform"] = "iPhone / iPad"
        query = LibraryQuery(fixture(), table)
        for platform in ("ios", "ipados"):
            self.assertIn("reference-client", [row["id"] for row in query.query({"platform": platform})["items"]])

    def test_dates_retain_distinct_meanings(self):
        row = self.query.query({"platform": "android"})["items"][0]
        self.assertEqual(row["last_updated"], "2026-01-01")
        self.assertEqual(row["checked_at"], "2026-01-02")
        self.assertNotEqual(row["last_updated"], "2026-10-01")
        self.assertEqual(row["combination_status"], "not_tested")

    def test_unreviewed_or_undated_relations_do_not_create_matches(self):
        for mode in ("unreviewed", "undated", "invalid_url"):
            records = fixture()
            topic = next(r for r in records if r["id"] == "protocol-vless")
            if mode == "unreviewed":
                topic["verification"]["status"] = "reference_only"
                topic["relations"][0].pop("verification_status")
            elif mode == "undated":
                topic["verification"]["checked_at"] = None
            else:
                topic["relations"][0]["evidence_url"] = "https://user:password@example.org/"
            self.assertEqual(LibraryQuery(records).query({"protocol": "vless"})["total"], 0)

    def test_malformed_data_rejected_before_queries(self):
        for records in (None, {}, fixture() + [fixture()[0]], [{"id": "x"}]):
            with self.subTest(records=type(records).__name__), self.assertRaises(ValueError):
                LibraryQuery(records)
        for table in ({}, {"rows": [{}]}, comparison("missing-client")):
            with self.subTest(table=table), self.assertRaises(ValueError):
                LibraryQuery(fixture(), table)

    def test_from_paths_is_local_and_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "library.json"
            table = Path(directory) / "comparison.json"
            library.write_text(json.dumps(fixture()), encoding="utf-8")
            table.write_text(json.dumps(comparison()), encoding="utf-8")
            query = LibraryQuery.from_paths(library, table)
            self.assertIn("reference-client", [row["id"] for row in query.query({"platform": "android"})["items"]])

    def test_canonical_aliases_are_explicit(self):
        self.assertEqual(normalize_query({"protocol": "SS"})["protocol"], "shadowsocks")
        self.assertEqual(normalize_query({"feature": "fake_ip"})["feature"], "fake-ip")
        self.assertEqual(normalize_query({"protocol": "vless_reality"})["required_features"], ["reality"])
        with self.assertRaises(QueryValidationError):
            normalize_query({"protocol": "reality"})
        with self.assertRaises(QueryValidationError):
            normalize_query({"protocol": "socks5"})

    def test_no_filters_do_not_claim_all_capabilities(self):
        row = self.query.query()["items"][0]
        self.assertEqual(row["match_status"], "not_filtered")
        self.assertEqual(row["criteria"], [])
        self.assertEqual(row["combination_status"], "not_tested")


class RealSnapshotTests(unittest.TestCase):
    def test_current_snapshot_scope_ids_and_android14_unknown(self):
        root = Path(__file__).resolve().parents[3]
        records = json.loads(Path(__file__).with_name("library.json").read_text())
        query = LibraryQuery(records, json.loads((root / "apps/site/content/client-comparison-v1.3-2026-09-12.json").read_text()))
        self.assertEqual(query.query()["scope"]["eligible_records"], 186)
        known_ids = {row["id"] for row in records}
        for offset in range(0, 186, 20):
            self.assertTrue({row["id"] for row in query.query({"offset": offset, "limit": 20})["items"]} <= known_ids)
        strict = query.query({"platform": "Android", "protocol": "VLESS-Reality",
                              "feature": "TUN", "os_version": "14"})
        self.assertEqual(strict["total"], 0)
        self.assertGreater(strict["excluded_unknown"], 0)
        self.assertEqual(query.query({"protocol": "vless"})["items"][0]["id"], "sing-box")


if __name__ == "__main__":
    unittest.main()
