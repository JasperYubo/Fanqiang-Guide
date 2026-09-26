"""Build consented, anonymized cases from one allowlisted public JSON source."""
from __future__ import annotations

import html
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

SITE = "https://fanqiang.guide"
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
RESULTS = {
    "resolution": {"resolved": "用户确认咨询问题已解决", "unresolved": "仍需补充", "unconfirmed": "用户尚未确认咨询结果"},
    "delivery": {"delivered": "I-Lang 工程书已交付", "not_delivered": "工程书尚未交付"},
    "execution": {"confirmed_success": "用户反馈实际执行成功", "confirmed_failure": "用户反馈实际执行未成功", "unverified": "实际执行尚未验证"},
}
LEAK = re.compile(r"(?:\b(?:sk-|ghp_|github_pat_|hf_|cfat_)[A-Za-z0-9_-]{12,}|-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|(?:vmess|vless|trojan|ss|ssr|hysteria2)://[^\s<>]+|https?://[^\s<>]+[?&](?:token|key|password|secret|auth|subscription)=[^\s<>]+|(?<!\d)1[3-9]\d{9}(?!\d))", re.I)
SOURCE_STATUS = {"primary_reviewed": "已核对第一方资料", "reference_only": "仅参考目录线索", "historical_reference": "历史资料"}
_VALIDATOR = None


def validate_book(book):
    global _VALIDATOR
    if _VALIDATOR is None:
        path = Path(__file__).resolve().parents[2] / "tools/ilang_grammar_validator.py"
        spec = importlib.util.spec_from_file_location("case_ilang_validator", path)
        _VALIDATOR = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_VALIDATOR)
    findings = _VALIDATOR.Linter("public-case-book", book).run()
    if any(item[0] in (_VALIDATOR.ERROR, _VALIDATOR.WARN) for item in findings):
        raise ValueError("Public engineering book failed strict I-Lang grammar validation")


def text(value, name, limit=20000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"Invalid {name}")
    if LEAK.search(value):
        raise ValueError(f"Unredacted private value in {name}")
    return value.strip()


def safe_url(value):
    value = text(value, "source URL", 2000)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query:
        raise ValueError("Sources require HTTPS URLs without credentials or query strings")
    return value


def date(value):
    value = text(value, "date", 40)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO date") from exc
    return value


def normalize(raw):
    """Deliberately discard every field not in the public rendering contract."""
    if raw.get("schema_version") != "1.0":
        raise ValueError("Unsupported public case schema")
    publication = raw.get("publication", {})
    if publication.get("approved") is not True or publication.get("anonymized") is not True:
        raise ValueError("Case has no anonymized publication approval")
    slug = text(raw.get("slug"), "slug", 100)
    if not SLUG.fullmatch(slug):
        raise ValueError("Invalid stable slug")
    out = {"schema_version": "1.0", "slug": slug,
           "title": text(raw.get("title"), "title", 160),
           "question": text(raw.get("question"), "question", 2000),
           "answer_summary": text(raw.get("answer_summary"), "answer_summary", 4000),
           "published_at": date(raw.get("published_at")), "updated_at": date(raw.get("updated_at")),
           "publication": {"approved": True, "anonymized": True}}
    out["provenance"] = {"content_kind": "generated_case", "basis": "anonymized_public_consultation"}
    for key in ("constraints", "selection_reasons"):
        values = raw.get(key)
        if not isinstance(values, list) or not values or len(values) > 30:
            raise ValueError(f"Missing or excessive {key}")
        out[key] = [text(v, key, 4000) for v in values]
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources or len(sources) > 30:
        raise ValueError("Sources are required")
    out["sources"] = [{"title": text(s.get("title"), "source title", 240),
                       "url": safe_url(s.get("url")), "checked_at": date(s.get("checked_at")),
                       **({"review_status": text(s["review_status"], "source status", 100)} if s.get("review_status") else {})} for s in sources]
    out["result"] = {}
    for key, allowed in RESULTS.items():
        status = raw.get("result", {}).get(key)
        if status not in allowed:
            raise ValueError(f"Invalid {key} status")
        out["result"][key] = status
    confirmation = raw.get("result", {}).get("confirmed_at")
    out["result"]["confirmed_at"] = date(confirmation) if confirmation else None
    if (out["result"]["resolution"] == "resolved" or out["result"]["execution"].startswith("confirmed_")) and not confirmation:
        raise ValueError("Confirmed outcomes require their confirmation date")
    book = text(raw.get("engineering_book_public"), "engineering_book_public", 160000)
    if not book.startswith("::ILANG::") or "::ILANG::COMPLETE::" not in book:
        raise ValueError("A real I-Lang engineering book is required")
    out["engineering_book_public"] = book
    validate_book(book)
    sections = raw.get("sections", [])
    if not isinstance(sections, list) or len(sections) > 20:
        raise ValueError("Invalid article sections")
    out["sections"] = []
    for section in sections:
        paragraphs = section.get("paragraphs")
        if not isinstance(paragraphs, list) or not paragraphs or len(paragraphs) > 30:
            raise ValueError("Invalid article paragraphs")
        out["sections"].append({"heading": text(section.get("heading"), "article heading", 180),
                                "paragraphs": [text(p, "article paragraph", 6000) for p in paragraphs]})
    conversation = raw.get("conversation_public", [])
    if not isinstance(conversation, list) or len(conversation) > 100:
        raise ValueError("Invalid public conversation")
    out["conversation_public"] = []
    for turn in conversation:
        if turn.get("role") not in ("user", "assistant"):
            raise ValueError("Only public user/assistant turns are allowed")
        out["conversation_public"].append({"role": turn["role"], "content": text(turn.get("content"), "conversation", 20000)})
    if raw.get("intent_key"):
        out["intent_key"] = text(raw["intent_key"], "intent_key", 180)
    return out


def mdtext(value):
    return html.escape(value, quote=False).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def result_lines(case):
    return [allowed[case["result"][key]] for key, allowed in RESULTS.items()]


def write(root, relative, body):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.rstrip() + "\n", encoding="utf-8", newline="\n")


def render(case, page):
    esc = html.escape
    slug = case["slug"]
    route = f"/cases/{slug}/"
    canonical = SITE + route
    status = result_lines(case)
    bullets = lambda items: "<ul>" + "".join("<li>" + esc(v) + "</li>" for v in items) + "</ul>"
    source_html = "<ul>" + "".join(f'<li><a href="{esc(s["url"], quote=True)}">{esc(s["title"])}</a> · 核对日期：{esc(s["checked_at"])}' + (" · " + esc(SOURCE_STATUS.get(s["review_status"], s["review_status"])) if s.get("review_status") else "") + '</li>' for s in case["sources"]) + "</ul>"
    conversation = "".join(f'<h3>{"用户" if t["role"] == "user" else "AI"}</h3><p style="white-space:pre-wrap">{esc(t["content"])}</p>' for t in case["conversation_public"])
    article_sections = "".join("<section><h2>" + esc(s["heading"]) + "</h2>" + "".join("<p>" + esc(p) + "</p>" for p in s["paragraphs"]) + "</section>" for s in case["sections"])
    body = f'''<main id="main" class="wrap guide-main"><nav class="breadcrumbs" aria-label="面包屑"><a href="/">翻墙指南</a><span>/</span><a href="/cases/">选型与问答案例</a></nav><article><header class="guide-header"><h1>{esc(case["title"])}</h1><p class="guide-summary">{esc(case["answer_summary"])}</p><p class="guide-meta">Fanqiang Guide · 发布：{esc(case["published_at"])} · 更新：{esc(case["updated_at"])}</p></header><div class="guide-body"><section><h2>这次要解决什么问题</h2><p>{esc(case["question"])}</p><h3>设备与需求条件</h3>{bullets(case["constraints"])}</section><section><h2>为什么这样选择</h2>{bullets(case["selection_reasons"])}</section><section><h2>交付与反馈</h2>{bullets(status)}<p>反馈确认时间：{esc(case["result"]["confirmed_at"] or "暂无")}</p></section><section><h2>来源与核对日期</h2>{source_html}</section><section><h2>I-Lang 工程书全文</h2><p>公开工程书已脱敏，个人参数使用变量。交给你自己的 AI，结合当前设备和资料继续处理。</p><p><a href="{route}engineering.ilang" download>下载 I-Lang 工程书</a> · <a href="{route}index.md">阅读 Markdown</a></p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">{esc(case["engineering_book_public"])}</pre></section><section><h2>脱敏对话</h2><p>仅保留本次问题所需的公开内容，账号与私人参数不公开。</p><details><summary>展开脱敏对话记录</summary>{conversation}</details><p><a href="{route}conversation.md">阅读脱敏记录</a></p></section></div></article></main>'''
    body = body.replace('<section><h2>交付与反馈</h2>', article_sections + '<section><h2>交付与反馈</h2>', 1)
    body = body.replace(f'href="{route}engineering.ilang" download>', f'href="{route}engineering.ilang" download="{slug}-v1.0-{case["updated_at"][:10]}.ilang">', 1)
    body = body.replace('<section><h2>来源与核对日期</h2>', '<section><h2>来源与核对日期</h2><p>本页根据已获公开同意的脱敏咨询整理，并引用下列资料。案例反馈与第一方文档的支持声明分别记录。</p>', 1)
    schemas = [{"@type": "Article", "@id": canonical + "#article", "url": canonical,
                "headline": case["title"], "description": case["answer_summary"], "inLanguage": "zh-CN",
                "datePublished": case["published_at"], "dateModified": case["updated_at"],
                "author": {"@type": "Organization", "name": "Fanqiang Guide", "url": SITE + "/guides/about.html"},
                "mainEntityOfPage": canonical, "citation": [s["url"] for s in case["sources"]]},
               {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "翻墙指南", "item": SITE + "/"}, {"@type": "ListItem", "position": 2, "name": "选型与问答案例", "item": SITE + "/cases/"}, {"@type": "ListItem", "position": 3, "name": case["title"], "item": canonical}]}]
    output_html = page(case["title"] + " | Fanqiang Guide", case["answer_summary"], route, body, schemas, route + "index.md")
    output_html = output_html.replace('content="website"', 'content="article"', 1)
    output_html = re.sub(r'(<script type="application/ld\+json">)(.*?)(</script>)', lambda m: m[1] + m[2].replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026") + m[3], output_html, flags=re.S)
    markdown = f'# {mdtext(case["title"])}\n\n{mdtext(case["answer_summary"])}\n\n发布：{case["published_at"]} · 更新：{case["updated_at"]}\n\n## 这次要解决什么问题\n\n{mdtext(case["question"])}\n\n## 设备与需求条件\n\n'
    markdown += "\n".join("- " + mdtext(v) for v in case["constraints"]) + "\n\n## 为什么这样选择\n\n" + "\n".join("- " + mdtext(v) for v in case["selection_reasons"])
    markdown += "".join("\n\n## " + mdtext(s["heading"]) + "\n\n" + "\n\n".join(mdtext(p) for p in s["paragraphs"]) for s in case["sections"])
    markdown += "\n\n## 交付与反馈\n\n" + "\n".join("- " + v for v in status) + "\n\n反馈确认时间：" + (case["result"]["confirmed_at"] or "暂无")
    markdown += "\n\n## 来源与核对日期\n\n本页根据已获公开同意的脱敏咨询整理，并引用下列资料。案例反馈与第一方文档的支持声明分别记录。\n\n" + "\n".join(f'- [{mdtext(s["title"])}]({s["url"]}) · 核对日期：{s["checked_at"]}' + (" · " + mdtext(SOURCE_STATUS.get(s["review_status"], s["review_status"])) if s.get("review_status") else "") for s in case["sources"])
    fence = "`" * max(3, 1 + max([len(m.group()) for m in re.finditer(r"`+", case["engineering_book_public"])] or [0]))
    markdown += f'\n\n## I-Lang 工程书全文\n\n公开工程书已脱敏，个人参数使用变量；交付不表示实际执行已验证。\n\n{fence}text\n{case["engineering_book_public"]}\n{fence}\n\n[下载工程书]({canonical}engineering.ilang) · [脱敏对话]({canonical}conversation.md)\n'
    transcript = "# 脱敏对话记录\n\n" + "\n\n".join("## " + ("用户" if t["role"] == "user" else "AI") + "\n\n" + mdtext(t["content"]) for t in case["conversation_public"])
    return {"index.html": output_html, "index.md": markdown, "conversation.md": transcript,
            "engineering.ilang": case["engineering_book_public"], "case.json": json.dumps(case, ensure_ascii=False, indent=2)}


def build_cases(public, sources, page):
    public, sources = Path(public), Path(sources)
    cases, slugs, intents = [], set(), set()
    for source in sorted(sources.glob("*/case.json")):
        case = normalize(json.loads(source.read_text(encoding="utf-8")))
        if source.parent.name != case["slug"] or case["slug"] in slugs:
            raise ValueError("Source path must match its unique stable slug")
        if case.get("intent_key") in intents:
            raise ValueError("Duplicate intent must update its existing stable case")
        slugs.add(case["slug"])
        if case.get("intent_key"):
            intents.add(case["intent_key"])
        cases.append(case)
    cases.sort(key=lambda c: (c["updated_at"], c["slug"]), reverse=True)
    # Remove only artifacts this builder previously recorded, including gzip
    # siblings. Revoked cases must not survive as stale public files.
    previous_path = public / "data/cases.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    for entry in previous.get("cases", []):
        slug = entry.get("slug", "")
        if SLUG.fullmatch(slug) and slug not in slugs:
            directory = public / "cases" / slug
            for name in ("index.html", "index.md", "conversation.md", "engineering.ilang", "case.json"):
                for target in (directory / name, directory / (name + ".gz")):
                    if target.is_file():
                        target.unlink()
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
    entries = []
    for case in cases:
        prefix = "cases/" + case["slug"] + "/"
        for name, value in render(case, page).items():
            write(public, prefix + name, value)
        entries.append({"slug": case["slug"], "title": case["title"], "summary": case["answer_summary"],
                        "url": SITE + "/" + prefix, "markdown": SITE + "/" + prefix + "index.md",
                        "data": SITE + "/" + prefix + "case.json", "engineering_book": SITE + "/" + prefix + "engineering.ilang",
                        "result": case["result"], "updated_at": case["updated_at"]})
    write(public, "data/cases.json", json.dumps({"schema_version": "1.0", "cases": entries}, ensure_ascii=False, indent=2))
    cards = "".join(f'<section><h2><a href="/cases/{c["slug"]}/">{html.escape(c["title"])}</a></h2><p>{html.escape(c["answer_summary"])}</p><p>{" · ".join(result_lines(c))}</p></section>' for c in cases)
    title = "选型与问答案例"
    body = f'<main id="main" class="wrap guide-main"><h1>{title}</h1><p class="guide-summary">按设备和需求阅读选型依据、来源及用户反馈。咨询结果与实际执行结果分别记录。</p><div class="guide-body">{cards or "<p>暂无已确认公开的案例。你可以先查阅工具指南。</p>"}</div><p><a href="/guides/index.html">阅读工具指南</a></p></main>'
    rendered = page(title + " | Fanqiang Guide", "公开选型与问答案例，保留设备条件、选择依据、来源和准确反馈状态。", "/cases/", body, [{"@type": "CollectionPage", "name": title, "url": SITE + "/cases/"}], "/cases/index.md")
    if not cases:
        rendered = rendered.replace('content="index,follow"', 'content="noindex,follow"')
    write(public, "cases/index.html", rendered)
    write(public, "cases/index.md", "# " + title + "\n\n" + ("\n".join(f'- [{mdtext(c["title"])}]({SITE}/cases/{c["slug"]}/)：{mdtext(c["answer_summary"])}' for c in cases) or "暂无已确认公开的案例。"))
    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    ET.register_namespace("", namespace)
    root = ET.fromstring((public / "sitemap.xml").read_text(encoding="utf-8"))
    for node in list(root):
        location = node.find(f"{{{namespace}}}loc")
        if location is not None and (location.text or "").startswith(SITE + "/cases/"):
            root.remove(node)
    known = {n.text for n in root.findall(f"{{{namespace}}}url/{{{namespace}}}loc")}
    routes = ([(SITE + "/cases/", max(c["updated_at"] for c in cases))] if cases else []) + [(e["url"], e["updated_at"]) for e in entries]
    for url, modified in routes:
        if url not in known:
            node = ET.SubElement(root, f"{{{namespace}}}url")
            ET.SubElement(node, f"{{{namespace}}}loc").text = url
            ET.SubElement(node, f"{{{namespace}}}lastmod").text = modified
    write(public, "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode"))
    catalog_path = public / ".well-known/ai-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    identifier = "urn:air:fanqiang.guide:resource:cases"
    catalog["entries"] = [e for e in catalog["entries"] if e.get("identifier") != identifier]
    if cases:
        catalog["entries"].append({"identifier": identifier, "displayName": title, "type": "application/json", "url": SITE + "/data/cases.json", "representativeQueries": [c["question"] for c in cases[:6]]})
    write(public, ".well-known/ai-catalog.json", json.dumps(catalog, ensure_ascii=False, indent=2))
    marker = "\n\n## 选型与问答案例\n"
    cases_md = marker + "\n".join(f'- [{mdtext(c["title"])}]({SITE}/cases/{c["slug"]}/)：{mdtext(c["answer_summary"])}' for c in cases) + "\n\n案例保留反馈状态；工程书交付不等于执行成功。\n"
    for name in ("llms.txt", "ai/index.md"):
        previous = (public / name).read_text(encoding="utf-8").split(marker, 1)[0]
        write(public, name, previous + (cases_md if cases else ""))
    write(public, "llms-full.txt", (public / "ai/index.md").read_text(encoding="utf-8"))
    for name in ("index.html", "guides/index.html"):
        previous = (public / name).read_text(encoding="utf-8")
        link = '<a href="/cases/">选型与问答案例</a>'
        if not cases:
            write(public, name, previous.replace(link, ""))
        elif link not in previous:
            previous = previous.replace('<nav aria-label="页脚导航">', '<nav aria-label="页脚导航">' + link, 1)
            write(public, name, previous)
    return {"cases": len(cases), "urls": [r[0] for r in routes]}
