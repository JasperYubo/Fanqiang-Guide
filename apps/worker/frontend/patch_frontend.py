"""Copy a static release and add the home-page chat interface; no deployment."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BASE = HERE.parents[1] / "site" / "public"

FORM = '''<div class="guide-chat" id="guide-chat">
<form class="site-search" id="guide-query-form" role="search" action="/guides/library.html" method="get">
<label for="site-query">说说你的问题，或查找工具资料</label>
<div class="chat-input-shell"><textarea id="site-query" name="q" rows="2" maxlength="1500" placeholder="说说你想解决的问题…" aria-describedby="chat-input-help chat-input-count"></textarea>
<div class="chat-input-bottom"><span id="chat-input-count">0 / 1500</span><div class="chat-entry-actions"><button class="button button-primary" id="chat-ask" type="button" hidden>问 AI <span aria-hidden="true">↗</span></button><button class="button button-secondary" type="submit">搜索资料</button></div></div></div>
<p id="chat-input-help">先确认你能使用的 AI，再整理设备和需求，生成工程书。</p>
<p class="chat-directory-links"><a href="/guides/library.html">浏览 310 条工具资料</a><span aria-hidden="true"> · </span><a href="/guides/merlin-models.html">查华硕梅林型号</a></p>
<noscript><p>启用 JavaScript 后可使用 AI 问答。搜索资料仍可直接使用。</p></noscript>
</form>
<section class="chat-panel" id="chat-panel" aria-labelledby="chat-heading" hidden>
<div class="chat-panel-heading"><h2 id="chat-heading">AI 问答</h2><div class="chat-session-actions"><button type="button" id="chat-stop" hidden>停止</button><button type="button" id="chat-reset" title="删除当前对话和已生成的文件">清空 / 新对话</button></div></div>
<p class="chat-flow-stage" id="chat-flow-stage">第一步 · 确认可用的 AI</p>
<div class="chat-transcript" id="chat-transcript" role="log" aria-label="对话记录" aria-live="off" tabindex="0"></div>
<p class="chat-status" id="chat-status" role="status" aria-live="polite" aria-atomic="true"></p>
<div class="chat-delivery"><button class="button button-secondary" type="button" id="chat-artifact" disabled>生成 I-Lang 工程书</button><p>需求齐全后自动生成。复制工程书，粘贴到你自己的 AI 对话框；也可下载后上传。如暂时没有 AI，可访问 <a href="https://www.deepseek.com/" target="_blank" rel="noopener noreferrer">DeepSeek 官网</a>。</p></div>
<p class="chat-retention">回答由 AI 根据公开资料生成；对话与文件保留 7 天。</p>
</section></div>'''


def patch(base: Path, output: Path) -> dict:
    base = base.resolve(strict=True)
    output = output.resolve()
    if base == output or base in output.parents or output in base.parents:
        raise ValueError("Output must be separate from the source directory.")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    before = (base / "index.html").read_text(encoding="utf-8")
    if 'id="guide-chat"' in before:
        raise ValueError("Source is already patched.")
    forms = list(re.finditer(r'<form\b[^>]*class="site-search"[^>]*>.*?</form>', before, re.S))
    if len(forms) != 1:
        raise ValueError(f"Expected exactly one existing home search form, got {len(forms)}.")
    if 'action="/guides/library.html"' not in forms[0].group():
        raise ValueError("The existing search action changed; review the integration first.")
    start, end = forms[0].span()
    after = before[:start] + FORM + before[end:]
    additions = '<link rel="stylesheet" href="/assets/chat-v1.1.css"><script defer src="/assets/chat-v1.1.js"></script>'
    if after.count("</head>") != 1:
        raise ValueError("Expected one HTML head.")
    after = after.replace("</head>", additions + "</head>", 1)
    # The original SEO and visible article content stay byte-for-byte intact.
    for pattern in (r'<h1\b[^>]*>.*?</h1>', r'<title>.*?</title>', r'<script type="application/ld\+json">.*?</script>'):
        assert re.findall(pattern, before, re.S) == re.findall(pattern, after, re.S)
    assert after.replace(additions, "", 1).replace(FORM, forms[0].group(), 1) == before
    shutil.copytree(base, output)
    (output / "index.html").write_text(after, encoding="utf-8")
    for name in ("chat-v1.1.js", "chat-v1.1.css"):
        shutil.copyfile(HERE / "assets" / name, output / "assets" / name)
    changed = ["index.html", "assets/chat-v1.1.js", "assets/chat-v1.1.css"]
    for rel in changed:
        path = output / rel
        path.with_name(path.name + ".gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0))
    return {"source": str(base), "output": str(output), "changed": changed,
            "sha256": {rel: hashlib.sha256((output / rel).read_bytes()).hexdigest() for rel in changed}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(patch(options.base, options.output), ensure_ascii=False, indent=2))
