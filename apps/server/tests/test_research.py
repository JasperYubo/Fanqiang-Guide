"""Evidence order, data isolation and failure behavior without external calls."""
import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("huarun_research", Path(__file__).resolve().parents[1] / "research.py")
research = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(research)


class FakeTransport:
    def __init__(self, fail=None, records=None, content="document reference", search_results=None):
        self.calls = []
        self.fail = fail or {}
        self.records = records or []
        self.content = content
        self.search_results = search_results if search_results is not None else [
            {"title": "Official docs", "url": "https://nginx.org/en/docs/", "summary": "Verified context", "content": "Documentation"}]

    def __call__(self, url, payload, headers, timeout, limit):
        self.calls.append({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
        method = payload.get("method", "search_web")
        target = payload.get("params", {}).get("name") or payload.get("params", {}).get("uri") or method
        if target in self.fail:
            raise self.fail[target]
        if url == research.SEARCH_URL:
            return {"results": self.search_results}
        if method == "initialize":
            return {"result": {"protocolVersion": "2025-11-25"}}
        if method == "resources/read":
            return {"result": {"contents": [{"text": json.dumps({"title": "排障", "content": self.content, "version": "1.1"})}]}}
        if target == "get_server_setup":
            return {"result": {"structuredContent": {"title": "Server", "content": self.content}}}
        if target == "search":
            return {"result": {"structuredContent": {"items": self.records, "total": len(self.records)}}}
        if target == "get":
            return {"result": {"structuredContent": {"id": payload["params"]["arguments"]["id"], "verification": "unknown", "details": self.content}}}
        raise AssertionError(target)


class ResearchTests(unittest.TestCase):
    def test_web_cannot_run_before_mcp_or_with_forged_receipt(self):
        transport = FakeTransport()
        client = research.ResearchClient("sk-test-DO-NOT-LEAK", transport)
        answer = client.search_deepseek("nginx tls", "missing TLS error details", "invented")
        self.assertEqual(answer["errors"][0]["code"], "mcp_first_required")
        self.assertEqual(transport.calls, [])

    def test_mcp_order_and_matching_record_get_before_web(self):
        transport = FakeTransport(records=[{"id": "xray-core", "name": "Xray", "verification": {"status": "unknown"}}])
        client = research.ResearchClient("sk-test-DO-NOT-LEAK", transport)
        evidence = client.query_mcp("xray")
        names = [c["payload"].get("params", {}).get("name") or c["payload"].get("method") for c in transport.calls]
        self.assertEqual(names, ["initialize", "resources/read", "get_server_setup", "search", "get"])
        self.assertEqual(evidence["answer_sufficiency"], "requires_assessment")
        self.assertTrue(evidence["retrieval_complete"])
        self.assertEqual(evidence["items"][0]["verification"]["status"], "unknown")
        self.assertTrue(all(d["trust"] == "untrusted" for d in evidence["documents"]))
        self.assertFalse(any(c["url"] == research.SEARCH_URL for c in transport.calls))
        found = client.search_deepseek("Xray unknown TLS alert", "本站没有该 TLS 错误的修复依据", evidence["query_id"])
        self.assertTrue(found["available"])
        self.assertEqual(transport.calls[-1]["url"], research.SEARCH_URL)
        self.assertEqual(found["source_sequence"][-1]["source"], "deepseek_search")
        self.assertNotIn("Authorization", transport.calls[0]["headers"])
        self.assertEqual(transport.calls[-1]["payload"]["count"], 5)

    def test_fallback_needs_specific_reason_and_current_turn_receipt(self):
        transport = FakeTransport()
        client = research.ResearchClient("sk-test", transport)
        old = client.query_mcp("nginx")
        fresh = client.query_mcp("xray")
        result = client.search_deepseek("xray", "missing version details", old["query_id"])
        self.assertEqual(result["errors"][0]["code"], "stale_query_id")
        result = client.search_deepseek("xray", "", fresh["query_id"])
        self.assertEqual(result["errors"][0]["code"], "specific_gap_required")
        self.assertFalse(any(c["url"] == research.SEARCH_URL for c in transport.calls))

    def test_unavailable_mcp_allows_explicit_degraded_web_path(self):
        transport = FakeTransport(fail={"initialize": research.ResearchError("http_error", 503)})
        client = research.ResearchClient("sk-test", transport)
        evidence = client.query_mcp("certificate")
        self.assertTrue(evidence["mcp_attempted"])
        self.assertFalse(evidence["available"])
        self.assertFalse(evidence["retrieval_complete"])
        self.assertEqual(evidence["errors"], [{"operation": "initialize", "code": "http_error", "http_status": 503}])
        self.assertFalse(evidence["source_sequence"][0]["ok"])
        answer = client.search_deepseek("nginx TLS renewal", "MCP 服务当前返回 503，无法取得排障资料", evidence["query_id"])
        self.assertTrue(answer["available"])

    def test_missing_runbook_remains_partial_not_full_success(self):
        transport = FakeTransport(fail={research.TROUBLESHOOTING_URI: research.ResearchError("mcp_rpc_error")})
        evidence = research.ResearchClient(transport=transport).query_mcp("nginx")
        self.assertTrue(evidence["available"])
        self.assertFalse(evidence["retrieval_complete"])
        self.assertEqual(evidence["errors"][0]["operation"], "troubleshooting")

    def test_empty_or_invalid_query_cannot_unlock_search(self):
        client = research.ResearchClient("sk-test", FakeTransport())
        evidence = client.query_mcp("")
        self.assertFalse(evidence["mcp_attempted"])
        self.assertIsNone(evidence["query_id"])
        self.assertEqual(client.search_deepseek("nginx", "no reference data", None)["errors"][0]["code"], "mcp_first_required")

    def test_query_redacts_keys_credentials_connection_links_and_addresses(self):
        sensitive = ["sk-private-SECRET-12345", "eytoken-private", "topSecret", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "user:pass", "198.51.100.2"]
        query = "nginx sk-private-SECRET-12345 Authorization: Bearer eytoken-private password=topSecret vmess://encodedAAA https://user:pass@private.example/cfg?id=key aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee 198.51.100.2"
        clean = research.sanitize_query(query, 1000)
        for secret in sensitive:
            self.assertNotIn(secret, clean)
        self.assertNotIn("encodedAAA", clean)
        transport = FakeTransport()
        evidence = research.ResearchClient(transport=transport).query_mcp(query)
        outgoing = json.dumps([c["payload"] for c in transport.calls])
        for secret in sensitive:
            self.assertNotIn(secret, outgoing)
        self.assertLessEqual(len(evidence["query"]), 128)

    def test_known_key_is_never_in_mcp_or_search_query_even_with_nonstandard_format(self):
        secret = "nonstandardActualKey"
        transport = FakeTransport()
        client = research.ResearchClient(secret, transport)
        evidence = client.query_mcp("nginx " + secret)
        client.search_deepseek("TLS " + secret, "MCP has no TLS guidance " + secret, evidence["query_id"])
        self.assertNotIn(secret, json.dumps([call["payload"] for call in transport.calls]))

    def test_upstream_or_transport_errors_do_not_expose_key(self):
        secret = "sk-secret-TEST-123456"
        transport = FakeTransport(fail={"initialize": RuntimeError(secret)})
        evidence = research.ResearchClient(secret, transport).query_mcp("nginx")
        self.assertNotIn(secret, json.dumps(evidence))
        self.assertEqual(evidence["errors"][0]["code"], "transport_error")

    def test_provider_echo_of_key_is_redacted_from_returned_data(self):
        secret = "api-specific-private-key"
        transport = FakeTransport(content="text " + secret,
                                  search_results=[{"title": secret, "url": "https://example.com/", "content": secret}])
        client = research.ResearchClient(secret, transport)
        evidence = client.query_mcp("nginx")
        self.assertNotIn(secret, json.dumps(evidence))
        result = client.search_deepseek("nginx TLS", "该证书错误的上游解释缺失", evidence["query_id"])
        self.assertNotIn(secret, json.dumps(result))

    def test_search_errors_empty_results_and_missing_key_are_distinct(self):
        transport = FakeTransport(search_results=[])
        client = research.ResearchClient("", transport)
        evidence = client.query_mcp("nginx")
        self.assertEqual(client.search_deepseek("nginx", "MCP缺少新版资料", evidence["query_id"])["errors"][0]["code"], "deepseek_key_missing")
        client = research.ResearchClient("sk-test", transport)
        evidence = client.query_mcp("nginx")
        result = client.search_deepseek("nginx", "MCP缺少新版资料", evidence["query_id"])
        self.assertTrue(result["empty"])
        self.assertEqual(result["errors"], [])
        transport.fail["search_web"] = research.ResearchError("http_error", 402)
        result = client.search_deepseek("nginx", "MCP缺少新版资料", evidence["query_id"])
        self.assertEqual(result["errors"][0]["http_status"], 402)

    def test_budget_prevents_unbounded_search(self):
        transport = FakeTransport()
        client = research.ResearchClient("sk-test", transport)
        evidence = client.query_mcp("nginx")
        for _ in range(2):
            self.assertTrue(client.search_deepseek("nginx", "MCP缺少新版资料", evidence["query_id"])["available"])
        self.assertEqual(client.search_deepseek("nginx", "MCP缺少新版资料", evidence["query_id"])["errors"][0]["code"], "search_budget_exhausted")
        self.assertEqual(sum(c["url"] == research.SEARCH_URL for c in transport.calls), 2)

    def test_document_payload_is_bounded_in_bytes_with_visible_truncation(self):
        transport = FakeTransport(content="证据" * 25000)
        evidence = research.ResearchClient(transport=transport).query_mcp("nginx")
        self.assertTrue(any(d["truncated"] for d in evidence["documents"]))
        size = sum(len(json.dumps(d, ensure_ascii=False).encode()) for d in evidence["documents"])
        self.assertLessEqual(size, research.MAX_DOCUMENT_BYTES)

    def test_total_mcp_deadline_stops_more_calls(self):
        now = [0.0]
        base = FakeTransport()
        def transport(*args):
            now[0] += 12
            return base(*args)
        evidence = research.ResearchClient(transport=transport, clock=lambda: now[0]).query_mcp("nginx")
        self.assertEqual(len(base.calls), 3)
        self.assertIn("deadline_exceeded", [e["code"] for e in evidence["errors"]])
        self.assertTrue(all(c["timeout"] <= 12 for c in base.calls))

    def test_malformed_json_and_sse_are_handled(self):
        with self.assertRaises(research.ResearchError):
            research._decode_response(b'{broken')
        data = research._decode_response(b'event: message\ndata: {"jsonrpc":"2.0","result":{"ok":true}}\n\n', 'text/event-stream')
        self.assertTrue(data["result"]["ok"])
        with self.assertRaises(research.ResearchError):
            research._decode_response(b'event: ping\ndata: {}\n\n', 'text/event-stream')

    def test_arbitrary_upstream_and_redirect_rejected(self):
        with self.assertRaises(research.ResearchError) as caught:
            research._json_post("http://127.0.0.1/private", {}, {}, 1)
        self.assertEqual(caught.exception.code, "upstream_not_allowed")
        with self.assertRaises(research.ResearchError):
            research._NoRedirect().redirect_request(None, None, 307, "", {}, "https://third-party.example/")

    def test_malformed_mcp_result_and_oversized_response_are_not_success(self):
        for data in [{"result": []}, {"result": {"oversize": "x" * research.MAX_RESPONSE_BYTES}}]:
            client = research.ResearchClient(transport=lambda *args, data=data: data)
            result = client.query_mcp("nginx")
            self.assertFalse(result["available"])
            self.assertFalse(result["retrieval_complete"])

    def test_malformed_resource_and_tool_payload_are_reported_not_raised(self):
        transport = FakeTransport()
        def malformed(url, payload, headers, timeout, limit):
            if payload.get("method") == "resources/read":
                return {"result": {"contents": {"unexpected": "map"}}}
            if payload.get("params", {}).get("name") == "get_server_setup":
                return {"result": {"content": None}}
            return transport(url, payload, headers, timeout, limit)
        evidence = research.ResearchClient(transport=malformed).query_mcp("nginx")
        self.assertFalse(evidence["retrieval_complete"])
        self.assertEqual({error["code"] for error in evidence["errors"]}, {"invalid_mcp_resource", "invalid_mcp_tool_result"})

    def test_result_urls_with_credentials_or_non_http_schemes_are_rejected(self):
        transport = FakeTransport(search_results=[{"url": "https://user:password@example.com/"}, {"url": "file:///etc/passwd"}, {"url": "javascript:alert(1)"}, {"url": "https://[malformed"}])
        client = research.ResearchClient("sk-test", transport)
        evidence = client.query_mcp("nginx")
        result = client.search_deepseek("nginx", "MCP缺少新版资料", evidence["query_id"])
        self.assertEqual(result["items"], [])
        self.assertNotIn("password", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
