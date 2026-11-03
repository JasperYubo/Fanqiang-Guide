import asyncio
import hashlib
import io
import logging
import tempfile
from unittest import mock
import jsonschema
import setup_book
import json
import socket
import threading
import time
import unittest
from pathlib import Path

import uvicorn
from starlette.testclient import TestClient
from mcp.shared.exceptions import McpError
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
import app
from library_core import validate_params, SEARCH_SCHEMA, MAX_BODY, MAX_RESPONSE


class LookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = app.Library(Path(__file__).with_name("library.json"))
        cls.client_context = TestClient(app.create_app(cls.library), base_url="http://127.0.0.1:8765")
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def rpc(self, method, params=None, ident=1, headers=None):
        return self.client.post("/mcp", headers={"Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25", **(headers or {})},
            json={"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}})

    def test_record_count(self):
        self.assertEqual(len(self.library.records), 310)

    def test_exact_search_first(self):
        self.assertEqual(self.library.search({"query": "V2RAYN"})["items"][0]["id"], "v2rayn")

    def test_chinese_search(self):
        result = self.library.search({"query": "梅林"})
        self.assertGreater(result["total"], 0)
        self.assertTrue(any("merlin" in x["id"] for x in result["items"]))

    def test_combined_filters(self):
        result = self.library.search({"platform": "android", "kind": "client", "limit": 20})
        self.assertGreater(result["total"], 0)
        self.assertTrue(all("Android" in x["platforms"] and x["kind"] == "client" for x in result["items"]))

    def test_verification_filter(self):
        status = self.library.filters["verification"][0]
        result = self.library.search({"verification": status})
        self.assertTrue(result["items"])
        self.assertTrue(all(x["verification"]["status"] == status for x in result["items"]))

    def test_preserves_every_field(self):
        for ident, original in self.library.records.items():
            returned = self.library.get({"id": ident})["item"]
            for key, value in original.items():
                self.assertEqual(returned[key], value, (ident, key))

    def test_unknown_maintenance_preserved(self):
        record = next(r for r in self.library.records.values() if r.get("maintenance", {}).get("status") == "unknown")
        self.assertEqual(self.library.get({"id": record["id"]})["item"]["maintenance"], record["maintenance"])

    def test_search_no_hits(self):
        result = self.library.search({"query": "__not_a_real_tool_972381__"})
        self.assertEqual((result["total"], result["items"], result["next_offset"]), (0, [], None))

    def test_pagination_nonoverlap(self):
        a = self.library.search({"limit": 2})
        b = self.library.search({"limit": 2, "offset": a["next_offset"]})
        self.assertTrue(set(x["id"] for x in a["items"]).isdisjoint(x["id"] for x in b["items"]))
        self.assertEqual(self.library.search({"offset": 310})["next_offset"], None)

    def test_rest_known_and_unknown(self):
        r = self.client.get("/api/agent/item?id=v2rayn")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["item"]["id"], "v2rayn")
        self.assertTrue(r.json()["item"]["source_url"].endswith("/export/cards/v2rayn-v0.1-2026-09-11.md"))
        self.assertIn(app.SOURCE_REVISION, r.json()["item"]["source_url"])
        self.assertTrue(r.json()["item"]["source_snapshot_url"].endswith("/export/library-v0.1-2026-09-11.json"))
        self.assertEqual(self.client.get("/api/agent/item?id=does-not-exist").status_code, 404)

    def test_rest_parameter_validation(self):
        for query in ("limit=21", "limit=0", "limit=-1", "limit=x", "offset=-1", "platform=imaginary", "unknown=1", "limit=1&limit=2", "query="+"x"*161):
            with self.subTest(query=query):
                self.assertEqual(self.client.get("/api/agent/search?"+query).status_code, 400)

    def test_rest_filter_and_response_limit(self):
        r = self.client.get("/api/agent/search?platform=android&kind=client&limit=20")
        self.assertEqual(r.status_code, 200)
        self.assertLess(len(r.content), MAX_RESPONSE)
        self.assertLessEqual(len(r.json()["items"]), 20)

    def test_uri_limit(self):
        self.assertEqual(self.client.get("/api/agent/search?query="+"a"*2100).status_code, 414)

    def test_origin(self):
        for path in ("/api/agent/health", "/mcp", "/openapi.json"):
            self.assertEqual(self.client.get(path, headers={"Origin": "https://attacker.example"}).status_code, 403)
        r = self.client.get("/api/agent/health", headers={"Origin": app.ORIGIN})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["access-control-allow-origin"], app.ORIGIN)

    def test_host(self):
        self.assertEqual(self.client.get("/api/agent/health", headers={"Host": "attacker.example"}).status_code, 400)
        self.assertEqual(self.client.get("/api/agent/health", headers={"Host": "fanqiang.guide"}).status_code, 200)

    def test_unknown_endpoint_and_head(self):
        self.assertEqual(self.client.get("/not-a-file").status_code, 404)
        r = self.client.head("/api/agent/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"")

    def test_metadata_contract(self):
        spec = self.client.get("/openapi.json").json()
        self.assertEqual(spec["security"], [])
        self.assertIn("/api/agent/search", spec["paths"])
        self.assertIn("/api/agent/item", spec["paths"])
        self.assertEqual(self.client.get("/.well-known/mcp/server-card.json").json()["transport"]["endpoint"], app.ORIGIN+"/mcp")

    def test_mcp_initialize_and_notification(self):
        r = self.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["result"]["serverInfo"]["version"], app.VERSION)
        self.assertEqual(r.json()["result"]["protocolVersion"], "2025-11-25")
        self.assertNotIn("mcp-session-id", r.headers)
        r = self.client.post("/mcp", headers={"Accept": "application/json, text/event-stream"}, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.content, b"")

    def test_mcp_ping_tools_and_descriptions(self):
        self.assertEqual(self.rpc("ping").json()["result"], {})
        tools = self.rpc("tools/list").json()["result"]["tools"]
        self.assertEqual({x["name"] for x in tools}, {"search", "get", "query"})
        self.assertTrue(all(x["description"].startswith("::ILANG::v5.0") and x["annotations"]["readOnlyHint"] for x in tools))

    def test_mcp_get_and_search(self):
        result = self.rpc("tools/call", {"name": "get", "arguments": {"id": "v2rayn"}}).json()["result"]
        self.assertFalse(result.get("isError", False))
        self.assertEqual(result["structuredContent"]["item"]["id"], "v2rayn")
        result = self.rpc("tools/call", {"name": "search", "arguments": {"query": "梅林", "limit": 2}}).json()["result"]
        self.assertFalse(result.get("isError", False))
        self.assertEqual(len(result["structuredContent"]["items"]), 2)

    def test_mcp_unknown_and_invalid_tool_arguments(self):
        for name, arguments in (("get", {"id": "does-not-exist"}), ("search", {"limit": 21}), ("search", {"limit": True}), ("get", {"id": "../../etc/passwd"}), ("get", {"id": "https://example.com"}), ("missing", {})):
            with self.subTest(name=name, arguments=arguments):
                result = self.rpc("tools/call", {"name": name, "arguments": arguments}).json()
                self.assertTrue(result.get("result", {}).get("isError") or "error" in result)

    def test_mcp_no_get_stream(self):
        self.assertEqual(self.client.get("/mcp", headers={"Accept":"text/event-stream"}).status_code, 405)

    def test_mcp_invalid_origin(self):
        self.assertEqual(self.rpc("ping", headers={"Origin":"https://evil.example"}).status_code, 403)

    def test_mcp_invalid_version(self):
        self.assertEqual(self.rpc("ping", headers={"MCP-Protocol-Version":"1900-01-01"}).status_code, 400)

    def test_mcp_accept(self):
        self.assertEqual(self.rpc("ping", headers={"Accept":"application/json"}).status_code, 200)
        self.assertEqual(self.rpc("ping", headers={"Accept":"text/html"}).status_code, 406)

    def test_mcp_body_limit(self):
        r = self.client.post("/mcp",headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"},content=b" "*(MAX_BODY+1))
        self.assertEqual(r.status_code, 413)

    def test_mcp_malformed_json(self):
        r = self.client.post("/mcp",headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream"},content=b"{")
        self.assertEqual(r.status_code, 400)


    def test_setup_book_manifest_and_integrity(self):
        payload = setup_book.setup_book_payload()
        self.assertEqual(payload["id"], "fanqiang-autosetup")
        self.assertEqual(payload["version"], "2.1")
        self.assertNotIn("execution_status", payload)
        self.assertEqual(payload["validation"]["mobile_hotspot"]["status"], "not_tested")
        self.assertEqual(payload["executor"], "user_agent")
        self.assertEqual(payload["sha256"], setup_book.BOOK_SHA256)
        raw = payload["content"].encode("utf-8")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), payload["sha256"])
        self.assertEqual(len(raw), payload["byte_length"])
        self.assertEqual(raw, setup_book.BOOK_PATH.read_bytes())
        self.assertTrue(payload["content"].rstrip().endswith("::ILANG::v5.0::ENGINEERING_BOOK"))
        self.assertEqual(payload["download_url"], app.ORIGIN + "/ai/books/fanqiang-autosetup-v2.1.ilang.md")
        self.assertEqual({k: v for k, v in payload.items() if k != "content"}, setup_book.setup_book_manifest())
        jsonschema.validate(payload, setup_book.setup_book_response_schema())
        payload["capability_boundaries"].clear()
        self.assertTrue(setup_book.setup_book_manifest()["capability_boundaries"])

    def test_setup_book_rejects_bad_files_with_fixed_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "book.md"
            cases = (None, b"synthetic-secret", b"x" * 65537)
            for data in cases:
                if data is not None:
                    source.write_bytes(data)
                with mock.patch.dict(setup_book.BOOK_REGISTRY, {"autosetup": {**setup_book.BOOK_REGISTRY["autosetup"], "path": source}}):
                    with self.assertRaisesRegex(ValueError, "^Public reference integrity check failed$"):
                        setup_book.setup_book_payload()
            source.write_bytes(b"\xff")
            with mock.patch.dict(setup_book.BOOK_REGISTRY, {"autosetup": {**setup_book.BOOK_REGISTRY["autosetup"], "path": source}}), mock.patch.object(
                    setup_book, "BOOK_SHA256", hashlib.sha256(b"\xff").hexdigest()):
                with self.assertRaisesRegex(ValueError, "^Public reference integrity check failed$"):
                    setup_book.setup_book_manifest()
            link = Path(folder) / "link.md"
            link.symlink_to(setup_book.BOOK_PATH)
            with mock.patch.dict(setup_book.BOOK_REGISTRY, {"autosetup": {**setup_book.BOOK_REGISTRY["autosetup"], "path": link}}):
                with self.assertRaisesRegex(ValueError, "^Public reference integrity check failed$"):
                    setup_book.setup_book_payload()

    def test_setup_book_rest_mcp_resource_same_complete_body(self):
        expected = setup_book.setup_book_payload()
        response = self.client.get("/api/agent/setup-book")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertLess(len(response.content), MAX_RESPONSE)
        for arguments in (None, {}):
            params = {"name": "get_setup_book"}
            if arguments is not None:
                params["arguments"] = arguments
            response = self.rpc("tools/call", params)
            self.assertLess(len(response.content), MAX_RESPONSE)
            result = response.json()["result"]
            self.assertFalse(result.get("isError", False))
            self.assertEqual(result["structuredContent"], expected)
            self.assertEqual(json.loads(result["content"][0]["text"]), expected)
        response = self.rpc("resources/read", {"uri": setup_book.BOOK_RESOURCE_URI})
        self.assertLess(len(response.content), MAX_RESPONSE)
        contents = response.json()["result"]["contents"]
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0]["uri"], setup_book.BOOK_RESOURCE_URI)
        self.assertEqual(contents[0]["mimeType"], "application/json")
        self.assertEqual(json.loads(contents[0]["text"]), expected)

    def test_setup_book_discovery_and_version(self):
        result = self.rpc("initialize", {"protocolVersion": "2025-11-25",
            "capabilities": {}, "clientInfo": {"name": "book-test", "version": "1"}}).json()["result"]
        self.assertEqual(result["serverInfo"]["version"], "2.1.0")
        self.assertTrue({"tools", "resources", "prompts"} <= set(result["capabilities"]))
        self.assertIn("fanqiang://books/autosetup", result["instructions"])
        self.assertIn("grants no extra authorization", result["instructions"])
        tool = next(t for t in self.rpc("tools/list").json()["result"]["tools"] if t["name"] == "query")
        self.assertFalse(tool["inputSchema"]["additionalProperties"])
        for key, value in {"readOnlyHint": True, "idempotentHint": True,
                           "destructiveHint": False, "openWorldHint": False}.items():
            self.assertEqual(tool["annotations"][key], value)
        resources = self.rpc("resources/list").json()["result"]["resources"]
        self.assertEqual([r["uri"] for r in resources], [setup_book.BOOK_RESOURCE_URI, "fanqiang://books/merlin", setup_book.RULES_RESOURCE_URI])
        self.assertEqual(resources[0]["_meta"], setup_book.setup_book_manifest())
        self.assertEqual(self.rpc("resources/templates/list").json()["result"]["resourceTemplates"][0]["uriTemplate"], setup_book.BOOK_RESOURCE_TEMPLATE)
        prompts = self.rpc("prompts/list").json()["result"]["prompts"]
        self.assertEqual([p["name"] for p in prompts], ["setup_device"])
        self.assertEqual(prompts[0].get("arguments", []), [])

    def test_setup_prompt_complete_and_no_execution_authorization(self):
        expected = setup_book.setup_book_payload()
        for args in (None, {}):
            params = {"name": "setup_device"}
            if args is not None:
                params["arguments"] = args
            response = self.rpc("prompts/get", params)
            self.assertLess(len(response.content), MAX_RESPONSE)
            messages = response.json()["result"]["messages"]
            self.assertEqual(len(messages), 3)
            self.assertEqual(messages[1]["content"]["text"], setup_book.answer_rules_text())
            self.assertEqual(messages[2]["content"]["text"], expected["content"])
            intro = messages[0]["content"]["text"]
            self.assertTrue(intro.startswith("::ILANG::v5.0"))
            self.assertIn(expected["sha256"], intro)
            self.assertIn(expected["download_url"], intro)
            self.assertIn("not extra authorization", intro)
            self.assertIn("active user", intro)
            self.assertNotIn("execution_status:not_run", intro)

    def test_setup_book_rest_accepts_no_private_inputs(self):
        secret = "synthetic-secret"
        requests = [
            ("GET", "/api/agent/setup-book?subscription=" + secret, {}),
            ("GET", "/api/agent/setup-book?x=", {}),
            ("GET", "/api/agent/setup-book", {"content": secret}),
            ("GET", "/api/agent/setup-book", {"content": iter([secret.encode()])}),
        ]
        for method, url, kwargs in requests:
            with self.subTest(url=url):
                response = self.client.request(method, url, **kwargs)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(secret, response.text)
                self.assertEqual(response.json()["error"], "invalid_parameter")
        response = self.client.head("/api/agent/setup-book")
        self.assertEqual((response.status_code, response.content), (200, b""))
        self.assertEqual(self.client.post("/api/agent/setup-book", json={}).status_code, 405)

    def test_setup_interfaces_reject_extra_arguments_without_echo_or_log(self):
        secret = "synthetic-secret"
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logging.getLogger().addHandler(handler)
        try:
            for method, name, arguments in (
                ("tools/call", "get_setup_book", {"subscription": secret}),
                ("tools/call", "get_setup_book", {"anything": {"nested": secret}}),
                ("prompts/get", "setup_device", {"subscription": secret}),
                ("prompts/get", "setup_device", {"subscription": {"nested": secret}}),
                ("tools/call", "get_setup_book", secret),
                ("prompts/get", "setup_device", [secret]),
            ):
                with self.subTest(method=method, arguments=arguments):
                    response = self.rpc(method, {"name": name, "arguments": arguments})
                    self.assertNotIn(secret, response.text)
                    body = response.json()
                    self.assertTrue("error" in body or body.get("result", {}).get("isError"))
                    self.assertIn("accepts no arguments", response.text)
            for method, name in (("tools/call", "get_setup_book"), ("prompts/get", "setup_device")):
                response = self.rpc(method, {"name": name, "subscription": secret})
                self.assertEqual(response.json()["error"]["code"], -32602)
                self.assertNotIn(secret, response.text)
            for metadata in (secret, {"progressToken": {"nested": secret}}):
                response = self.rpc("prompts/get", {"name": "setup_device", "_meta": metadata})
                self.assertEqual(response.json()["error"]["code"], -32602)
                self.assertNotIn(secret, response.text)
            self.assertNotIn(secret, output.getvalue())
        finally:
            logging.getLogger().removeHandler(handler)

    def test_setup_request_envelope_never_echoes_or_logs_invalid_values(self):
        secret = "synthetic-private-probe"
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logging.getLogger().addHandler(handler)
        try:
            for method, name in (("tools/call", "get_setup_book"), ("prompts/get", "setup_device")):
                cases = [
                    ({"jsonrpc": secret}, {}),
                    ({"jsonrpc": {"token": secret}}, {}),
                    ({"id": {"token": secret}}, {"subscription": secret}),
                    ({"id": [secret]}, {}),
                    ({"id": True}, {}),
                    ({"id": None}, {}),
                    ({"subscription": secret}, {}),
                ]
                for changed, arguments in cases:
                    with self.subTest(method=method, changed=changed):
                        request = {"jsonrpc": "2.0", "id": 42, "method": method,
                            "params": {"name": name, "arguments": arguments}, **changed}
                        response = self.client.post("/mcp",
                            headers={"Accept": "application/json, text/event-stream"}, json=request)
                        body = response.json()
                        self.assertEqual(body["error"], {
                            "code": -32600, "message": "Invalid setup-book request envelope"})
                        self.assertEqual(body["id"], 42 if "id" not in changed else None)
                        self.assertNotIn(secret, response.text)
                for missing in ("id", "jsonrpc"):
                    request = {"jsonrpc": "2.0", "id": 42, "method": method, "params": {"name": name}}
                    del request[missing]
                    response = self.client.post("/mcp",
                        headers={"Accept": "application/json, text/event-stream"}, json=request)
                    self.assertEqual(response.json()["error"]["code"], -32600)
            self.assertNotIn(secret, output.getvalue())
        finally:
            logging.getLogger().removeHandler(handler)

    def test_setup_request_preserves_valid_rpc_ids(self):
        for ident in (0, -7, "public-request-id"):
            result = self.rpc("tools/call", {"name": "get_setup_book"}, ident=ident).json()
            self.assertEqual(result["id"], ident)
            self.assertEqual(result["result"]["structuredContent"], setup_book.setup_book_payload())

    def test_setup_book_allows_standard_progress_metadata(self):
        for method, name in (("tools/call", "get_setup_book"), ("prompts/get", "setup_device")):
            result = self.rpc(method, {"name": name, "_meta": {"progressToken": "public-test"}}).json()
            self.assertIn("result", result)

    def test_setup_resource_is_fixed_and_readonly(self):
        for uri in ("file:///etc/passwd", "https://example.com/private", "fanqiang://books/missing"):
            result = self.rpc("resources/read", {"uri": uri}).json()
            self.assertIn("error", result)
        tools = self.rpc("tools/list").json()["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {"search", "get", "query"})

    def test_setup_metadata_exports_match_dynamic_and_do_not_change_records(self):
        spec = self.client.get("/openapi.json").json()
        card = self.client.get("/.well-known/mcp/server-card.json").json()
        health = self.client.get("/api/agent/health").json()
        for metadata in (spec["info"], card["serverInfo"], health):
            self.assertEqual(metadata["version"], "2.1.0")
        self.assertEqual(card["version"], "1.0")
        self.assertEqual(card["setupBook"], setup_book.setup_book_manifest())
        self.assertEqual(spec["paths"]["/api/agent/setup-book"]["get"]["parameters"], [])
        for filename, data in (("openapi.json", spec), ("server-card.json", card)):
            self.assertEqual(json.loads(Path(__file__).with_name(filename).read_text()), data)
        search = self.rpc("tools/call", {"name": "search", "arguments": {"query": "v2rayn"}}).json()["result"]["structuredContent"]
        self.assertEqual(search, self.library.search({"query": "v2rayn"}))
        got = self.rpc("tools/call", {"name": "get", "arguments": {"id": "v2rayn"}}).json()["result"]["structuredContent"]
        self.assertEqual(got, self.library.get({"id": "v2rayn"}))


class OfficialClientTest(unittest.TestCase):
    def test_real_http_official_client(self):
        library = app.Library(Path(__file__).with_name("library.json"))
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app.create_app(library), host="127.0.0.1", port=port, access_log=False, log_level="critical"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            for _ in range(200):
                if server.started: break
                time.sleep(0.02)
            self.assertTrue(server.started)
            async def client_run():
                async with streamable_http_client(f"http://127.0.0.1:{port}/mcp", terminate_on_close=False) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        init = await session.initialize()
                        self.assertEqual(init.serverInfo.version, app.VERSION)
                        tools = await session.list_tools()
                        self.assertEqual({t.name for t in tools.tools}, {"search", "get", "query"})
                        found = await session.call_tool("search", {"query":"v2rayN", "limit":1})
                        self.assertFalse(found.isError)
                        self.assertEqual(found.structuredContent["items"][0]["id"], "v2rayn")
                        read_item = await session.call_tool("get", {"id":"v2rayn"})
                        self.assertFalse(read_item.isError)
                        self.assertEqual(read_item.structuredContent["item"]["verification"], library.records["v2rayn"]["verification"])
                        book = await session.call_tool("get_setup_book")
                        self.assertFalse(book.isError)
                        self.assertEqual(book.structuredContent, setup_book.setup_book_payload())
                        resource_list = await session.list_resources()
                        self.assertEqual([str(r.uri) for r in resource_list.resources], [setup_book.BOOK_RESOURCE_URI, "fanqiang://books/merlin", setup_book.RULES_RESOURCE_URI])
                        resource = await session.read_resource(setup_book.BOOK_RESOURCE_URI)
                        self.assertEqual(json.loads(resource.contents[0].text), book.structuredContent)
                        prompt_list = await session.list_prompts()
                        self.assertEqual([p.name for p in prompt_list.prompts], ["setup_device"])
                        prompt = await session.get_prompt("setup_device")
                        self.assertEqual(prompt.messages[2].content.text, book.structuredContent["content"])
                        with self.assertRaises(McpError) as caught:
                            await session.call_tool("get_setup_book", {"subscription": "synthetic-secret"})
                        self.assertEqual(caught.exception.error.code, -32602)
                        self.assertNotIn("synthetic-secret", str(caught.exception))
                        with self.assertRaises(McpError) as caught:
                            await session.get_prompt("setup_device", {"subscription": "synthetic-secret"})
                        self.assertNotIn("synthetic-secret", str(caught.exception))
                        unknown = await session.call_tool("get", {"id":"does-not-exist"})
                        self.assertTrue(unknown.isError)
            asyncio.run(client_run())
        finally:
            server.should_exit = True
            thread.join(5)
            sock.close()
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
