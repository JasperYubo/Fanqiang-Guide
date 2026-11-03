"""MCP v2 protocol and privacy regressions against the real ASGI SDK stack.

No network listeners, device operations, external APIs or mocked book bodies.
"""
import hashlib
import io
import json
import logging
from pathlib import Path
import unittest

from starlette.testclient import TestClient

import app
from library_query import QUERY_SCHEMA
import setup_book


class MCPV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = app.Library(Path(__file__).with_name("library.json"))
        cls.context = TestClient(app.create_app(cls.library),
            base_url="http://127.0.0.1:8765", raise_server_exceptions=False)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def post_rpc(self, request):
        return self.client.post("/mcp", json=request, headers={
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25"})

    def rpc(self, method, params=None):
        response = self.post_rpc({"jsonrpc": "2.0", "id": 7,
            "method": method, "params": {} if params is None else params})
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertNotIn("error", payload, payload)
        return payload["result"]

    def query(self, params):
        result = self.rpc("tools/call", {"name": "query", "arguments": params})
        self.assertFalse(result.get("isError"), result)
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        return result["structuredContent"]

    def test_public_selector_privacy_matrix(self):
        secret = "SYNTHETIC_PRIVATE_SELECTOR_DO_NOT_ECHO_9827"
        cases = {
            "uri_object": ({"method": "resources/read", "params": {"uri": {"private": secret}}}, -32602),
            "uri_array": ({"method": "resources/read", "params": {"uri": [secret]}}, -32602),
            "params_string": ({"method": "resources/read", "params": secret}, -32602),
            "params_array": ({"method": "resources/read", "params": [secret]}, -32602),
            "params_null": ({"method": "resources/read", "params": None}, -32602),
            "method_array": ({"method": [secret], "params": {}}, -32600),
            "method_object": ({"method": {"private": secret}, "params": {}}, -32600),
            "query_badarg": ({"method": "tools/call", "params": {"name": "query", "arguments": {"platform": secret}}}, -32602),
            "query_badid": ({"method": "tools/call", "id": {"private": secret}, "params": {"name": "query", "arguments": {}}}, -32600),
            "query_badmeta": ({"method": "tools/call", "params": {"name": "query", "arguments": {}, "_meta": {"progressToken": [secret]}}}, -32602),
            "query_valid": ({"method": "tools/call", "params": {"name": "query", "arguments": {"platform": "android", "limit": 1}}}, None),
            "resource_valid": ({"method": "resources/read", "params": {"uri": "fanqiang://books/autosetup"}}, None),
            "search_valid": ({"method": "tools/call", "params": {"name": "search", "arguments": {"query": "android", "limit": 1}}}, None),
            "get_valid": ({"method": "tools/call", "params": {"name": "get", "arguments": {"id": "sing-box"}}}, None),
        }
        for name, (partial, expected_code) in cases.items():
            with self.subTest(case=name):
                output = io.StringIO()
                handler = logging.StreamHandler(output)
                logging.getLogger().addHandler(handler)
                try:
                    response = self.post_rpc({"jsonrpc": "2.0", "id": 7, **partial})
                finally:
                    logging.getLogger().removeHandler(handler)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(secret, response.text)
                self.assertNotIn(secret, output.getvalue())
                payload = response.json()
                if expected_code is None:
                    self.assertNotIn("error", payload)
                    self.assertFalse(payload["result"].get("isError", False))
                else:
                    self.assertEqual(payload["error"]["code"], expected_code)
                if name == "query_badid":
                    self.assertIsNone(payload["id"])

    def test_query_envelope_and_value_failures_do_not_echo_or_log(self):
        secret = "SYNTHETIC_PRIVATE_VALUE_27511"
        requests = [
            {"jsonrpc": secret, "id": 1, "method": "tools/call", "params": {"name": "query"}},
            {"id": True, "method": "tools/call", "params": {"name": "query", "arguments": {}}},
            {"id": [secret], "method": "tools/call", "params": {"name": "query"}},
            {"method": "tools/call", "params": {"name": "query", "arguments": [secret]}},
            {"method": "tools/call", "params": {"name": "query", "arguments": {secret: "x"}}},
            {"method": "tools/call", "params": {"name": "query", "arguments": {"kind": secret}}},
            {"method": "tools/call", "params": {"name": "query", "arguments": {"include_unknown": secret}}},
            {"method": "tools/call", "params": {"name": "query", "arguments": {"limit": secret}}},
            {"method": "resources/read", "params": {"uri": "fanqiang://books/" + secret}},
            {"method": "resources/read", "params": {"uri": setup_book.BOOK_RESOURCE_URI, "_meta": secret}},
            {"method": "resources/read", "params": {"uri": setup_book.BOOK_RESOURCE_URI, secret: "x"}},
        ]
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logging.getLogger().addHandler(handler)
        try:
            for case in requests:
                response = self.post_rpc({"jsonrpc": "2.0", "id": 1, **case})
                self.assertEqual(response.status_code, 200)
                self.assertIn(response.json()["error"]["code"], (-32600, -32602))
                self.assertNotIn(secret, response.text)
            self.assertNotIn(secret, output.getvalue())
        finally:
            logging.getLogger().removeHandler(handler)

    def test_query_discovery_matches_the_strict_schema(self):
        tools = self.rpc("tools/list")["tools"]
        self.assertEqual({tool["name"] for tool in tools}, {"search", "get", "query"})
        tool = next(tool for tool in tools if tool["name"] == "query")
        self.assertEqual(tool["inputSchema"], QUERY_SCHEMA)
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])
        self.assertTrue(tool["description"].startswith("::ILANG::v5.0"))
        self.assertIn("Zero results", tool["description"])

    def test_query_http_and_mcp_are_identical(self):
        for params in (
            {"kind": "client", "platform": "android", "limit": 2},
            {"protocol": "VLESS-Reality", "feature": "tun", "include_unknown": True, "limit": 3, "offset": 1},
            {"platform": "android", "os_version": "14", "include_unknown": True, "limit": 2},
        ):
            with self.subTest(params=params):
                http_params = {key: str(value).lower() if type(value) is bool else str(value)
                               for key, value in params.items()}
                response = self.client.get("/api/agent/query", params=http_params)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json(), self.query(params))

    def test_query_http_rejects_ambiguous_and_private_parameters(self):
        secret = "SYNTHETIC_PRIVATE_FILTER_1789"
        urls = [
            "?platform=android&platform=ios",
            "?include_unknown=1", "?limit=true", "?limit=-1",
            "?platform=Android14", "?os_version=14", "?kind=" + secret,
            "?protocol=" + secret, "?" + secret + "=x",
        ]
        for suffix in urls:
            with self.subTest(suffix=suffix):
                response = self.client.get("/api/agent/query" + suffix)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"], "invalid_parameter")
                self.assertNotIn(secret, response.text)

    def test_unknown_candidates_are_not_compatibility_claims(self):
        params = {"kind": "client", "platform": "android", "protocol": "VLESS-Reality", "feature": "tun",
                  "os_version": "14", "limit": 20}
        strict = self.query(params)
        self.assertEqual(strict["total"], 0)
        self.assertGreater(strict["excluded_unknown"], 0)
        self.assertTrue(strict["notices"])
        candidates = self.query({**params, "include_unknown": True})
        self.assertGreater(candidates["total"], 0)
        self.assertEqual(candidates["excluded_unknown"], 0)
        self.assertEqual(candidates["total"], strict["excluded_unknown"])
        self.assertEqual(candidates["filter_operator"], "AND")
        self.assertEqual(candidates["filters"]["protocol"], "vless")
        self.assertEqual(set(candidates["filters"]["required_features"]), {"reality", "tun"})
        self.assertEqual(candidates["ordering"],
            ["platform_matched_first", "matched_condition_count_desc", "id_asc"])
        self.assertTrue(candidates["items"])
        for item in candidates["items"]:
            self.assertEqual(item["kind"], "client")
            self.assertEqual(item["match_status"], "unknown")
            self.assertEqual(item["combination_status"], "not_tested")
            version = next(c for c in item["criteria"] if c["field"] == "os_version")
            self.assertEqual(version["state"], "unknown")
            self.assertEqual(self.library.get({"id": item["id"]})["item"]["id"], item["id"])

    def test_record_review_and_live_source_dates_keep_separate_meanings(self):
        result = self.query({"platform": "android", "limit": 20})
        self.assertEqual(result["date_semantics"]["last_updated"], "knowledge_record_updated_at")
        self.assertEqual(result["date_semantics"]["checked_at"], "record_source_review_date")
        self.assertTrue(result["items"])
        for item in result["items"]:
            original = self.library.records[item["id"]]
            self.assertEqual(item["last_updated"], original.get("updated_at"))
            self.assertEqual(item["checked_at"], original.get("verification", {}).get("checked_at"))
            freshness = item["source_freshness"]
            self.assertTrue(freshness["does_not_revalidate_compatibility"])
            self.assertEqual(freshness["scope"], "repository_metadata_only")
            self.assertIn("source_checked_at", freshness)
            self.assertIn("last_attempt_at", freshness)
            self.assertEqual(item["combination_status"], "not_tested")

    def test_books_catalog_template_and_resource_payload_agree(self):
        response = self.client.get("/api/agent/books")
        self.assertEqual(response.status_code, 200)
        catalog = response.json()
        self.assertEqual(catalog, setup_book.book_catalog())
        self.assertEqual(catalog["resource_template"], "fanqiang://books/{book_id}")
        templates = self.rpc("resources/templates/list")["resourceTemplates"]
        self.assertEqual([t["uriTemplate"] for t in templates], [catalog["resource_template"]])
        resources = {r["uri"]: r for r in self.rpc("resources/list")["resources"]}
        for manifest in catalog["books"]:
            self.assertEqual(resources[manifest["resource_uri"]]["_meta"], manifest)
            response = self.client.get("/api/agent/books/" + manifest["book_id"])
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload, setup_book.book_payload(manifest["book_id"]))
            content = self.rpc("resources/read", {"uri": manifest["resource_uri"]})["contents"]
            self.assertEqual(len(content), 1)
            self.assertEqual(content[0]["mimeType"], "application/json")
            self.assertEqual(json.loads(content[0]["text"]), payload)
            raw = payload["content"].encode("utf-8")
            self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest["sha256"])
            self.assertEqual(len(raw), manifest["byte_length"])

    def test_unknown_book_and_arbitrary_path_are_not_resolved(self):
        for book_id in ("unknown-book", "SYNTHETIC_PRIVATE_BOOK_87"):
            response = self.client.get("/api/agent/books/" + book_id)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json(), {"error": "not_found", "message": "Unknown book id"})
            self.assertNotIn(book_id, response.text)
        for uri in ("fanqiang://books/unknown-book", "file:///etc/passwd",
                    "https://example.com/book", "fanqiang://books/../../etc/passwd"):
            response = self.post_rpc({"jsonrpc": "2.0", "id": 1,
                "method": "resources/read", "params": {"uri": uri}})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["error"]["code"], -32602)
            self.assertNotIn(uri, response.text)

    def test_book_endpoints_never_accept_private_request_data(self):
        secret = "SYNTHETIC_PRIVATE_BOOK_PAYLOAD_27"
        for path in ("/api/agent/books", "/api/agent/books/autosetup", "/api/agent/setup-book"):
            for kwargs in ({"params": {"subscription": secret}}, {"content": secret}):
                response = self.client.request("GET", path, **kwargs)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(secret, response.text)
            self.assertEqual(self.client.post(path, json={}).status_code, 405)

    def test_prompt_rules_are_complete_and_byte_identical_to_the_resource(self):
        rules = setup_book.answer_rules_text()
        self.assertEqual(rules.count("[MUST]"), 9)
        resource = self.rpc("resources/read", {"uri": setup_book.RULES_RESOURCE_URI})["contents"][0]
        self.assertEqual(resource["text"], rules)
        self.assertEqual(resource["mimeType"], "text/plain")
        payload = setup_book.setup_book_payload()
        messages = self.rpc("prompts/get", {"name": "setup_device"})["messages"]
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[1]["content"]["text"], rules)
        self.assertEqual(messages[2]["content"]["text"], payload["content"])
        self.assertIn(payload["sha256"], messages[0]["content"]["text"])
        self.assertIn("not extra authorization", messages[0]["content"]["text"])
        self.assertEqual(hashlib.sha256(messages[2]["content"]["text"].encode()).hexdigest(), payload["sha256"])

    def test_prompt_preserves_explicit_hardware_validation_boundaries(self):
        payload = setup_book.setup_book_payload()
        body = payload["content"]
        for module in ("PICK_PHONE", "HOTSPOT", "VERIFY_SHARED", "MAINTAIN_SHARED"):
            self.assertIn("::MODULE{" + module + "|", body)
        self.assertEqual(payload["validation"]["mobile_hotspot"]["status"], "not_tested")
        self.assertIn("phone_hardware:not_tested", body)
        self.assertIn("hotspot_hardware:not_tested", body)
        self.assertIn("a short pass is not continuous-service certification", body)
        self.assertIn("A phone VPN does not by itself prove tethered clients use that VPN",
                      "\n".join(payload["capability_boundaries"]))


if __name__ == "__main__":
    unittest.main()
