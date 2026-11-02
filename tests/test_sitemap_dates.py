import gzip
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/site"))
from sitemap_dates import NS, canonical_path, normalize_sitemaps

class SitemapDateTests(unittest.TestCase):
    def test_content_dates_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = [("/", "2026-09-19"), ("/guides/about.html", "2026-09-19"),
                     ("/answers/faq-one/", "2026-09-27"),
                     ("/answers/entity/one/", "2026-09-27"),
                     ("/answers/entity/newer/", "2026-11-03"),
                     ("/cases/example/", "2026-10-01")]
            xml = '<urlset xmlns="'+NS+'">' + ''.join(
                '<url><loc>https://fanqiang.guide'+p+'</loc><lastmod>'+d+'</lastmod></url>'
                for p,d in items) + '</urlset>'
            for name in ("sitemap.xml", "sitemap-answers.xml"):
                (root/name).write_text(xml)
                (root/(name+".gz")).write_bytes(gzip.compress(xml.encode()))
            changed = ["index.html", "answers/entity/one/index.html", "answers/entity/newer/index.html"]
            normalize_sitemaps(root, changed)
            parsed = ET.parse(root/"sitemap.xml").getroot()
            dates = {n.findtext('{'+NS+'}loc'): n.findtext('{'+NS+'}lastmod') for n in parsed}
            self.assertEqual(dates['https://fanqiang.guide/'], '2026-11-02')
            self.assertIsNone(dates['https://fanqiang.guide/guides/about.html'])
            self.assertEqual(dates['https://fanqiang.guide/answers/faq-one/'], '2026-09-27')
            self.assertEqual(dates['https://fanqiang.guide/answers/entity/one/'], '2026-11-02')
            self.assertEqual(dates['https://fanqiang.guide/answers/entity/newer/'], '2026-11-03')
            self.assertEqual(dates['https://fanqiang.guide/cases/example/'], '2026-10-01')
            before=(root/'sitemap.xml').read_bytes()
            normalize_sitemaps(root, changed)
            self.assertEqual(before,(root/'sitemap.xml').read_bytes())
            for name in ('sitemap.xml','sitemap-answers.xml'):
                self.assertEqual((root/name).read_bytes(),gzip.decompress((root/(name+'.gz')).read_bytes()))
    def test_canonical_index_paths(self):
        self.assertEqual(canonical_path('index.html'), '/')
        self.assertEqual(canonical_path('ai/index.html'), '/ai/')
        self.assertEqual(canonical_path('guides/index.html'), '/guides/index.html')
    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError):
            normalize_sitemaps(Path('/unused'), modification_date='today')

if __name__ == '__main__':
    unittest.main()
