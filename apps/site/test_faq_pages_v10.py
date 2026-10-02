"""Publication contracts use synthetic answers only in temporary directories."""
import copy
import gzip
import html
import json
from pathlib import Path
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET

from faq_pages_v10 import SITE, NS, build_faq_pages, title


def fixture():
    entry = {"faq_id": "faq-test-one", "canonical_question": "测试软件从哪里下载？", "intent": "download", "entities": ["test-tool"], "platforms": ["windows"], "facets": [], "aliases": ["测试软件下载"], "required_slots": [], "version_constraints": [], "hardware_constraints": [], "forbidden_mismatch": [], "short_answer": "请核对官方发行页面的安装包与设备。", "answer_sections": [{"title": "核对范围", "content": "安装包说明不等于当前设备的实测结果。"}], "source_ids": ["source-test"], "checked_at_utc": "2026-09-20T00:00:00Z", "origin_kind": "google_autocomplete_editorial_faq", "review_state": "approved", "cache_eligible": True}
    return {"schema_version": 1, "entity_aliases": {"test-tool": ["测试软件"]}, "entries": [entry], "sources": [{"source_id": "source-test", "title": "官方发行说明", "url": "https://example.com/releases", "verification_status": "verified", "checked_at_utc": "2026-09-19T00:00:00Z"}]}


def page(title, description, path, body, schemas, md=None):
    schema = json.dumps({"@context": "https://schema.org", "@graph": schemas}, ensure_ascii=False)
    return f'<html><head><title>{html.escape(title)}</title><link rel="canonical" href="{SITE}{path}"><script type="application/ld+json">{schema}</script></head><body>{body}</body></html>'


class FaqPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.public = self.base / "public"
        (self.public / ".well-known").mkdir(parents=True)
        (self.public / "ai").mkdir()
        (self.public / "sitemap.xml").write_text(f'<urlset xmlns="{NS}"><url><loc>{SITE}/guides/existing.html</loc><lastmod>2026-09-10</lastmod></url></urlset>', encoding="utf-8")
        (self.public / ".well-known/ai-catalog.json").write_text('{"entries":[]}', encoding="utf-8")
        for name in ("llms.txt", "ai/index.md", "index.md"):
            (self.public / name).write_text("# 原有资料\n", encoding="utf-8")
        (self.public / "index.html").write_text('<html><head></head><body><main>原有首页</main></body></html>', encoding="utf-8")

    def build(self, data):
        source = self.base / "faq.json"
        source.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return build_faq_pages(self.public, source, page)

    def test_complete_answer_facts_sources_and_schema_are_shared_with_markdown(self):
        data = fixture()
        result = self.build(data)
        self.assertEqual(result["pages"], 1)
        raw = (self.public / "answers/faq-test-one/index.html").read_text(encoding="utf-8")
        md = (self.public / "answers/faq-test-one/index.md").read_text(encoding="utf-8")
        for content in (data["entries"][0]["short_answer"], data["entries"][0]["answer_sections"][0]["content"], "https://example.com/releases"):
            self.assertIn(content, raw)
            self.assertIn(content, md)
        graph = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', raw, re.S)[1])["@graph"]
        article = next(s for s in graph if s["@type"] == "Article")
        self.assertEqual(article["dateModified"], data["entries"][0]["checked_at_utc"])
        self.assertEqual(article["url"], SITE + "/answers/faq-test-one/")
        self.assertTrue(any(s["@type"] == "BreadcrumbList" for s in graph))
        self.assertNotIn("FAQPage", raw)
        self.assertNotIn("model", raw)
        for content in ("需要按自己的设备继续整理？", "说明可用的 AI、设备和需求，获取 I-Lang 工程书。"):
            self.assertIn(content, raw)
            self.assertIn(content, md)
        self.assertIn('href="/">回首页</a>', raw)

    def test_directories_prevent_orphans_and_sitemap_preserves_existing_urls(self):
        self.build(fixture())
        directory = (self.public / "answers/entity/test-tool/index.html").read_text(encoding="utf-8")
        self.assertIn('href="/answers/faq-test-one/"', directory)
        index = (self.public / "answers/index.html").read_text(encoding="utf-8")
        self.assertIn('href="/answers/entity/test-tool/"', index)
        urls = [n.text for n in ET.parse(self.public / "sitemap.xml").findall(f"{{{NS}}}url/{{{NS}}}loc")]
        self.assertIn(SITE + "/guides/existing.html", urls)
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(len(urls), 4)

    def test_exact_equivalent_content_uses_one_canonical_but_different_scope_does_not(self):
        data = fixture()
        duplicate = copy.deepcopy(data["entries"][0]); duplicate.update(faq_id="faq-test-two", canonical_question="测试软件安装说明？", facets=["installation"])
        other = copy.deepcopy(duplicate); other.update(faq_id="faq-test-three", platforms=["android"])
        data["entries"] += [duplicate, other]
        result = self.build(data)
        self.assertEqual((result["pages"], result["canonical_pages"]), (3, 2))
        raw = (self.public / "answers/faq-test-two/index.html").read_text(encoding="utf-8")
        self.assertIn('rel="canonical" href="' + SITE + '/answers/faq-test-one/"', raw)
        self.assertNotIn(SITE + "/answers/faq-test-two/", (self.public / "sitemap-answers.xml").read_text(encoding="utf-8"))

    def test_repeated_build_is_deterministic_and_discovery_has_one_natural_entry(self):
        data = fixture()
        self.build(data)
        first = {p.relative_to(self.public).as_posix(): p.read_bytes() for p in self.public.rglob("*") if p.is_file()}
        self.build(data)
        second = {p.relative_to(self.public).as_posix(): p.read_bytes() for p in self.public.rglob("*") if p.is_file()}
        self.assertEqual(first, second)
        home = (self.public / "index.html").read_text(encoding="utf-8")
        self.assertEqual(home.count('href="/answers/"'), 1)
        for target in self.public.rglob("*.gz"):
            self.assertEqual(gzip.decompress(target.read_bytes()), target.with_suffix("").read_bytes())
            self.assertEqual(target.read_bytes()[4:8], bytes(4))

    def test_navigation_link_does_not_replace_home_answer_discovery(self):
        (self.public / "index.html").write_text('<html><head></head><body><nav><a href="/answers/">常见问题</a></nav><main>原有首页</main></body></html>', encoding="utf-8")
        self.build(fixture())
        self.build(fixture())
        home = (self.public / "index.html").read_text(encoding="utf-8")
        self.assertEqual(home.count('id="faq-discovery"'), 1)
        self.assertIn('<a class="button button-primary" href="/answers/">浏览全部问答', home)

    def test_unapproved_private_sources_and_path_injection_fail_before_publication(self):
        for mutate in (lambda d: d["entries"][0].update(review_state="unreviewed"), lambda d: d["entries"][0].update(faq_id="../escape"), lambda d: d["sources"][0].update(url="https://user:password@example.com/"), lambda d: d["sources"][0].update(verification_status="reference_only")):
            data = fixture(); mutate(data)
            with self.assertRaises(ValueError):
                self.build(data)
            self.assertFalse((self.public / "answers").exists())

    def test_related_answers_are_bounded_and_do_not_cross_entities(self):
        data = fixture()
        for n in range(9):
            item = copy.deepcopy(data["entries"][0]); item.update(faq_id=f"faq-test-{n}", short_answer=f"测试答案{n}。", canonical_question=f"测试问题{n}？")
            data["entries"].append(item)
        data["entries"][-1]["entities"] = ["other-tool"]
        self.build(data)
        raw = (self.public / "answers/faq-test-one/index.html").read_text(encoding="utf-8")
        related = raw.split("<h2>相关问题</h2>", 1)[1].split("</section>", 1)[0]
        self.assertEqual(related.count("<li>"), 6)
        self.assertNotIn("faq-test-8/", related)

    def test_removed_approved_answers_and_empty_categories_do_not_survive_rebuild(self):
        data = fixture()
        extra = copy.deepcopy(data["entries"][0]); extra.update(faq_id="faq-removed", entities=["obsolete-tool"])
        data["entries"].append(extra)
        self.build(data)
        self.assertTrue((self.public / "answers/faq-removed/index.html").exists())
        self.build(fixture())
        self.assertFalse((self.public / "answers/faq-removed").exists())
        self.assertFalse((self.public / "answers/entity/obsolete-tool").exists())
        self.assertNotIn("faq-removed", (self.public / "sitemap.xml").read_text(encoding="utf-8"))

    def test_human_titles_and_deployment_mapping_match_generated_pages(self):
        data = fixture()
        data["entries"][0].update(canonical_question="测试软件出现连接问题时，应整理哪些排错资料（服务端资料、订阅地址）？", facets=["server_build", "subscription_address"], intent="troubleshooting")
        result = self.build(data)
        mapping = json.loads((self.public / "data/faq-pages.json").read_text(encoding="utf-8"))
        self.assertEqual(mapping["source_sha256"], result["source_sha256"])
        entry = mapping["entries"][0]
        self.assertEqual(entry["url"], SITE + "/answers/faq-test-one/")
        self.assertEqual(entry["canonical"], entry["url"])
        self.assertNotIn("（", entry["title"])
        self.assertIn("服务端", entry["title"])
        self.assertIn("订阅格式", entry["title"])
        self.assertNotIn("搭建教程", entry["title"])


if __name__ == "__main__":
    unittest.main()
