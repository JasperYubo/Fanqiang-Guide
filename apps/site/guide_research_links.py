"""Attach authored method reports to the guides that use those methods.

The reports explain a method; linking them never promotes a device to tested.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path

SITE = "https://fanqiang.guide"
GUIDE_REPORTS = {
    "subscription-conversion": ("subscription-semantics",),
    "shadowrocket-qr": ("subscription-semantics",),
    "airport-subscription-nodes": ("subscription-semantics",),
    "client-downloads": ("device-setup-protocol", "shared-network-validation"),
    "router-guide": ("shared-network-validation", "device-setup-protocol", "router-package-matching"),
    "openwrt-tools": ("shared-network-validation", "device-setup-protocol"),
    "asus-merlin": ("router-package-matching",),
    "proxy-cores": ("device-setup-protocol", "local-diagnostics-consent"),
}
AI_REPORTS = ("device-setup-protocol", "shared-network-validation")
SCOPES = {
    "subscription-semantics": "区分二维码载体、订阅与配置格式，检查转换前后的字段、规则和 DNS 语义。",
    "device-setup-protocol": "按环境识别、安装配置、排错与分层验证记录执行证据。",
    "shared-network-validation": "分别验证手机本机与热点下游设备，检查出口、DNS、IPv6、断线和重连。",
    "router-package-matching": "按具体型号、硬件修订、固件分支与软件中心匹配平台包和 full / lite。",
    "local-diagnostics-consent": "在本地采集必要证据、预览脱敏内容，再由用户主动提交诊断报告。",
}
BOUNDARY = "这些报告说明检查与验证方法；具体版本支持仍以项目官方资料为准，设备覆盖范围和可用性需要在目标环境分别验证。"
CORE_BOUNDARY = "以下报告支持分层验证与诊断方法；不能据此认定 TUN 覆盖所有应用、热点下游或全部流量。"
AI_START = "<!-- guide-method-reports:start -->"
AI_END = "<!-- guide-method-reports:end -->"


def load_report_index(path):
    records = json.loads(Path(path).read_text(encoding="utf-8"))["publications"]
    return {item["slug"]: item for item in records}


def report_sources(slugs, records):
    sources = []
    for slug in slugs:
        item = records[slug]
        doi = item["doi"]
        if not doi.startswith("10.") or "/" not in doi:
            raise ValueError("Method report requires a reserved DOI")
        sources.append({"label": item["title"], "url": SITE + "/research/" + slug + "/",
                        "doi": doi, "role": "method_reference",
                        "scope": SCOPES[slug], "verification_boundary": BOUNDARY})
    return sources


def guide_sources(slug, records):
    return report_sources(GUIDE_REPORTS.get(slug, ()), records)


def method_reports_html(sources, *, proxy_cores=False):
    if not sources:
        return ""
    esc = lambda value: escape(str(value), quote=True)
    rows = []
    for source in sources:
        route = source["url"].removeprefix(SITE)
        rows.append('<li><a href="' + esc(route) + '">' + esc(source["label"]) + '</a>'
                    '<p>' + esc(source["scope"]) + '</p><p class="sources">'
                    '<a href="https://doi.org/' + esc(source["doi"]) + '">DOI: ' + esc(source["doi"]) + '</a>'
                    ' · <a href="' + esc(route) + '#citation">复制 APA / BibTeX 引用</a></p></li>')
    return ('<section id="method-reports" aria-labelledby="method-reports-title">'
            '<h2 id="method-reports-title">研究依据 / 方法报告</h2><p>'
            + esc(CORE_BOUNDARY if proxy_cores else BOUNDARY)
            + '</p><ul>' + "".join(rows) + '</ul></section>')


def method_reports_markdown(sources, *, proxy_cores=False):
    if not sources:
        return ""
    lines = ["## 研究依据 / 方法报告", "", CORE_BOUNDARY if proxy_cores else BOUNDARY, ""]
    for source in sources:
        lines += ["### [" + source["label"] + "](" + source["url"] + ")", "", source["scope"], "",
                  "DOI：[ " + source["doi"] + " ](https://doi.org/" + source["doi"] + ") · "
                  "[复制 APA / BibTeX 引用](" + source["url"] + "#citation)", ""]
    return "\n".join(lines)


def add_ai_method_reports(public, records):
    """Run after the AI reader layout so the entry stays outside its closed library."""
    public = Path(public)
    sources = report_sources(AI_REPORTS, records)
    html_path, md_path = public / "ai/index.html", public / "ai/index.md"
    raw = html_path.read_text(encoding="utf-8")
    block = AI_START + '<div class="guide-body">' + method_reports_html(sources) + '</div>' + AI_END
    if AI_START in raw:
        start, end = raw.index(AI_START), raw.index(AI_END) + len(AI_END)
        raw = raw[:start] + block + raw[end:]
    elif '<!-- research-discovery:start -->' in raw:
        raw = raw.replace('<!-- research-discovery:start -->', block + '<!-- research-discovery:start -->', 1)
    elif raw.count("</main>") == 1:
        raw = raw.replace("</main>", block + "</main>", 1)
    else:
        raise ValueError("AI method reports require one main element")
    html_path.write_text(raw, encoding="utf-8")
    markdown = md_path.read_text(encoding="utf-8")
    md_block = AI_START + "\n" + method_reports_markdown(sources) + "\n" + AI_END
    if AI_START in markdown:
        start, end = markdown.index(AI_START), markdown.index(AI_END) + len(AI_END)
        markdown = markdown[:start] + md_block + markdown[end:]
    else:
        markdown = markdown.rstrip() + "\n\n" + md_block + "\n"
    md_path.write_text(markdown, encoding="utf-8")
    (public / "llms-full.txt").write_text(markdown, encoding="utf-8")
