"""Setup entry scope, equivalent URLs, device boundaries and legacy compatibility."""
import copy
from pathlib import Path
import unittest
import test_faq_pages_v10 as fixtures

class DiagnosticsEntryTests(unittest.TestCase):
    setUp = fixtures.FaqPageTests.setUp
    build = fixtures.FaqPageTests.build

    def test_equivalent_answer_urls_get_one_setup_entry_in_html_and_markdown(self):
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
            self.assertEqual(raw.count('id="autosetup-next-step"'), 1)
            self.assertEqual(raw.count('data-copy-mcp'), 1)
            self.assertEqual(raw.count('data-copy-setup-request'), 1)
            self.assertIn('/ai/#device-setup', raw)
            self.assertIn('https://fanqiang.guide/mcp', markdown)
            self.assertIn('/ai/setup-request.ilang', markdown)
            self.assertIn('断开后重连', markdown)
            self.assertNotIn('id="diagnostics-next-step"', raw)
            self.assertNotIn('/diagnostics/#submit-report', markdown)
        raw = (self.public / "answers/faq-ios-installation/index.html").read_text()
        self.assertNotIn('id="autosetup-next-step"', raw)

    def test_router_requires_target_control_and_downstream_verification(self):
        data = fixtures.fixture()
        data["entries"][0]["faq_id"] = "faq-c77f1b4e6050233d09cc7090"
        self.build(data)
        directory = self.public / "answers" / data["entries"][0]["faq_id"]
        for filename in ("index.html", "index.md"):
            content = (directory / filename).read_text()
            self.assertIn("型号、固件和实际控制权限", content)
            self.assertIn("路由器本机与下游设备要分别验收", content)
            self.assertIn("保留恢复方式", content)

    def test_mobile_does_not_treat_desktop_checks_as_phone_success(self):
        data = fixtures.fixture()
        data["entries"][0]["faq_id"] = "faq-33d46f18184a41076fbe00f5"
        self.build(data)
        directory = self.public / "answers" / data["entries"][0]["faq_id"]
        for filename in ("index.html", "index.md"):
            content = (directory / filename).read_text()
            self.assertIn("只在电脑上测通，不能证明手机已配置", content)
            self.assertIn("手机的系统 VPN 授权", content)
            self.assertIn("不得声称已经完成", content)

    def test_legacy_diagnostics_page_still_has_destinations_without_auto_start(self):
        page = Path(__file__).resolve().parents[1] / "diagnostics/site/index.html"
        raw = page.read_text(encoding="utf-8")
        self.assertEqual(raw.count('id="install"'), 1)
        self.assertEqual(raw.count('id="submit-report"'), 1)
        self.assertNotIn("127.0.0.1", raw)
        self.assertNotIn("googletagmanager", raw)
        self.assertNotIn("<script", raw)

if __name__ == "__main__":
    unittest.main()
