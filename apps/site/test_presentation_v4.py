"""Preservation and progressive-enhancement contracts for the original v4 shell."""
import unittest

from presentation_v4 import enhance_presentation, sidebar_links, table_of_contents


class PresentationShellTest(unittest.TestCase):
    def setUp(self):
        self.header = '<header class="site-header"><div class="wrap header-inner"><a class="brand" href="/">翻墙指南</a><nav class="main-nav" aria-label="主导航"><a href="/guides/index.html">工具指南</a><a href="/ai/">MCP 与工程书</a></nav></div></header>'
        self.footer = '<footer class="site-footer"><a href="/original-source">原来源</a></footer>'
        self.top = [("/guides/index.html", "工具指南"), ("/ai/", "MCP 与工程书")]

    def page(self, inner):
        return '<!doctype html><html lang="zh-CN"><head><title>原标题</title></head><body>' + self.header + '<main id="main">' + inner + '</main><script>window.original = "kept";</script>' + self.footer + '</body></html>'

    def test_existing_actions_and_code_remain_exact(self):
        protected = '<h1>原标题</h1><h2 id="original-heading">原小节</h2><p>原正文 &amp; 原实体。</p><form id="query-form" action="/api/query" data-event="original-event"><input id="q" name="q"><button>查询</button></form><pre>  原样\n代码 &lt;tag&gt;\n</pre>'
        raw = self.page(protected)
        output = enhance_presentation(raw, "guides/example.html", self.top, [])
        self.assertIn(protected, output)
        self.assertIn('<nav class="main-nav" aria-label="主导航"><a href="/guides/index.html">工具指南</a><a href="/ai/">MCP 与工程书</a></nav>', output)
        self.assertIn('<script>window.original = "kept";</script>', output)
        self.assertLess(output.index('</main>'), output.index('window.original'))
        self.assertLess(output.index('window.original'), output.index('href="/original-source"'))
        self.assertEqual(output.count('id="original-heading"'), 1)
        self.assertIn('class="fg-toc fg-generated-toc"', output)

    def test_original_toc_moves_without_rewriting(self):
        original = '<aside class="guide-aside" aria-label="本页目录"><h2>本页内容</h2><nav><a href="#section-anchor">原目录</a></nav><a href="/article.md">Markdown 全文</a></aside>'
        output = enhance_presentation(self.page('<section id="section-anchor"><h2>原章节</h2></section>' + original), "guides/example.html", self.top, [])
        self.assertIn(original, output)
        self.assertEqual(output.count('class="guide-aside"'), 1)
        self.assertNotIn('fg-generated-toc', output)
        self.assertIn('<details class="fg-mobile-toc">', output)
        self.assertGreater(output.index(original), output.index('</main>'))

    def test_toc_only_reuses_existing_heading_ids(self):
        toc = table_of_contents('<section id="section-only"><h2>无标题锚点</h2></section><h2 id="yes">已有锚点</h2><h3 id="child">下级</h3>')
        self.assertNotIn('section-only', toc)
        self.assertIn('href="#yes"', toc)
        self.assertIn('href="#child"', toc)
        self.assertNotIn('id="', toc)

    def test_native_fallbacks_and_idempotence(self):
        raw = self.page('<h1>原标题</h1>')
        output = enhance_presentation(raw, "index.html", self.top, [])
        self.assertIn('<details class="fg-mobile-navigation">', output)
        self.assertIn('href="/guides/library.html" data-fg-search-open', output)
        self.assertIn('data-fg-search-open aria-label="资料检索"', output)
        self.assertIn('action="/guides/library.html" method="get"', output)
        self.assertIn('data-fg-theme-toggle hidden', output)
        self.assertIn('fg-home', output)
        self.assertEqual(enhance_presentation(output, "index.html", self.top, []), output)

    def test_sidebar_uses_source_labels_and_deduplicates(self):
        top, guides = sidebar_links(self.header + self.header, '<a href="/guides/example.html"><h3>完整原标题</h3><p>说明不应成为导航标签</p></a>')
        self.assertEqual(top, self.top)
        self.assertEqual(guides, [("/guides/example.html", "完整原标题")])


if __name__ == "__main__":
    unittest.main()
