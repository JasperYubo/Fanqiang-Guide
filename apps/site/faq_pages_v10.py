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

# The release validator loads this file directly from outside the checkout.
normalize_sitemaps = runpy.run_path(
    str(Path(__file__).resolve().with_name("sitemap_dates.py"))
)["normalize_sitemaps"]

_autosetup = runpy.run_path(str(Path(__file__).resolve().with_name("autosetup_discovery.py")))
setup_context = _autosetup["setup_context"]
render_autosetup_callout = _autosetup["render_autosetup_callout"]
autosetup_markdown = _autosetup["autosetup_markdown"]

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
    candidates = [e for e in canonical_entries(entries) if e["faq_id"] != entry["faq_id"] and set(e["entities"]) & set(entry["entities"]) and e["representative"] != entry["representative"]]
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
    autosetup_context = setup_context(entry)
    autosetup_html = render_autosetup_callout(autosetup_context) if autosetup_context else ""
    sources = "<ul>" + "".join(f'<li><a href="{esc(s["url"], quote=True)}">{esc(s["title"])}</a> · 核对：{esc(s["checked_at"][:10])}</li>' for s in entry["sources"]) + "</ul>"
    sections = "".join(("<h2>" + esc(s["title"]) + "</h2>" if s["title"] else "") + '<p style="white-space:pre-wrap">' + esc(s["content"]) + "</p>" for s in entry["sections"])
    related_entries = related(entry, entries)
    links = "<ul>" + "".join(f'<li><a href="{canonical_route(e)}">{esc(title(e))}</a></li>' for e in related_entries) + "</ul>"
    body = f'<main id="main" class="wrap guide-main"><nav class="breadcrumbs" aria-label="面包屑"><a href="/">翻墙指南</a><span>/</span><a href="/answers/">常见问题</a></nav><article><header class="guide-header"><h1>{esc(heading)}</h1><p class="guide-meta">资料核对：<time datetime="{esc(entry["checked_at_utc"], quote=True)}">{esc(entry["checked_at_utc"][:10])}</time> · <a href="{path}index.md">Markdown</a></p></header><div class="guide-body"><p style="white-space:pre-wrap">{esc(entry["short_answer"])}</p>{sections}{autosetup_html}<section><h2>来源与核对日期</h2>{sources}</section>' + (f'<section><h2>相关问题</h2>{links}</section>' if related_entries else "") + '<p>需要继续配置自己的设备？<a href="/ai/#device-setup">让自己的 AI 获取工程书</a>，完成安装、排错与验证。</p><p><a href="/answers/">浏览全部常见问题</a></p></div></article></main>'
    schemas = [{"@type": "Article", "@id": canonical + "#article", "url": canonical, "headline": heading, "description": entry["short_answer"], "inLanguage": "zh-CN", "dateModified": entry["checked_at_utc"], "mainEntityOfPage": canonical, "author": {"@type": "Organization", "name": "Fanqiang Guide", "url": SITE + "/"}, "citation": [s["url"] for s in entry["sources"]]}, {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "翻墙指南", "item": SITE + "/"}, {"@type": "ListItem", "position": 2, "name": "常见问题", "item": SITE + "/answers/"}, {"@type": "ListItem", "position": 3, "name": heading, "item": canonical}]}]
    rendered = page(heading + " | Fanqiang Guide", entry["short_answer"], canonical[len(SITE):], body, schemas, path + "index.md").replace('content="website"', 'content="article"', 1)
    markdown = "# " + mdtext(heading) + "\n\n" + mdtext(entry["short_answer"]) + "\n\n资料核对：" + entry["checked_at_utc"][:10] + "\n"
    for section in entry["sections"]:
        markdown += ("\n## " + mdtext(section["title"]) + "\n" if section["title"] else "") + "\n" + mdtext(section["content"]) + "\n"
    if autosetup_context:
        markdown += autosetup_markdown(autosetup_context)
    markdown += "\n## 来源与核对日期\n\n" + "\n".join(f'- [{mdtext(s["title"])}]({s["url"]}) · 核对：{s["checked_at"][:10]}' for s in entry["sources"])
    if related_entries:
        markdown += "\n\n## 相关问题\n\n" + "\n".join(f'- [{mdtext(title(e))}]({SITE}{canonical_route(e)})' for e in related_entries)
    markdown += "\n\n需要继续配置自己的设备？[让自己的 AI 获取工程书](" + SITE + "/ai/#device-setup)，完成安装、排错与验证。\n\n[浏览全部常见问题](" + SITE + "/answers/)\n"
    return structured_html(rendered), markdown


# These routes are reader-facing links; artifact filenames keep their stable IDs.
def canonical_route(entry):
    return "/answers/" + entry.get("representative", entry["faq_id"]) + "/"


def canonical_entries(entries):
    by_id = {entry["faq_id"]: entry for entry in entries}
    result, seen = [], set()
    for entry in entries:
        ident = entry.get("representative", entry["faq_id"])
        if ident not in seen:
            result.append(by_id.get(ident, entry))
            seen.add(ident)
    return result


def source_links(entry):
    return "<ul>" + "".join(
        f'<li><a href="{html.escape(s["url"], quote=True)}">{html.escape(s["title"])}</a>'
        f' · 核对：{html.escape(s["checked_at"][:10])}</li>'
        for s in entry["sources"]
    ) + "</ul>"


def category_answer(entry):
    sections = "".join(
        ("<h3>" + html.escape(section["title"]) + "</h3>" if section["title"] else "")
        + '<p style="white-space:pre-wrap">' + html.escape(section["content"]) + "</p>"
        for section in entry["sections"]
    )
    return (
        f'<section id="{entry["representative"]}"><h2>'
        f'<a href="{canonical_route(entry)}">{html.escape(title(entry))}</a></h2>'
        f'<p style="white-space:pre-wrap">{html.escape(entry["short_answer"])}</p>{sections}'
        f'<p class="guide-meta">资料核对：<time datetime="{html.escape(entry["checked_at_utc"], quote=True)}">'
        f'{html.escape(entry["checked_at_utc"][:10])}</time></p>'
        '<h3>来源与核对日期</h3>' + source_links(entry) + "</section>"
    )


def category_markdown(entry):
    result = f'## [{mdtext(title(entry))}]({SITE}{canonical_route(entry)})\n\n'
    result += mdtext(entry["short_answer"]) + "\n"
    for section in entry["sections"]:
        if section["title"]:
            result += "\n### " + mdtext(section["title"]) + "\n"
        result += "\n" + mdtext(section["content"]) + "\n"
    result += "\n资料核对：" + entry["checked_at_utc"][:10] + "\n\n"
    result += "\n".join(
        f'- [{mdtext(s["title"])}]({s["url"]}) · 核对：{s["checked_at"][:10]}'
        for s in entry["sources"]
    )
    return result


def update_discovery_html(public, relative, key, fragment, after_heading=False):
    target = public / relative
    if not target.is_file():
        return
    raw = target.read_text(encoding="utf-8")
    start, end = f"<!-- {key}:start -->", f"<!-- {key}:end -->"
    if not fragment and start not in raw:
        return
    block = start + fragment + end if fragment else ""
    pattern = re.escape(start) + r".*?" + re.escape(end)
    if start in raw:
        rendered, count = re.subn(pattern, lambda match: block, raw, flags=re.S)
        if count != 1:
            raise ValueError("Invalid discovery marker in " + relative)
    elif key == "faq-home-discovery" and 'id="faq-discovery"' in raw:
        rendered, count = re.subn(r'<section\b[^>]*\bid="faq-discovery"[^>]*>.*?</section>',
                                  lambda match: block, raw, count=1, flags=re.S)
        if count != 1:
            raise ValueError("Missing home discovery section")
    elif after_heading:
        rendered, count = re.subn(r"</h1>", lambda match: match[0] + block, raw, count=1)
        if not count:
            raise ValueError("Missing page heading in " + relative)
    else:
        if "</main>" not in raw:
            raise ValueError("Missing page main in " + relative)
        rendered = raw.replace("</main>", block + "</main>", 1)
    write(public, relative, rendered)


def update_discovery_markdown(public, relative, key, content):
    target = public / relative
    if not target.is_file():
        return
    raw = target.read_text(encoding="utf-8")
    start, end = f"<!-- {key}:start -->", f"<!-- {key}:end -->"
    if not content and start not in raw:
        return
    block = start + "\n" + content.rstrip() + "\n" + end if content else ""
    if start in raw:
        raw, count = re.subn(re.escape(start) + r".*?" + re.escape(end),
                            lambda match: block, raw, flags=re.S)
        if count != 1:
            raise ValueError("Invalid Markdown discovery marker in " + relative)
    else:
        raw = raw.rstrip() + "\n\n" + block
    write(public, relative, raw)


GUIDE_ENTITIES = {
    "client-downloads": ("v2rayn", "v2rayng", "shadowrocket", "clash-verge-rev", "hiddify"),
    "ladder-vpn-proxy": ("network-access", "vpn", "proxy"),
    "airport-subscription-nodes": ("subscription", "proxy"),
    "free-nodes": ("subscription",),
    "subscription-conversion": ("subconverter", "sub-store", "subscription"),
    "shadowrocket-platforms": ("shadowrocket",),
    "shadowrocket-qr": ("shadowrocket",),
    "router-guide": ("router", "openwrt", "asuswrt-merlin"),
    "openwrt-tools": ("openwrt", "openclash", "passwall", "passwall2"),
    "asus-merlin": ("asuswrt-merlin", "asuswrt-merlin-gnuton", "fancyss"),
    "v2rayn-guide": ("v2rayn",),
    "proxy-cores": ("mihomo", "xray-core", "sing-box", "v2ray-core"),
    "clash-projects": ("clash", "clash-verge-rev", "clash-meta"),
    "merlin-models": ("asuswrt-merlin", "asuswrt-merlin-gnuton"),
}


def guide_answers(entries, entities):
    candidates = [entry for entry in canonical_entries(entries)
                  if set(entry["entities"]) & set(entities)]
    # Prefer a range of existing question intents over many versions of one intent.
    candidates.sort(key=lambda entry: (len(entry["facets"]), title(entry), entry["faq_id"]))
    chosen, seen_intents = [], set()
    for entry in candidates:
        if entry["intent"] not in seen_intents:
            chosen.append(entry)
            seen_intents.add(entry["intent"])
        if len(chosen) == 6:
            return chosen
    chosen_ids = {entry["faq_id"] for entry in chosen}
    return (chosen + [entry for entry in candidates if entry["faq_id"] not in chosen_ids])[:6]


def add_answer_discovery(public, entries, categories, names):
    preferred = ("openwrt", "openclash", "shadowrocket", "v2rayn",
                 "clash-verge-rev", "sing-box", "asuswrt-merlin", "subscription")
    featured = [entity for entity in preferred if entity in categories]
    featured += [entity for entity in sorted(categories, key=lambda value: names[value].casefold())
                 if entity not in featured]
    featured = featured[:8]
    topics = '<ul class="related-links">' + "".join(
        f'<li><a href="/answers/entity/{entity}/">{html.escape(names[entity])}常见问题</a></li>'
        for entity in featured
    ) + "</ul>"
    topic_md = "\n".join(
        f'- [{mdtext(names[entity])}常见问题]({SITE}/answers/entity/{entity}/)'
        for entity in featured
    )
    home = (
        '<section class="section wrap faq-discovery" id="faq-discovery" aria-labelledby="faq-discovery-title">'
        '<div class="faq-discovery-inner"><div><p class="mini-label">公开问答 / 官方参考</p>'
        '<h2 id="faq-discovery-title">翻墙与科学上网<span class="faq-title-tail">常见问题</span></h2>'
        '<p>按工具和主题查答案，沿出处核对官方资料。</p></div>'
        '<a class="button button-primary" href="/answers/">浏览全部问答 ↗</a></div>'
        + topics + '</section>'
    )
    update_discovery_html(public, "index.html", "faq-home-discovery", home)
    update_discovery_markdown(public, "index.md", "faq-topic-discovery",
                              "## 按工具阅读常见问题\n\n" + topic_md)
    ai = ('<section class="guide-body" id="faq-ai-discovery"><h2>常见问题与官方参考</h2>'
          '<p>按工具阅读已审核的答案、来源和资料核对日期。'
          '<a href="/answers/">浏览全部常见问题</a></p>' + topics + '</section>')
    update_discovery_html(public, "ai/index.html", "faq-ai-discovery", ai, after_heading=True)
    update_discovery_markdown(public, "ai/index.md", "faq-topic-discovery",
                              "## 按工具阅读常见问题\n\n" + topic_md)
    for slug, entities in GUIDE_ENTITIES.items():
        chosen = guide_answers(entries, entities)
        if not chosen:
            update_discovery_html(public, "guides/" + slug + ".html", "faq-guide-discovery", "")
            update_discovery_markdown(public, "guides/" + slug + ".md", "faq-guide-discovery", "")
            continue
        links = '<ul>' + "".join(
            f'<li><a href="{canonical_route(entry)}">{html.escape(title(entry))}</a>'
            f'<p>{html.escape(entry["short_answer"])}</p></li>' for entry in chosen
        ) + '</ul>'
        block = ('<section class="guide-body" id="faq-guide-discovery">'
                 '<h2>相关问题与官方参考</h2>' + links + '</section>')
        update_discovery_html(public, "guides/" + slug + ".html", "faq-guide-discovery", block)
        markdown = "## 相关问题与官方参考\n\n" + "\n\n".join(
            f'### [{mdtext(title(entry))}]({SITE}{canonical_route(entry)})\n\n'
            + mdtext(entry["short_answer"]) for entry in chosen
        )
        update_discovery_markdown(public, "guides/" + slug + ".md", "faq-guide-discovery", markdown)
    return [relative for relative in ("index.html", "ai/index.html",
            *("guides/" + slug + ".html" for slug, entities in GUIDE_ENTITIES.items()
              if guide_answers(entries, entities)))
            if (public / relative).is_file()]


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
    categories = {entity: canonical_entries(items) for entity, items in categories.items()}
    dates = {SITE + route(e): e["checked_at_utc"] for e in entries if e["faq_id"] == e["representative"]}
    newest = max((e["checked_at_utc"] for e in entries), default=None)
    names = {entity: GENERIC_NAMES.get(entity) or (aliases.get(entity) or [entity])[0] for entity in categories}
    for entity in sorted(categories):
        path = "/answers/entity/" + entity + "/"
        heading = names[entity] + "常见问题"
        items = sorted(categories[entity], key=lambda e: (e["intent"], title(e), e["faq_id"]))
        cards = "".join(category_answer(entry) for entry in items)
        body = f'<main id="main" class="wrap guide-main"><nav class="breadcrumbs"><a href="/answers/">常见问题</a></nav><h1>{html.escape(heading)}</h1><p class="guide-summary">直接阅读相关问题的审核答案，沿每条来源核对资料；问题标题链接到独立答案。</p><div class="guide-body">{cards}</div></main>'
        write(public, path.strip("/") + "/index.html", structured_html(page(heading + " | Fanqiang Guide", heading, path, body, [{"@type": "CollectionPage", "name": heading, "url": SITE + path}], path + "index.md")))
        write(public, path.strip("/") + "/index.md", "# " + mdtext(heading) + "\n\n" + "\n\n".join(category_markdown(entry) for entry in items) + "\n\n[全部常见问题](" + SITE + "/answers/)")
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
    discovery = {
        "llms.txt": "- [常见问题与官方参考](" + SITE + "/answers/)：按软件与设备分类的中文答案，每页附官方来源、核对日期和 Markdown 阅读版本。",
        "ai/index.md": "- [常见问题与官方参考](" + SITE + "/answers/)：按软件与设备阅读答案及官方参考资料。",
        "index.md": "## 翻墙与科学上网常见问题\n\n[按软件、设备和需求阅读答案](" + SITE + "/answers/)；每页保留官方参考资料和相关问题。",
    }
    for name, entry in discovery.items():
        previous = (public / name).read_text(encoding="utf-8")
        if SITE + "/answers/" not in previous:
            write(public, name, previous.rstrip() + "\n\n" + entry)
    changed_paths = add_answer_discovery(public, entries, categories, names)
    write(public, "llms-full.txt", (public / "ai/index.md").read_text(encoding="utf-8"))
    catalog = public / ".well-known/ai-catalog.json"
    obj = json.loads(catalog.read_text(encoding="utf-8"))
    identifier = "urn:air:fanqiang.guide:resource:answers"
    obj["entries"] = [e for e in obj["entries"] if e.get("identifier") != identifier] + [{"identifier": identifier, "displayName": heading, "type": "text/html", "url": SITE + "/answers/"}]
    write(public, ".well-known/ai-catalog.json", json.dumps(obj, ensure_ascii=False, indent=2))
    changed_paths += ["answers/index.html"] + [
        "answers/entity/" + entity + "/index.html" for entity in sorted(categories)
    ]
    normalize_sitemaps(public, changed_paths=changed_paths)
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
    from research_pages import build_research_pages, add_research_discovery
    build_research_pages(directory / "public", directory.parents[1] / "research/publications.json",
                         base["page"])
    base["inject_ga4_into_final_html"]()
    guard = runpy.run_path(str(directory.parent / "worker/frontend/patch_external_browser.py"))["INJECTION"]
    for target in [*(directory / "public/answers").rglob("*.html"),
                   *(directory / "public/research").rglob("*.html")]:
        content = target.read_text(encoding="utf-8")
        if "external-browser-v1.0.js" not in content:
            write(directory / "public", target.relative_to(directory / "public").as_posix(), content.replace("<head>", "<head>" + guard, 1))
    from reader_layout import apply_reader_layout
    apply_reader_layout(directory / "public", base["header"](), base["footer"]())
    add_research_discovery(directory / "public")
    from guide_research_links import add_ai_method_reports, load_report_index
    add_ai_method_reports(directory / "public", load_report_index(directory.parents[1] / "research/publications.json"))
    manifest = {}
    for target in sorted((directory / "public").rglob("*")):
        if target.is_file() and target.suffix != ".gz":
            relative = target.relative_to(directory / "public").as_posix()
            manifest[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
            if target.suffix in (".html", ".md", ".json", ".txt", ".xml") or target.with_name(target.name + ".gz").exists():
                target.with_name(target.name + ".gz").write_bytes(gzip.compress(target.read_bytes(), mtime=0))
    (directory / "release-manifest-v1.4-2026-09-13.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
