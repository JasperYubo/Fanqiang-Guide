"""Render the project's authored technical reports and citation metadata."""
from __future__ import annotations

from datetime import date
import gzip
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

SITE = "https://fanqiang.guide"
INDEX = SITE + "/research/"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
START = "<!-- research-discovery:start -->"
END = "<!-- research-discovery:end -->"
TYPES = {"technicalreport": "技术报告", "technicalnote": "技术说明"}


def https_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Research references must use public HTTPS URLs")
    return value


def validate_person(person):
    if not isinstance(person, dict) or not isinstance(person.get("name"), str) or not person["name"].strip():
        raise ValueError("Named people require an explicit name")
    if person.get("orcid") and not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", person["orcid"]):
        raise ValueError("Invalid ORCID")


def reference_authors(reference):
    """Keep the cited work's authors separate from this report's creators."""
    values = reference.get("authors", [])
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        raise ValueError("Reference authors must be text or a list")
    authors = []
    for value in values:
        name = value.get("name") if isinstance(value, dict) else value
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Reference authors require complete names")
        if name not in authors:
            authors.append(name)
    for person in reference.get("author_identifiers", []):
        validate_person(person)
    return authors


def reference_people(reference):
    # Bibliography text can abbreviate authors; structured identities cannot.
    def clean(name):
        return re.sub(r"(?:[,;]?\s*)et\s+al\.?\s*$", "", name, flags=re.I).strip(" ,;")
    def key(name):
        return tuple(sorted(re.findall(r"[^\W_]+", clean(name).casefold())))
    identifiers = {key(person["name"]): person for person in reference.get("author_identifiers", []) if person.get("orcid")}
    raw_names = [clean(part) for author in reference_authors(reference) for part in re.split(r"[;；]", author)]
    people, seen = [], set()
    for name in raw_names:
        ident = key(name)
        if not name or not ident or ident in seen:
            continue
        verified = identifiers.get(ident)
        if verified:
            value = {"@type": "Person", "name": verified["name"], "sameAs": "https://orcid.org/" + verified["orcid"]}
        elif "contributors" in name.casefold() or name.casefold() in {"ilang", "ilang inc.", "koolcenter"}:
            value = {"@type": "Organization", "name": name}
        elif "," in name or len(ident) >= 2:
            value = {"@type": "Person", "name": name}
        else:
            # An untyped single handle remains visible in the bibliography.
            continue
        seen.add(ident)
        people.append(value)
    for ident, person in identifiers.items():
        if ident not in seen:
            people.append({"@type": "Person", "name": person["name"], "sameAs": "https://orcid.org/" + person["orcid"]})
            seen.add(ident)
    return people


def person_html(person):
    name = escape(person["name"], quote=True)
    if person.get("orcid"):
        value = escape(person["orcid"], quote=True)
        return name + ' · <a href="https://orcid.org/' + value + '">ORCID ' + value + '</a>'
    return name


def reference_schema(reference):
    value = {"@type": "CreativeWork", "name": reference["title"], "url": reference["url"]}
    authors = reference_people(reference)
    if authors:
        value["author"] = authors
    if reference.get("year") is not None:
        value["datePublished"] = str(reference["year"])
    return value


def load_publications(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("publications"), list) or not data["publications"]:
        raise ValueError("A versioned research publication list is required")
    slugs, dois = set(), set()
    for item in data["publications"]:
        for name in ("slug", "title", "version", "publication_date", "doi", "record_url", "abstract"):
            if not isinstance(item.get(name), str) or not item[name].strip():
                raise ValueError("Missing research metadata: " + name)
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", item["slug"]) or item["slug"] in slugs:
            raise ValueError("Research slugs must be unique safe paths")
        slugs.add(item["slug"])
        if not re.fullmatch(r"10\.5281/zenodo\.[1-9][0-9]*", item["doi"]) or item["doi"] in dois:
            raise ValueError("Each report requires a unique production Zenodo DOI")
        dois.add(item["doi"])
        date.fromisoformat(item["publication_date"])
        https_url(item["record_url"])
        if item.get("type") not in TYPES:
            raise ValueError("Research records must have an explicit report type")
        if not item.get("creators"):
            raise ValueError("Research records require an author")
        for author in item["creators"]:
            if not isinstance(author.get("name"), str) or not author["name"].strip():
                raise ValueError("Research author name is required")
            if author.get("orcid") and not re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", author["orcid"]):
                raise ValueError("Invalid author ORCID")
        for advisor in item.get("advisors", []):
            validate_person(advisor)
            if advisor.get("role") != "学术顾问":
                raise ValueError("Advisors require an explicit report-scoped role")
        for material in item.get("materials", []):
            if not isinstance(material.get("title"), str) or not material["title"].strip():
                raise ValueError("Report materials require a title")
            https_url(material["url"])
            if material.get("description") is not None and not isinstance(material["description"], str):
                raise ValueError("Report material descriptions must be text")
        ids = {"abstract", "references", "citation", "related-publications", "materials"}
        if not item.get("sections"):
            raise ValueError("A full report body is required")
        for section in item["sections"]:
            ident = section.get("id", "")
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", ident) or ident in ids:
                raise ValueError("Report sections need unique safe identifiers")
            ids.add(ident)
            if not section.get("title") or not section.get("paragraphs"):
                raise ValueError("Report sections require a heading and paragraphs")
            if any(not isinstance(text, str) for text in section["paragraphs"] + section.get("items", [])):
                raise ValueError("Report body items must be text")
        ref_ids = set()
        for index, reference in enumerate(item.get("references", []), 1):
            ident = str(reference.get("id", index))
            if not re.fullmatch(r"[1-9][0-9]*", ident) or ident in ref_ids:
                raise ValueError("Reference identifiers must be unique positive numbers")
            ref_ids.add(ident)
            if not reference.get("title"):
                raise ValueError("Reference title required")
            https_url(reference["url"])
            reference_authors(reference)
            if reference.get("year") is not None and not re.fullmatch(r"[12][0-9]{3}", str(reference["year"])):
                raise ValueError("Reference publication years must have four digits")
        expected_pdf = "research/" + item["slug"] + "/paper.pdf"
        if item.get("pdf") not in (expected_pdf, "/" + expected_pdf):
            raise ValueError("Each report needs its canonical PDF path")
        pdf = Path(path).parent / "pdfs" / (item["slug"] + ".pdf")
        if not pdf.is_file() or not pdf.read_bytes().startswith(b"%PDF-"):
            raise ValueError("Report PDF is missing or invalid: " + item["slug"])
    by_slug = {item["slug"]: item for item in data["publications"]}
    for item in data["publications"]:
        seen = set()
        for related in item.get("related_publications", []):
            target = by_slug.get(related.get("slug"))
            if not target or target["slug"] == item["slug"] or target["slug"] in seen:
                raise ValueError("Related publications require distinct known report targets")
            if related.get("doi") != target["doi"] or related.get("relation") not in {"isSupplementedBy", "isSupplementTo"}:
                raise ValueError("Related publication DOI or relationship mismatch")
            related["title"] = target["title"]
            seen.add(target["slug"])
    return data["publications"]


def apa_author(name):
    if "," not in name:
        return name
    family, given = name.split(",", 1)
    return family.strip() + ", " + " ".join(part[0] + "." for part in given.strip().split() if part)


def bibtex_value(value):
    mapping = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
               "&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_"}
    return "".join(mapping.get(char, char) for char in value)


def citation_texts(item):
    author = " & ".join(apa_author(creator["name"]) for creator in item["creators"])
    year = item["publication_date"][:4]
    doi_url = "https://doi.org/" + item["doi"]
    kind = TYPES[item["type"]]
    apa = f'{author} ({year}). {item["title"]} (Version {item["version"]}) [{kind}]. Zenodo. {doi_url}'
    fields = {
        "author": " and ".join(creator["name"] for creator in item["creators"]),
        "title": item["title"], "type": kind, "institution": "Zenodo",
        "year": year, "date": item["publication_date"], "version": item["version"],
        "doi": item["doi"], "url": doi_url,
    }
    bibtex = "@techreport{fanqiang_" + item["slug"].replace("-", "_") + ",\n"
    bibtex += ",\n".join("  " + key + " = {" + bibtex_value(value) + "}" for key, value in fields.items())
    bibtex += "\n}"
    return {"apa": apa, "bibtex": bibtex, "doi": doi_url}


def inject_research_link(raw, *, ai=False):
    """Insert one discovery fragment while preserving every surrounding byte."""
    classes = "guide-body" if ai else "section wrap"
    block = (START + f'<section class="{classes}" id="research-discovery" aria-labelledby="research-discovery-title">'
             '<h2 id="research-discovery-title">研究成果与技术报告</h2>'
             '<p>阅读本项目的知识服务、设备执行、配置转换、共享网络验证、路由器匹配与诊断方法。'
             '<a href="/research/">阅读全文、下载报告与引用 DOI →</a></p></section>' + END)
    if START in raw:
        raw, count = re.subn(re.escape(START) + r".*?" + re.escape(END), lambda _: block, raw, flags=re.S)
        if count != 1:
            raise ValueError("Duplicate research discovery markers")
        return raw
    if raw.count("</main>") != 1:
        raise ValueError("Research discovery needs one main element")
    return raw.replace("</main>", block + "</main>", 1)


def write(public, relative, content):
    target = Path(public) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = content if isinstance(content, bytes) else content.encode("utf-8")
    target.write_bytes(payload)
    target.with_name(target.name + ".gz").write_bytes(gzip.compress(payload, mtime=0))


def report_markdown(item, texts):
    lines = ["# " + item["title"], ""]
    if item.get("title_en"):
        lines += [item["title_en"], ""]
    lines += ["作者：" + "；".join(a["name"] for a in item["creators"]), "",
              "版本：" + item["version"] + "；发布日期：" + item["publication_date"] + "；类型：" + TYPES[item["type"]], "",
              "[DOI](" + texts["doi"] + ") · [Zenodo](" + item["record_url"] + ") · [PDF](" + SITE + "/" + item["pdf"].lstrip("/") + ")", ""]
    if item.get("advisors"):
        lines += ["学术顾问：" + "；".join(advisor["name"] + (" · ORCID https://orcid.org/" + advisor["orcid"] if advisor.get("orcid") else "") for advisor in item["advisors"]), ""]
    lines += ["## 摘要", "", item["abstract"], ""]
    if item.get("abstract_en"):
        lines += [item["abstract_en"], ""]
    if item.get("materials"):
        lines += ["## 复现材料", ""]
        for material in item["materials"]:
            lines += ["- [下载：" + material["title"] + "](" + material["url"] + ")" +
                      (" — " + material["description"] if material.get("description") else ""), ""]
    for section in item["sections"]:
        lines += ["## " + section["title"], ""]
        for paragraph in section["paragraphs"]:
            lines += [paragraph, ""]
        for bullet in section.get("items", []):
            lines += ["- " + bullet]
        lines += [""]
    lines += ["## 参考文献", ""]
    for index, reference in enumerate(item.get("references", []), 1):
        ident = reference.get("id", index)
        names = "；".join(reference_authors(reference))
        year = " (" + str(reference["year"]) + ")" if reference.get("year") is not None else ""
        citation = f'[{ident}] ' + (names + year + ". " if names else year.strip() + " " if year else "") + f'[{reference["title"]}]({reference["url"]})'
        identifiers = [person["name"] + " · ORCID https://orcid.org/" + person["orcid"] for person in reference.get("author_identifiers", []) if person.get("orcid")]
        if identifiers:
            citation += " · " + "；".join(identifiers)
        lines += [citation + (" — " + reference["note"] if reference.get("note") else ""), ""]
    if item.get("related_publications"):
        lines += ["## 配套技术文献", ""]
        for related in item["related_publications"]:
            label = "补充本文的技术说明" if related["relation"] == "isSupplementedBy" else "本文补充的系统报告"
            lines += ["- " + label + "：[" + related.get("title", related["slug"]) + "](" + SITE + "/research/" + related["slug"] + "/) · [DOI](https://doi.org/" + related["doi"] + ")", ""]
    lines += ["## 引用本文", "", texts["apa"], "", "```bibtex", texts["bibtex"], "```", ""]
    return "\n".join(lines)


def render_report(item, page):
    esc = lambda value: escape(str(value), quote=True)
    route = "/research/" + item["slug"] + "/"
    texts = citation_texts(item)
    ref_ids = {str(reference.get("id", index)) for index, reference in enumerate(item.get("references", []), 1)}
    def text_html(text):
        raw = esc(text)
        def citation_group(match):
            if "," not in match[1]:
                return '<a href="#reference-' + match[1] + '">' + match[0] + "</a>" if match[1] in ref_ids else match[0]
            linked = re.sub(r"[1-9][0-9]*", lambda number: '<a href="#reference-' + number[0] + '">' + number[0] + "</a>" if number[0] in ref_ids else number[0], match[1])
            return "[" + linked + "]"
        return re.sub(r"\[([1-9][0-9]*(?:\s*,\s*[1-9][0-9]*)*)\]", citation_group, raw)
    authors = []
    for author in item["creators"]:
        name = esc(author["name"])
        if author.get("orcid"):
            name += ' · <a rel="author" href="https://orcid.org/' + esc(author["orcid"]) + '">ORCID ' + esc(author["orcid"]) + "</a>"
        if author.get("affiliation"):
            name += " · " + esc(author["affiliation"])
        authors.append(name)
    sections = '<section id="abstract"><h2>摘要</h2><p>' + text_html(item["abstract"]) + '</p>'
    if item.get("abstract_en"):
        sections += '<p lang="en">' + text_html(item["abstract_en"]) + "</p>"
    sections += "</section>"
    if item.get("materials"):
        sections += '<section id="materials"><h2>复现材料</h2>'
        for material in item["materials"]:
            if material.get("description"):
                sections += '<p>' + esc(material["description"]) + '</p>'
            sections += '<p><a class="button button-secondary" href="' + esc(material["url"]) + '" download>下载：' + esc(material["title"]) + '</a></p>'
        sections += '</section>'
    for section in item["sections"]:
        sections += '<section id="' + esc(section["id"]) + '"><h2>' + esc(section["title"]) + "</h2>"
        sections += "".join("<p>" + text_html(paragraph) + "</p>" for paragraph in section["paragraphs"])
        if section.get("items"):
            sections += "<ul>" + "".join("<li>" + text_html(bullet) + "</li>" for bullet in section["items"]) + "</ul>"
        sections += "</section>"
    references = ""
    for index, reference in enumerate(item.get("references", []), 1):
        ident = esc(reference.get("id", index))
        names = "；".join(reference_authors(reference))
        year = " (" + str(reference["year"]) + ")" if reference.get("year") is not None else ""
        attribution = names + year + ". " if names else year.strip() + " " if year else ""
        references += '<li id="reference-' + ident + '">[' + ident + '] ' + esc(attribution) + '<a href="' + esc(reference["url"]) + '">' + esc(reference["title"]) + "</a>"
        identifiers = [person_html(person) for person in reference.get("author_identifiers", []) if person.get("orcid")]
        if identifiers:
            references += " · " + "；".join(identifiers)
        if reference.get("note"):
            references += " — " + esc(reference["note"])
        references += "</li>"
    sections += '<section id="references"><h2>参考文献</h2><ul>' + references + "</ul></section>"
    if item.get("related_publications"):
        links = ""
        for related in item["related_publications"]:
            label = "补充本文的技术说明" if related["relation"] == "isSupplementedBy" else "本文补充的系统报告"
            links += ('<li data-doi-relation="' + esc(related["relation"]) + '">' + label + '：<a href="/research/'
                      + esc(related["slug"]) + '/">' + esc(related.get("title", related["slug"])) + '</a>'
                      + ' · <a href="https://doi.org/' + esc(related["doi"]) + '">' + esc(related["doi"]) + '</a></li>')
        sections += '<section id="related-publications"><h2>配套技术文献</h2><ul>' + links + '</ul></section>'
    sections += (
        '<section id="citation"><h2>引用本文</h2><p>使用固定版本 DOI 引用；每个文本块均可一键复制。</p>'
        '<h3>APA</h3><pre id="citation-apa"><code>' + esc(texts["apa"]) + '</code></pre>'
        '<h3>BibTeX</h3><pre id="citation-bibtex"><code>' + esc(texts["bibtex"]) + '</code></pre>'
        '<h3>DOI</h3><pre id="citation-doi"><code>' + esc(texts["doi"]) + '</code></pre>'
        '<p><a href="' + route + 'citation.bib" download>下载 BibTeX</a> · '
        '<a href="' + route + 'citation.txt" download>下载文本引用</a></p></section>'
    )
    nav = '<a href="#abstract">摘要</a>' + ('<a href="#materials">复现材料</a>' if item.get("materials") else "") + "".join('<a href="#' + esc(s["id"]) + '">' + esc(s["title"]) + '</a>' for s in item["sections"])
    nav += '<a href="#references">参考文献</a>'
    if item.get("related_publications"):
        nav += '<a href="#related-publications">配套技术文献</a>'
    nav += '<a href="#citation">引用本文</a>'
    advisors_html = ('<p class="guide-meta"><strong>学术顾问：</strong>' + "；".join(person_html(advisor) for advisor in item["advisors"]) + '</p>') if item.get("advisors") else ""
    body = (
        '<main id="main" class="wrap guide-main"><nav class="breadcrumbs"><a href="/">翻墙指南</a>'
        '<a href="/research/">研究成果</a><span>' + TYPES[item["type"]] + '</span></nav>'
        '<header class="guide-header"><p class="mini-label">' + TYPES[item["type"]] + ' / DOI</p><h1>'
        + esc(item["title"]) + '</h1>'
        + ('<p class="guide-summary" lang="en">' + esc(item["title_en"]) + '</p>' if item.get("title_en") else "")
        + '<p class="guide-meta">' + "<br>".join(authors) + '<br>版本 ' + esc(item["version"])
        + ' · <time datetime="' + esc(item["publication_date"]) + '">' + esc(item["publication_date"]) + '</time>'
        + '</p>' + advisors_html + '<div class="hero-actions"><a class="button button-primary" href="' + esc(item["record_url"]) + '">Zenodo 与 DOI ↗</a>'
        '<a class="button button-secondary" href="' + route + 'paper.pdf" download>下载完整 PDF</a>'
        '<a class="button button-secondary" href="#citation">复制引用</a></div></header>'
        '<div class="guide-layout"><article class="guide-body">' + sections + '</article>'
        '<aside class="guide-aside"><h2>本文目录</h2><nav>' + nav + '</nav><div class="aside-formats">'
        '<a href="' + route + 'index.md">Markdown 全文</a><a href="/research/">全部研究成果</a>'
        '</div></aside></div></main>'
    )
    schema = {
        "@type": "Report", "@id": texts["doi"], "name": item["title"],
        "headline": item["title"], "abstract": item["abstract"], "genre": TYPES[item["type"]],
        "version": item["version"], "datePublished": item["publication_date"], "inLanguage": "zh-CN",
        "url": SITE + route, "identifier": item["doi"], "publisher": {"@type": "Organization", "name": "Zenodo"},
        "author": [{"@type": "Person", "name": author["name"],
                    **({"sameAs": "https://orcid.org/" + author["orcid"]} if author.get("orcid") else {})}
                   for author in item["creators"]],
        "citation": [reference_schema(ref) for ref in item.get("references", [])],
        "encoding": {"@type": "MediaObject", "contentUrl": SITE + route + "paper.pdf", "encodingFormat": "application/pdf"},
        "sameAs": item["record_url"],
    }
    if item.get("advisors"):
        schema["contributor"] = [{"@type": "Person", "name": advisor["name"], "description": "本报告学术顾问",
                                  **({"sameAs": "https://orcid.org/" + advisor["orcid"]} if advisor.get("orcid") else {})}
                                 for advisor in item["advisors"]]
    rendered = page(item["title"] + " | Fanqiang Guide 研究", item["abstract"], route, body, [schema], route + "index.md")
    meta = [("citation_title", item["title"]), *[("citation_author", a["name"]) for a in item["creators"]],
            ("citation_publication_date", item["publication_date"].replace("-", "/")),
            ("citation_doi", item["doi"]), ("citation_pdf_url", SITE + route + "paper.pdf")]
    tags = "".join('<meta name="' + name + '" content="' + esc(value) + '">' for name, value in meta)
    rendered = rendered.replace("</head>", tags + "</head>", 1)
    return rendered, report_markdown(item, texts), texts


def build_research_pages(public, metadata_path, page):
    public, metadata_path = Path(public), Path(metadata_path)
    records = load_publications(metadata_path)
    esc = lambda value: escape(str(value), quote=True)
    listing = ""
    sitemap_entries = {INDEX: max(item["publication_date"] for item in records)}
    for item in records:
        slug = item["slug"]
        route = "research/" + slug + "/"
        rendered, markdown, texts = render_report(item, page)
        write(public, route + "index.html", rendered)
        write(public, route + "index.md", markdown)
        write(public, route + "citation.bib", texts["bibtex"] + "\n")
        write(public, route + "citation.txt", texts["apa"] + "\n")
        pdf = metadata_path.parent / "pdfs" / (slug + ".pdf")
        (public / route / "paper.pdf").write_bytes(pdf.read_bytes())
        listing += ('<section><p class="mini-label">' + TYPES[item["type"]] + ' · v' + esc(item["version"]) + '</p>'
                    '<h2><a href="/' + route + '">' + esc(item["title"]) + '</a></h2>'
                    '<p>' + esc(item["abstract"]) + '</p><p>'
                    '<a href="/' + route + '">阅读全文 →</a> · <a href="/' + route + 'paper.pdf">PDF</a> · '
                    '<a href="' + esc(texts["doi"]) + '">' + esc(item["doi"]) + '</a></p></section>')
        sitemap_entries[SITE + "/" + route] = item["publication_date"]
    intro = "围绕公共知识服务、设备执行、配置转换、共享网络验证、路由器匹配与本地诊断，整理方法、规则、验证范围与可复现资料。"
    body = ('<main id="main" class="wrap guide-main"><nav class="breadcrumbs"><a href="/">翻墙指南</a><span>研究成果</span></nav>'
            '<header class="guide-header"><p class="mini-label">RESEARCH / 开放技术文档</p><h1>研究成果与技术报告</h1>'
            '<p class="guide-summary">' + intro + '</p><p class="guide-meta">作者、版本、DOI、完整正文和参考文献在每篇报告中分别列出。</p></header>'
            '<div class="guide-body">' + listing + '</div>'
            '<p>这些成果以技术报告或技术说明发布。DOI 提供稳定标识，搜索平台的收录与引用统计由各平台独立决定。</p></main>')
    schemas = [{"@type": "CollectionPage", "name": "Fanqiang Guide 研究成果", "url": INDEX,
                "hasPart": [{"@type": "Report", "name": item["title"], "url": SITE + "/research/" + item["slug"] + "/"} for item in records]}]
    write(public, "research/index.html", page("研究成果与技术报告 | Fanqiang Guide", intro, "/research/", body, schemas, "/research/index.md"))
    markdown = "# 研究成果与技术报告\n\n" + intro + "\n\n"
    for item in records:
        markdown += "## [" + item["title"] + "](" + SITE + "/research/" + item["slug"] + "/)\n\n" + item["abstract"] + "\n\n"
        markdown += "DOI：https://doi.org/" + item["doi"] + "\n\n"
    write(public, "research/index.md", markdown)
    root = ET.fromstring((public / "sitemap.xml").read_bytes())
    ET.register_namespace("", NS)
    for node in list(root):
        if (node.findtext("{" + NS + "}loc") or "").startswith(INDEX):
            root.remove(node)
    for url, stamp in sitemap_entries.items():
        node = ET.SubElement(root, "{" + NS + "}url")
        ET.SubElement(node, "{" + NS + "}loc").text = url
        ET.SubElement(node, "{" + NS + "}lastmod").text = stamp
    write(public, "sitemap.xml", ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n")
    return {"reports": len(records), "sitemap_urls": len(sitemap_entries)}


def add_research_discovery(public):
    for relative, ai in (("index.html", False), ("ai/index.html", True)):
        path = Path(public) / relative
        write(public, relative, inject_research_link(path.read_text(encoding="utf-8"), ai=ai))
