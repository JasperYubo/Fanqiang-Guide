"""Regression checks for canonical navigation and reviewed-answer hubs."""
import copy
import html
import unittest
import test_faq_pages_v10 as fixtures

fixture = fixtures.fixture


class FaqDiscoveryTests(unittest.TestCase):
    setUp = fixtures.FaqPageTests.setUp
    build = fixtures.FaqPageTests.build

    def prepare_readers(self):
        (self.public / "guides").mkdir()
        content = ('<html><head><script>GA4_EXISTING_TAG</script></head><body>'
                   '<main><h1>Existing title</h1><p id="personal-handoff">Personal flow</p>'
                   '</main></body></html>')
        for name in ("ai/index.html", "guides/openwrt-tools.html"):
            (self.public / name).write_text(content, encoding="utf-8")
        (self.public / "guides/openwrt-tools.md").write_text("# Existing guide\n", encoding="utf-8")

    def openwrt_data(self):
        data = fixture()
        data["entries"][0]["entities"] = ["openwrt"]
        data["entity_aliases"] = {"openwrt": ["OpenWrt"]}
        return data

    def test_canonical_navigation_omits_duplicate_routes_and_repeats(self):
        data = fixture()
        duplicate = copy.deepcopy(data["entries"][0])
        duplicate.update(faq_id="faq-test-two", canonical_question="Duplicate question")
        other = copy.deepcopy(data["entries"][0])
        other.update(faq_id="faq-test-three", short_answer="Different reviewed answer")
        data["entries"] += [duplicate, other]
        self.build(data)
        directory = (self.public / "answers/entity/test-tool/index.html").read_text()
        self.assertEqual(directory.count('href="/answers/faq-test-one/"'), 1)
        self.assertNotIn('href="/answers/faq-test-two/"', directory)
        related = (self.public / "answers/faq-test-three/index.html").read_text()
        self.assertIn('href="/answers/faq-test-one/"', related)
        self.assertNotIn('href="/answers/faq-test-two/"', related)
        md = (self.public / "answers/entity/test-tool/index.md").read_text()
        self.assertIn("/answers/faq-test-one/)", md)
        self.assertNotIn("/answers/faq-test-two/)", md)

    def test_topic_page_contains_reviewed_body_sections_sources_and_escaping(self):
        data = fixture()
        entry = data["entries"][0]
        entry["short_answer"] = 'Reviewed <script>alert("x")</script> & text'
        self.build(data)
        raw = (self.public / "answers/entity/test-tool/index.html").read_text()
        md = (self.public / "answers/entity/test-tool/index.md").read_text()
        for content in (html.escape(entry["short_answer"]),
                        entry["answer_sections"][0]["content"],
                        "https://example.com/releases", "2026-09-19", "2026-09-20"):
            self.assertIn(content, raw)
        self.assertIn(entry["answer_sections"][0]["content"], md)
        self.assertNotIn('<script>alert("x")</script>', raw)

    def test_ai_home_and_matching_guide_add_live_links_without_touching_existing_flow(self):
        self.prepare_readers()
        data = self.openwrt_data()
        self.build(data)
        for relative in ("index.html", "ai/index.html"):
            raw = (self.public / relative).read_text()
            self.assertIn('href="/answers/entity/openwrt/"', raw)
        ai = (self.public / "ai/index.html").read_text()
        self.assertLess(ai.index('id="faq-ai-discovery"'), ai.index('id="personal-handoff"'))
        guide = (self.public / "guides/openwrt-tools.html").read_text()
        self.assertIn('href="/answers/faq-test-one/"', guide)
        self.assertEqual(guide.count("GA4_EXISTING_TAG"), 1)
        self.assertEqual(guide.count('id="personal-handoff"'), 1)
        self.assertIn(data["entries"][0]["short_answer"], guide)
        self.assertIn("/answers/faq-test-one/", (self.public / "guides/openwrt-tools.md").read_text())

    def test_repeated_build_updates_content_once_and_keeps_gzip_equal(self):
        self.prepare_readers()
        data = self.openwrt_data()
        self.build(data)
        data["entries"][0]["short_answer"] = "Replacement reviewed answer"
        self.build(data)
        first = {p.relative_to(self.public): p.read_bytes() for p in self.public.rglob("*") if p.is_file()}
        self.build(data)
        self.assertEqual(first, {p.relative_to(self.public): p.read_bytes() for p in self.public.rglob("*") if p.is_file()})
        for relative, marker in (("index.html", "faq-home-discovery:start"),
                                 ("ai/index.html", "faq-ai-discovery:start"),
                                 ("guides/openwrt-tools.html", "faq-guide-discovery:start")):
            raw = (self.public / relative).read_text()
            self.assertEqual(raw.count(marker), 1)
        self.assertIn("Replacement reviewed answer", (self.public / "guides/openwrt-tools.html").read_text())

    def test_removed_answers_do_not_leave_stale_guide_recommendations(self):
        self.prepare_readers()
        self.build(self.openwrt_data())
        self.build(fixture())
        for name in ("guides/openwrt-tools.html", "guides/openwrt-tools.md"):
            raw = (self.public / name).read_text()
            self.assertNotIn("faq-guide-discovery", raw)
            self.assertNotIn("/answers/faq-test-one/", raw)

if __name__ == "__main__":
    unittest.main()
