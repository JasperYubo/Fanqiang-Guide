"""Router mode transport tests against the official MCP SDK and real curated matrix."""
import hashlib
import io
import json
import logging
from pathlib import Path
import unittest
from starlette.testclient import TestClient
import app
import setup_book

class RouterTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = app.Library(Path(__file__).with_name("library.json"))
        cls.context = TestClient(app.create_app(cls.library),
            base_url="http://127.0.0.1:8765", raise_server_exceptions=False)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def rpc_response(self, method, params):
        return self.client.post("/mcp", json={"jsonrpc":"2.0","id":81,
            "method":method,"params":params}, headers={"Accept":"application/json, text/event-stream"})

    def rpc(self, method, params):
        response = self.rpc_response(method, params)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("error", data)
        self.assertFalse(data["result"].get("isError", False))
        return data["result"]

    def test_router_http_mcp_identical(self):
        for values in (
            {"router_model":"RT-AX86U"},
            {"router_model":"RT-AX86U","firmware_family":"koolcenter-merlin-mod",
             "firmware_branch":"3004.388","architecture":"aarch64","protocol":"vless","package_variant":"lite"},
            {"router_model":"ZenWiFi_BD4","firmware_family":"koolcenter-asuswrt-mod"},
            {"router_model":"TUF-BE6500","firmware_family":"koolcenter-asuswrt-mod"},
            {"router_model":"RT-AX89X","architecture":"aarch64"},
            {"router_model":"RT-AX86U","protocol":"tuic","package_variant":"lite"},
            {"router_model":"RT-AX86U","limit":1,"offset":1},
            {"router_model":"RT-AX86U","kernel":"4.1.52-"+"a"*30},
        ):
            with self.subTest(values=values):
                http = self.client.get("/api/agent/query",params=values)
                self.assertEqual(http.status_code,200,http.text)
                mcp = self.rpc("tools/call",{"name":"query","arguments":values})
                result=mcp["structuredContent"]
                self.assertEqual(result,json.loads(mcp["content"][0]["text"]))
                self.assertEqual(http.json(),result)
                self.assertEqual(http.headers["cache-control"],"no-store")
                self.assertEqual(result["query_mode"],"router")
                self.assertEqual(result["book_resource"],"fanqiang://books/merlin")
                self.assertLess(len(http.content),app.MAX_RESPONSE)

    def test_router_discovery_reuses_query(self):
        tools=self.rpc("tools/list",{})["tools"]
        self.assertEqual({t["name"] for t in tools},{"search","get","query","get_server_setup"})
        query=next(t for t in tools if t["name"]=="query")
        self.assertTrue(query["annotations"]["readOnlyHint"])
        self.assertFalse(query["inputSchema"]["additionalProperties"])
        for key in ("router_model","hardware_revision","device_model_id","firmware_family","firmware_branch",
                    "firmware_version","architecture","kernel","package_variant"):
            self.assertIn(key,query["inputSchema"]["properties"])
        self.assertIn("fanqiang://books/merlin",query["description"])

    def test_router_parameters_cannot_silently_override_generic_filters(self):
        for params in (
            {"router_model":"RT-AX86U","platform":"android"},
            {"router_model":"RT-AX86U","kind":"client"},
            {"router_model":"RT-AX86U","feature":"tun"},
            {"router_model":"RT-AX86U","os_version":"14"},
            {"router_model":"RT-AX86U","limit":"true"},
            {"router_model":"RT-AX86U","offset":"-1"},
            {"router_model":"RT-AX86U","unknown":"1"},
        ):
            self.assertEqual(self.client.get("/api/agent/query",params=params).status_code,400,params)
            rpc=self.rpc_response("tools/call",{"name":"query","arguments":params}).json()
            self.assertEqual(rpc["error"]["code"],-32602)

    def test_router_private_values_rejected_before_sdk_logging(self):
        secret="https://private.invalid/sub?token=SYNTHETIC_ROUTER_SECRET_73914"
        output=io.StringIO();handler=logging.StreamHandler(output)
        logging.getLogger().addHandler(handler)
        try:
            for key in ("router_model","hardware_revision","device_model_id","firmware_family","firmware_branch",
                        "firmware_version","architecture","kernel","package_variant"):
                params={"router_model":"RT-AX86U",key:secret}
                response=self.client.get("/api/agent/query",params=params)
                self.assertEqual(response.status_code,400,key)
                self.assertNotIn("SYNTHETIC_ROUTER_SECRET",response.text)
                rpc=self.rpc_response("tools/call",{"name":"query","arguments":params})
                self.assertEqual(rpc.json()["error"]["code"],-32602)
                self.assertNotIn("SYNTHETIC_ROUTER_SECRET",rpc.text)
            self.assertNotIn("SYNTHETIC_ROUTER_SECRET",output.getvalue())
        finally:
            logging.getLogger().removeHandler(handler)

    def test_router_malformed_types_are_fixed_errors(self):
        for value in ([],{},True,12):
            response=self.rpc_response("tools/call",{"name":"query","arguments":{"router_model":value}})
            self.assertEqual(response.json()["error"]["code"],-32602)

    def test_registered_books_are_retrievable_with_exact_content(self):
        catalog=self.client.get("/api/agent/books").json()
        self.assertEqual({b["book_id"] for b in catalog["books"]},{"autosetup","merlin","server"})
        for ident in ("autosetup","merlin"):
            expected=setup_book.book_payload(ident)
            response=self.client.get("/api/agent/books/"+ident)
            self.assertEqual(response.json(),expected)
            remote=self.rpc("resources/read",{"uri":"fanqiang://books/"+ident})
            self.assertEqual(json.loads(remote["contents"][0]["text"]),expected)
            self.assertEqual(hashlib.sha256(expected["content"].encode()).hexdigest(),expected["sha256"])
        prompt=self.rpc("prompts/get",{"name":"setup_device"})
        self.assertEqual(len(prompt["messages"]),3)
        self.assertEqual(prompt["messages"][1]["content"]["text"],setup_book.answer_rules_text())
        self.assertIn("fanqiang://books/merlin",prompt["messages"][2]["content"]["text"])

    def test_original_records_have_explicit_separate_router_handoff(self):
        response=self.client.get("/api/agent/item?id=fancyss").json()
        self.assertEqual(response["item"]["router_setup"]["book_resource"],"fanqiang://books/merlin")
        self.assertFalse(response["item"]["router_setup"]["hardware_tested"])
        self.assertIsNone(response["item"]["compatibility"]["supported_models"])

    def test_generic_queries_still_work_with_null_router_defaults(self):
        values={"kind":"client","platform":"android","limit":2}
        self.assertEqual(self.rpc("tools/call",{"name":"query","arguments":values})["structuredContent"],
                         self.client.get("/api/agent/query",params=values).json())

if __name__ == "__main__":
    unittest.main()
