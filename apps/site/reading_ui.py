"""Progressively enhance static code blocks without reserializing their contents."""
from html import escape
from html.parser import HTMLParser
import re

READING_CSS_PATH = "assets/reading-ui-v1.0-2026-11-02.css"
READING_SCRIPT_PATH = "assets/reading-ui-v1.0-2026-11-02.js"
CSS_PATH = READING_CSS_PATH
SCRIPT_PATH = READING_SCRIPT_PATH


class _CodeBlocks(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.offsets = [0] + [match.end() for match in re.finditer("\\n", source)]
        self.blocks = []
        self.ids = set()
        self.active = None

    def source_offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        if tag == "pre" and self.active is None:
            start = self.source_offset()
            self.active = (start, start + len(self.get_starttag_text()), attributes)

    def handle_endtag(self, tag):
        if tag == "pre" and self.active is not None:
            start, content_start, attrs = self.active
            end_start = self.source_offset()
            end = self.source.index(">", end_start) + 1
            self.blocks.append((start, content_start, end_start, end, attrs))
            self.active = None


class _TextContent(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


COPY_ICON = (
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
    'stroke="currentColor" stroke-width="1.7" aria-hidden="true" focusable="false">'
    '<rect x="8" y="8" width="12" height="12" rx="2"></rect>'
    '<path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"></path>'
    '</svg>'
)


def enhance_code_blocks(html_text, collapse_long=False):
    """Wrap each pre once; its original contents and attributes remain verbatim."""
    parser = _CodeBlocks(html_text)
    parser.feed(html_text)
    parser.close()
    edits = []
    next_id = 1
    for start, content_start, content_end, end, attrs in parser.blocks:
        if attrs.get("data-reading-enhanced") == "true":
            continue
        text_parser = _TextContent()
        text_parser.feed(html_text[content_start:content_end])
        text_parser.close()
        text = "".join(text_parser.parts)
        # HTML ignores one initial newline immediately following a pre opening tag.
        if html_text[content_start:content_end].startswith("\n"):
            text = text[1:]
        lines = max(1, len(text.splitlines()))
        label = "I-Lang" if "::ILANG::" in text or "::MODULE" in text else "代码 / 配置"
        pre_id = attrs.get("id")
        additions = ' data-reading-enhanced="true"'
        if not pre_id:
            while f"reading-code-{next_id}" in parser.ids:
                next_id += 1
            pre_id = f"reading-code-{next_id}"
            parser.ids.add(pre_id)
            next_id += 1
            additions += f' id="{pre_id}"'
        if "tabindex" not in attrs:
            additions += ' tabindex="0"'
        if "role" not in attrs:
            additions += ' role="region"'
        if "aria-label" not in attrs:
            additions += f' aria-label="{label}，可滚动查看完整内容"'
        pre = html_text[start:content_start - 1] + additions + html_text[content_start - 1:end]
        safe_id = escape(pre_id, quote=True)
        toolbar = (
            '<div class="reading-code-toolbar">'
            f'<span class="reading-code-language">{label}</span>'
            '<button class="reading-code-copy" type="button" data-copy-code '
            f'aria-controls="{safe_id}" hidden>{COPY_ICON}<span>复制代码</span></button>'
            '</div>'
        )
        if collapse_long and lines > 12:
            pre = (
                '<details class="reading-code-details">'
                f'<summary>展开完整内容（{lines} 行）</summary>{pre}</details>'
            )
        wrapped = (
            '<div class="reading-code" data-reading-code>'
            + toolbar + pre
            + '<p class="reading-code-status" role="status" aria-live="polite" aria-atomic="true"></p>'
            + '<noscript><p class="reading-code-hint">可选中代码后复制；长内容可点击上方展开。</p></noscript>'
            + '</div>'
        )
        edits.append((start, end, wrapped))
    for start, end, wrapped in reversed(edits):
        html_text = html_text[:start] + wrapped + html_text[end:]
    return html_text
