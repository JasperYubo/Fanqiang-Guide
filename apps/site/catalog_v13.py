"""Render the human catalog from the unchanged, public source snapshots."""

from collections import Counter
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


ORIGIN = "https://fanqiang.guide"
VERIFY = {
    "primary_reviewed": "已核对第一方资料",
    "reference_only": "仅参考目录线索",
    "historical_reference": "历史资料",
}
SUPPORT = {
    "current_listed": "来源列表列为支持",
    "explicitly_unsupported": "来源明确不支持",
    "source_only": "仅来源记录，支持未确认",
}
FIRMWARE = {
    "asuswrt-merlin": "Asuswrt-Merlin",
    "asuswrt-merlin-gnuton": "Asuswrt-Merlin GNUton",
}
FIELDS = {
    "name": "名称", "kind": "分类", "summary": "简介", "platforms": "平台",
    "repository": "代码仓库", "official_urls": "项目入口", "ecosystems": "相关生态",
    "relations": "项目关联", "aliases": "别名", "tags": "标签",
    "compatibility": "兼容性说明", "maintenance": "维护状态",
}


def h(value):
    return escape(str(value), quote=True)


def text(value):
    if value is None:
        return "未记录"
    if isinstance(value, list):
        return "、".join(text(v) for v in value) if value else "未记录"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def md_text(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def link(label, url):
    parts = urlsplit(str(url or ""))
    if parts.scheme in ("http", "https") and parts.netloc and not parts.username:
        return f'<a href="{h(url)}">{h(label)}</a>'
    return h(label)


def md_link(label, url):
    parts = urlsplit(str(url or ""))
    if parts.scheme in ("http", "https") and parts.netloc and not parts.username:
        safe = str(url).replace("<", "%3C").replace(">", "%3E")
        return f'[{md_text(label)}](<{safe}>)'
    return md_text(label)


def stable_id(prefix, value):
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError(f"Unsupported record identifier: {value!r}")
    return f"{prefix}-{value}"


def flatten(value):
    if isinstance(value, dict):
        return " ".join(flatten(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(flatten(v) for v in value)
    return "" if value is None else str(value)


def pair(label, value):
    return f'<p><strong>{h(label)}：</strong>{h(value)}</p>', f'- {md_text(label)}：{md_text(value)}'


def links_pair(label, urls):
    urls = list(dict.fromkeys(u for u in urls if u))
    if not urls:
        return "", ""
    return (
        f'<div class="catalog-source-group"><p><strong>{h(label)}</strong></p><ul>'
        + "".join(f'<li>{link(u, u)}</li>' for u in urls) + '</ul></div>',
        f'- {md_text(label)}：' + "；".join(md_link(u, u) for u in urls),
    )


def source_note(source, updated_at):
    label = "本页资料快照"
    url = source.get("source_url")
    when = source.get("snapshot_date") or updated_at or "未记录"
    return (
        f'<p class="catalog-snapshot">资料快照日期：{h(when)} · {link(label, url)}。日期表示资料整理时间，不代表所有项目仍可用。</p>',
        f'资料快照日期：{md_text(when)} · {md_link(label, url)}。日期表示资料整理时间，不代表所有项目仍可用。',
    )


def schemas(title, description, path, count):
    url = ORIGIN + path
    return [
        {"@type": "CollectionPage", "@id": url + "#page", "url": url,
         "name": title, "description": description, "inLanguage": "zh-CN",
         "mainEntity": {"@type": "ItemList", "numberOfItems": count}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "首页", "item": ORIGIN + "/"},
            {"@type": "ListItem", "position": 2, "name": "工具指南", "item": ORIGIN + "/guides/index.html"},
            {"@type": "ListItem", "position": 3, "name": title, "item": url},
        ]},
    ]


def intro(title, description, source, updated_at, links):
    hs, ms = source_note(source, updated_at)
    navigation = "".join(f'<a class="button button-secondary" href="{h(path)}">{h(label)}</a>' for label, path in links)
    html = f'''<nav class="breadcrumbs" aria-label="面包屑"><a href="/">首页</a><span aria-hidden="true">/</span><a href="/guides/index.html">工具指南</a><span aria-hidden="true">/</span><span>{h(title)}</span></nav>
<header class="guide-header"><p class="eyebrow">FANQIANG GUIDE</p><h1>{h(title)}</h1><p class="guide-summary">{h(description)}</p>{hs}<nav class="hero-actions" aria-label="相关资料">{navigation}</nav></header>'''
    markdown = f'# {title}\n\n{description}\n\n{ms}\n\n' + " · ".join(md_link(label, ORIGIN + path) for label, path in links) + "\n\n"
    return html, markdown


def controls(prefix, search_label, placeholder, selectors, total, unit):
    selects = ""
    for parameter, label, options in selectors:
        selects += f'<div class="catalog-field"><label for="{prefix}-{parameter}">{h(label)}</label><select id="{prefix}-{parameter}" data-filter="{h(parameter)}"><option value="">全部{h(label)}</option>'
        selects += "".join(f'<option value="{h(value)}">{h(name)}</option>' for value, name in options)
        selects += '</select></div>'
    return f'''<div class="catalog-controls" role="search" aria-label="{h(search_label)}">
<div class="catalog-field catalog-query"><label for="{prefix}-query">{h(search_label)}</label><input id="{prefix}-query" type="search" name="q" data-query placeholder="{h(placeholder)}" autocomplete="off" aria-describedby="{prefix}-search-help" aria-controls="{prefix}-results"><p id="{prefix}-search-help" class="catalog-help">不区分大小写；多个关键词用空格分开。筛选只影响当前页面显示。</p></div>
{selects}<button type="button" class="button button-secondary catalog-clear" data-clear>清除筛选</button></div>
<p class="catalog-count" id="{prefix}-count" role="status" aria-live="polite" aria-atomic="true" data-count>显示 {total} / {total} {unit}</p>
<p class="catalog-empty" data-empty hidden>没有找到符合条件的记录。请缩短关键词或清除筛选；未找到不代表不支持。</p>
<noscript><p class="catalog-noscript">当前浏览器未启用 JavaScript，下面仍显示全部资料。可使用浏览器的“查找”功能查找名称或完整型号。</p></noscript>'''


def render_record(item, categories):
    ident = stable_id("tool", item["id"])
    verification = item.get("verification") or {}
    status = verification.get("status", "unknown")
    label = VERIFY.get(status, "核对范围未确认")
    kind = item.get("kind", "unknown")
    category = categories.get(kind, kind)
    fields = [FIELDS.get(k, k) for k in verification.get("reviewed_fields", [])]
    visible = []
    if item.get("aliases"):
        visible.append(("别名", text(item["aliases"])))
    visible.append(("平台", text(item.get("platforms"))))
    if item.get("ecosystems"):
        visible.append(("相关生态", text(item["ecosystems"])))
    if item.get("tags"):
        visible.append(("资料标签", text(item["tags"])))
    visible.append(("资料核对日期", verification.get("checked_at") or "未记录"))
    visible.append(("已核对字段", "、".join(fields) if fields else "来源未逐项列出；以核对说明为准"))
    if verification.get("notes"):
        visible.append(("核对说明", verification["notes"]))
    compatibility = item.get("compatibility") or {}
    if compatibility.get("supported_models") is not None:
        visible.append(("资料记载型号", text(compatibility["supported_models"])))
    if compatibility.get("notes"):
        visible.append(("兼容性说明", compatibility["notes"]))
    visible_pairs = [pair(label, value) for label, value in visible]
    extra = []
    maintenance = item.get("maintenance") or {}
    maintenance_labels = {"unknown": "未核验", "archived": "来源记录为已归档", "active": "来源记录为活跃", "unmaintained": "来源记录为停止维护"}
    if maintenance.get("status"):
        extra.append(pair("维护记录", maintenance_labels.get(maintenance["status"], maintenance["status"])))
    extra.append(links_pair("项目入口（核对范围见上方）", item.get("official_urls", [])))
    extra.append(links_pair("代码仓库", [item.get("repository")]))
    extra.append(links_pair("第一方核对依据", verification.get("evidence_urls", [])))
    extra.append(links_pair("参考来源（不等于独立核验）", item.get("reference_sources", [])))
    extra.append(links_pair("维护记录依据", [maintenance.get("evidence_url")]))
    for relation in item.get("relations", []):
        value = f'{relation.get("predicate", "关联")} → {relation.get("target_name", "未记录")}'
        if relation.get("verification_status"):
            value += f'；资料状态：{relation["verification_status"]}'
        extra.append(pair("资料中的关联", value))
        extra.append(links_pair("关联来源", [relation.get("evidence_url")]))
    sources = [("条目原始资料", item.get("source_url")), ("固定版本资料", item.get("source_snapshot_url"))]
    source_h = " · ".join(link(label, url) for label, url in sources if url)
    source_m = " · ".join(md_link(label, url) for label, url in sources if url)
    html = f'''<article class="catalog-record" id="{h(ident)}" data-record data-category="{h(kind)}" data-status="{h(status)}" data-search="{h(flatten(item))}">
<div class="catalog-record-top"><span>{h(category)}</span><span class="catalog-badge">{h(label)}</span></div><h3><a href="#{h(ident)}">{h(item['name'])}</a></h3>
<p class="catalog-summary">{h(item.get('summary', '来源未提供简介。'))}</p>
<div class="catalog-facts">{''.join(a for a, b in visible_pairs)}</div>
<p class="catalog-origin">{source_h}</p><details><summary>来源与关联资料</summary><div class="catalog-details">{''.join(a for a, b in extra)}</div></details></article>'''
    markdown = f'<a id="{ident}"></a>\n\n### {md_text(item["name"])}\n\n分类：{md_text(category)} · {md_text(label)}\n\n{md_text(item.get("summary", "来源未提供简介。"))}\n\n'
    markdown += "\n".join(b for a, b in visible_pairs + extra if b) + f'\n\n{source_m}\n\n'
    return html, markdown


def render_library(data, category_data):
    items = data["items"]
    category_items = category_data["items"]
    categories = {row["kind"]: row["name"] for row in category_items}
    kinds = list(dict.fromkeys([row["kind"] for row in category_items] + [item["kind"] for item in items]))
    title = "翻墙与科学上网工具目录"
    description = f'按名称、平台线索、类别与核对范围查找 {len(items)} 条公开资料。已核对第一方资料仅覆盖条目列出的字段，不表示已安装、实测、安全审计或当前可用。'
    html, markdown = intro(title, description, data.get("source", {}), data.get("updated_at"), [("客户端下载与选择", "/guides/client-downloads.html"), ("华硕梅林型号表", "/guides/merlin-models.html"), ("Markdown 资料", "/guides/library.md")])
    html += '<div class="catalog-browser" data-catalog data-unit="条资料">'
    options = [(kind, categories.get(kind, kind)) for kind in kinds]
    statuses = [(value, VERIFY.get(value, "核对范围未确认")) for value in dict.fromkeys(x["verification"]["status"] for x in items)]
    html += controls("library", "搜索工具名称、别名或资料内容", "例如 v2rayN、Android、OpenWrt", [("category", "分类", options), ("status", "核对状态", statuses)], len(items), "条资料")
    html += '<nav class="catalog-category-nav" aria-label="分类目录">' + "".join(f'<a href="#category-{h(kind)}">{h(categories.get(kind, kind))}</a>' for kind in kinds) + '</nav><div id="library-results">'
    for kind in kinds:
        subset = [item for item in items if item["kind"] == kind]
        if not subset:
            continue
        label = categories.get(kind, kind)
        html += f'<section class="catalog-group" id="category-{h(kind)}" data-group><h2>{h(label)} <span class="catalog-group-total">{len(subset)} 条</span></h2><div class="catalog-grid">'
        markdown += f'## {label}\n\n'
        for item in subset:
            record_html, record_md = render_record(item, categories)
            html += record_html
            markdown += record_md
        html += '</div></section>'
    html += '</div></div>'
    return title, description, html, markdown


def render_models(data):
    items = data["items"]
    title = "华硕梅林固件支持型号对照表"
    description = f'查找 {len(items)} 条完整型号记录，区分来源列为支持、来源明确不支持与仅来源记录。请逐字核对型号中的 V1、V2、PRO 等标识；固件支持、插件兼容与实际刷机结果分别判断。'
    html, markdown = intro(title, description, data.get("source", {}), data.get("updated_at"), [("梅林固件选择指南", "/guides/asus-merlin.html"), ("全部工具目录", "/guides/library.html"), ("Markdown 型号表", "/guides/merlin-models.md")])
    count = Counter(item.get("support_claim", "source_only") for item in items)
    tested = sum(item.get("tested") is True for item in items)
    note = f'本页来源列为支持 {count["current_listed"]} 条，明确不支持 {count["explicitly_unsupported"]} 条，其他来源记录 {len(items) - count["current_listed"] - count["explicitly_unsupported"]} 条；已实测记录 {tested} 条。支持结论限定于每行固件分支与所列来源，不代表插件已经兼容。'
    html += f'<p class="catalog-boundary">{h(note)}</p>'
    markdown += note + '\n\n'
    html += '<div class="catalog-browser" data-catalog data-unit="条型号记录">'
    firmware_options = [(value, FIRMWARE.get(value, value)) for value in dict.fromkeys(item["firmware_entity_id"] for item in items)]
    support_options = [(value, SUPPORT.get(value, "仅来源记录，支持未确认")) for value in dict.fromkeys(item.get("support_claim", "source_only") for item in items)]
    html += controls("models", "搜索完整型号或修订标识", "例如 RT-AX58U V2、RT-AX86U PRO", [("firmware", "固件分支", firmware_options), ("status", "来源支持状态", support_options)], len(items), "条型号记录")
    html += '<p class="catalog-help">窄屏可在表格区域内横向滑动，查看来源与限定说明。</p><div class="catalog-table-region" role="region" aria-label="梅林完整型号与来源对照表，可横向滚动" tabindex="0"><table id="models-results" class="catalog-model-table"><caption>完整型号、固件分支、来源结论与实测状态</caption><thead><tr><th scope="col">完整型号</th><th scope="col">固件分支</th><th scope="col">来源支持状态</th><th scope="col">实测</th><th scope="col">来源与限定说明</th></tr></thead><tbody>'
    markdown += '| 完整型号 | 固件分支 | 来源支持状态 | 实测 | 来源与限定说明 |\n|---|---|---|---|---|\n'
    bad_notes = 0
    for item in items:
        ident = stable_id("model", item["id"])
        claim = item.get("support_claim", "source_only")
        support = SUPPORT.get(claim, "仅来源记录，支持未确认")
        firmware = FIRMWARE.get(item["firmware_entity_id"], item["firmware_entity_id"])
        test_label = "资料记录为已实测" if item.get("tested") is True else "未实测" if item.get("tested") is False else "未提供实测记录"
        revision = item.get("hardware_revision") or "来源未单列硬件修订"
        notes = item.get("notes") or "来源未提供附加说明；请以原始来源为准。"
        if "\ufffd" in notes:
            bad_notes += 1
            notes = "原始说明含无法解码的字符，请核对所列来源；本行仅展示已有结构化记录，未补推支持或兼容结论。"
        source = item.get("source_url")
        checked = item.get("checked_at") or "未记录"
        model_search = flatten([item["model_exact"], item.get("hardware_revision"), item.get("vendor"), firmware])
        html += f'''<tr id="{h(ident)}" data-record data-firmware="{h(item['firmware_entity_id'])}" data-status="{h(claim)}" data-search="{h(model_search)}"><th scope="row"><a href="#{h(ident)}">{h(item['model_exact'])}</a><span class="catalog-model-sub">{h(item.get('vendor', '未记录厂商'))} · {h(revision)}</span></th><td>{h(firmware)}</td><td><span class="catalog-badge">{h(support)}</span></td><td>{h(test_label)}</td><td>{link('查看原始来源', source)}<p class="catalog-model-date">资料核对日期：{h(checked)}</p><p>{h(notes)}</p></td></tr>'''
        model_md = f'<a id="{ident}"></a>{md_text(item["model_exact"])}<br>{md_text(item.get("vendor", "未记录厂商"))} · {md_text(revision)}'
        detail_md = f'{md_link("查看原始来源", source)}<br>资料核对日期：{md_text(checked)}<br>{md_text(notes)}'
        markdown += f'| {model_md} | {md_text(firmware)} | {md_text(support)} | {md_text(test_label)} | {detail_md} |\n'
    html += '</tbody></table></div></div>'
    return title, description, html, markdown, bad_notes


CATALOG_JS = r'''"use strict";
(() => {
  const normalize = value => String(value || "").normalize("NFKC").toLocaleLowerCase().trim();
  for (const browser of document.querySelectorAll("[data-catalog]")) {
    const query = browser.querySelector("[data-query]");
    const filters = Array.from(browser.querySelectorAll("[data-filter]"));
    const records = Array.from(browser.querySelectorAll("[data-record]"));
    const groups = Array.from(browser.querySelectorAll("[data-group]"));
    const indexed = records.map(node => ({node, text: normalize(node.dataset.search)}));
    const count = browser.querySelector("[data-count]");
    const empty = browser.querySelector("[data-empty]");
    const params = new URLSearchParams(window.location.search);
    query.value = params.get("q") || "";
    for (const filter of filters) {
      const supplied = params.get(filter.dataset.filter);
      if (supplied !== null && Array.from(filter.options).some(option => option.value === supplied)) filter.value = supplied;
    }
    function apply() {
      const words = normalize(query.value).split(/\s+/).filter(Boolean);
      let shown = 0;
      for (const {node, text} of indexed) {
        const matches = words.every(word => text.includes(word)) && filters.every(filter => !filter.value || node.dataset[filter.dataset.filter] === filter.value);
        node.hidden = !matches;
        if (matches) shown++;
      }
      for (const group of groups) group.hidden = !Array.from(group.querySelectorAll("[data-record]")).some(node => !node.hidden);
      count.textContent = `显示 ${shown} / ${records.length} ${browser.dataset.unit}`;
      empty.hidden = shown !== 0;
    }
    query.addEventListener("input", apply);
    for (const filter of filters) filter.addEventListener("change", apply);
    browser.querySelector("[data-clear]").addEventListener("click", () => {
      query.value = "";
      for (const filter of filters) filter.value = "";
      apply();
      query.focus();
    });
    for (const anchor of browser.querySelectorAll(".catalog-category-nav a")) {
      anchor.addEventListener("click", () => {
        query.value = "";
        for (const filter of filters) filter.value = "";
        apply();
      });
    }
    apply();
  }
})();
'''


CATALOG_CSS = r'''
.catalog-main{min-width:0}.catalog-main a:not(.button){color:var(--blue)}
.catalog-snapshot{font-size:12px;color:var(--muted);margin-top:18px;overflow-wrap:anywhere}
.catalog-controls{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-end;padding:24px;background:#fff;border:1px solid var(--line);border-radius:12px}
.catalog-field{min-width:150px;flex:1}.catalog-query{flex:3;min-width:min(290px,100%)}
.catalog-field label{display:block;font-size:13px;font-weight:650;margin-bottom:7px}
.catalog-field input,.catalog-field select{font:inherit;font-size:14px;color:var(--ink);width:100%;min-width:0;max-width:100%;min-height:46px;background:#fff;border:1px solid #aab8cc;border-radius:7px;padding:9px 11px}
.catalog-field input:focus-visible,.catalog-field select:focus-visible,.catalog-clear:focus-visible,.catalog-table-region:focus-visible,details summary:focus-visible{outline:3px solid #7095ff;outline-offset:3px}
.catalog-help{font-size:12px;color:var(--muted);margin-top:8px;line-height:1.8}.catalog-clear{cursor:pointer;min-height:46px;align-self:center}
.catalog-count{font-size:14px;font-weight:650;margin:19px 0 15px}.catalog-empty,.catalog-noscript,.catalog-boundary{padding:17px 20px;border:1px solid #dce5fa;background:#eef3ff;border-radius:9px;margin:18px 0;font-size:14px;line-height:1.9}
.catalog-category-nav{display:flex;flex-wrap:wrap;gap:8px 16px;font-size:12px;margin-bottom:26px}.catalog-category-nav a{padding-block:4px}
.catalog-group{margin:0 0 34px}.catalog-group h2{font-size:23px;margin:0 0 17px}.catalog-group-total{font-size:12px;font-weight:450;color:var(--muted);margin-left:8px}
.catalog-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
.catalog-record{min-width:0;padding:24px;border:1px solid var(--line);border-radius:12px;background:#fff;overflow-wrap:anywhere;scroll-margin-top:25px}
.catalog-record:target,.catalog-model-table tr:target{outline:3px solid #7095ff;outline-offset:2px}
.catalog-record-top{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:11px;color:var(--muted);margin-bottom:12px;flex-wrap:wrap}
.catalog-badge{display:inline-block;border:1px solid #dce3ef;border-radius:5px;padding:3px 7px;background:#f5f7fb;color:#4a5e7a;font-size:11px;line-height:1.6}
.catalog-record h3{font-size:21px;margin-bottom:12px}.catalog-summary{font-size:14px;line-height:1.95;margin-bottom:17px}
.catalog-facts{font-size:12px;line-height:1.9;color:#52647e}.catalog-facts p+p{margin-top:8px}.catalog-facts strong{font-weight:650}
.catalog-origin{margin-top:16px;font-size:12px;line-height:1.9}.catalog-record details{margin-top:16px;border-top:1px solid var(--line);padding-top:12px;font-size:12px;line-height:1.85}
.catalog-record summary{cursor:pointer;color:#436496;padding:3px 0}.catalog-details{padding-top:12px}.catalog-details>p{margin-bottom:9px}.catalog-source-group{margin-top:12px}.catalog-source-group ul{padding-left:19px;margin:5px 0 0}.catalog-source-group li{margin-top:5px}
.catalog-table-region{max-width:100%;min-width:0;overflow-x:auto;margin-top:13px;border:1px solid var(--line);border-radius:12px;background:#fff}
.catalog-model-table{width:100%;min-width:1000px;border-collapse:collapse;text-align:left;font-size:13px;line-height:1.85}
.catalog-model-table caption{text-align:left;padding:17px 20px;font-weight:650;font-size:14px;background:#f1f5fc}
.catalog-model-table th,.catalog-model-table td{vertical-align:top;padding:16px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
.catalog-model-table thead th{font-size:12px;background:#f8faff}.catalog-model-table tbody th{width:20%;font-size:14px;font-weight:650}.catalog-model-table td:nth-child(2){width:16%}.catalog-model-table td:nth-child(3){width:16%}.catalog-model-table td:nth-child(4){width:8%}.catalog-model-table td:last-child{width:40%}
.catalog-model-sub{display:block;font-size:11px;font-weight:400;line-height:1.8;color:var(--muted);margin-top:7px}.catalog-model-date{font-size:11px;color:var(--muted);margin:6px 0}
.catalog-browser [hidden]{display:none!important}
@media(max-width:760px){.catalog-controls{padding:19px;gap:14px}.catalog-query{flex-basis:100%}.catalog-field{min-width:0;flex-basis:calc(50% - 7px)}.catalog-clear{width:100%}.catalog-grid{grid-template-columns:1fr}.catalog-record{padding:21px}.catalog-record h3{font-size:20px}.catalog-main .hero-actions{gap:9px}.catalog-main .hero-actions .button{padding:9px 12px;gap:8px}.catalog-group h2{font-size:21px}.catalog-category-nav{gap:7px 14px}}
'''


def build_catalog(P: Path, page_renderer) -> dict:
    """P is the public output directory; source data are never modified."""
    P = Path(P)
    data = json.loads((P / "data/library.json").read_text(encoding="utf-8"))
    model_data = json.loads((P / "data/merlin-models.json").read_text(encoding="utf-8"))
    category_data = json.loads((P / "data/categories.json").read_text(encoding="utf-8"))
    for label, dataset in (("library", data), ("models", model_data)):
        ids = [row["id"] for row in dataset["items"]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate identifiers in {label}")
        for ident in ids:
            stable_id(label, ident)
    library = render_library(data, category_data)
    models = render_models(model_data)
    (P / "guides").mkdir(parents=True, exist_ok=True)
    (P / "assets").mkdir(parents=True, exist_ok=True)
    urls = []
    for slug, rendered, count in (("library", library, len(data["items"])), ("merlin-models", models, len(model_data["items"]))):
        title, description, body, markdown = rendered[:4]
        path = f"/guides/{slug}.html"
        markdown_path = f"/guides/{slug}.md"
        page = page_renderer(title, description, path, f'<main id="main" class="wrap guide-main catalog-main">{body}</main>', schemas(title, description, path, count), markdown_path)
        if "</head>" not in page:
            raise ValueError("page_renderer must return complete HTML with a head element")
        assets = '<link rel="stylesheet" href="/assets/catalog-v1.3.css"><script defer src="/assets/catalog-v1.3.js"></script>'
        page = page.replace("</head>", assets + "</head>", 1)
        (P / path.lstrip("/")).write_text(page, encoding="utf-8")
        (P / markdown_path.lstrip("/")).write_text(markdown, encoding="utf-8")
        urls.append(ORIGIN + path)
    (P / "assets/catalog-v1.3.js").write_text(CATALOG_JS, encoding="utf-8")
    (P / "assets/catalog-v1.3.css").write_text(CATALOG_CSS, encoding="utf-8")
    return {"urls": urls, "counts": {"library": len(data["items"]), "merlin_models": len(model_data["items"]), "categories": len(category_data["items"]), "verification": dict(Counter(row.get("verification", {}).get("status", "unknown") for row in data["items"])), "support_claims": dict(Counter(row.get("support_claim", "source_only") for row in model_data["items"])), "tested_models": sum(row.get("tested") is True for row in model_data["items"]), "undecodable_model_notes": models[4]}}
