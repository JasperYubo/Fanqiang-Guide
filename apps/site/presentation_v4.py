"""Original presentation shell; keep the generated document bytes and actions intact."""
from __future__ import annotations

import gzip
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import re

DESIGN_CSS = "assets/guide-design-v4.0-2026-11-19.css"
SHELL_JS = "assets/guide-shell-v4.0-2026-11-19.js"
SHELL_ASSETS = (DESIGN_CSS, SHELL_JS)

SEARCH_ICON = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>'
THEME_ICON = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>'
CLOSE_ICON = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m6 6 12 12M18 6 6 18"/></svg>'


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(markup):
    parser = TextOnly()
    parser.feed(markup)
    return " ".join("".join(parser.parts).split())


def add_class(opening_tag, *classes):
    """Only add a class attribute; retain all original attributes and their values."""
    match = re.search(r'\bclass=("|\')(.*?)\1', opening_tag, re.S)
    if match:
        original = match.group(2).split()
        added = [name for name in classes if name not in original]
        if not added:
            return opening_tag
        return opening_tag[:match.end(2)] + " " + " ".join(added) + opening_tag[match.end(2):]
    return opening_tag[:-1] + ' class="' + " ".join(classes) + '">'


def route_for(relative_path):
    route = "/" + str(relative_path).replace("\\", "/")
    return route[:-10] if route.endswith("index.html") else route


def nav_link(href, label, route, *, extra=""):
    current = href.split("#", 1)[0] == route and "#" not in href
    attrs = ' aria-current="page"' if current else ""
    return '<a class="fg-nav-link' + extra + '" href="' + escape(href, quote=True) + '"' + attrs + '>' + escape(label) + '</a>'


def sidebar_links(header, guides_index):
    """Reuse the current site's routes and labels, never theme demo navigation."""
    top = []
    seen = set()
    # Both desktop and mobile navigation are scanned, then de-duplicated.
    for nav in re.findall(r'<nav\b[^>]*>.*?</nav>', header, re.S):
        for href, label in re.findall(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>', nav, re.S):
            if href in seen:
                continue
            seen.add(href)
            top.append((unescape(href), plain_text(label)))
    guides = []
    for href, body in re.findall(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>', guides_index, re.S):
        heading = re.search(r'<h[23]\b[^>]*>(.*?)</h[23]>', body, re.S)
        if heading and href.startswith("/guides/") and href.endswith(".html"):
            guides.append((unescape(href), plain_text(heading.group(1))))
    return top, list(dict.fromkeys(guides))


def tools():
    return ('<div class="fg-shell-tools">'
            '<a class="fg-search-launch" href="/guides/library.html" data-fg-search-open aria-label="资料检索" '
            'aria-haspopup="dialog" aria-controls="fg-search-dialog">' + SEARCH_ICON +
            '<span>资料检索</span><kbd aria-hidden="true">Ctrl K</kbd></a>'
            '<button class="fg-theme-toggle" type="button" data-fg-theme-toggle hidden '
            'aria-label="切换明暗模式">' + THEME_ICON +
            '<span data-fg-theme-label>跟随系统</span></button></div>')


def sidebar(top_links, guide_links, route):
    top = "".join(nav_link(href, text, route) for href, text in top_links)
    guides = "".join(nav_link(href, text, route) for href, text in guide_links)
    groups = ('<div class="fg-nav-group"><p class="fg-nav-label">翻墙指南</p>' + top + '</div>' +
              ('<div class="fg-nav-group"><p class="fg-nav-label">工具指南</p>' + guides + '</div>' if guides else ''))
    return ('<aside class="fg-sidebar" aria-label="站点目录"><div class="fg-sidebar-inner">'
            '<nav class="fg-sidebar-nav fg-desktop-navigation" aria-label="资料导航">' + groups + '</nav>'
            '<details class="fg-mobile-navigation"><summary class="fg-sidebar-summary">工具指南</summary>'
            '<nav class="fg-sidebar-nav" aria-label="资料导航">' + groups + '</nav></details></div></aside>')


def table_of_contents(raw):
    entries = []
    seen = set()
    # Never mint or alter anchors. Existing document headings are the only source.
    for match in re.finditer(r'<(h[23])\b([^>]*)>(.*?)</\1>', raw, re.S):
        ident = re.search(r'\bid=("|\')(.*?)\1', match.group(2), re.S)
        if not ident or ident.group(2) in seen:
            continue
        value = unescape(ident.group(2))
        label = plain_text(match.group(3))
        if not value or not label:
            continue
        seen.add(value)
        entries.append((value, label, match.group(1)))
    if not entries:
        return ""
    links = "".join('<a class="fg-toc-link fg-toc-' + level + '" href="#' +
                    escape(ident, quote=True) + '">' + escape(label) + '</a>'
                    for ident, label, level in entries)
    return '<aside class="fg-toc fg-generated-toc" aria-label="本页目录"><div class="fg-toc-inner"><p class="fg-toc-label">本页内容</p><nav>' + links + '</nav></div></aside>'


def mobile_table_of_contents(toc):
    if not toc:
        return ""
    links = "".join('<a href="' + escape(unescape(href), quote=True) + '">' + escape(plain_text(label)) + '</a>'
                    for href, label in re.findall(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>(.*?)</a>', toc, re.S))
    return '<details class="fg-mobile-toc"><summary>本页内容</summary><nav aria-label="本页目录">' + links + '</nav></details>'


def search_dialog(top_links):
    choices = [item for item in top_links if item[0].startswith("/")]
    links = "".join('<a href="' + escape(href, quote=True) + '">' + escape(label) + '</a>'
                    for href, label in choices)
    return ('<dialog class="fg-search-dialog" id="fg-search-dialog" aria-labelledby="fg-search-title">'
            '<div class="fg-search-panel"><div class="fg-search-heading">'
            '<p id="fg-search-title">资料检索</p><button class="fg-search-close" type="button" '
            'data-fg-search-close aria-label="关闭资料检索">' + CLOSE_ICON + '</button></div>'
            '<form class="fg-search-form" action="/guides/library.html" method="get">'
            '<label class="fg-search-label" for="fg-search-input">资料检索</label>'
            '<div class="fg-search-field">' + SEARCH_ICON +
            '<input class="fg-search-input" id="fg-search-input" name="q" type="search" '
            'autocomplete="off" placeholder="资料检索" autofocus>'
            '<button class="fg-search-submit" type="submit">检索</button></div></form>'
            '<nav class="fg-search-shortcuts" aria-label="快捷入口">' + links + '</nav>'
            '<p class="fg-search-hint"><kbd>Enter</kbd> 检索 <span><kbd>Esc</kbd> 关闭</span></p>'
            '</div></dialog>')


def page_kind(relative_path):
    name = str(relative_path).replace("\\", "/")
    if name == "index.html":
        return "home"
    if name in {"guides/library.html", "guides/merlin-models.html"}:
        return "directory"
    if name.startswith("free-proxies/") or "updates" in name:
        return "archive"
    return "document"


def enhance_presentation(raw, relative_path, top_links, guide_links):
    if 'data-fg-presentation="4"' in raw or not re.search(r'<main\b', raw):
        return raw
    kind = page_kind(relative_path)
    raw = re.sub(r'<body\b[^>]*>', lambda m: add_class(m[0], "fg-page", "fg-" + kind)[:-1] +
                 ' data-fg-presentation="4">', raw, count=1)
    raw = re.sub(r'<header\b[^>]*\bclass="[^"]*\bsite-header\b[^"]*"[^>]*>',
                 lambda m: add_class(m[0], "fg-site-header"), raw, count=1)
    raw = re.sub(r'<footer\b[^>]*\bclass="[^"]*\bsite-footer\b[^"]*"[^>]*>',
                 lambda m: add_class(m[0], "fg-site-footer"), raw, count=1)
    header = re.search(r'<header\b[^>]*\bclass="[^"]*\bsite-header\b[^"]*"[^>]*>.*?</header>', raw, re.S)
    if header:
        # Add the new controls without replacing any existing navigation node.
        updated = header[0].replace('</div></header>', tools() + '</div></header>', 1)
        raw = raw[:header.start()] + updated + raw[header.end():]
    main = re.search(r'<main\b[^>]*>.*?</main>', raw, re.S)
    if not main:
        return raw
    body = main[0]
    original_toc = re.search(r'<aside\b[^>]*\bclass="[^"]*\bguide-aside\b[^"]*"[^>]*>.*?</aside>', body, re.S)
    if original_toc:
        toc = '<div class="fg-toc"><div class="fg-toc-inner">' + original_toc[0] + '</div></div>'
        body = body[:original_toc.start()] + body[original_toc.end():]
    else:
        toc = "" if kind == "home" else table_of_contents(body)
    raw = raw[:main.start()] + body + raw[main.end():]
    main_start = main.start()
    main_end = main_start + len(body)
    footer = re.search(r'<footer\b[^>]*\bclass="[^"]*\bsite-footer\b[^"]*"[^>]*>.*?</footer>', raw[main_end:], re.S)
    end = main_end + footer.end() if footer else main_end
    content = raw[main_start:end]
    modifier = " fg-shell-with-toc" if toc else " fg-shell-wide"
    shell = '<div class="fg-shell' + modifier + '">' + sidebar(top_links, guide_links, route_for(relative_path)) + mobile_table_of_contents(toc) + '<div class="fg-content">' + content + '</div>' + toc + '</div>'
    raw = raw[:main_start] + shell + raw[end:]
    raw = raw.replace('</body>', search_dialog(top_links) + '</body>', 1)
    head = '<link rel="stylesheet" href="/' + DESIGN_CSS + '"><script defer src="/' + SHELL_JS + '"></script>'
    return raw.replace('</head>', head + '</head>', 1)


def apply_presentation(public, header):
    public = Path(public)
    source = Path(__file__).resolve().parent / "content"
    from directory_v4 import DIRECTORY_ASSETS, enhance_directory
    for asset in (*SHELL_ASSETS, *DIRECTORY_ASSETS):
        destination = public / asset
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((source / Path(asset).name).read_bytes())
        destination.with_name(destination.name + ".gz").write_bytes(gzip.compress(destination.read_bytes(), mtime=0))
    guides = public / "guides/index.html"
    top_links, guide_links = sidebar_links(header, guides.read_text(encoding="utf-8") if guides.exists() else "")
    changed = []
    for path in sorted(public.rglob("*.html")):
        raw = path.read_text(encoding="utf-8")
        if '<head>' not in raw or not re.search(r'<main\b', raw):
            continue
        relative = path.relative_to(public).as_posix()
        enhanced = enhance_directory(raw, relative)
        enhanced = enhance_presentation(enhanced, relative, top_links, guide_links)
        if enhanced != raw:
            path.write_text(enhanced, encoding="utf-8")
            changed.append(relative)
    return changed
