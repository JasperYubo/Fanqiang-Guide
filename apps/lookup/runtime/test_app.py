import asyncio
import json
import socket
import threading
import time
import unittest
from pathlib import Path

import uvicorn
from starlette.testclient import TestClient
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
        self.assertEqual({x["name"] for x in tools}, {"search", "get"})
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
                        self.assertEqual({t.name for t in tools.tools}, {"search", "get"})
                        found = await session.call_tool("search", {"query":"v2rayN", "limit":1})
                        self.assertFalse(found.isError)
                        self.assertEqual(found.structuredContent["items"][0]["id"], "v2rayn")
                        read_item = await session.call_tool("get", {"id":"v2rayn"})
                        self.assertFalse(read_item.isError)
                        self.assertEqual(read_item.structuredContent["item"]["verification"], library.records["v2rayn"]["verification"])
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
