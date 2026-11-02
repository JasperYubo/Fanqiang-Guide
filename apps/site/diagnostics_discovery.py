"""Reader-facing links to the separately deployed local diagnostics client."""
from __future__ import annotations

SITE = "https://fanqiang.guide"
# Explicit reviewed groups; equivalent URLs share their representative's context.
DESKTOP_GROUPS = frozenset({
    "faq-0c9ed33129b42758e3e0fd95", "faq-12d5b73a86d361ed7ccfafeb",
    "faq-3a18e28fb588a916dc7602c8", "faq-5ef4b7b9b0ce71d2d473c3bb",
    "faq-4c2d5493d990a3ea50245dd1", "faq-52331c4c5840607744639d8f",
    "faq-b66e1a79855b59489f27c237", "faq-cb6165fc2dc26eec4f4a917f",
    "faq-7afba6c72d4c9f4a1cb0ccab", "faq-650b9ec12d096abc2c440344",
    "faq-bbd2560ac06ba3c97cd417ac", "faq-12966950f9a8c6d57c370bdb",
    "faq-a5ef905caa42cde923e5807b",
})
ROUTER_GROUPS = frozenset({
    "faq-c77f1b4e6050233d09cc7090", "faq-9ad918a8496f6474d2e73160",
    "faq-7943ae32763ce22e66abbf4c",
})

def diagnostic_context(entry):
    group = entry.get("representative", entry.get("faq_id"))
    if group in ROUTER_GROUPS:
        return "router"
    if group in DESKTOP_GROUPS:
        return "desktop"
    return None

def copy_for(context):
    if context not in {"home", "desktop", "router"}:
        raise ValueError("Unknown diagnostics placement")
    title = "连接慢、打不开？先看本机诊断结果" if context == "home" else "仍然连接异常？补充一份本机诊断报告"
    intro = (
        "在连接这台路由器的 Windows 或 Linux 电脑上运行网络诊断 MCP，补充电脑经路由器访问固定目标的测量。它不会读取路由器插件配置或日志。"
        if context == "router" else
        "先按上文检查配置；程序能够启动、但连接仍异常时，可在 Windows 或 Linux 电脑上运行网络诊断 MCP，补充 DNS、连接、TLS 与下载表现。"
        if context == "desktop" else
        "网络诊断 MCP 帮你在自己的电脑上测量连接、预览脱敏结果，再决定是否把结构化报告提交给本站排查。无需先接入 AI，也能直接打开本地诊断页面。"
    )
    steps = [
        ("下载安装", "选择 Windows / Linux x64 版，完整解压后启动；要接入自己的 AI，再生成并添加 MCP 配置。"),
        ("本地测量与预览", "自己点击开始，下载测速默认关闭。查看完整报告与可选日志脱敏预览，日志全文不提交。"),
        ("自己决定是否提交", "预览后点击“提交这份报告”。收到回执后可撤回；重启也能恢复最近一份待提交报告或回执。"),
    ]
    note = "首版只测电脑到本站固定诊断目标的系统／TUN 路径，结果不代表所有节点或应用，不自动使用 HTTP／SOCKS 应用代理；不支持手机本机采样。打开安装页或安装软件不会自动提交报告。"
    return title, intro, steps, note

def render_diagnostics_callout(context="home"):
    title, intro, steps, note = copy_for(context)
    ident = "diagnostics-home" if context == "home" else "diagnostics-next-step"
    classes = "diagnostics-callout wrap" if context == "home" else "diagnostics-callout"
    items = "".join(f"<li><strong>{heading}</strong><p>{description}</p></li>" for heading, description in steps)
    return (
        f'<section class="{classes}" id="{ident}" aria-labelledby="{ident}-title">'
        '<p class="diagnostics-kicker">网络诊断 MCP · 先预览，再决定是否分享</p>'
        f'<h2 id="{ident}-title">{title}</h2><p>{intro}</p>'
        f'<ol class="diagnostics-steps">{items}</ol>'
        '<div class="diagnostics-actions"><a class="button button-primary" href="/diagnostics/#install">下载并安装网络诊断 MCP →</a>'
        '<a class="button button-secondary" href="/diagnostics/#submit-report">查看报告提交步骤</a></div>'
        f'<p class="diagnostics-note">{note}</p></section>'
    )

def diagnostics_markdown(context="home"):
    title, intro, steps, note = copy_for(context)
    numbered = "\n".join(f"{n}. **{heading}**：{description}" for n, (heading, description) in enumerate(steps, 1))
    return (
        f"\n## {title}\n\n{intro}\n\n{numbered}\n\n"
        f"[下载并安装网络诊断 MCP]({SITE}/diagnostics/#install) · "
        f"[查看报告提交步骤]({SITE}/diagnostics/#submit-report)\n\n{note}\n"
    )
