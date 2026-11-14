"""Shared product facts must survive registry changes without two-site drift."""
from copy import deepcopy
import html
import importlib.util
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = load("product_contract_test", "apps/site/product_contract.py")
sync = load("pages_sync_test", "developer/sync_pages_contract.py")


class ProductContractTests(unittest.TestCase):
    def test_shared_server_and_book_facts_are_the_pinned_mcp_registry(self):
        registry = runpy.run_path(str(ROOT / "apps/lookup/runtime/setup_book.py"))
        actual = contract.product_facts()
        self.assertEqual(actual["server"], registry["book_manifest"]("server"))
        self.assertEqual([{key: value for key, value in book.items() if key != "display_title"} for book in actual["books"]],
                         registry["book_catalog"]()["books"])
        self.assertEqual([book["display_title"] for book in actual["books"]], ["设备配置", "梅林路由器", "服务器助手"])
        self.assertEqual(actual["book_count"], len(registry["BOOK_REGISTRY"]))
        self.assertEqual(actual["price_sentence"], "充值 10 元，即可开始使用 AI 维护。VPS 自备，费用另计。")
        self.assertEqual(actual["mcp_url"], actual["site_url"] + "mcp")

    def test_book_version_url_and_server_updates_reach_pages_without_copying_facts(self):
        changed = deepcopy(contract.product_facts())
        server = changed["server"]
        server.update(version="9.2", download_url="https://fanqiang.guide/ai/books/server-test-v9.2.ilang.md",
                      entry_url="https://fanqiang.guide/server-new/", installer_url="https://fanqiang.guide/server-new/install.sh",
                      install_command="curl https://fanqiang.guide/server-new/install.sh && bash reviewed.sh")
        server["assistant"].update(runtime="TestRuntime", runtime_version="9.2", model="test-model")
        next(book for book in changed["books"] if book["book_id"] == "server").update(
            version=server["version"], download_url=server["download_url"])
        changed["os_label"] = "全新的 Test OS VPS"
        changed["price_sentence"] = "共享价格说明测试。"
        template = "\n".join("{{" + token + "}}" for token in sorted(sync.REQUIRED_TOKENS))
        rendered = html.unescape(sync.render(template, changed))
        for value in (server["entry_url"], server["installer_url"], server["install_command"],
                      "server-test-v9.2.ilang.md", "v9.2", "TestRuntime", "test-model", changed["os_label"], changed["price_sentence"]):
            self.assertIn(value, rendered)
        self.assertNotIn("{{", rendered)

    def test_new_book_is_listed_without_hardcoded_count_or_card(self):
        changed = deepcopy(contract.product_facts())
        extra = deepcopy(changed["books"][0])
        extra.update(book_id="new-test-book", title="New public book", display_title="新工程书", version="4.5", download_url="https://fanqiang.guide/ai/books/new-test.md")
        changed["books"].append(extra)
        changed["book_count"] = len(changed["books"])
        template = "\n".join("{{" + token + "}}" for token in sorted(sync.REQUIRED_TOKENS))
        rendered = sync.render(template, changed)
        self.assertEqual(rendered.count('class="book-link"'), changed["book_count"])
        self.assertIn('href="https://fanqiang.guide/ai/books/new-test.md"', rendered)
        self.assertIn("v4.5", rendered)

    def test_missing_or_unknown_tokens_fail_instead_of_publishing_partial_facts(self):
        template = "\n".join("{{" + token + "}}" for token in sorted(sync.REQUIRED_TOKENS))
        with self.assertRaisesRegex(ValueError, "missing="):
            sync.render(template.replace("{{MCP_URL}}", "hardcoded old MCP"))
        with self.assertRaisesRegex(ValueError, "unknown="):
            sync.render(template + "{{UNKNOWN_FACT}}")

    def test_main_site_module_works_from_isolated_build_layout(self):
        # Production build copies apps/site and apps/lookup into an isolated root.
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "apps/site").mkdir(parents=True)
            shutil.copyfile(ROOT / "apps/site/product_contract.py", root / "apps/site/product_contract.py")
            shutil.copytree(ROOT / "apps/lookup/runtime/books", root / "apps/lookup/runtime/books")
            shutil.copyfile(ROOT / "apps/lookup/runtime/setup_book.py", root / "apps/lookup/runtime/setup_book.py")
            spec = importlib.util.spec_from_file_location("isolated_product_contract", root / "apps/site/product_contract.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.product_facts(), contract.product_facts())


if __name__ == "__main__":
    unittest.main()
