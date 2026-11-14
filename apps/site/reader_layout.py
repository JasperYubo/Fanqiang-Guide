"""Reader layout for the final HTML build; canonical machine sources stay intact."""
import re
import gzip
import hashlib
from html import escape
from product_contract import product_facts
from pathlib import Path
from reading_ui import enhance_code_blocks, READING_CSS_PATH, READING_SCRIPT_PATH
from design_refresh import DESIGN_CSS, refresh_home

LAYOUT_CSS = "assets/reader-layout-v1.0-2026-11-02.css"
ICON = '<svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>'

def product_sections(facts):
    server = facts["server"]
    book_links = "".join(
        '<a href="' + escape(book["download_url"], quote=True) + '"><strong>' +
        escape(book["display_title"]) + '</strong><span>v' + escape(book["version"]) + '</span></a>'
        for book in facts["books"])
    overview = (
        '<section class="ai-workflows" aria-labelledby="ai-workflows-title">'
        '<p class="eyebrow">' + str(facts["book_count"]) + ' 本配置工程书</p>'
        '<h2 id="ai-workflows-title">从你要配置的目标开始</h2>'
        '<div class="ai-workflow-grid">'
        '<a href="#device-setup"><strong>手机与电脑</strong><span>客户端配置、设备选择与共享网络 →</span></a>'
        '<a href="#merlin-setup"><strong>梅林路由器</strong><span>核对型号、固件和插件条件 →</span></a>'
        '<a href="#server-setup"><strong>自己的 VPS</strong><span>安装网络服务与内置 AI 助手 →</span></a>'
        '</div></section>')
    server_section = (
        '<section class="ai-server-setup" id="server-setup" aria-labelledby="server-setup-title">'
        '<p class="eyebrow">服务器助手 / 自己的 VPS</p><h2 id="server-setup-title">安装一次，让 AI 帮你维护</h2>'
        '<p>准备 ' + escape(server["assistant"]["provider"]) + ' Key，SSH 连接自己的服务器，'
        '安装网络服务与内置 ' + escape(server["assistant"]["runtime"]) +
        ' 助手，再把连接导入手机或电脑。遇到问题，在服务器运行 <code>' +
        escape(server["assistant"]["command"]) + '</code>，用中文检查和排错。</p>'
        '<p>' + escape(facts["price_sentence"]) + '</p>'
        '<p class="ai-server-actions"><a class="button button-primary" href="' +
        escape(server["entry_url"], quote=True) + '">开始安装服务器助手 →</a>'
        '<a href="' + escape(server["download_url"], quote=True) + '" download>下载服务器工程书</a></p>'
        '<p class="note">同一个公共 MCP 提供工具 <code>' + escape(server["tool"]) +
        '</code>、提示 <code>' + escape(server["prompt"]) + '</code> 和资源 <code>' +
        escape(server["resource_uri"]) + '</code>。服务器安装与维护在你的 VPS 中进行，'
        'Key 在自己的终端输入。</p></section>')
    catalog = '<div class="ai-book-directory">' + book_links + '</div>'
    return overview, server_section, catalog


def ai_layout(raw, header, footer):
    if 'class="ai-page"' in raw:
        return raw
    raw = raw.replace('<style>', '<link rel="stylesheet" href="/assets/site-v1.3.css"><style>', 1)
    raw = re.sub(r'<body>.*?<main', '<body class="ai-page">'+header+'<main', raw, count=1, flags=re.S)
    raw = re.sub(r'<footer>.*?</footer>', lambda _: footer, raw, count=1, flags=re.S)
    raw = raw.replace('<h1>让自己的 AI 配好设备｜Fanqiang Guide</h1>', '<h1>让自己的 AI 配好设备与服务器</h1>')
    facts = product_facts()
    overview, server_section, catalog = product_sections(facts)
    raw = raw.replace('先取设备配置工程书，再按需检索下方的完整公开资料。记录保留来源、核对日期与适用范围。', '按手机电脑、梅林路由器或自己的 VPS 选择配置流程。所有工程书共用一个 MCP 入口，安装步骤按目标分别执行。')
    raw = raw.replace('<section id="device-setup"', overview + '<section id="device-setup"', 1)
    raw = raw.replace('<main class="wrap" id="main">', '<main class="wrap ai-main" id="main">')
    faq_pattern = r'<!-- faq-ai-discovery:start -->.*?<!-- faq-ai-discovery:end -->'
    faq = re.search(faq_pattern, raw, re.S)
    faq_html = faq[0] if faq else ''
    raw = re.sub(faq_pattern, '', raw, count=1, flags=re.S)
    resource_pattern = r'<div class="resource-links">.*?</nav>'
    resource = re.search(resource_pattern, raw, re.S)
    if not resource:
        raise ValueError('AI resource directory missing')
    raw = raw[:resource.start()] + raw[resource.end():]
    # The source has a single setup card; put each action with its numbered step.
    card = re.search(r'<section id="device-setup".*?</section>', raw, re.S)
    text = card[0]
    endpoint = re.search(r'<p class="autosetup-endpoint">.*?</p>', text, re.S)[0]
    text = text.replace(endpoint, '')
    mcp = re.search(r'<button[^>]*data-copy-mcp[^>]*>.*?</button>', text, re.S)[0]
    request = re.search(r'<button[^>]*data-copy-setup-request[^>]*>.*?</button>', text, re.S)[0]
    text = text.replace(mcp, '').replace(request, '')
    steps = re.search(r'<ol class="autosetup-steps">(.*?)</ol>', text, re.S)
    rows = re.findall(r'<li>.*?</li>', steps[1], re.S)
    if len(rows) != 3:
        raise ValueError('AI setup requires three steps')
    rows[0] = rows[0].replace('</li>', endpoint+mcp+'</li>')
    rows[1] = rows[1].replace('</li>', request+'</li>')
    text = text[:steps.start(1)]+''.join(rows)+text[steps.end(1):]
    raw = raw[:card.start()]+text+raw[card.end():]
    raw = raw.replace('<section id="device-setup"', '<nav class="ai-jump" aria-label="本页快捷导航"><a href="#device-setup">接入 MCP</a><a href="#merlin-setup">梅林路由器</a><a href="#server-setup">服务器助手</a><a href="#reference-library">资料与接口</a></nav><section id="device-setup"', 1)
    # Advertise every registered book, keeping each execution flow separate.
    raw = raw.replace('<section aria-labelledby="setup-access">', server_section + '<section aria-labelledby="setup-access">', 1)
    raw = re.sub(r'当前为 <code>fanqiang://books/autosetup</code>。',
        lambda _: '当前有 ' + str(facts["book_count"]) + ' 本配置工程书：' +
        '、'.join('<code>' + escape(book["resource_uri"]) + '</code>' for book in facts["books"]) + '。', raw, count=1)
    raw = raw.replace('<a href="/ai/books/index.json">工程书目录</a>',
        '<a href="/ai/books/index.json">工程书目录</a>' + catalog, 1)
    prompt_item = '<li><code>setup_device</code> 提示无参数，依次提供前导、完整九条 ANSWER_RULES 与完整工程书。</li>'
    if prompt_item in raw:
        raw = raw.replace(prompt_item,
            '<li>配置提示按目标选择：' + '、'.join('<code>' + escape(prompt) + '</code>' for prompt in dict.fromkeys(book["prompt"] for book in facts["books"])) +
            '。各自提供对应工程书；服务器助手也可通过工具 <code>' + escape(facts["server"]["tool"]) + '</code> 获取安装说明。</li>', 1)
    # Keep technical interface information available without blocking the basic flow.
    access = re.search(r'<section aria-labelledby="setup-access">.*?</section>', raw, re.S)
    if access:
        body = re.sub(r'<h3 id="setup-access">.*?</h3>', '', access[0])
        body = re.sub(r'^<section[^>]*>|</section>$', '', body)
        panel = '<details class="ai-access" id="setup-access"><summary>接入参数与高级用法<span>工具、资源、HTTP 备用接口</span></summary><div class="ai-access-body">'+body+'</div></details>'
        raw = raw[:access.start()]+panel+raw[access.end():]
    raw = raw.replace('<a class="top" href="#top">', '<a class="top" href="#reference-library">')
    start = raw.index('<section id="source-freshness">')
    end = raw.index('</main>', start)
    full = raw[start:end]
    library = '<details class="ai-library" id="reference-library"><summary><span>完整资料与工程书原文</span><small>按分类浏览 · 每个代码块均可一键复制</small></summary><div class="ai-library-body">'+resource[0]+full+'</div></details>'
    raw = raw[:start]+faq_html+library+raw[end:]
    return raw

def apply_reader_layout(public, header, footer):
    public=Path(public)
    assets=Path(__file__).resolve().parent/'content'
    for asset in (READING_CSS_PATH, READING_SCRIPT_PATH, LAYOUT_CSS, DESIGN_CSS):
        (public/asset).write_bytes((assets/Path(asset).name).read_bytes())
    design_path=public/DESIGN_CSS
    design_path.with_name(design_path.name+".gz").write_bytes(gzip.compress(design_path.read_bytes(),mtime=0))
    changed=[]
    for path in sorted(public.rglob('*.html')):
        if path.name.startswith('google') and '<head>' not in path.read_text(encoding='utf-8'):
            continue
        raw=path.read_text(encoding='utf-8')
        if path == public/'index.html':
            raw=refresh_home(raw)
        if path == public/'ai/index.html':
            raw=ai_layout(raw, header, footer)
        # All lengthy limitations remain readable on demand beside the action.
        raw=re.sub(r'(<p class="autosetup-note">.*?</p>)(<p class="autosetup-optional">.*?</p>)?',
            lambda m:'<details class="autosetup-boundaries"><summary>操作范围与验证说明</summary>'+m[0]+'</details>',
            raw, flags=re.S)
        raw=re.sub(r'(<button\b[^>]*\bdata-copy-(?:mcp|setup-request)[^>]*>)(?!<svg)',
            lambda m:m[1]+ICON, raw)
        raw=enhance_code_blocks(raw, collapse_long=path == public/'ai/index.html')
        layout_version = hashlib.sha256((public/LAYOUT_CSS).read_bytes()).hexdigest()[:12]
        design_version = hashlib.sha256((public/DESIGN_CSS).read_bytes()).hexdigest()[:12]
        additions=(f'<link rel="stylesheet" href="/{READING_CSS_PATH}">'
                   f'<link rel="stylesheet" href="/{LAYOUT_CSS}?v={layout_version}">'
                   f'<link rel="stylesheet" href="/{DESIGN_CSS}?v={design_version}">'
                   f'<script defer src="/{READING_SCRIPT_PATH}"></script>')
        raw=raw.replace('</head>', additions+'</head>', 1)
        path.write_text(raw,encoding='utf-8')
        changed.append(path.relative_to(public).as_posix())
    return changed
