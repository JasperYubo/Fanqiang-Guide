"""Add directory presentation without reserializing protected catalog content."""

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
import json
import re


DIRECTORY_ASSETS = (
    "assets/directory-v4.0-2026-11-19.css",
    "assets/directory-v4.0-2026-11-19.js",
)
_PATHS = {"guides/library.html": "library", "guides/merlin-models.html": "models"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


@dataclass
class _Node:
    tag: str
    attrs: dict
    start: int
    opening_end: int
    end: int = 0
    children: list = field(default_factory=list)
    text: list = field(default_factory=list)

    def all(self):
        yield self
        for child in self.children:
            yield from child.all()

    def has_class(self, name):
        return name in self.attrs.get("class", "").split()

    def content(self):
        return "".join(self.text).strip()


class _CatalogMarkup(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw = raw
        self.offsets = [0] + [match.end() for match in re.finditer("\n", raw)]
        self.root = _Node("", {}, 0, 0, len(raw))
        self.stack = [self.root]

    def position(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.position()
        node = _Node(tag, dict(attrs), start, start + len(self.get_starttag_text()))
        self.stack[-1].children.append(node)
        if tag in _VOID:
            node.end = node.opening_end
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.stack[-1].end = self.stack[-1].opening_end
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                end = self.raw.index(">", self.position()) + 1
                for node in self.stack[index:]:
                    node.end = end
                del self.stack[index:]
                break

    def handle_data(self, data):
        for node in self.stack:
            node.text.append(data)


def _pair(node):
    strong = next((child for child in node.children if child.tag == "strong"), None)
    if strong is None:
        return "", ""
    label = strong.content().rstrip("：:")
    return label, node.content()[len(strong.content()):].strip()


def _select(prefix, key, label, options, default_label):
    ident = f"fg-directory-{prefix}-{key}"
    attribute = "data-fg-directory-sort" if key == "sort" else f'data-fg-directory-filter="{key}"'
    return (
        '<div class="fg-directory-field">'
        f'<label for="{ident}">{escape(label)}</label>'
        f'<select id="{ident}" {attribute} aria-controls="{prefix}-results">'
        f'<option value="">{escape(default_label)}</option>'
        + "".join(f'<option value="{escape(value, quote=True)}">{escape(label)}</option>' for value, label in options)
        + '</select></div>'
    )


def enhance_directory(raw, relative_path):
    """Annotate the two existing catalog pages; leave every original text intact.

    Extra filter values come from facts already rendered on the page. There is
    no dependency on a new dataset, and no attempt to infer absent capabilities.
    """
    prefix = _PATHS.get(str(relative_path).replace("\\", "/").lstrip("/"))
    if prefix is None or 'data-fg-directory="' in raw:
        return raw
    parser = _CatalogMarkup(raw)
    parser.feed(raw)
    parser.close()
    nodes = list(parser.root.all())
    browser = next((node for node in nodes if "data-catalog" in node.attrs), None)
    if browser is None:
        return raw
    records = [node for node in browser.all() if "data-record" in node.attrs]
    controls = next((node for node in browser.all() if node.has_class("catalog-controls")), None)
    if controls is None or not controls.end:
        raise ValueError("Directory controls must have a complete closing tag")
    updates = {}

    def mark(node, classes="", **attributes):
        existing = updates.setdefault(node.start, {"node": node, "classes": [], "attrs": {}})
        existing["classes"].extend(classes.split())
        existing["attrs"].update(attributes)

    class_map = {
        "catalog-browser": "fg-directory",
        "catalog-controls": "fg-directory-controls",
        "catalog-field": "fg-directory-field",
        "catalog-category-nav": "fg-directory-categories",
        "catalog-group": "fg-directory-group",
        "catalog-grid": "fg-directory-list",
        "catalog-record": "fg-directory-record",
        "catalog-record-top": "fg-directory-meta",
        "catalog-summary": "fg-directory-summary",
        "catalog-facts": "fg-directory-facts",
        "catalog-origin": "fg-directory-origin",
        "catalog-details": "fg-directory-details",
        "catalog-source-group": "fg-directory-source",
        "catalog-count": "fg-directory-count",
        "catalog-table-region": "fg-directory-table-region",
        "catalog-model-table": "fg-directory-models",
    }
    for node in browser.all():
        additions = [new for old, new in class_map.items() if node.has_class(old)]
        if additions:
            mark(node, " ".join(additions))
    mark(browser, **{"data-fg-directory": prefix})
    platforms = set()
    maintenance_values = set()
    for order, record in enumerate(records):
        record_nodes = list(record.all())
        if prefix == "library":
            heading = next(node for node in record_nodes if node.tag == "h3")
            pairs = {label: value for node in record_nodes if node.tag == "p" for label, value in [_pair(node)] if label}
            record_platforms = [value for value in pairs.get("平台", "").split("、") if value and value != "未记录"]
            platforms.update(record_platforms)
            maintenance = pairs.get("维护记录", "")
            if maintenance:
                maintenance_values.add(maintenance)
            checked = pairs.get("资料核对日期", "")
            mark(record, **{
                "data-fg-name": heading.content(),
                "data-fg-platforms": json.dumps(record_platforms, ensure_ascii=False, separators=(",", ":")),
                "data-fg-maintenance": maintenance,
            })
            for node in record_nodes:
                if node.tag == "details":
                    mark(node, "fg-directory-disclosure")
                if node.tag != "p":
                    continue
                label, _ = _pair(node)
                if not label:
                    continue
                group = "compatibility" if label in {"资料记载型号", "兼容性说明"} else "relationship" if label == "资料中的关联" else "fact"
                mark(node, f"fg-directory-{group}")
        else:
            cells = [node for node in record.children if node.tag in {"th", "td"}]
            title = next(node for node in cells[0].all() if node.tag == "a")
            checked_node = next((node for node in record_nodes if node.has_class("catalog-model-date")), None)
            checked = checked_node.content() if checked_node else ""
            mark(record, "fg-directory-model", **{"data-fg-name": title.content()})
            labels = ["完整型号", "固件分支", "来源支持状态", "实测", "来源与限定说明"]
            for cell, label in zip(cells, labels):
                mark(cell, **{"data-fg-label": label})
        date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", checked)
        mark(record, **{"data-fg-order": str(order), "data-fg-checked": date.group() if date else ""})
    additions = []
    if platforms:
        additions.append(_select(prefix, "platform", "设备 / 平台", [(value, value) for value in sorted(platforms, key=str.casefold)], "全部设备 / 平台"))
    if maintenance_values:
        additions.append(_select(prefix, "maintenance", "维护 / 归档记录", [(value, value) for value in sorted(maintenance_values)], "全部维护 / 归档记录"))
    scope = "分类内" if prefix == "library" else ""
    additions.append(_select(prefix, "sort", "排序", [
        ("name-asc", f"{scope}名称 A → Z"),
        ("name-desc", f"{scope}名称 Z → A"),
        ("checked-desc", f"{scope}资料核对日期：新 → 旧"),
    ], "原始资料顺序"))
    extra_controls = '<div class="fg-directory-extra" data-fg-directory-extra hidden>' + "".join(additions) + '</div>'
    edits = [(controls.end, controls.end, extra_controls)]
    for update in updates.values():
        node = update["node"]
        opening = raw[node.start:node.opening_end]
        classes = list(dict.fromkeys(update["classes"]))
        if classes:
            match = re.search(r'\bclass\s*=\s*([\"\'])(.*?)\1', opening, re.S)
            if match:
                opening = opening[:match.end(2)] + " " + " ".join(classes) + opening[match.end(2):]
            else:
                update["attrs"]["class"] = " ".join(classes)
        attributes = "".join(f' {name}="{escape(value, quote=True)}"' for name, value in update["attrs"].items())
        opening = opening[:-1] + attributes + opening[-1:]
        edits.append((node.start, node.opening_end, opening))
    head_end = raw.find("</head>")
    if head_end < 0:
        raise ValueError("Directory presentation requires a complete HTML head")
    assets = f'<link rel="stylesheet" href="/{DIRECTORY_ASSETS[0]}"><script defer src="/{DIRECTORY_ASSETS[1]}"></script>'
    edits.append((head_end, head_end, assets))
    for start, end, replacement in sorted(edits, reverse=True):
        raw = raw[:start] + replacement + raw[end:]
    return raw
