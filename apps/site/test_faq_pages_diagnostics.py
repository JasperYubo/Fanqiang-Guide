"""The diagnostics CTA stays scoped and preserves the equivalent-page contract."""
import copy
from pathlib import Path
import unittest
import test_faq_pages_v10 as fixtures

class DiagnosticsEntryTests(unittest.TestCase):
    setUp = fixtures.FaqPageTests.setUp
    build = fixtures.FaqPageTests.build

    def test_equivalent_answer_urls_get_one_cta_in_html_and_markdown(self):
        data = fixtures.fixture()
        selected = data["entries"][0]
        selected["faq_id"] = "faq-4c2d5493d990a3ea50245dd1"
        duplicate = copy.deepcopy(selected)
        duplicate["faq_id"] = "faq-ca69f90138b2e82a6cbc6462"
        duplicate["canonical_question"] = "Equivalent question"
        unrelated = copy.deepcopy(selected)
        unrelated.update(faq_id="faq-ios-installation", short_answer="Different mobile installation answer")
        data["entries"] += [duplicate, unrelated]
        self.build(data)
        for entry in (selected, duplicate):
            directory = self.public / "answers" / entry["faq_id"]
            raw = (directory / "index.html").read_text()
            markdown = (directory / "index.md").read_text()
            self.assertEqual(raw.count('id="diagnostics-next-step"'), 1)
            self.assertIn('/diagnostics/#install', raw)
            self.assertIn('/diagnostics/#submit-report', markdown)
            self.assertIn("不支持手机本机采样", raw)
            self.assertIn("固定诊断目标", markdown)
        raw = (self.public / "answers/faq-ios-installation/index.html").read_text()
        self.assertNotIn('id="diagnostics-next-step"', raw)

    def test_router_context_asks_for_a_connected_computer_not_router_install(self):
        data = fixtures.fixture()
        data["entries"][0]["faq_id"] = "faq-c77f1b4e6050233d09cc7090"
        self.build(data)
        directory = self.public / "answers" / data["entries"][0]["faq_id"]
        for filename in ("index.html", "index.md"):
            content = (directory / filename).read_text()
            self.assertIn("在连接这台路由器的 Windows 或 Linux 电脑上运行", content)
            self.assertIn("不会读取路由器插件配置或日志", content)

    def test_installation_page_has_both_real_destinations_and_no_auto_start(self):
        page = Path(__file__).resolve().parents[1] / "diagnostics/site/index.html"
        raw = page.read_text(encoding="utf-8")
        self.assertEqual(raw.count('id="install"'), 1)
        self.assertEqual(raw.count('id="submit-report"'), 1)
        self.assertNotIn("127.0.0.1", raw)
        self.assertNotIn("googletagmanager", raw)
        self.assertNotIn("<script", raw)

if __name__ == "__main__":
    unittest.main()
