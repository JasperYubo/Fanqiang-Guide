"""Reader layout for the final HTML build; canonical machine sources stay intact."""
import re
from pathlib import Path
from reading_ui import enhance_code_blocks, READING_CSS_PATH, READING_SCRIPT_PATH

LAYOUT_CSS = "assets/reader-layout-v1.0-2026-11-02.css"
ICON = '<svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>'

def ai_layout(raw, header, footer):
    if 'class="ai-page"' in raw:
        return raw
    raw = raw.replace('<style>', '<link rel="stylesheet" href="/assets/site-v1.3.css"><style>', 1)
    raw = re.sub(r'<body>.*?<main', '<body class="ai-page">'+header+'<main', raw, count=1, flags=re.S)
    raw = re.sub(r'<footer>.*?</footer>', lambda _: footer, raw, count=1, flags=re.S)
    raw = raw.replace('<h1>让自己的 AI 配好设备｜Fanqiang Guide</h1>', '<h1>让自己的 AI 配好设备</h1>')
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
    raw = raw.replace('<section id="device-setup"', '<nav class="ai-jump" aria-label="本页快捷导航"><a href="#device-setup">开始接入</a><a href="#merlin-setup">配置梅林路由器</a><a href="#reference-library">资料与接口</a></nav><section id="device-setup"', 1)
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
    for asset in (READING_CSS_PATH, READING_SCRIPT_PATH, LAYOUT_CSS):
        (public/asset).write_bytes((assets/Path(asset).name).read_bytes())
    changed=[]
    for path in sorted(public.rglob('*.html')):
        if path.name.startswith('google') and '<head>' not in path.read_text(encoding='utf-8'):
            continue
        raw=path.read_text(encoding='utf-8')
        if path == public/'ai/index.html':
            raw=ai_layout(raw, header, footer)
        # All lengthy limitations remain readable on demand beside the action.
        raw=re.sub(r'(<p class="autosetup-note">.*?</p>)(<p class="autosetup-optional">.*?</p>)?',
            lambda m:'<details class="autosetup-boundaries"><summary>操作范围与验证说明</summary>'+m[0]+'</details>',
            raw, flags=re.S)
        raw=re.sub(r'(<button\b[^>]*\bdata-copy-(?:mcp|setup-request)[^>]*>)(?!<svg)',
            lambda m:m[1]+ICON, raw)
        raw=enhance_code_blocks(raw, collapse_long=path == public/'ai/index.html')
        additions=(f'<link rel="stylesheet" href="/{READING_CSS_PATH}">'
                   f'<link rel="stylesheet" href="/{LAYOUT_CSS}">'
                   f'<script defer src="/{READING_SCRIPT_PATH}"></script>')
        raw=raw.replace('</head>', additions+'</head>', 1)
        path.write_text(raw,encoding='utf-8')
        changed.append(path.relative_to(public).as_posix())
    return changed
