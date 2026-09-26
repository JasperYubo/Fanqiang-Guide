"""Publication tests use synthetic fixtures only inside temporary directories."""
import copy
import html
import json
import re
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from cases_v10 import SITE, build_cases, normalize, render

BOOK = "::ILANG::v5.0\n[TYPE:engineering_book][LANG:zh]\n\n::MODULE{REFERENCE}\n  [MUST] 请核对用户自己的设备条件与第一方来源。\n::ILANG::COMPLETE::"


def fixture():
    return {"schema_version": "1.0", "slug": "case-fixture", "intent_key": "fixture-windows-selection",
            "title": "测试：Windows 客户端怎么选", "question": "测试设备应该选哪个客户端？",
            "answer_summary": "测试结论需要核对系统与官方安装包。", "constraints": ["Windows，架构尚未确认"],
            "selection_reasons": ["先确认架构，再核对官方发布入口"],
            "sources": [{"title": "官方指南", "url": "https://fanqiang.guide/guides/client-downloads.html", "checked_at": "2026-09-27"}],
            "result": {"resolution": "unconfirmed", "delivery": "delivered", "execution": "unverified", "confirmed_at": None},
            "publication": {"approved": True, "anonymized": True},
            "published_at": "2026-09-27T03:00:00Z", "updated_at": "2026-09-27T03:00:00Z",
            "engineering_book_public": BOOK,
            "conversation_public": [{"role": "user", "content": "请按我的设备选型。"}, {"role": "assistant", "content": "请核对系统架构。"}],
            "sections": [{"heading": "安装包核对", "paragraphs": ["按第一方发布页核对架构。"]}]}


def page(title, description, path, body, schemas, md=None):
    structured = json.dumps({"@context": "https://schema.org", "@graph": schemas}, ensure_ascii=False).replace("</", "<\\/")
    return f'<html><head><meta name="robots" content="index,follow"><link rel="canonical" href="{SITE}{path}"><link rel="alternate" href="{SITE}{md}"><script type="application/ld+json">{structured}</script></head><body>{body}</body></html>'


class CaseTests(unittest.TestCase):
    def test_requires_actual_public_approval(self):
        for field in ("approved", "anonymized"):
            raw = fixture()
            raw["publication"][field] = False
            with self.assertRaises(ValueError):
                normalize(raw)

    def test_real_ilang_is_required(self):
        for book in ("中文正文 ::ILANG 标签", "::ILANG::v5.0\n::BOGUS{broken}\n::ILANG::COMPLETE::"):
            raw = fixture()
            raw["engineering_book_public"] = book
            with self.assertRaises(ValueError):
                normalize(raw)

    def test_confirmation_is_user_feedback_not_delivery(self):
        raw = fixture()
        out = render(normalize(raw), page)
        self.assertIn("工程书已交付", out["index.html"])
        self.assertIn("实际执行尚未验证", out["index.html"])
        self.assertNotIn("用户反馈实际执行成功", out["index.html"])
        raw["result"]["execution"] = "confirmed_success"
        with self.assertRaises(ValueError):
            normalize(raw)
        raw["result"]["confirmed_at"] = "2026-09-27T04:00:00Z"
        self.assertIn("用户反馈实际执行成功", render(normalize(raw), page)["index.html"])

    def test_escaping_and_allowlist(self):
        raw = fixture()
        raw["title"] = '<script>alert("fixture")</script>'
        raw["answer_summary"] = '</script><img src=x onerror="boom">'
        raw["conversation_public"][0]["content"] = '<iframe src="evil">'
        raw["private_raw_session"] = "never publish this value"
        clean = normalize(raw)
        outputs = render(clean, page)
        self.assertNotIn('<img src=x onerror=', outputs["index.html"])
        self.assertIn("&lt;iframe", outputs["index.html"])
        self.assertNotIn("private_raw_session", outputs["case.json"])
        schemas = json.loads(re.search(r'application/ld\+json">(.*?)</script>', outputs["index.html"]).group(1))
        self.assertEqual(schemas["@graph"][0]["headline"], raw["title"])
        self.assertIn("&lt;script&gt;", outputs["index.md"])

    def test_private_values_and_unsafe_sources_fail_closed(self):
        for value in ("contact fixture@example.com", "host 192.168.5.20", "sk-abcdefghijklmnop123456", "ss://abcsecret@host", "https://host/sub?token=private", "电话 13800138000"):
            raw = fixture()
            raw["answer_summary"] = value
            with self.assertRaises(ValueError):
                normalize(raw)
        for url in ("javascript:alert(1)", "https://user:password@example.org/", "https://example.org/?token=secret"):
            raw = fixture()
            raw["sources"][0]["url"] = url
            with self.assertRaises(ValueError):
                normalize(raw)

    def test_stable_context_url_sources_and_revocation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            public, source = root / "public", root / "source"
            (public / ".well-known").mkdir(parents=True)
            (public / "ai").mkdir()
            (public / "guides").mkdir()
            (source / "case-fixture").mkdir(parents=True)
            (source / "case-fixture/case.json").write_text(json.dumps(fixture()), encoding="utf-8")
            (public / "sitemap.xml").write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://fanqiang.guide/guides/client-downloads.html</loc></url></urlset>', encoding="utf-8")
            (public / ".well-known/ai-catalog.json").write_text('{"entries":[{"identifier":"kept"}]}', encoding="utf-8")
            for name in ("llms.txt", "ai/index.md"):
                (public / name).write_text("existing first-party guide content", encoding="utf-8")
            for name in ("index.html", "guides/index.html"):
                (public / name).write_text('<head></head><div id="chat-panel"></div><nav aria-label="页脚导航"></nav>', encoding="utf-8")
            first = build_cases(public, source, page)
            self.assertEqual(first["cases"], 1)
            build_cases(public, source, page)
            sitemap = (public / "sitemap.xml").read_text(encoding="utf-8")
            self.assertEqual(sitemap.count(SITE + "/cases/case-fixture/</loc>"), 1)
            self.assertIn("client-downloads.html", sitemap)
            self.assertIn('id="chat-panel"', (public / "index.html").read_text(encoding="utf-8"))
            self.assertIn("kept", (public / ".well-known/ai-catalog.json").read_text(encoding="utf-8"))
            self.assertEqual((public / "llms-full.txt").read_bytes(), (public / "ai/index.md").read_bytes())
            raw = (public / "cases/case-fixture/index.html").read_text(encoding="utf-8")
            for link in ("index.md", "engineering.ilang", "conversation.md"):
                self.assertIn(f'/cases/case-fixture/{link}', raw)
                self.assertTrue((public / "cases/case-fixture" / link).is_file())
            case = json.loads((public / "cases/case-fixture/case.json").read_text(encoding="utf-8"))
            self.assertEqual(case["sources"], fixture()["sources"])
            (source / "case-fixture/case.json").unlink()
            build_cases(public, source, page)
            self.assertFalse((public / "cases/case-fixture/index.html").exists())
            self.assertNotIn("/cases/case-fixture/", (public / "sitemap.xml").read_text(encoding="utf-8"))
            self.assertIn('content="noindex,follow"', (public / "cases/index.html").read_text(encoding="utf-8"))

    def test_duplicate_intent_requires_existing_url(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for slug in ("case-fixture", "case-other"):
                (root / slug).mkdir()
                raw = fixture()
                raw["slug"] = slug
                (root / slug / "case.json").write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate intent"):
                build_cases(root / "never-write", root, page)


if __name__ == "__main__":
    unittest.main()
