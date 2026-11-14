'''Build the first-party server onboarding page and its homepage discovery.'''
from __future__ import annotations

import gzip
import html
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

SITE = "https://fanqiang.guide"
ENTRY_URL = SITE + "/server/"
INSTALLER_URL = ENTRY_URL + "install.sh"
INSTALL_COMMAND = "curl -fsSLo huarun-install.sh " + INSTALLER_URL + " && bash huarun-install.sh"
CSS_PATH = "/assets/server-assistant-v1.0-2026-11-13.css"
BOOK_PATH = "/ai/books/fanqiang-server-v1.0.ilang.md"
TITLE = "华润服务器助手：自己的 VPS，自带 AI 助手"
DESCRIPTION = "在自己的 Debian 12 VPS 安装华润服务器助手：准备 DeepSeek API Key、SSH 登录、运行安装命令，再把连接导入手机或电脑，用内置 AI 检查与排障。"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def write(public: Path, relative: str, payload: str | bytes) -> None:
    target = public / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    target.write_bytes(raw)
    target.with_name(target.name + ".gz").write_bytes(gzip.compress(raw, mtime=0))


def code(command: str) -> str:
    return '<pre><code class="language-bash">' + html.escape(command) + '</code></pre>'


def add_styles(raw: str) -> str:
    if CSS_PATH not in raw:
        raw = raw.replace("</head>", '<link rel="stylesheet" href="' + CSS_PATH + '"></head>', 1)
    return raw


def build_server_page(public: Path, page, server_source: Path) -> None:
    '''Use the shared page shell; the normal reader pass adds copy controls.'''
    body = r'''
<main class="wrap guide-main server-page" id="main">
<nav class="breadcrumb" aria-label="面包屑"><a href="/">首页</a><span aria-hidden="true"> / </span><span>服务器助手</span></nav>
<header class="server-hero"><p class="eyebrow">华润 / 服务器助手</p><h1>自己的服务器，<br><span>自带 AI 助手。</span></h1><p class="server-lead">已经有一台海外 VPS，想让手机和电脑都能用上？<br>在服务器安装一次，拿到连接信息，再用内置 AI 帮你检查网络、证书和服务。</p><div class="server-actions"><a class="button button-primary" href="#prepare">开始准备 →</a><a class="button button-secondary" href="#install">已有 Key 和服务器，直接安装</a></div><p class="server-caption">PicoClaw + DeepSeek · 在你自己的 Linux 服务器上运行</p></header>
<div class="server-overview"><div><span class="mini-label">准备这些就能开始</span><h2>一台 VPS，一把自己的 Key。</h2><p>准备一台<strong>全新的 Debian 12 x64 VPS</strong>，能够以 root 登录，且 80、443 端口可用。充值 10 元，即可开始使用 AI 维护。VPS 自备，费用另计。</p><p>安装后，你会得到 VMess 连接信息和 <code>huarun</code> 管理命令。API Key 在服务器终端里输入，网页无需填写。</p></div><ol class="server-route" aria-label="安装步骤"><li><a href="#prepare"><span>01</span>准备 DeepSeek</a></li><li><a href="#connect"><span>02</span>连接自己的 VPS</a></li><li><a href="#install"><span>03</span>安装服务器助手</a></li><li><a href="#client"><span>04</span>导入手机或电脑</a></li><li><a href="#assistant"><span>05</span>让 AI 帮你维护</a></li></ol></div>
<section class="server-step" id="prepare" aria-labelledby="prepare-title"><div class="server-step-number" aria-hidden="true">01</div><div><p class="eyebrow">准备 DEEPSEEK</p><h2 id="prepare-title">充值 10 元，创建 API Key。</h2><p>打开 DeepSeek 开放平台，登录后充值 10 元，再创建并保存自己的 API Key。充值 10 元，即可开始使用 AI 维护。</p><p><a class="button button-primary" href="https://platform.deepseek.com" target="_blank" rel="noopener noreferrer">打开 DeepSeek 开放平台 ↗</a></p><p class="server-note">到第 3 步时，在自己的服务器终端输入 Key。终端隐藏输入内容，不显示星号也属于正常现象。</p></div></section>
<section class="server-step" id="connect" aria-labelledby="connect-title"><div class="server-step-number" aria-hidden="true">02</div><div><p class="eyebrow">连接自己的 VPS</p><h2 id="connect-title">打开终端，SSH 登录。</h2><p>Windows 使用终端或 PowerShell，macOS、Linux 使用终端。把下面的示例 IP 换成你的 VPS 公网 IP，再执行：</p>
''' + code("ssh root@203.0.113.10") + r'''
<p>按提示完成 SSH 登录。看到服务器终端后，下面的安装命令都在这台 VPS 上运行。若你的服务器使用其他 SSH 端口，请按服务商提供的连接方式登录。</p><p class="server-note">本页不会连接你的服务器；SSH 密码、私钥和 DeepSeek Key 都在你自己的终端中使用。</p></div></section>
<section class="server-step" id="install" aria-labelledby="install-title"><div class="server-step-number" aria-hidden="true">03</div><div><p class="eyebrow">安装服务器助手</p><h2 id="install-title">复制命令，跟着终端完成安装。</h2><p>确认已经以 root 登录全新的 Debian 12 x64 VPS。命令从华润主站下载安装脚本，然后启动交互安装。</p>
''' + code(INSTALL_COMMAND) + r'''
<ol class="server-checklist"><li>输入你的 DeepSeek API Key，安装器会先验证是否可用。</li><li>按提示设置连接信息。没有域名时，可按安装器提示使用 sslip.io 域名。</li><li>等待安装完成，保存终端输出的 VMess 连接信息。</li></ol><p>安装内容包括代理服务、证书与续期任务，以及内置 PicoClaw AI 助手。使用的 DeepSeek 模型以安装器实际配置为准。</p><details class="server-details"><summary>终端提示找不到 curl？</summary><p>先安装 curl 和证书，再重新执行上面的安装命令：</p>
''' + code("apt-get update && apt-get install -y curl ca-certificates") + r'''
</details><p class="server-note">如果安装中途报错，先保留错误信息，检查提示对应的端口、域名或 Key。已有业务或旧配置的服务器，请先备份并确认兼容性。</p><a class="text-link" href="/server/install.sh">查看安装脚本 →</a></div></section>
<section class="server-step" id="client" aria-labelledby="client-title"><div class="server-step-number" aria-hidden="true">04</div><div><p class="eyebrow">导入手机或电脑</p><h2 id="client-title">把连接信息，带到你的设备上。</h2><p>安装结束后复制 VMess 链接，在设备上的客户端选择“从剪贴板导入”或对应的导入功能。之后可随时在服务器查看：</p>
''' + code("huarun info") + r'''
<div class="server-client-grid"><a href="/guides/client-downloads.html"><strong>Windows</strong><span>v2rayN · 查看下载入口 →</span></a><a href="/guides/client-downloads.html"><strong>Android</strong><span>v2rayNG · 查看下载入口 →</span></a><a href="/guides/shadowrocket-platforms.html"><strong>iPhone / iPad</strong><span>Shadowrocket · 查看使用指南 →</span></a><a href="/guides/client-downloads.html"><strong>macOS / Linux</strong><span>选择支持 VMess 的客户端 →</span></a></div><p>导入后启动客户端，实际打开要访问的网站验证。服务器服务正常与手机、电脑实际连通，需要分别检查。</p><p class="server-note">默认使用域名白名单：进入此通道的非白名单目标会被阻止。若要增加目标域名，可以在下一步让 AI 帮你检查和添加。</p></div></section>
<section class="server-step" id="assistant" aria-labelledby="assistant-title"><div class="server-step-number" aria-hidden="true">05</div><div><p class="eyebrow">让 AI 帮你维护</p><h2 id="assistant-title">有问题，直接在服务器里问。</h2><p>重新 SSH 登录你的 VPS，打开内置 AI 助手：</p>
''' + code("huarun chat") + r'''
<div class="server-examples" aria-label="可以问助手的问题"><p>“手机连不上，帮我检查服务和证书。”</p><p>“把连接信息再给我看一下。”</p><p>“检查 example.com 能否访问，需要的话加入白名单。”</p><p>“证书还有多少天到期？”</p></div><p>AI 会通过 DeepSeek API 理解你的问题，在这台服务器上检查相关配置。需要改动时，先看清它准备执行的操作。提问和回复会使用你的 DeepSeek API 余额。</p><details class="server-details"><summary>查看状态、诊断和修复命令</summary><p>这些命令在 SSH 终端直接运行。先查看状态与诊断结果，再按提示决定是否修复。</p>
''' + code("huarun status\nhuarun doctor\nhuarun fix") + r'''
</details></div></section>
<section class="server-mcp" id="mcp" aria-labelledby="mcp-title"><p class="eyebrow">也可以交给你常用的 AI</p><h2 id="mcp-title">MCP 接入，也是同一条安装路径。</h2><p>如果你的 AI 客户端支持 MCP，可连接华润 MCP，获取服务器助手的准备条件、安装步骤与工程书，再由你授权的 AI 带着操作自己的 VPS。</p>
''' + code(SITE + "/mcp") + r'''
<p>告诉 AI：“帮我在自己的 VPS 安装华润服务器助手。”服务器助手入口与本页一致；已有设备配置继续使用原来的设备配置流程。</p><p class="server-note">华润公共 MCP 提供安装说明，不代管你的服务器登录信息。Key 仍在自己的服务器终端配置。</p><details class="server-details"><summary>查看 MCP 的对应入口</summary><dl class="server-mcp-contract"><dt>安装工具</dt><dd><code>get_server_setup</code></dd><dt>安装提示</dt><dd><code>setup_server</code></dd><dt>工程书资源</dt><dd><code>fanqiang://books/server</code></dd></dl></details><div class="server-actions"><a class="button button-secondary" href="/ai/#device-setup">查看 MCP 接入说明</a><a class="text-link" href="''' + BOOK_PATH + r'''" download>下载服务器助手工程书 →</a></div></section>
</main>
'''
    schemas = [
        {"@type": "WebPage", "@id": ENTRY_URL + "#webpage", "url": ENTRY_URL,
         "name": TITLE, "description": DESCRIPTION, "inLanguage": "zh-CN"},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "首页", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "服务器助手", "item": ENTRY_URL}]},
    ]
    write(public, "server/index.html", add_styles(page(TITLE, DESCRIPTION, "/server/", body, schemas, md="/server/index.md")))
    write(public, "server/index.md", (server_source / "README.md").read_bytes())
    write(public, "server/install.sh", (server_source / "install.sh").read_bytes())
    asset = Path(__file__).resolve().parent / "content" / Path(CSS_PATH).name
    write(public, CSS_PATH.lstrip("/"), asset.read_bytes())


def add_server_discovery(public: Path) -> None:
    '''Run after the existing homepage layout pass, preserving its chat flow.'''
    home = public / "index.html"
    raw = home.read_text(encoding="utf-8")
    if 'id="server-home"' not in raw:
        marker = '<aside class="start-card wrap"'
        if marker not in raw:
            raise RuntimeError("Homepage start-card marker missing; cannot place the server entry.")
        card = (
            '<section class="wrap server-home" id="server-home" aria-labelledby="server-home-title">'
            '<div><p class="eyebrow">华润 / 服务器助手</p><h2 id="server-home-title">自己的服务器，自带 AI 助手。</h2>'
            '<p>已经有一台 VPS？准备 DeepSeek Key，运行安装命令，再把连接导入手机和电脑。之后让内置 AI 帮你检查和排障。</p></div>'
            '<div class="server-home-action"><a class="button button-primary" href="/server/">开始安装服务器助手 →</a>'
            '<span>Debian 12 x64 · PicoClaw + DeepSeek</span></div></section>'
        )
        raw = raw.replace(marker, card + marker, 1)
    hero_link = '<a class="button button-secondary" href="/server/">安装服务器助手 →</a>'
    if hero_link not in raw:
        raw, count = re.subn(r'(<div class="hero-actions">)', lambda match: match[0] + hero_link, raw, count=1)
        if count != 1:
            raise RuntimeError("Homepage hero actions missing; cannot place installation shortcut.")
    write(public, "index.html", add_styles(raw))

    description = "- [华润服务器助手](" + ENTRY_URL + ")：准备 DeepSeek Key → SSH 自己的 VPS → 安装 → 导入客户端 → huarun chat 排障。"
    for name in ("index.md", "llms.txt", "ai/index.md", "llms-full.txt"):
        target = public / name
        if target.exists():
            previous = target.read_text(encoding="utf-8")
            if ENTRY_URL not in previous:
                write(public, name, previous.rstrip() + "\n\n" + description + "\n")
    catalog_path = public / ".well-known/ai-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    identifier = "urn:air:fanqiang.guide:resource:server-setup"
    catalog["entries"] = [e for e in catalog["entries"] if e.get("identifier") != identifier] + [
        {"identifier": identifier, "displayName": "华润服务器助手", "type": "text/html", "url": ENTRY_URL}
    ]
    write(public, ".well-known/ai-catalog.json", json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    ET.register_namespace("", NS)
    sitemap = ET.fromstring((public / "sitemap.xml").read_text(encoding="utf-8"))
    for node in list(sitemap):
        location = node.find("{" + NS + "}loc")
        if location is not None and location.text in (ENTRY_URL, ENTRY_URL + "index.html"):
            sitemap.remove(node)
    node = ET.SubElement(sitemap, "{" + NS + "}url")
    ET.SubElement(node, "{" + NS + "}loc").text = ENTRY_URL
    ET.SubElement(node, "{" + NS + "}lastmod").text = "2026-11-13"
    write(public, "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(sitemap, encoding="unicode"))
