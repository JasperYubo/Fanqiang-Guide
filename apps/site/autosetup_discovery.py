"""Discovery for a user's AI executing the pinned device setup book."""
from __future__ import annotations
import html
import runpy
from pathlib import Path

SITE = "https://fanqiang.guide"
MCP_URL = SITE + "/mcp"
REQUEST_PATH = "/ai/setup-request.ilang"
_BOOK = runpy.run_path(str(Path(__file__).resolve().parent.parent / "lookup/runtime/setup_book.py"))["book_manifest"]("autosetup")
BOOK_PATH = "/ai/books/" + Path(_BOOK["download_url"]).name
BOOK_VERSION = _BOOK["version"]
CSS_PATH = "assets/autosetup-entry-v2.0-2026-11-02.css"
SCRIPT_PATH = "assets/autosetup-entry-v2.0-2026-11-02.js"

# Explicit reviewed canonical groups; equivalent URLs inherit the representative.
DESKTOP_GROUPS = frozenset({
    "faq-0c9ed33129b42758e3e0fd95",
    "faq-12d5b73a86d361ed7ccfafeb",
    "faq-3a18e28fb588a916dc7602c8",
    "faq-5ef4b7b9b0ce71d2d473c3bb",
    "faq-4c2d5493d990a3ea50245dd1",
    "faq-52331c4c5840607744639d8f",
    "faq-b66e1a79855b59489f27c237",
    "faq-cb6165fc2dc26eec4f4a917f",
    "faq-7afba6c72d4c9f4a1cb0ccab",
    "faq-650b9ec12d096abc2c440344",
    "faq-bbd2560ac06ba3c97cd417ac",
    "faq-12966950f9a8c6d57c370bdb",
    "faq-a5ef905caa42cde923e5807b",
    "faq-9240fc9491ddc5ada5a577cb",
    "faq-eb197a39aeb41ece3f86703f",
    "faq-a2ffe33ae5888ce357625782",
    "faq-da25482eee44dde65ca49a0a",
    "faq-a518a8d8515e7f4295c00d1d",
    "faq-13281da778cc45403d562e29",
})
MOBILE_GROUPS = frozenset({
    "faq-0294069b241ec7850438df7a",
    "faq-a9e46d2fd70a214dc918d3fd",
    "faq-dce8868487b1bc4a13d6924d",
    "faq-33d46f18184a41076fbe00f5",
    "faq-42246a83f9bcf1511a8fe609",
    "faq-337a6328431b236718f02f87",
    "faq-1daf311926fe8bc8c70dedfd",
    "faq-045f6395641e62c0e294c628",
    "faq-61b9cef27d533cbcbc4fafaa",
    "faq-20706ce83766871974f22f17",
    "faq-f750ea853da8c3c837ac3cf3",
    "faq-5da2735c475c5000b5cf1ac6",
    "faq-66f8e40d6a0e06a29aaf77b3",
    "faq-4460164fa592de1ca6ab0446",
})
ROUTER_GROUPS = frozenset({
    "faq-c77f1b4e6050233d09cc7090",
    "faq-9ad918a8496f6474d2e73160",
    "faq-7943ae32763ce22e66abbf4c",
    "faq-e3b7a4628d244898671a28a3",
    "faq-a85c47537786d1196df1418d",
    "faq-400539119cb0da825b40244b",
    "faq-cc120903e022f19316201c86",
})


def setup_context(entry):
    group = entry.get("representative", entry.get("faq_id"))
    if group in MOBILE_GROUPS:
        return "mobile"
    if group in ROUTER_GROUPS:
        return "router"
    if group in DESKTOP_GROUPS:
        return "desktop"
    return None


def copy_for(context):
    if context not in {"home", "desktop", "router", "mobile"}:
        raise ValueError("Unknown autosetup placement")
    titles = {
        "home": "三步，让自己的 AI 帮你配好设备",
        "desktop": "让自己的 AI 继续安装、配置与排错",
        "router": "让自己的 AI 按路由器条件继续配置",
        "mobile": "让自己的 AI 在这部手机上继续配置",
    }
    intros = {
        "home": "把本站知识接到自己的 AI，再交给它配置任务：识别环境、选择工具、安装配置、诊断修复，最后验证实际访问与重新连接。",
        "desktop": "把上面的资料交给能操作这台电脑的 AI。它先检查已有客户端和配置，保留可用设置，再完成必要的安装、配置、排错与验证。",
        "router": "AI 先确认路由器型号、固件和实际控制权限，再按兼容条件配置并验证。它需要能操作目标路由器；只在电脑上测通，不能证明路由器已配置。",
        "mobile": "AI 先确认手机系统、已有客户端和实际控制能力，再完成兼容的安装、配置与验证。它需要能操作这部手机；只在电脑上测通，不能证明手机已配置。",
    }
    note = "知识 MCP 只提供公共资料，不会替 AI 获得设备权限。订阅与凭据只在目标设备安全输入；付款、账号或区域变更不包含在这份请求中。"
    if context == "mobile":
        note += " 手机的系统 VPN 授权仍须按平台要求操作；缺少设备控制时，AI 应说明必要的连接或手动步骤，不得声称已经完成。"
    elif context == "router":
        note += " 路由器本机与下游设备要分别验收；路由变更前要保留恢复方式，刷固件不包含在默认配置范围内。"
    else:
        note += " 缺少目标设备控制时，AI 应说明必要的连接或手动步骤，不得声称已经完成。"
    if context in {"home", "mobile", "router"}:
        intros[context] += " 工程书 v" + BOOK_VERSION + " 也包含 PICK_PHONE 选手机与 HOTSPOT 旧手机共享家庭网络分支，先考虑复用现有设备。"
        note += " 手机自身 VPN 连通不等于热点下设备走代理；共享路径、DNS、IPv6、UDP 和重连须在下游分别验收，本站尚未完成手机热点硬件实测。"
    return titles[context], intros[context], note


def render_autosetup_callout(context="home"):
    title, intro, note = copy_for(context)
    ident = "autosetup-home" if context == "home" else "autosetup-next-step"
    classes = "autosetup-callout wrap" if context == "home" else "autosetup-callout"
    return (
        f'<section class="{classes}" id="{ident}" data-setup-entry aria-labelledby="{ident}-title">'
        '<p class="autosetup-kicker">自己的 AI × 本站知识 MCP</p>'
        f'<h2 id="{ident}-title">{html.escape(title)}</h2><p class="autosetup-intro">{html.escape(intro)}</p>'
        '<ol class="autosetup-steps">'
        '<li><h3>添加远程 MCP</h3><p>在支持远程 MCP 的 AI 中添加这个地址。</p>'
        f'<code class="autosetup-address">{MCP_URL}</code>'
        '<p class="autosetup-protocol">Streamable HTTP · 本站知识服务无需令牌</p>'
        '<button type="button" class="button button-secondary" data-copy-mcp>复制 MCP 地址</button></li>'
        '<li><h3>把请求交给自己的 AI</h3><p>复制配置请求，再告诉 AI 目标设备和想访问的网站或应用。</p>'
        '<button type="button" class="button button-primary" data-copy-setup-request>复制配置请求</button></li>'
        '<li><h3>完成配置与实际验收</h3><p>AI 使用它自己的设备工具安装、配置和排错，并验证目标访问、预期路由及断开后重连。未完成的检查要明确说明。</p></li>'
        '</ol>'
        '<div class="autosetup-actions"><a class="button button-secondary" href="/ai/#device-setup">查看接入与执行说明 →</a>'
        f'<a href="{BOOK_PATH}" download>下载 v{BOOK_VERSION} 完整工程书</a></div>'
        '<p class="autosetup-status" data-copy-status role="status" aria-live="polite" aria-atomic="true">复制后粘贴到自己的 AI；打开本页不会自动连接或执行配置。</p>'
        '<details class="autosetup-fallback" data-setup-fallback><summary>查看请求或手动复制</summary>'
        f'<label for="{ident}-mcp">MCP 地址</label>'
        f'<textarea id="{ident}-mcp" data-mcp-fallback readonly rows="1" spellcheck="false">{MCP_URL}</textarea>'
        f'<label for="{ident}-request">给自己的 AI 的配置请求</label>'
        f'<textarea id="{ident}-request" data-setup-request-text readonly rows="7" spellcheck="false" placeholder="展开后从本站加载请求；也可以下载请求文件。"></textarea>'
        f'<a href="{REQUEST_PATH}" download>下载同一份配置请求</a>'
        '<noscript><p>浏览器未运行复制脚本，可直接选中地址，下载请求后交给自己的 AI。</p></noscript></details>'
        f'<p class="autosetup-note">{html.escape(note)}</p>'
        '<p class="autosetup-optional">只想手动补充电脑连接测量？<a href="/diagnostics/">可选网络诊断工具</a>可单独使用，不是设备配置的前置步骤。</p>'
        '</section>'
    )


def autosetup_markdown(context="home"):
    title, intro, note = copy_for(context)
    return (
        f"\n## {title}\n\n{intro}\n\n"
        f"1. **添加远程 MCP**：{MCP_URL}，传输方式 **Streamable HTTP**；本站知识服务无需令牌。\n"
        f"2. **交给自己的 AI**：[下载同一份配置请求]({SITE}{REQUEST_PATH})，告诉它目标设备与想访问的网站或应用。请求原文以该文件为唯一来源。\n"
        "3. **完成配置与实际验收**：AI 使用自己的目标设备工具安装、配置和排错，再验证目标访问、预期路由与断开后重连；未完成的检查须明确说明。\n\n"
        f"[接入与执行说明]({SITE}/ai/#device-setup) · [完整工程书]({SITE}{BOOK_PATH})\n\n"
        f"{note}\n\n打开页面不会自动连接、安装或提交报告。"
        f"[可选网络诊断工具]({SITE}/diagnostics/)可单独使用，不是配置前置步骤。\n"
    )
