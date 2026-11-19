"""Real JSON-RPC server handoff, transport parity and privacy regressions."""
import hashlib
import io
import json
import logging
from pathlib import Path
import unittest

from starlette.testclient import TestClient

import app
import setup_book


class ServerSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = app.Library(Path(__file__).with_name("library.json"))
        cls.context = TestClient(app.create_app(cls.library), base_url="http://127.0.0.1:8765")
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)

    def post(self, method, params=None, **envelope):
        return self.client.post("/mcp", headers={"Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25"}, json={"jsonrpc": "2.0", "id": 71,
            "method": method, "params": params or {}, **envelope})

    def rpc(self, method, params=None):
        response = self.post(method, params)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertNotIn("error", payload, payload)
        return payload["result"]

    def test_troubleshooting_resource_http_and_catalog_have_same_pinned_content(self):
        expected = setup_book.book_payload("troubleshooting")
        self.assertIsNone(expected["prompt"], "Troubleshooting is a directly read resource, not the installation prompt")
        resources = self.rpc("resources/list")["resources"]
        resource = next(row for row in resources if row["uri"] == "fanqiang://books/troubleshooting")
        self.assertEqual(resource["_meta"], setup_book.book_manifest("troubleshooting"))
        self.assertIn("排障", resource["description"])
        result = self.rpc("resources/read", {"uri": resource["uri"]})
        self.assertEqual(json.loads(result["contents"][0]["text"]), expected)
        self.assertEqual(self.client.get("/api/agent/books/troubleshooting").json(), expected)
        self.assertEqual(hashlib.sha256(expected["content"].encode()).hexdigest(), expected["sha256"])
        self.assertIn("huarun doctor --json", expected["content"])
        self.assertIn("DeepSeek", expected["content"])
        self.assertEqual(len(self.client.get("/api/agent/books").json()["books"]), 4)

    def test_server_metadata_declares_mcp_first_search_fallback_and_recheck(self):
        meta = setup_book.book_manifest("server")
        self.assertEqual(meta["version"], "1.4")
        policy = meta["knowledge_policy"]
        self.assertEqual(policy["primary"], "huarun_mcp")
        self.assertEqual(policy["fallback"], "deepseek_search_when_insufficient")
        self.assertIn("fanqiang://books/troubleshooting", policy["resources"])
        self.assertEqual(policy["recheck"], ["huarun doctor --json", "huarun status --json"])
        self.assertEqual(policy["instruction_format"], "iLang")

    def test_provider_discovery_is_open_ended_and_statuses_do_not_conflate_unknown_with_absent_api(self):
        meta = setup_book.book_manifest("server")
        rotation = meta["network_maintenance"]["automatic_ip_rotation"]
        self.assertEqual(rotation["provider_scope"], "open_ended_official_document_discovery")
        self.assertEqual(rotation["unknown_provider"], "discover_validate_then_activate")
        self.assertEqual(rotation["no_api"], "notify_owner_only_after_official_evidence")
        self.assertNotIn("providers", rotation, "Built-in adapters are not a closed provider allowlist")
        self.assertIn("aws_elastic_ip", rotation["built_in_adapters"])
        self.assertEqual(rotation["discovery_commands"], {"discover": "huarun network provider-discover", "status": "huarun network provider-status"})
        self.assertEqual(rotation["provider_setup_command"], "huarun network provider-setup")
        self.assertIn("cloudflare_token", rotation["provider_setup_preserves"])
        self.assertNotIn(rotation["provider_setup_command"], rotation["agent_allowed_commands"])
        self.assertEqual(rotation["discovery_order"][0], "huarun_mcp")
        self.assertIn("official_document_fetch", rotation["discovery_order"])
        self.assertTrue({"no_api_documented", "credentials_required", "parameters_required", "documentation_unavailable", "documentation_incomplete", "identity_unconfirmed", "adapter_contract_unsupported", "adapter_validation_failed"} <= set(rotation["separate_action_required_states"]))
        self.assertEqual(rotation["credentials"], "local_private_secret_references_never_sent_to_model")
        self.assertIn("validated_provider_profiles", meta["automatic_updates"]["preserves"])
        book = setup_book.book_payload("server")["content"]
        for phrase in ("PROVIDER_DISCOVERY_AND_ADAPTERS", "huarun network provider-discover", "声明式", "只读核对"):
            self.assertIn(phrase, book)

    def test_existing_server_handoff_never_routes_to_fresh_installation(self):
        initialized = self.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "migration-test", "version": "1"}})
        instructions = initialized["instructions"].split("::MODULE{SERVER_SETUP}")[1].split("::MODULE{DEVICE_SETUP}")[0]
        tool = next(t for t in self.rpc("tools/list")["tools"] if t["name"] == "get_server_setup")
        prompt = self.rpc("prompts/get", {"name": "setup_server"})["messages"][0]["content"]["text"]
        for text in (instructions, tool["description"], prompt):
            with self.subTest(surface=text[:50]):
                self.assertIn("For a fresh installation", text)
                self.assertIn("For an existing 1.0 or 1.1 server", text)
                self.assertIn("only the book's one-time --upgrade-assistant migration", text)
                self.assertIn("Preserve node configuration, whitelist and API Key", text)
                self.assertIn("do not reinstall the network or ask for another Key", text)
                for old in ("[MUST] First use https://platform.deepseek.com", "[MUST] Start at https://platform.deepseek.com",
                            "[MUST] Install PicoClaw", "[MUST] Follow PicoClaw", "[MUST] Follow the server book's PicoClaw"):
                    self.assertNotIn(old, text)
        description = next(p for p in self.rpc("prompts/list")["prompts"] if p["name"] == "setup_server")["description"]
        self.assertIn("已装 1.0 / 1.1", description)
        self.assertIn("不要求重装或重新提供 Key", description)

    def test_automatic_update_metadata_preserves_existing_server_and_admin_boundary(self):
        meta = setup_book.book_manifest("server")
        self.assertEqual(meta["assistant"]["version"], "1.4.0")
        update = meta["automatic_updates"]
        self.assertTrue(update["enabled_by_default"])
        self.assertEqual((update["interval_hours"], update["boot_delay_minutes"], update["random_delay_max_minutes"]), (6, 10, 30))
        self.assertEqual(update["timer"], "huarun-auto-update.timer")
        self.assertEqual(update["release_source"], "github_published_release_with_matching_sites")
        self.assertTrue(update["existing_installation_requires_one_time_migration"])
        self.assertEqual(update["migration_command"], meta["upgrade_command"])
        self.assertFalse(update["network_services_restarted"])
        self.assertTrue(update["backup_before_update"] and update["rollback_on_failure"])
        self.assertEqual(update["busy_policy"], "defer_while_chat_or_manager_active")
        self.assertIn("chat_memory", update["preserves"])
        self.assertEqual(update["agent_allowed_commands"], ["huarun auto-update status"])
        self.assertEqual(set(update["commands"]), {"status", "check", "disable", "enable"})

    def test_initialize_routes_server_and_client_flows_separately(self):
        result = self.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "server-test", "version": "1"}})
        self.assertEqual(result["serverInfo"]["version"], "2.6.0")
        instructions = result["instructions"]
        server = instructions.split("::MODULE{SERVER_SETUP}")[1].split("::MODULE{DEVICE_SETUP}")[0]
        for value in ("get_server_setup", "fanqiang://books/server", "setup_server", "https://platform.deepseek.com",
                      "10 CNY", setup_book.SERVER_INSTALL_COMMAND, "PicoClaw", "deepseek-flash", "huarun chat"):
            self.assertIn(value, server)
        self.assertNotIn("www.deepseek.com", server)
        self.assertIn("fanqiang://books/autosetup", instructions.split("::MODULE{DEVICE_SETUP}")[1])

    def test_tool_resource_http_and_card_return_the_same_pinned_server_book(self):
        expected = setup_book.book_payload("server")
        tool = self.rpc("tools/call", {"name": "get_server_setup"})
        self.assertFalse(tool.get("isError"), tool)
        self.assertEqual(tool["structuredContent"], expected)
        self.assertEqual(json.loads(tool["content"][0]["text"]), expected)
        resource = self.rpc("resources/read", {"uri": "fanqiang://books/server"})
        self.assertEqual(json.loads(resource["contents"][0]["text"]), expected)
        self.assertEqual(self.client.get("/api/agent/books/server").json(), expected)
        catalog = self.client.get("/api/agent/books").json()
        metadata = next(b for b in catalog["books"] if b["book_id"] == "server")
        self.assertEqual(metadata, {key: value for key, value in expected.items() if key != "content"})
        card = self.client.get("/.well-known/mcp/server-card.json").json()
        self.assertEqual(card["serverAssistant"], metadata)
        self.assertEqual(card["setupBook"]["book_id"], "autosetup")
        self.assertEqual(hashlib.sha256(expected["content"].encode()).hexdigest(), expected["sha256"])
        self.assertEqual(expected["prompt"], "setup_server")
        self.assertEqual(expected["tool"], "get_server_setup")
        self.assertEqual(expected["entry_url"], "https://fanqiang.guide/server/")
        self.assertEqual(expected["installer_url"], "https://fanqiang.guide/server/install.sh")
        self.assertEqual(expected["install_command"], "curl -fsSLo huarun-install.sh https://fanqiang.guide/server/install.sh && bash huarun-install.sh")
        self.assertIn("充值 10 元，即可开始使用 AI 维护。VPS 自备，费用另计。", expected["content"])
        self.assertEqual(expected["assistant"]["model"], "deepseek-flash")
        self.assertFalse(expected["recommended_api_balance"]["minimum_required"])

    def test_server_discovery_is_readonly_and_accepts_no_arguments(self):
        tools = self.rpc("tools/list")["tools"]
        tool = next(t for t in tools if t["name"] == "get_server_setup")
        self.assertEqual(tool["inputSchema"], setup_book.NO_ARGUMENTS_SCHEMA)
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])
        self.assertIn("platform.deepseek.com", tool["description"])
        resources = self.rpc("resources/list")["resources"]
        server = next(b for b in resources if b["uri"] == "fanqiang://books/server")
        self.assertEqual(server["_meta"], setup_book.book_manifest("server"))
        self.assertIn("PicoClaw", server["description"])
        prompts = self.rpc("prompts/list")["prompts"]
        prompt = next(p for p in prompts if p["name"] == "setup_server")
        self.assertEqual(prompt.get("arguments", []), [])

    def test_prompt_uses_complete_rules_and_server_book_not_device_intake(self):
        for args in (None, {}):
            params = {"name": "setup_server"}
            if args is not None:
                params["arguments"] = args
            messages = self.rpc("prompts/get", params)["messages"]
            self.assertEqual(len(messages), 3)
            self.assertIn("SETUP_SERVER_HANDOFF", messages[0]["content"]["text"])
            self.assertIn("https://platform.deepseek.com", messages[0]["content"]["text"])
            self.assertEqual(messages[1]["content"]["text"], setup_book.answer_rules_text())
            self.assertEqual(messages[2]["content"]["text"], setup_book.book_payload("server")["content"])
        client = self.rpc("prompts/get", {"name": "setup_device"})["messages"]
        self.assertEqual(client[2]["content"]["text"], setup_book.book_payload("autosetup")["content"])
        self.assertIn("fanqiang://books/merlin", client[0]["content"]["text"])

    def test_server_search_handoff_preserves_library_records_and_client_routes(self):
        for query in ("服务器助手", "华润服务器助手安装", "安装自己的 VPS", "搭建VPS", "VPS安装", "搭建服务器", "repair my VPS", "PicoClaw", "Get-Bot"):
            with self.subTest(query=query):
                rpc = self.rpc("tools/call", {"name": "search", "arguments": {"query": query}})["structuredContent"]
                http = self.client.get("/api/agent/search", params={"query": query}).json()
                self.assertEqual(rpc, http)
                self.assertEqual(rpc["server_setup"], setup_book.book_manifest("server"))
                self.assertEqual(rpc["returned"], len(rpc["items"]))
                self.assertEqual(rpc["snapshot"]["record_count"], 310)
        for query in ("Linux 客户端", "v2rayN", "Android", "手机热点", "fancyss", "路由器安装", "server"):
            with self.subTest(query=query):
                result = self.rpc("tools/call", {"name": "search", "arguments": {"query": query}})["structuredContent"]
                self.assertNotIn("server_setup", result)
        router = self.rpc("tools/call", {"name": "get", "arguments": {"id": "fancyss"}})["structuredContent"]
        self.assertEqual(router["item"]["router_setup"]["book_resource"], "fanqiang://books/merlin")

    def test_server_interfaces_reject_private_inputs_before_sdk_logging(self):
        secret = "SYNTHETIC_SERVER_SECRET_NEVER_ECHO_4739"
        log = io.StringIO()
        handler = logging.StreamHandler(log)
        logger = logging.getLogger()
        logger.addHandler(handler)
        try:
            for method, name in (("tools/call", "get_server_setup"), ("prompts/get", "setup_server")):
                for arguments in ({"api_key": secret}, {"root_password": {"value": secret}}, [secret], secret):
                    response = self.post(method, {"name": name, "arguments": arguments})
                    self.assertEqual(response.json()["error"]["code"], -32602)
                    self.assertNotIn(secret, response.text)
                response = self.post(method, {"name": name, "target": secret})
                self.assertEqual(response.json()["error"]["code"], -32602)
                self.assertNotIn(secret, response.text)
                response = self.post(method, {"name": name}, id={"private": secret})
                self.assertEqual(response.json()["error"]["code"], -32600)
                self.assertNotIn(secret, response.text)
                response = self.post(method, {"name": name, "_meta": {"progressToken": {"private": secret}}})
                self.assertEqual(response.json()["error"]["code"], -32602)
                self.assertNotIn(secret, response.text)
                self.assertIn("result", self.post(method, {"name": name, "_meta": {"progressToken": "public"}}).json())
            for response in (self.client.get("/api/agent/books/server", params={"api_key": secret}),
                             self.client.request("GET", "/api/agent/books/server", content=secret)):
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(secret, response.text)
        finally:
            logger.removeHandler(handler)
        self.assertNotIn(secret, log.getvalue())


if __name__ == "__main__":
    unittest.main()
