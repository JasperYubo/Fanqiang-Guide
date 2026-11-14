"""Presentation facts shared by the main site and the independent Pages entry.

Server and book facts come from the pinned public MCP registry. This module
adds only the companion entry URL and human-facing labels; it does not change
the MCP protocol, books, installer or user authorization.
"""
from __future__ import annotations

from pathlib import Path
import runpy
from urllib.parse import urlsplit

PAGES_URL = "https://jasperyubo.github.io/Fanqiang-Guide/"
BOOK_DISPLAY_TITLES = {"autosetup": "设备配置", "merlin": "梅林路由器", "server": "服务器助手"}


def product_facts() -> dict:
    root = Path(__file__).resolve().parents[2]
    registry = runpy.run_path(str(root / "apps/lookup/runtime/setup_book.py"))
    canonical_books = registry["book_catalog"]()["books"]
    server = next(book for book in canonical_books if book["book_id"] == "server")
    books = [{**book, "display_title": BOOK_DISPLAY_TITLES.get(book["book_id"], book["title"])}
             for book in canonical_books]
    origin = urlsplit(server["entry_url"])
    site_url = origin.scheme + "://" + origin.netloc + "/"
    amount = server["recommended_api_balance"]["amount"]
    if server["recommended_api_balance"]["currency"] != "CNY":
        raise ValueError("The Chinese price sentence needs an explicit currency update")
    os_name = server["recommended_os"]
    if not os_name.startswith("fresh "):
        raise ValueError("The OS label needs an explicit recommendation update")
    os_label = "全新的 " + os_name.removeprefix("fresh ").replace("x86_64", "x64") + " VPS"
    return {
        "site_url": site_url,
        "pages_url": PAGES_URL,
        "server": server,
        "mcp_url": site_url + "mcp",
        "books_url": site_url + "api/agent/books",
        "books": books,
        "book_count": len(books),
        "price_sentence": f"充值 {amount} 元，即可开始使用 AI 维护。VPS 自备，费用另计。",
        "os_label": os_label,
    }


def public_contract() -> dict:
    """Small, stable deployment contract: only facts the two public sites share."""
    product = product_facts()
    server = product["server"]
    server_fields = ("entry_url", "installer_url", "install_command", "api_url", "recommended_os",
                     "recommended_api_balance", "assistant", "tool", "prompt", "resource_uri", "download_url")
    book_fields = ("book_id", "display_title", "version", "sha256", "download_url", "resource_uri")
    return {
        "schema_version": 1,
        "site_url": product["site_url"],
        "pages_url": product["pages_url"],
        "mcp_url": product["mcp_url"],
        "books_url": product["books_url"],
        "price_sentence": product["price_sentence"],
        "os_label": product["os_label"],
        "book_count": product["book_count"],
        "server": {key: server[key] for key in server_fields},
        "books": [{key: book[key] for key in book_fields} for book in product["books"]],
    }
