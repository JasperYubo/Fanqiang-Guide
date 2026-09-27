"""Render reviewed public answers through the site's existing page template."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import html
import json
from pathlib import Path
import re
import runpy
import sys
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

SITE = "https://fanqiang.guide"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ID = re.compile(r"faq-[a-z0-9-]+\Z")
ENTITY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
FACETS = dict(zip(
    "ai_access apple_device_unknown blocked_address bypass_router chain_proxy computer_device config_generator config_template firmware_branch firmware_flash format game_acceleration installation ip_check ipv6 language_translation phone_device proxy_node proxy_service qr_code return_to_china scripts_modules server_build sharing speed_test streaming_device subscription_address subscription_import subscription_management subscription_merge subscription_parse target_wechat".split(),
    "AI访问 苹果设备 地址被阻断 旁路由 链式代理 电脑 配置生成 配置模板 固件分支 刷写固件 配置格式 游戏加速 安装 IP检查 IPv6 中文界面 手机 代理节点 节点服务 二维码 回国访问 脚本与模块 服务端搭建 分享 测速 电视设备 订阅地址 订阅导入 订阅管理 订阅合并 订阅解析 微信".split()))
GENERIC_NAMES = {"network-access": "翻墙与科学上网", "subscription": "节点与订阅", "proxy": "代理", "router": "路由器", "vpn": "VPN", "general": "综合问题"}


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Invalid " + name)
    return value.strip()


def checked_date(value):
    stamp = datetime.fromisoformat(text(value, "checked date").replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
        raise ValueError("Invalid checked date")
    return value


def public_url(value):
    parsed = urlsplit(text(value, "source URL"))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or "." not in parsed.hostname or parsed.hostname.endswith((".local", ".internal", ".localhost")) or re.fullmatch(r"[0-9.]+", parsed.hostname):
        raise ValueError("Invalid public HTTPS source")
    return value


def load_answers(source):
    data = json.loads(Path(source).read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError("Invalid public FAQ envelope")
    manifest = {s["source_id"]: s for s in data.get("sources", [])}
    entries, seen = [], set()
    for raw in data["entries"]:
        if raw.get("review_state") != "approved" or raw.get("cache_eligible") is not True or raw.get("origin_kind") != "google_autocomplete_editorial_faq":
            raise ValueError("Only approved public answers may be rendered")
        ident = text(raw.get("faq_id"), "FAQ id")
        if not ID.fullmatch(ident) or ident in seen:
            raise ValueError("Invalid or duplicate FAQ id")
        seen.add(ident)
        entry = {key: raw.get(key, []) for key in ("entities", "platforms", "facets", "aliases", "required_slots", "version_constraints", "hardware_constraints", "forbidden_mismatch", "source_ids")}
        if any(not isinstance(entry[key], list) for key in entry):
            raise ValueError("Invalid FAQ scope")
        if any(not isinstance(e, str) or not ENTITY.fullmatch(e) for e in entry["entities"]):
            raise ValueError("Invalid entity id")
        entry.update(faq_id=ident, canonical_question=text(raw.get("canonical_question"), "question"), intent=text(raw.get("intent"), "intent"), short_answer=text(raw.get("short_answer"), "answer"), checked_at_utc=checked_date(raw.get("checked_at_utc")), sections=[], sources=[])
        for section in raw.get("answer_sections", []):
            if isinstance(section, str):
                entry["sections"].append({"title": "", "content": text(section, "section")})
            elif isinstance(section, dict):
                entry["sections"].append({"title": section.get("title", ""), "content": text(section.get("content"), "section")})
            else:
                raise ValueError("Invalid answer section")
        for ident_source in raw.get("source_ids", []):
            item = manifest.get(ident_source)
            if not item or item.get("verification_status") != "verified":
                raise ValueError("Unverified source")
            entry["sources"].append({"title": text(item.get("title"), "source title"), "url": public_url(item.get("url")), "checked_at": checked_date(item.get("checked_at_utc"))})
        if not entry["sources"]:
            raise ValueError("Missing sources")
        entries.append(entry)
    return sorted(entries, key=lambda e: e["faq_id"]), data.get("entity_aliases", {})


def route(entry):
    return "/answers/" + entry["faq_id"] + "/"


def equivalent_key(entry):
    keys = ("short_answer", "sections", "entities", "platforms", "intent", "source_ids", "version_constraints", "hardware_constraints")
    return json.dumps({key: entry[key] for key in keys}, ensure_ascii=False, sort_keys=True)


def title(entry):
    if entry.get("display_title"):
        return entry["display_title"]
    value = entry["canonical_question"]
    labels = re.search(r"[（(]([^()（）]+)[）)](?=[？?]?$)", value)
    scope = labels[1] if labels else "、".join(FACETS.get(f, f) for f in entry["facets"] if FACETS.get(f, f) not in value)
    if not scope:
        return value
    scope = scope.replace("服务端资料", "服务端").replace("代理节点", "节点").replace("代理服务", "节点服务").replace("订阅地址", "订阅格式")
    base = value[:labels.start()] + value[labels.end():] if labels else value
    patterns = [
        (r"^使用(.+?)前应确认哪些信息", lambda m: m[1] + "：" + scope + "资料怎么核对？"),
        (r"^(.+?)出现(.+?)问题时", lambda m: m[1] + m[2] + "问题：" + scope + "相关资料怎么核对？"),
        (r"^如何按设备和需求选择(.+?)[？?]?$", lambda m: m[1].rstrip("？?") + "怎么选：" + scope + "需要核对什么？"),
        (r"^(.+?)是什么，主要用于什么", lambda m: m[1] + "是什么？" + scope + "相关概念"),
        (r"^(.+?)从哪里下载", lambda m: m[1] + "下载：" + scope + "官方资料在哪里？"),
        (r"^(.+?)的官方项目和资料入口在哪里", lambda m: m[1] + "官方资料：" + scope + "入口在哪里？"),
    ]
    for pattern, render in patterns:
        match = re.search(pattern, base)
        if match:
            return render(match)
    return "关于" + scope + "，" + base


def mdtext(value):
    return html.escape(value, quote=False).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def write(public, relative, content):
    target = public / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")
    if relative != "sitemap.xml":
        target.with_name(target.name + ".gz").write_bytes(gzip.compress(target.read_bytes(), mtime=0))
    return target


def structured_html(rendered):
    return re.sub(r'(<script type="application/ld\+json">)(.*?)(</script>)', lambda m: m[1] + m[2].replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026") + m[3], rendered, flags=re.S)


def related(entry, entries):
    candidates = [e for e in entries if e["faq_id"] != entry["faq_id"] and set(e["entities"]) & set(entry["entities"]) and e["representative"] != entry["representative"]]
    candidates.sort(key=lambda e: (e["intent"] != entry["intent"], -len(set(e["facets"]) & set(entry["facets"])), e["faq_id"]))
    result, seen = [], set()
    for candidate in candidates:
        if candidate["representative"] not in seen:
            result.append(candidate); seen.add(candidate["representative"])
        if len(result) == 6:
            break
    return result


def render_answer(entry, entries, page):
    esc = html.escape
    path, canonical = route(entry), SITE + "/answers/" + entry["representative"] + "/"
    heading = title(entry)
    sources = "<ul>" + "".join(f'<li><a href="{esc(s["url"], quote=True)}">{esc(s["title"])}</a> · 核对：{esc(s["checked_at"][:10])}</li>' for s in entry["sources"]) + "</ul>"
    sections = "".join(("<h2>" + esc(s["title"]) + "</h2>" if s["title"] else "") + '<p style="white-space:pre-wrap">' + esc(s["content"]) + "</p>" for s in entry["sections"])
    related_entries = related(entry, entries)
    links = "<ul>" + "".join(f'<li><a href="{route(e)}">{esc(title(e))}</a></li>' for e in related_entries) + "</ul>"
    body = f'<main id="main" class="wrap guide-main"><nav class="breadcrumbs" aria-label="面包屑"><a href="/">翻墙指南</a><span>/</span><a href="/answers/">常见问题</a></nav><article><header class="guide-header"><h1>{esc(heading)}</h1><p class="guide-meta">资料核对：<time datetime="{esc(entry["checked_at_utc"], quote=True)}">{esc(entry["checked_at_utc"][:10])}</time> · <a href="{path}index.md">Markdown</a></p></header><div class="guide-body"><p style="white-space:pre-wrap">{esc(entry["short_answer"])}</p>{sections}<section><h2>来源与核对日期</h2>{sources}</section>' + (f'<section><h2>相关问题</h2>{links}</section>' if related_entries else "") + '<p>需要按自己的设备继续整理？<a href="/">回首页</a>说明可用的 AI、设备和需求，获取 I-Lang 工程书。</p><p><a href="/answers/">浏览全部常见问题</a></p></div></article></main>'
    schemas = [{"@type": "Article", "@id": canonical + "#article", "url": canonical, "headline": heading, "description": entry["short_answer"], "inLanguage": "zh-CN", "dateModified": entry["checked_at_utc"], "mainEntityOfPage": canonical, "author": {"@type": "Organization", "name": "Fanqiang Guide", "url": SITE + "/"}, "citation": [s["url"] for s in entry["sources"]]}, {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "翻墙指南", "item": SITE + "/"}, {"@type": "ListItem", "position": 2, "name": "常见问题", "item": SITE + "/answers/"}, {"@type": "ListItem", "position": 3, "name": heading, "item": canonical}]}]
    rendered = page(heading + " | Fanqiang Guide", entry["short_answer"], canonical[len(SITE):], body, schemas, path + "index.md").replace('content="website"', 'content="article"', 1)
    markdown = "# " + mdtext(heading) + "\n\n" + mdtext(entry["short_answer"]) + "\n\n资料核对：" + entry["checked_at_utc"][:10] + "\n"
    for section in entry["sections"]:
        markdown += ("\n## " + mdtext(section["title"]) + "\n" if section["title"] else "") + "\n" + mdtext(section["content"]) + "\n"
    markdown += "\n## 来源与核对日期\n\n" + "\n".join(f'- [{mdtext(s["title"])}]({s["url"]}) · 核对：{s["checked_at"][:10]}' for s in entry["sources"])
    if related_entries:
        markdown += "\n\n## 相关问题\n\n" + "\n".join(f'- [{mdtext(title(e))}]({SITE}{route(e)})' for e in related_entries)
    markdown += "\n\n需要按自己的设备继续整理？[回首页](" + SITE + "/)说明可用的 AI、设备和需求，获取 I-Lang 工程书。\n\n[浏览全部常见问题](" + SITE + "/answers/)\n"
    return structured_html(rendered), markdown


def build_faq_pages(public, source, page):
    public = Path(public)
    entries, aliases = load_answers(source)
    representatives = {}
    groups = defaultdict(list)
    for entry in entries:
        key = equivalent_key(entry)
        entry["representative"] = representatives.setdefault(key, entry["faq_id"])
        groups[key].append(entry)
    for group in groups.values():
        if len(group) > 1:
            shortest = min(group, key=lambda e: (len(e["facets"]), len(e["canonical_question"]), e["faq_id"]))
            if shortest["intent"] == "how_to_use":
                names = [GENERIC_NAMES.get(e) or (aliases.get(e) or [e])[0] for e in shortest["entities"]]
                heading = "、".join(names) + "：使用前的核对事项与官方资料"
            else:
                heading = title(shortest)
            for entry in group:
                entry["display_title"] = heading
    ownership = public / "data/faq-pages.json"
    previous = json.loads(ownership.read_text(encoding="utf-8")) if ownership.exists() else {}
    current_ids = {e["faq_id"] for e in entries}
    current_entities = {entity for e in entries for entity in (e["entities"] or ["general"])}
    obsolete = ["answers/" + item["faq_id"] for item in previous.get("entries", []) if isinstance(item, dict) and isinstance(item.get("faq_id"), str) and ID.fullmatch(item["faq_id"]) and item["faq_id"] not in current_ids]
    obsolete += ["answers/entity/" + ident for ident in previous.get("entity_ids", []) if isinstance(ident, str) and ENTITY.fullmatch(ident) and ident not in current_entities]
    for relative in obsolete:
        directory = public / relative
        for name in ("index.html", "index.md", "index.html.gz", "index.md.gz"):
            target = directory / name
            if target.is_file():
                target.unlink()
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    categories = defaultdict(list)
    for entry in entries:
        rendered, markdown = render_answer(entry, entries, page)
        write(public, "answers/" + entry["faq_id"] + "/index.html", rendered)
        write(public, "answers/" + entry["faq_id"] + "/index.md", markdown)
        for entity in entry["entities"] or ["general"]:
            categories[entity].append(entry)
    dates = {SITE + route(e): e["checked_at_utc"] for e in entries if e["faq_id"] == e["representative"]}
    newest = max((e["checked_at_utc"] for e in entries), default=None)
    names = {entity: GENERIC_NAMES.get(entity) or (aliases.get(entity) or [entity])[0] for entity in categories}
    for entity in sorted(categories):
        path = "/answers/entity/" + entity + "/"
        heading = names[entity] + "常见问题"
        items = sorted(categories[entity], key=lambda e: (e["intent"], title(e), e["faq_id"]))
        cards = "<ul>" + "".join(f'<li><a href="{route(e)}">{html.escape(title(e))}</a></li>' for e in items) + "</ul>"
        body = f'<main id="main" class="wrap guide-main"><nav class="breadcrumbs"><a href="/answers/">常见问题</a></nav><h1>{html.escape(heading)}</h1>{cards}</main>'
        write(public, path.strip("/") + "/index.html", structured_html(page(heading + " | Fanqiang Guide", heading, path, body, [{"@type": "CollectionPage", "name": heading, "url": SITE + path}], path + "index.md")))
        write(public, path.strip("/") + "/index.md", "# " + mdtext(heading) + "\n\n" + "\n".join(f'- [{mdtext(title(e))}]({SITE}{route(e)})' for e in items) + "\n\n[全部常见问题](" + SITE + "/answers/)")
        dates[SITE + path] = max(e["checked_at_utc"] for e in items)
    links = "<ul>" + "".join(f'<li><a href="/answers/entity/{entity}/">{html.escape(names[entity])}</a>（{len(categories[entity])}）</li>' for entity in sorted(categories, key=lambda e: names[e].casefold())) + "</ul>"
    heading = "常见问题与官方参考"
    body = f'<main id="main" class="wrap guide-main"><nav class="breadcrumbs"><a href="/">翻墙指南</a></nav><h1>{heading}</h1><p class="guide-summary">按工具和主题查阅问题答案，沿来源阅读官方资料。</p>{links}</main>'
    write(public, "answers/index.html", structured_html(page(heading + " | Fanqiang Guide", "按工具和主题阅读常见问题答案及官方来源。", "/answers/", body, [{"@type": "CollectionPage", "name": heading, "url": SITE + "/answers/"}], "/answers/index.md")))
    write(public, "answers/index.md", "# " + heading + "\n\n按工具和主题查阅问题答案，沿来源阅读官方资料。\n\n" + "\n".join(f'- [{mdtext(names[entity])}]({SITE}/answers/entity/{entity}/)' for entity in sorted(categories)))
    if newest:
        dates[SITE + "/answers/"] = newest
    ET.register_namespace("", NS)
    sitemap = ET.fromstring((public / "sitemap.xml").read_text(encoding="utf-8"))
    for node in list(sitemap):
        location = node.find(f"{{{NS}}}loc")
        if location is not None and (location.text or "").startswith(SITE + "/answers/"):
            sitemap.remove(node)
    answers_sitemap = ET.Element(f"{{{NS}}}urlset")
    for location, modified in sorted(dates.items()):
        for parent in (sitemap, answers_sitemap):
            node = ET.SubElement(parent, f"{{{NS}}}url")
            ET.SubElement(node, f"{{{NS}}}loc").text = location
            ET.SubElement(node, f"{{{NS}}}lastmod").text = modified
    for name, root in (("sitemap.xml", sitemap), ("sitemap-answers.xml", answers_sitemap)):
        write(public, name, '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode"))
    discovery = "- [常见问题与官方参考](" + SITE + "/answers/)：按工具和主题阅读答案与官方来源。"
    for name in ("llms.txt", "ai/index.md", "index.md"):
        previous = (public / name).read_text(encoding="utf-8")
        if SITE + "/answers/" not in previous:
            write(public, name, previous.rstrip() + "\n\n" + discovery)
    write(public, "llms-full.txt", (public / "ai/index.md").read_text(encoding="utf-8"))
    home = (public / "index.html").read_text(encoding="utf-8")
    if 'href="/answers/"' not in home:
        home = home.replace("</main>", '<section class="wrap"><h2><a href="/answers/">常见问题与官方参考</a></h2><p>按工具和主题查阅答案，沿来源阅读官方资料。</p></section></main>', 1)
        write(public, "index.html", home)
    catalog = public / ".well-known/ai-catalog.json"
    obj = json.loads(catalog.read_text(encoding="utf-8"))
    identifier = "urn:air:fanqiang.guide:resource:answers"
    obj["entries"] = [e for e in obj["entries"] if e.get("identifier") != identifier] + [{"identifier": identifier, "displayName": heading, "type": "text/html", "url": SITE + "/answers/"}]
    write(public, ".well-known/ai-catalog.json", json.dumps(obj, ensure_ascii=False, indent=2))
    result = {"version": "1.0", "pages": len(entries), "canonical_pages": len(representatives), "entity_directories": len(categories), "sitemap_urls": len(dates), "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest()}
    write(public, "data/faq-pages.json", json.dumps({**result, "entity_ids": sorted(current_entities), "entries": [{"faq_id": e["faq_id"], "title": title(e), "url": SITE + route(e), "canonical": SITE + "/answers/" + e["representative"] + "/"} for e in entries]}, ensure_ascii=False, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    options = parser.parse_args()
    directory = Path(__file__).resolve().parent
    # The base builder runs once. Its page function is then used without importing
    # that executable script into another build or changing the live checkout.
    sys.path.insert(0, str(directory))
    base = runpy.run_path(str(directory / "build-site-v1.4-2026-09-13.py"))
    result = build_faq_pages(directory / "public", options.source, base["page"])
    base["inject_ga4_into_final_html"]()
    guard = runpy.run_path(str(directory.parent / "worker/frontend/patch_external_browser.py"))["INJECTION"]
    for target in (directory / "public/answers").rglob("*.html"):
        content = target.read_text(encoding="utf-8")
        if "external-browser-v1.0.js" not in content:
            write(directory / "public", target.relative_to(directory / "public").as_posix(), content.replace("<head>", "<head>" + guard, 1))
    manifest = {}
    for target in sorted((directory / "public").rglob("*")):
        if target.is_file() and target.suffix != ".gz":
            relative = target.relative_to(directory / "public").as_posix()
            manifest[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
            if relative != "sitemap.xml" and (target.suffix in (".html", ".md", ".json", ".txt", ".xml") or target.with_name(target.name + ".gz").exists()):
                target.with_name(target.name + ".gz").write_bytes(gzip.compress(target.read_bytes(), mtime=0))
    (directory / "release-manifest-v1.4-2026-09-13.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
