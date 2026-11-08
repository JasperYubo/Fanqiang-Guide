"""Validate the published Pages artifact, without network access or extra packages."""
from collections import Counter
from html.parser import HTMLParser
import datetime
import hashlib
import json
from pathlib import Path
import struct
from urllib.parse import unquote, urljoin, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'apps/pages'

class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.links = []
        self.assets = []
        self.ids = []
        self.anchors = []
        self.structured = []
        self.current = None
        self.buffer = []
        self.title = ''
        self.headings = []
        self.lang = ''

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'html': self.lang = d.get('lang', '')
        if 'id' in d: self.ids.append(d['id'])
        if tag == 'meta':
            key = d.get('name', d.get('property'))
            if key:
                assert key not in self.meta, f'Duplicate metadata: {key}'
                self.meta[key] = d.get('content', '')
        if tag == 'link':
            self.links.append(d)
            if d.get('rel') in ('stylesheet','icon'): self.assets.append(d['href'])
        if tag == 'a': self.anchors.append(d.get('href', ''))
        if tag in ('img','script') and 'src' in d: self.assets.append(d['src'])
        if tag in ('title','h1') or (tag == 'script' and d.get('type') == 'application/ld+json'):
            assert self.current is None
            self.current, self.buffer = tag, []

    def handle_data(self, data):
        if self.current: self.buffer.append(data)

    def handle_endtag(self, tag):
        if self.current == tag:
            value = ''.join(self.buffer).strip()
            if tag == 'title':
                assert not self.title, 'Duplicate title'
                self.title = value
            elif tag == 'h1': self.headings.append(value)
            else: self.structured.append(json.loads(value))
            self.current, self.buffer = None, []

def require(value, message):
    if not value: raise SystemExit(message)

def local_path(url, canonical):
    target = urlsplit(urljoin(canonical, url))
    base = urlsplit(canonical)
    require(target.scheme == 'https' and target.netloc == base.netloc and target.path.startswith(base.path), 'Asset leaves project URL: '+url)
    path = (PUBLIC / unquote(target.path[len(base.path):])).resolve()
    require(path.is_relative_to(PUBLIC.resolve()), 'Asset path traversal: '+url)
    if path.is_dir():
        path = path / 'index.html'
    require(path.is_file(), 'Missing asset: '+str(path))
    return path

def png_dimensions(path):
    data = path.read_bytes()
    require(data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR', 'Invalid PNG header: '+str(path))
    return struct.unpack('>II', data[16:24])

def main():
    p = Page()
    p.feed((PUBLIC/'index.html').read_text(encoding='utf-8'))
    require(p.lang == 'zh-CN', 'Missing Chinese document language')
    require(10 <= len(p.title) <= 90 and 'Fanqiang Guide' in p.title, 'Missing descriptive project title')
    require(len(p.headings) == 1 and '翻墙' in p.headings[0], 'Page needs one topic-specific H1')
    require(40 <= len(p.meta.get('description','')) <= 200, 'Missing useful description')
    require(not [i for i,n in Counter(p.ids).items() if n > 1], 'Duplicate element IDs')
    require(all(h[1:] in p.ids for h in p.anchors if h.startswith('#')), 'Broken in-page anchor')
    canonicals = [x['href'] for x in p.links if x.get('rel') == 'canonical']
    require(len(canonicals) == 1, 'Expected one canonical URL')
    canonical = canonicals[0]
    c = urlsplit(canonical)
    require(c.scheme == 'https' and c.netloc == 'jasperyubo.github.io' and c.path == '/Fanqiang-Guide/' and not c.query and not c.fragment, 'Canonical must be the project page, without query/fragment')
    require(p.meta.get('og:url') == canonical, 'Canonical and Open Graph URL disagree')
    require(p.meta.get('og:title') == p.title == p.meta.get('twitter:title'), 'Search/social titles disagree')
    require(p.meta['description'] == p.meta.get('og:description') == p.meta.get('twitter:description'), 'Search/social descriptions disagree')
    require(p.meta.get('twitter:card') == 'summary_large_image', 'Missing large share card')
    require(bool(p.meta.get('google-site-verification')), 'Google ownership verification tag missing')
    robots = p.meta.get('robots', '').lower()
    require('noindex' not in robots and 'nofollow' not in robots and 'none' not in robots, 'Indexing/link following blocked')
    require('max-image-preview:large' in robots, 'Large image previews not enabled')
    require(not (PUBLIC/'robots.txt').exists(), 'A project-subdirectory robots.txt cannot control this host')
    for asset in p.assets:
        path = local_path(asset, canonical)
        if path.suffix == '.css':
            require(urlsplit(asset).query == 'v='+hashlib.sha256(path.read_bytes()).hexdigest()[:12], 'Stylesheet fingerprint is stale')
    for href in p.anchors:
        if href and not href.startswith(('#','https://','http://','mailto:')): local_path(href, canonical)
    image = p.meta.get('og:image', '')
    require(image == p.meta.get('twitter:image') and bool(p.meta.get('og:image:alt')) and bool(p.meta.get('twitter:image:alt')), 'Incomplete share-image metadata')
    dimensions = png_dimensions(local_path(image, canonical))
    require(dimensions == (int(p.meta.get('og:image:width','0')), int(p.meta.get('og:image:height','0'))), 'Share-image dimensions disagree with metadata')
    require(dimensions[0] >= 1200 and dimensions[1] >= 630, 'Share image is undersized')
    require(local_path(image, canonical).stat().st_size < 5_000_000, 'Share image exceeds 5 MB')
    icons = [x for x in p.links if x.get('rel') == 'icon']
    require(len(icons) == 1, 'Expected one crawlable icon')
    iw,ih = png_dimensions(local_path(icons[0]['href'], canonical))
    require(iw == ih and iw >= 48, 'Icon must be square and at least 48 pixels')
    require(len(p.structured) == 1, 'Expected one page description in JSON-LD')
    data = p.structured[0]
    require(data.get('@context') == 'https://schema.org' and data.get('@type') in ('WebPage','CollectionPage'), 'Unexpected page schema')
    require(data.get('url') == canonical and data.get('name') == p.title and data.get('description') == p.meta['description'] and data.get('inLanguage') == p.lang, 'Structured data and visible metadata disagree')
    require(set(data.get('relatedLink',[])) <= set(p.anchors), 'Structured related links must appear on the page')
    require(data.get('image',{}).get('url') == image, 'Structured image differs from share image')
    sitemap = ET.parse(PUBLIC/'sitemap.xml').getroot()
    ns = {'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls = sitemap.findall('s:url',ns)
    require([u.findtext('s:loc',namespaces=ns) for u in urls] == [canonical], 'Sitemap must list only this canonical page, not external URLs or fragments')
    for item in urls:
        date = item.findtext('s:lastmod',namespaces=ns)
        if date: datetime.date.fromisoformat(date)
    require(any(x.get('rel') == 'sitemap' for x in p.links) and './sitemap.xml' in p.anchors, 'Sitemap needs a discoverable link')
    print(json.dumps({'result':'pass','title':p.title,'canonical':canonical,'links':len(p.anchors),'jsonld':data['@type'],'sitemap_urls':len(urls),'share_image':dimensions,'favicon':[iw,ih]},ensure_ascii=False))

if __name__ == '__main__': main()
