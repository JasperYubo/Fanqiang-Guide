'''Regression checks for the public installation handoff, not server execution.'''
import gzip
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from reading_ui import enhance_code_blocks
from server_assistant import (BOOK_PATH, CSS_PATH, ENTRY_URL, INSTALL_COMMAND,
                              NS, add_server_discovery, build_server_page)


class CodeReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.code = []
        self.current = []

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self.depth += 1
            self.current = []

    def handle_data(self, data):
        if self.depth:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "pre":
            self.code.append("".join(self.current))
            self.depth -= 1


class ServerPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.public = Path(self.tmp.name) / "public"
        self.source = Path(self.tmp.name) / "server-source"
        self.public.mkdir()
        self.source.mkdir()
        self.installer = b"#!/usr/bin/env bash\nprintf 'fixture only\\n'\n"
        (self.source / "install.sh").write_bytes(self.installer)
        (self.source / "README.md").write_text("# Server\n", encoding="utf-8")

    @staticmethod
    def page(title, description, path, body, schemas, md):
        return ('<!doctype html><html><head><title>' + escape(title) +
                '</title><link rel="canonical" href="https://fanqiang.guide' +
                path + '"></head><body>' + body + '</body></html>')

    def build(self):
        build_server_page(self.public, self.page, self.source)
        return (self.public / "server/index.html").read_text(encoding="utf-8")

    def discovery_fixture(self):
        (self.public / "index.html").write_text(
            '<html><head></head><body><section class="hero wrap"><div class="hero-actions">'
            '<a href="#topics">现有工具导航</a></div><div id="chat-panel">现有聊天</div></section>'
            '<aside class="start-card wrap"><a href="/ai/#device-setup">已有设备配置</a></aside>'
            '</body></html>', encoding="utf-8")
        (self.public / ".well-known").mkdir()
        (self.public / ".well-known/ai-catalog.json").write_text(
            '{"entries":[{"identifier":"existing","url":"https://fanqiang.guide/ai/"}]}')
        (self.public / "sitemap.xml").write_text(
            '<urlset xmlns="' + NS + '"><url><loc>https://fanqiang.guide/</loc></url></urlset>')
        (self.public / "index.md").write_text("# Existing\n")
        (self.public / "ai").mkdir()
        (self.public / "ai/index.md").write_text("# AI entry\n")
        (self.public / "llms.txt").write_text("# Existing discovery\n")

    def test_installer_is_exact_and_gzip_matches(self):
        self.build()
        for relative, expected in (("server/install.sh", self.installer),):
            path = self.public / relative
            self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(gzip.decompress(path.with_name(path.name + ".gz").read_bytes()), expected)
        self.assertTrue((self.public / CSS_PATH.lstrip("/")).is_file())
        markdown = (self.public / "server/index.md").read_text(encoding="utf-8")
        self.assertIn(INSTALL_COMMAND, markdown)
        self.assertIn(ENTRY_URL, markdown)
        self.assertNotIn("{{", markdown)

    def test_handoff_order_copy_text_and_no_secret_form(self):
        raw = enhance_code_blocks(self.build())
        steps = ['id="' + value + '"' for value in ("prepare", "connect", "install", "client", "assistant")]
        self.assertEqual(sorted(raw.index(step) for step in steps), [raw.index(step) for step in steps])
        reader = CodeReader()
        reader.feed(raw)
        self.assertIn(INSTALL_COMMAND, reader.code)
        self.assertIn("ssh root@203.0.113.10", reader.code)
        self.assertIn("huarun chat", reader.code)
        self.assertIn("huarun status\nhuarun doctor\nhuarun fix", reader.code)
        self.assertEqual(raw.count("data-copy-code"), len(reader.code))
        self.assertIn('id="main"', raw)
        self.assertNotIn("<input", raw)
        self.assertNotIn("<form", raw)
        for marker in (ENTRY_URL, BOOK_PATH, "get_server_setup", "setup_server",
                       "fanqiang://books/server", "DeepSeek API 余额", "终端隐藏输入",
                       "每轮先查华润 MCP", "资料不足再用 DeepSeek 搜索", "修复后自动复查"):
            self.assertIn(marker, raw)

    def test_ssh_example_stays_readable_without_email_decoder(self):
        # Cloudflare's documented HTML exclusion must survive reader wrapping.
        raw = enhance_code_blocks(self.build())
        self.assertEqual(raw.count("<!--email_off-->"), 1)
        self.assertEqual(raw.count("<!--/email_off-->"), 1)
        protected = raw.split("<!--email_off-->", 1)[1].split("<!--/email_off-->", 1)[0]
        reader = CodeReader()
        reader.feed(protected)
        self.assertEqual(reader.code, ["ssh root@203.0.113.10"])
        self.assertEqual(protected.count("data-copy-code"), 1)
        self.assertIn("<noscript>", protected)
        self.assertNotIn(INSTALL_COMMAND, protected)
        self.assertEqual(enhance_code_blocks(raw), raw)

    def test_existing_install_upgrade_is_separate_from_fresh_install(self):
        raw = self.build()
        reader = CodeReader()
        reader.feed(raw)
        self.assertIn(INSTALL_COMMAND + " --upgrade-assistant", reader.code)
        self.assertIn('id="upgrade"', raw)
        self.assertIn("保留原节点配置、连接信息、白名单、DeepSeek Key 和聊天记忆", raw)
        markdown = (self.public / "server/index.md").read_text()
        self.assertIn(INSTALL_COMMAND + " --upgrade-assistant", markdown)
        for text in ("新安装默认开启自动更新", "旧版 1.0 / 1.1", "每 6 小时", "失败回滚", "正在使用时延期", "huarun auto-update status", "huarun auto-update disable", "不能改动更新设置"):
            self.assertIn(text, raw)
        self.assertIn("不依赖你的电脑开机", markdown)

    def test_assisted_recovery_same_command_and_guards_reach_html_and_markdown(self):
        from product_contract import product_facts
        facts = product_facts()
        html_text = self.build()
        markdown = (self.public / "server/index.md").read_text()
        for text in (html_text, markdown):
            self.assertIn(facts["assisted_recovery_sentence"], text)
            self.assertIn(facts["confirm_ip_command"], text)
            for phrase in ("每日次数上限", "未完成", "保留已验证的新静态地址"):
                self.assertIn(phrase, text)
            self.assertNotIn("{{", text)

    def test_home_entry_is_idempotent_and_preserves_device_flow(self):
        self.discovery_fixture()
        add_server_discovery(self.public)
        first = {str(p.relative_to(self.public)): p.read_bytes() for p in self.public.rglob("*") if p.is_file()}
        add_server_discovery(self.public)
        self.assertEqual(first, {str(p.relative_to(self.public)): p.read_bytes() for p in self.public.rglob("*") if p.is_file()})
        raw = (self.public / "index.html").read_text(encoding="utf-8")
        self.assertEqual(raw.count('id="server-home"'), 1)
        self.assertEqual(raw.count('href="/server/"'), 2)
        self.assertIn('id="chat-panel"', raw)
        self.assertIn('href="/ai/#device-setup"', raw)
        sitemap = ET.parse(self.public / "sitemap.xml")
        locations = [node.text for node in sitemap.iter("{" + NS + "}loc")]
        self.assertEqual(locations.count(ENTRY_URL), 1)
        self.assertIn("https://fanqiang.guide/", locations)
        catalog = json.loads((self.public / ".well-known/ai-catalog.json").read_text())
        self.assertEqual(len(catalog["entries"]), 2)
        ai_markdown = (self.public / "ai/index.md").read_text()
        self.assertIn("fanqiang://books/troubleshooting | 直接读取资源 |", ai_markdown)

    def test_missing_home_anchor_fails_instead_of_silent_omission(self):
        self.discovery_fixture()
        home = self.public / "index.html"
        home.write_text("<html><head></head><body></body></html>")
        with self.assertRaisesRegex(RuntimeError, "marker missing"):
            add_server_discovery(self.public)


if __name__ == "__main__":
    unittest.main()
