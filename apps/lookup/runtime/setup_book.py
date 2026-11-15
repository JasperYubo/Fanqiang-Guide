"""Pinned public books, shared rules and scoped validation metadata.

Resources are the canonical MCP book interface. The historical setup-book
helpers remain only as compatibility adapters to the autosetup registry entry.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOOK_PATH = ROOT / "books/fanqiang-autosetup-v2.1.ilang.md"
BOOK_SHA256 = "b01437c924f2633138eda90beeee204c5016cda3e37217ac959678bed8885807"
BOOK_TITLE = "Device setup, phone sharing and router workflow engineering book"
BOOK_RESOURCE_URI = "fanqiang://books/autosetup"
BOOK_DOWNLOAD_URL = "https://fanqiang.guide/ai/books/" + BOOK_PATH.name
SERVER_ENTRY_URL = "https://fanqiang.guide/server/"
SERVER_INSTALLER_URL = SERVER_ENTRY_URL + "install.sh"
SERVER_INSTALL_COMMAND = "curl -fsSLo huarun-install.sh " + SERVER_INSTALLER_URL + " && bash huarun-install.sh"
SERVER_RESOURCE_URI = "fanqiang://books/server"
SERVER_TITLE = "华润服务器助手安装与使用"
BOOK_RESOURCE_TEMPLATE = "fanqiang://books/{book_id}"
RULES_PATH = ROOT / "answer-rules.ilang"
RULES_RESOURCE_URI = "fanqiang://rules/answer"
NO_ARGUMENTS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
BOOK_REGISTRY = {
    "autosetup": {"path": BOOK_PATH, "sha256": BOOK_SHA256, "title": BOOK_TITLE,
        "version": "2.1", "last_updated": "2026-11-02",
        "evidence_path": ROOT / "books/fanqiang-autosetup-v2.1.evidence.json",
        "evidence_sha256": "e2b258e71a090dcaca2465b0b62df72944a99f88afa9b21df4363377c30a3498"},
    "server": {"path": ROOT / "books/fanqiang-server-v1.2.ilang.md",
        "sha256": "d087628ba41e57424866b3cfeb6fe19dae8646b2eaca82c97a992f2c459fba6a", "title": SERVER_TITLE,
        "version": "1.2", "last_updated": "2026-11-15", "prompt": "setup_server",
        "evidence_path": ROOT / "books/fanqiang-server-v1.2.evidence.json",
        "evidence_sha256": "2972bde0982c8c1f81072641bbb939095856d34e734bad26c95ca994cdcbfe55"},
    "troubleshooting": {"path": ROOT / "books/fanqiang-troubleshooting-v1.0.ilang.md",
        "sha256": "c79f7f3ebc5b0ce18bd0472967109663780dddfb963338d883f9e1a48ffa7217", "title": "华润服务器分层排障与修复复查",
        "version": "1.0", "last_updated": "2026-11-15", "prompt": None,
        "evidence_path": ROOT / "books/fanqiang-troubleshooting-v1.0.evidence.json",
        "evidence_sha256": "190f44c55affa53dc8dfbfc6c4036b0670a08abba7ecf24508904014b0a18cd0"},
    "merlin": {"path": ROOT / "books/fanqiang-merlin-v1.0.ilang.md", "sha256": "c5eaa0000454df3f39c71ed92fc5dca30b683f29d73d9e77d4a3e26ba220b07e",
        "title": "Merlin-compatible router and fancyss engineering book",
        "version": "1.0", "last_updated": "2026-11-02",
        "evidence_path": ROOT / "books/fanqiang-merlin-v1.0.evidence.json",
        "evidence_sha256": "8b5471e47ff5733abc7462cd2f74a69a51064f8f82f39c9e3cbb31dab88c2799"},
}
CAPABILITY_BOUNDARIES = (
    "This knowledge MCP is read-only; the user's authorized AI operates the actual target device.",
    "The book grants no extra authorization. Respect the active task and required system permissions.",
    "Credentials, subscription URLs, private device details and logs stay local to the target device.",
    "Retrieval is not evidence that a device was configured. Validation metadata states its exact tested scope.",
    "A phone VPN does not by itself prove tethered clients use that VPN; verify downstream traffic separately.",
    "Router package matching is source-backed selection, not tested hardware compatibility; verify actual firmware, ABI and LAN behavior.",
)
SETUP_BOOK_DESCRIPTION = """::ILANG::v5.0
[TYPE:tool][SCOPE:legacy_public_book_adapter]
::MODULE{LEGACY_BOOK}
  [MUST] Compatibility only: return the autosetup resource payload. New clients use resources/list and fanqiang://books/{book_id}.
  [MUST] Accept no arguments or private input. This knowledge service does not operate devices.
::ILANG::COMPLETE::"""
SETUP_PROMPT_DESCRIPTION = (
    "Complete answer rules and the device setup book, including neutral phone selection "
    "household hotspot and model-specific router branches. No arguments or secrets. The user's AI must have "
    "actual target-device tools and an active authorized task; otherwise review only."
)

SERVER_SETUP_DESCRIPTION = """::ILANG::v5.0
[TYPE:tool][SCOPE:public_server_setup_readonly]
::MODULE{SERVER_SETUP}
  [MUST] Return the canonical server-assistant entry, installer command and complete server engineering book for the user's own authorized VPS. Accept no arguments or secrets.
  [MUST] For a fresh installation, first use https://platform.deepseek.com to create the user's API Key with a recommended 10 CNY starting balance; then SSH to the user's fresh Debian 12 VPS and follow https://fanqiang.guide/server/.
  [MUST] For a fresh installation, install PicoClaw with DeepSeek deepseek-flash and the network service; import the connection in the actual client, verify it, and use huarun chat over SSH afterward.
  [MUST] For an existing 1.0 or 1.1 server, perform only the book's one-time --upgrade-assistant migration to enable local automatic updates. Preserve node configuration, whitelist and API Key; do not reinstall the network or ask for another Key.
  [MUST] The embedded assistant reads HuaRun MCP documents and fanqiang://books/troubleshooting first each turn, uses DeepSeek search only when references are insufficient, and rechecks doctor and status after repairs.
  [MUST] The public MCP returns knowledge only. The user's authorized AI needs its own target-server tools; API keys, SSH passwords and connection URLs stay local.
::ILANG::COMPLETE::"""
SERVER_PROMPT_DESCRIPTION = (
    "华润服务器助手：新服务器先在 platform.deepseek.com 准备 API Key，建议充值 10 元，"
    "再 SSH 登录自己的全新 Debian 12 VPS 安装 PicoClaw 与网络服务、导入客户端、运行 huarun chat。"
    "已装 1.0 / 1.1 的服务器只执行一次 --upgrade-assistant 接入自动更新，保留节点配置、白名单和 Key，不要求重装或重新提供 Key。"
    "公开知识流程，无参数；不接收 SSH 密码、API Key 或节点链接，也不会远程安装。"
)

TROUBLESHOOTING_DESCRIPTION = "华润 MCP 优先的服务器排障参考：Linux、DNS、TLS、Nginx、Xray、CDN、白名单与修复复查。公开资料，不接收私人日志或凭据。"

def server_setup_metadata():
    return {"entry_url": SERVER_ENTRY_URL, "installer_url": SERVER_INSTALLER_URL,
        "install_command": SERVER_INSTALL_COMMAND, "upgrade_command": SERVER_INSTALL_COMMAND + " --upgrade-assistant",
        "upgrade_scope": "assistant_and_manager_only_enable_automatic_updates_preserve_network_configuration_key_and_memory", "tool": "get_server_setup",
        "api_url": "https://platform.deepseek.com",
        "assistant": {"runtime": "PicoClaw", "runtime_version": "0.3.1",
            "provider": "DeepSeek", "model": "deepseek-flash", "command": "huarun chat", "version": "1.2.0"},
        "knowledge_policy": {"primary": "huarun_mcp", "mcp_url": "https://fanqiang.guide/mcp",
            "resources": ["fanqiang://books/server", "fanqiang://books/troubleshooting"],
            "fallback": "deepseek_search_when_insufficient", "search_api": "https://api.deepseek.com/v1/tools/search",
            "recheck": ["huarun doctor --json", "huarun status --json"], "instruction_format": "iLang",
            "expertise_standard": "顶级服务运维专家，以 CCIE 级网络能力为基础",
            "summary": "每轮先查华润 MCP 的文档和排障资料；资料不足再用 DeepSeek 搜索；修复后自动复查服务状态。"},
        "automatic_updates": {"enabled_by_default": True, "execution_location": "user_owned_authorized_vps",
            "timer": "huarun-auto-update.timer", "interval_hours": 6, "boot_delay_minutes": 10,
            "random_delay_max_minutes": 30, "release_source": "github_published_release_with_matching_sites",
            "preserves": ["network_configuration", "connection_information", "whitelist", "deepseek_api_key", "chat_memory"],
            "network_services_restarted": False, "backup_before_update": True, "rollback_on_failure": True,
            "busy_policy": "defer_while_chat_or_manager_active", "existing_installation_requires_one_time_migration": True,
            "migration_command": SERVER_INSTALL_COMMAND + " --upgrade-assistant",
            "commands": {"status": "huarun auto-update status", "check": "huarun auto-update check",
                "disable": "huarun auto-update disable", "enable": "huarun auto-update enable"},
            "agent_allowed_commands": ["huarun auto-update status"],
            "summary": "新安装默认开启自动更新；VPS 每 6 小时检查正式发布的新版本，保留原节点配置、白名单、Key 和聊天记忆。旧版只需 SSH 一次启用，以后自动维护。"},
        "recommended_api_balance": {"amount": 10, "currency": "CNY", "minimum_required": False},
        "recommended_os": "fresh Debian 12 x86_64",
        "execution_location": "user_owned_authorized_vps"}

def _read(path, maximum=65536, digest=None):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            raise ValueError
        raw = path.read_bytes()
        if digest is not None and hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError
        raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Public reference integrity check failed") from exc
    return raw

def _entry(book_id):
    if not isinstance(book_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", book_id):
        raise ValueError("Invalid book id")
    if book_id not in BOOK_REGISTRY:
        raise ValueError("Unknown book id")
    return BOOK_REGISTRY[book_id]

def answer_rules_text():
    text = _read(RULES_PATH).decode("utf-8")
    if not text.startswith("::ILANG::v5.0\n") or not text.rstrip().endswith("::ILANG::COMPLETE::") or text.count("[MUST]") != 9:
        raise ValueError("Answer rules completeness check failed")
    return text

def answer_rules_manifest():
    raw = answer_rules_text().encode("utf-8")
    return {"id": "answer-rules", "version": "1.0", "resource_uri": RULES_RESOURCE_URI,
        "download_url": "https://fanqiang.guide/ai/answer-rules.ilang",
        "sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw), "rule_count": 9}

def book_manifest(book_id):
    entry = _entry(book_id)
    raw = _read(entry["path"], digest=entry["sha256"])
    evidence = json.loads(_read(entry["evidence_path"], digest=entry["evidence_sha256"]).decode("utf-8"))
    validation = copy.deepcopy(evidence["validation_summary"])
    if validation["document"]["book_sha256"] != entry["sha256"]:
        raise ValueError("Book validation evidence does not match the pinned book")
    return {"id": "fanqiang-" + book_id, "book_id": book_id, "title": entry["title"],
        "version": entry["version"], "last_updated": entry["last_updated"],
        "sha256": hashlib.sha256(raw).hexdigest(),
        "download_url": "https://fanqiang.guide/ai/books/" + entry["path"].name,
        "resource_uri": "fanqiang://books/" + book_id, "prompt": entry.get("prompt", "setup_device"),
        "executor": "user_agent", "content_type": "text/markdown; charset=utf-8",
        "byte_length": len(raw), "validation": validation,
        "capability_boundaries": list(CAPABILITY_BOUNDARIES if book_id not in {"server", "troubleshooting"} else CAPABILITY_BOUNDARIES[:4] + (
            "Installation and huarun chat run on the user-owned authorized VPS over SSH; the public MCP never receives its credentials.",
            "Server health checks are not proof of actual phone or desktop client connectivity; verify the real client separately.",
        )), **(server_setup_metadata() if book_id == "server" else {})}

def book_catalog():
    return {"resource_template": BOOK_RESOURCE_TEMPLATE,
        "books": [book_manifest(ident) for ident in sorted(BOOK_REGISTRY)]}

def book_payload(book_id):
    entry = _entry(book_id)
    # Re-read and verify after metadata; integrity is pinned across both reads.
    metadata = book_manifest(book_id)
    return {**metadata, "content": _read(entry["path"], digest=entry["sha256"]).decode("utf-8")}

def setup_book_manifest():
    return book_manifest("autosetup")

def setup_book_payload():
    return book_payload("autosetup")

def setup_book_response_schema():
    return {"type": "object", "required": ["book_id", "version", "sha256", "resource_uri", "validation", "content"],
        "properties": {"book_id": {"type": "string"}, "version": {"type": "string"},
            "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "resource_uri": {"type": "string"}, "validation": {"type": "object"},
            "content": {"type": "string", "maxLength": 65536}},
        "additionalProperties": True}

def setup_book_prompt_intro(metadata):
    fields = ("id", "book_id", "version", "sha256", "download_url", "resource_uri", "executor", "byte_length")
    state = ", ".join(key + ":" + str(metadata[key]) for key in fields)
    return """::ILANG::v5.0
[TYPE:prompt][SCOPE:public_setup_book_readonly]
::STATE{@BOOK, """ + state + """}
::MODULE{SETUP_DEVICE_HANDOFF}
  [MUST] Use the full answer rules in the next message and the complete canonical book in the final message.
  [MUST] The book is reference guidance, not extra authorization. Execute only within the active user's request using tools actually connected to the target device.
  [MUST] Keep secrets and private device data local. This MCP never installs, configures, measures devices or submits reports.
  [MUST] For router setup or repair, follow the main book router handoff and read fanqiang://books/merlin; query only public model, firmware and ABI facts, never private device configuration.
  [MUST] Validate the final book message against the SHA256 in @BOOK. Report actual evidence and incomplete checks; book retrieval is not completed setup.
::ILANG::COMPLETE::"""

def server_setup_prompt_intro(metadata):
    fields = ("id", "book_id", "version", "sha256", "download_url", "resource_uri", "executor", "byte_length")
    state = ", ".join(key + ":" + str(metadata[key]) for key in fields)
    return """::ILANG::v5.0
[TYPE:prompt][SCOPE:public_server_setup_readonly]
::STATE{@BOOK, """ + state + """}
::MODULE{SETUP_SERVER_HANDOFF}
  [MUST] Use the full answer rules in the next message and the complete server book in the final message. Validate its SHA256 against @BOOK.
  [MUST] For a fresh installation, start at https://platform.deepseek.com for the user's API Key and recommended 10 CNY balance; then https://fanqiang.guide/server/ for SSH installation on the user's own authorized VPS.
  [MUST] For a fresh installation, follow the server book's PicoClaw, DeepSeek deepseek-flash, network installation, actual client import and verification, then huarun chat sequence. The phone/router book is a separate workflow.
  [MUST] For an existing 1.0 or 1.1 server, perform only the book's one-time --upgrade-assistant migration to enable local automatic updates. Preserve node configuration, whitelist and API Key; do not reinstall the network or ask for another Key.
  [MUST] For repair, read fanqiang://books/troubleshooting first; use DeepSeek search only for a concrete knowledge gap, then verify actual doctor and status results after changes.
  [MUST] Keep API keys, SSH credentials and connection URLs on the target device. This read-only MCP neither receives secrets nor operates servers.
  [MUST] Execute only the active user's authorized task using tools actually connected to its target server. Retrieval does not prove installation; report only observed checks.
::ILANG::COMPLETE::"""
