"""Render or check the Pages entry from the same facts used by the main site.

Edit apps/pages-template/index.html for page layout and copy, then run --write.
The generated apps/pages/index.html is checked into Git for direct review.
"""
from __future__ import annotations
import argparse
import html
import hashlib
import importlib.util
from pathlib import Path
from html.parser import HTMLParser
import json
from urllib.parse import urljoin
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "apps/pages-template/index.html"
OUTPUT = ROOT / "apps/pages/index.html"
REQUIRED_TOKENS = {
    "SITE_URL", "PAGES_URL", "SERVER_ENTRY_URL", "INSTALLER_URL", "INSTALL_COMMAND",
    "API_URL", "MCP_URL", "PRICE_SENTENCE", "OS_LABEL", "RUNTIME", "RUNTIME_VERSION",
    "MODEL", "SERVER_TOOL", "SERVER_PROMPT", "SERVER_RESOURCE", "BOOK_COUNT", "BOOK_CARDS",
}
BOOK_DESCRIPTIONS = {
    "autosetup": "手机与电脑配置、手机共享、路由器流程入口",
    "merlin": "兼容固件、fancyss 选包、安装检查与恢复流程",
    "server": "准备 DeepSeek Key、安装自己的 VPS、导入客户端与中文排错",
}


def provider():
    spec = importlib.util.spec_from_file_location("fanqiang_product_contract", ROOT / "apps/site/product_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def facts() -> dict:
    return provider().product_facts()


def book_cards(books: list[dict]) -> str:
    cards = []
    escape = html.escape
    for book in books:
        title = book["display_title"]
        description = BOOK_DESCRIPTIONS.get(book["book_id"], "完整工程书与验证范围")
        cards.append('<a class="book-link" href="' + escape(book["download_url"], quote=True) + '"><div><h4>' +
            escape(title) + ' <span>v' + escape(book["version"]) + '</span></h4><p>' + escape(description) +
            '</p></div><span class="book-action">打开原文 <span aria-hidden="true">↗</span></span></a>')
    return "\n            ".join(cards)


def render(template: str, product: dict | None = None) -> str:
    product = product or facts()
    server, assistant = product["server"], product["server"]["assistant"]
    values = {
        "SITE_URL": product["site_url"], "PAGES_URL": product["pages_url"],
        "SERVER_ENTRY_URL": server["entry_url"], "INSTALLER_URL": server["installer_url"],
        "INSTALL_COMMAND": server["install_command"], "API_URL": server["api_url"],
        "MCP_URL": product["mcp_url"], "BOOKS_URL": product["books_url"],
        "PRICE_SENTENCE": product["price_sentence"], "PRICE_AMOUNT": server["recommended_api_balance"]["amount"],
        "OS_LABEL": product["os_label"], "RUNTIME": assistant["runtime"],
        "RUNTIME_VERSION": assistant["runtime_version"], "PROVIDER": assistant["provider"],
        "MODEL": assistant["model"], "CHAT_COMMAND": assistant["command"],
        "SERVER_TOOL": server["tool"], "SERVER_PROMPT": server["prompt"],
        "SERVER_RESOURCE": server["resource_uri"], "SERVER_BOOK_URL": server["download_url"],
        "BOOK_COUNT": product["book_count"],
        "CSS_VERSION": hashlib.sha256((ROOT / "apps/pages/style.css").read_bytes()).hexdigest()[:12],
        "SCRIPT_VERSION": hashlib.sha256((ROOT / "apps/pages/script.js").read_bytes()).hexdigest()[:12],
    }
    supplied = set(re.findall(r"\{\{([A-Z_]+)\}\}", template))
    missing = REQUIRED_TOKENS - supplied
    unknown = supplied - set(values) - {"BOOK_CARDS"}
    if missing or unknown:
        raise ValueError("Pages template contract tokens: missing=" + str(sorted(missing)) + "; unknown=" + str(sorted(unknown)))
    def replace(match):
        name = match[1]
        return book_cards(product["books"]) if name == "BOOK_CARDS" else html.escape(str(values[name]), quote=True)
    rendered = re.sub(r"\{\{([A-Z_]+)\}\}", replace, template)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("Unexpanded Pages template token")
    return rendered


class Links(HTMLParser):
    def __init__(self, raw):
        super().__init__()
        self.anchors = []
        self.current = None
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = [dict(attrs).get("href", ""), ""]

    def handle_data(self, text):
        if self.current is not None:
            self.current[1] += text

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.anchors.append(tuple(self.current))
            self.current = None


def validate_main_site(public: Path) -> list[str]:
    """Verify rendered facts and reciprocal entry links, without requiring identical copy."""
    product = facts()
    server = product["server"]
    failures = []
    try:
        raw = (public / "server/index.html").read_text(encoding="utf-8")
        readable = html.unescape(raw)
        required = [server["install_command"], product["price_sentence"], product["os_label"],
                    product["mcp_url"], server["api_url"], server["tool"], server["prompt"], server["resource_uri"],
                    *[server["assistant"][key] for key in ("runtime", "runtime_version", "model", "command")]]
        for value in required:
            if value not in readable:
                failures.append("site/server/index.html:shared_fact_missing:" + value)
        markdown = (public / "server/index.md").read_text(encoding="utf-8")
        for value in (server["install_command"], product["price_sentence"]):
            if value not in markdown:
                failures.append("site/server/index.md:shared_fact_missing:" + value)
        home = Links((public / "index.html").read_text(encoding="utf-8"))
        if product["pages_url"] not in {urljoin(product["site_url"], href) for href, _ in home.anchors}:
            failures.append("site/index.html:pages_entry_missing")
        ai = Links((public / "ai/index.html").read_text(encoding="utf-8"))
        for book in product["books"]:
            matches = [text for href, text in ai.anchors if urljoin(product["site_url"], href) == book["download_url"]]
            if not matches or not any(book["version"] in text for text in matches):
                failures.append("site/ai/index.html:book_version_or_link_missing:" + book["book_id"])
        published = json.loads((public / "data/product-contract.json").read_text(encoding="utf-8"))
        if published != provider().public_contract():
            failures.append("site/data/product-contract.json:shared_facts_mismatch")
    except (OSError, ValueError, KeyError, TypeError) as error:
        failures.append("site:product_contract_unreadable:" + type(error).__name__)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = render(TEMPLATE.read_text(encoding="utf-8"))
    if args.write:
        OUTPUT.write_text(expected, encoding="utf-8")
        print("Pages entry generated from the shared product contract")
    elif not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != expected:
        raise SystemExit("Pages entry is stale; run python developer/sync_pages_contract.py --write and commit the generated index.html")
    else:
        print("Pages entry matches the shared product contract")


if __name__ == "__main__":
    main()
