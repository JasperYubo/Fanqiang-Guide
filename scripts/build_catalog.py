#!/usr/bin/env python3
"""Render the complete catalog and GitHub observations; never modify snapshots.

Only entity.repository determines monitoring identity. A successful GitHub request
does not verify that a reference-only entity is the project it claims to be.
"""

import argparse
import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
LIBRARY_PATH = Path("export/library-v0.1-2026-09-11.json")
MANIFEST_PATH = Path("config/upstream-repositories.json")
CARD_SUFFIX = "-v0.1-2026-09-11.md"
# Existing GitHub accounts can end in a hyphen (for example wangyu-).
OWNER = r"[A-Za-z0-9][A-Za-z0-9-]{0,38}"
REPOSITORY = r"[A-Za-z0-9_.-]{1,100}"
ROOT_URL = re.compile(rf"https://github\.com/({OWNER})/({REPOSITORY})/?\Z")
ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
KINDS = {
    "client": "客户端", "core": "代理核心", "protocol": "协议",
    "transport": "传输与外层方案", "concept": "基础概念", "firmware": "路由器固件",
    "router_plugin": "路由器插件", "package_ecosystem": "软件包生态",
    "deployment": "部署工具", "panel": "管理面板", "rules": "规则集",
    "dns": "DNS 工具", "subscription": "订阅管理", "browser_extension": "浏览器扩展",
    "vpn": "VPN", "mesh": "组网工具", "diagnostic": "诊断工具",
    "library": "开发库", "directory": "资料目录", "historical": "历史项目",
}
REVIEW = {
    "primary_reviewed": "已查阅官方资料",
    "reference_only": "仅有目录介绍，来源待核实",
    "historical_reference": "历史资料，当前可用性待确认",
}
EXCLUSIONS = {
    "missing_repository": "请在资料页查看官网或其他来源",
    "non_github_repository": "请在资料页查看项目网站",
    "invalid_repository_mapping": "项目地址待核实，请先阅读资料页",
}
CATEGORY_ANCHORS = {
    "client": "clients", "core": "cores", "protocol": "protocols",
    "concept": "concepts", "firmware": "router-firmware", "router_plugin": "router-plugins",
}


def cell(value):
    """Remote strings become plain single-line table text, not Markdown/HTML."""
    if value is None:
        return "未记录"
    text = re.sub(r"[\x00-\x1f\x7f\u2028\u2029]+", " ", str(value))
    text = " ".join(text.split())
    text = html.escape(text, quote=True)
    for char in "\\|`[]*_{}()":
        text = text.replace(char, "&#%d;" % ord(char))
    return text or "未记录"


def github_root(value):
    """Return owner/repo only for a strict HTTPS root URL; no inference."""
    if not isinstance(value, str):
        return None
    match = ROOT_URL.fullmatch(value)
    if not match:
        return None
    owner, repo = match.groups()
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not repo or repo in {".", ".."}:
        return None
    return owner + "/" + repo


def exclusion_reason(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return "missing_repository"
    if isinstance(value, str):
        try:
            hostname = urlsplit(value).hostname
        except ValueError:
            hostname = None
        if hostname and hostname.lower() != "github.com":
            return "non_github_repository"
    return "invalid_repository_mapping"


def validate_library(library):
    if not isinstance(library, list):
        raise ValueError("library must be a JSON list")
    seen = set()
    for entity in library:
        if not isinstance(entity, dict) or not isinstance(entity.get("id"), str):
            raise ValueError("every entity needs a string id")
        entity_id = entity["id"]
        if not ID.fullmatch(entity_id) or entity_id in seen:
            raise ValueError("invalid or duplicate entity id: " + entity_id)
        seen.add(entity_id)
        if not isinstance(entity.get("name"), str) or not isinstance(entity.get("kind"), str):
            raise ValueError("entity needs name and kind: " + entity_id)
        if not isinstance(entity.get("platforms"), list):
            raise ValueError("platforms must be a list: " + entity_id)
        if not all(isinstance(p, str) for p in entity["platforms"]):
            raise ValueError("platforms must contain strings: " + entity_id)
        if not isinstance(entity.get("verification"), dict):
            raise ValueError("verification must be an object: " + entity_id)


def make_manifest(library):
    validate_library(library)
    repos, excluded = {}, []
    for entity in sorted(library, key=lambda item: item["id"]):
        full_name = github_root(entity.get("repository"))
        if full_name is None:
            excluded.append({"entity_id": entity["id"], "reason": exclusion_reason(entity.get("repository"))})
            continue
        key = full_name.casefold()
        row = repos.setdefault(key, {"full_name": full_name, "entity_ids": []})
        row["full_name"] = min(row["full_name"], full_name)
        row["entity_ids"].append(entity["id"])
    return {"schema_version": 1, "repositories": [repos[k] for k in sorted(repos)], "excluded": excluded}


def validate_manifest(library, manifest):
    """Require exactly one mapping or exclusion per entity, matching repository."""
    expected = make_manifest(library)
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("manifest schema_version must be 1")
    if not isinstance(manifest.get("repositories"), list) or not isinstance(manifest.get("excluded"), list):
        raise ValueError("manifest repositories and excluded must be lists")
    actual, seen_repos = {}, set()
    for row in manifest["repositories"]:
        if not isinstance(row, dict) or not isinstance(row.get("full_name"), str):
            raise ValueError("invalid manifest repository")
        name = row["full_name"]
        if github_root("https://github.com/" + name) != name or name.casefold() in seen_repos:
            raise ValueError("invalid or duplicate manifest repository: " + name)
        seen_repos.add(name.casefold())
        if not isinstance(row.get("entity_ids"), list) or not row["entity_ids"]:
            raise ValueError("repository entity_ids must be a nonempty list")
        for entity_id in row["entity_ids"]:
            if not isinstance(entity_id, str) or entity_id in actual:
                raise ValueError("entity occurs more than once in manifest")
            actual[entity_id] = ("repository", name.casefold())
    for row in manifest["excluded"]:
        if not isinstance(row, dict) or not isinstance(row.get("entity_id"), str) or row.get("reason") not in EXCLUSIONS:
            raise ValueError("invalid manifest exclusion")
        entity_id = row["entity_id"]
        if entity_id in actual:
            raise ValueError("entity occurs more than once in manifest: " + entity_id)
        actual[entity_id] = ("excluded", row["reason"])
    wanted = {}
    for row in expected["repositories"]:
        wanted.update({entity_id: ("repository", row["full_name"].casefold()) for entity_id in row["entity_ids"]})
    wanted.update({row["entity_id"]: ("excluded", row["reason"]) for row in expected["excluded"]})
    if actual != wanted:
        raise ValueError("manifest must cover every catalog entity exactly once using its repository field")


def validate_state(state):
    if not isinstance(state, dict) or type(state.get("schema_version")) is not int or state["schema_version"] != 1:
        raise ValueError("state schema_version must be 1")
    if not isinstance(state.get("repositories"), dict):
        raise ValueError("state repositories must be an object")
    run = state.get("last_run")
    if run is not None:
        if not isinstance(run, dict):
            raise ValueError("state last_run must be an object or null")
        for key in ("repository_count", "ok_count", "error_count"):
            if type(run.get(key)) is not int or run[key] < 0:
                raise ValueError("invalid last_run count: " + key)
        if run["ok_count"] + run["error_count"] != run["repository_count"]:
            raise ValueError("last_run counts do not add up")
    seen = set()
    for name, row in state["repositories"].items():
        if name.casefold() in seen or not isinstance(row, dict):
            raise ValueError("duplicate or invalid state repository")
        seen.add(name.casefold())
        if row.get("repository_status") not in {"ok", "unavailable", "error"}:
            raise ValueError("invalid repository_status")
        if row.get("release_status") not in {"ok", "none", "error", "not_checked"}:
            raise ValueError("invalid release_status")
        for key in ("repository", "release"):
            if row.get(key) is not None and not isinstance(row[key], dict):
                raise ValueError(key + " must be an object or null")


def date_text(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2}))?", value):
        return "时间未记录"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "时间无效"
    if len(value) == 10:
        return value
    return parsed.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M") + "（北京时间）"


def release_url(value):
    if not isinstance(value, str) or re.search(r"[\x00-\x20\x7f<>\\]", value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment:
        return None
    parts = parsed.path.split("/")
    if len(parts) < 6 or parts[3:5] != ["releases", "tag"] or not parts[5]:
        return None
    if github_root("https://github.com/" + "/".join(parts[1:3])) is None:
        return None
    decoded = unquote(parsed.path)
    if re.search(r"[\x00-\x20\x7f<>\\]", decoded) or re.search(r"%(?![0-9A-Fa-f]{2})", parsed.path):
        return None
    return "https://github.com" + quote(parsed.path, safe="/%-._~:@!$&'()*+,;=")


def card_link(entity):
    return "[" + cell(entity["name"]) + "](export/cards/" + entity["id"] + CARD_SUFFIX + ")"


def repo_observation(row, detailed=False):
    if row is None:
        return "暂未取得项目信息"
    status = row["repository_status"]
    data = row.get("repository")
    if status == "ok":
        prefix = "信息更新于 " + date_text(row.get("checked_at")) if detailed else ""
    elif status == "unavailable":
        prefix = "暂时无法查看项目（未确认是否删除）；查询于 " + date_text(row.get("checked_at"))
    else:
        prefix = "本次未能取得项目信息；查询于 " + date_text(row.get("checked_at"))
    if isinstance(data, dict):
        flags = []
        if type(data.get("archived")) is bool:
            flags.append("已归档" if data["archived"] else "未归档")
        else:
            flags.append("归档状态未记录")
        if data.get("disabled") is True:
            flags.append("已禁用")
        snapshot = "；".join(flags)
        if status != "ok":
            snapshot = "以下为旧信息：" + snapshot + "；上次查到 " + date_text(row.get("repository_last_success_at"))
        prefix += ("；" if prefix else "") + snapshot
        if detailed:
            actual = github_root(data.get("html_url"))
            label = "项目来源" if status == "ok" else "旧信息来源"
            if actual:
                prefix += "；" + label + "：[" + cell(actual) + "](<https://github.com/" + actual + ">)"
            else:
                prefix += "；" + label + "链接暂不可用"
            prefix += "；" + ("最近提交代码 " if status == "ok" else "旧信息中的代码提交时间 ") + date_text(data.get("pushed_at"))
    elif status == "ok":
        prefix += ("；" if prefix else "") + "暂无项目详情"
    return prefix


def release_observation(row):
    if row is None:
        return "暂无版本记录"
    status = row["release_status"]
    if status == "none":
        return "GitHub 未查到正式发布版；查询于 " + date_text(row.get("release_last_success_at") or row.get("checked_at"))
    data = row.get("release")
    if status == "error":
        prefix = "本次版本查询失败"
    elif status == "not_checked":
        prefix = "本次未查询版本"
    else:
        prefix = ""
    if isinstance(data, dict):
        tag = cell(data.get("tag_name"))
        link = release_url(data.get("html_url"))
        item = "[" + tag + "](<" + link + ">)" if link else tag + "（版本链接暂不可用）"
        if status != "ok":
            prefix += "；以下为旧版本信息："
        prefix += item + "；发布于 " + date_text(data.get("published_at"))
        prefix += "；查询于 " + date_text(row.get("release_last_success_at"))
    elif status == "ok":
        prefix = "暂无完整版本信息"
    else:
        prefix += "；暂无旧版本记录"
    if status != "ok":
        prefix += "；本次查询于 " + date_text(row.get("checked_at"))
    return prefix


def run_summary(state):
    run = state.get("last_run")
    if run is None:
        return "暂未取得版本信息。你可以先打开资料页，查看项目介绍和下载来源。"
    return ("最近查询：" + date_text(run.get("checked_at")) + "。本次已更新 " + str(run["ok_count"])
            + " 个项目的信息，另有 " + str(run["error_count"]) + " 个暂未更新；各项目的版本和日期见下表。")


def render(library, manifest, state):
    validate_manifest(library, manifest)
    validate_state(state)
    entities = {item["id"]: item for item in library}
    mapping = {entity_id: row["full_name"] for row in manifest["repositories"] for entity_id in row["entity_ids"]}
    excluded = {row["entity_id"]: row["reason"] for row in manifest["excluded"]}
    observations = {key.casefold(): value for key, value in state["repositories"].items()}
    catalog = ["# 工具与知识目录", "", "共 " + str(len(library)) + " 条资料。先按类型和平台找工具，点击名称查看用途、使用提示和相关来源。", "",
               "版本号可直接打开发布页面。“来源待核实”的资料目前只有其他目录的介绍，尚未确认对应项目；“已查阅官方资料”也不代表已经实测安装或兼容性。", "",
               "[返回首页](README.md) · [查看版本与项目更新](UPDATES.md)", ""]
    kinds = sorted({item["kind"] for item in library}, key=lambda kind: (list(KINDS).index(kind) if kind in KINDS else len(KINDS), kind))
    for kind in kinds:
        group = sorted((item for item in library if item["kind"] == kind), key=lambda item: (item["name"].casefold(), item["id"]))
        anchor = CATEGORY_ANCHORS.get(kind, re.sub(r"[^a-z0-9-]", "-", kind.lower()))
        catalog.extend(['<a id="' + anchor + '"></a>', "", "## " + cell(KINDS.get(kind, kind)) + "（" + str(len(group)) + "）", "",
                        "| 名称（查看详情） | 适用平台 | 最近查到的正式版 | 资料来源 | 项目状态 |",
                        "| --- | --- | --- | --- | --- |"])
        for entity in group:
            full_name = mapping.get(entity["id"])
            row = observations.get(full_name.casefold()) if full_name else None
            repo_text = repo_observation(row) if full_name else "请查看资料页中的来源"
            release_text = release_observation(row) if full_name else EXCLUSIONS[excluded[entity["id"]]]
            platforms = "、".join(cell(p) for p in entity["platforms"]) or "未记录或不适用"
            review = cell(REVIEW.get(entity["verification"].get("status"), "请查看资料页的来源说明"))
            catalog.append("| " + " | ".join([card_link(entity), platforms, release_text, review, repo_text]) + " |")
        catalog.append("")
    updates = ["# 版本与项目更新", "", "查看工具最近发布的版本，点击版本号前往下载与更新说明。", "",
               "[返回工具目录](CATALOG.md) · [返回首页](README.md)", "", run_summary(state), "",
               "这里列出 " + str(len(manifest["repositories"])) + " 个 GitHub 项目的信息。其他资料的版本或来源见[本页下方](#other-sources)。", "",
               "版本取自 GitHub 正式发布页（Release），不含草稿、预发布或仅有版本标签的记录，可能与应用商店版本不同。“暂无版本记录”不代表工具没有发布过版本。", "",
               "“旧信息”表示本次未能取得新信息，请留意旁边的日期。“已归档”表示作者将项目设为只读；未归档或近期提交过代码，并不保证仍在维护。选择版本时仍需查看设备要求。", "",
               "## 项目版本", "", "| 名称（查看详情） | GitHub 项目来源 | 最近查到的正式版 | 项目信息 |", "| --- | --- | --- | --- |"]
    for repo in sorted(manifest["repositories"], key=lambda item: (item["full_name"].casefold(), item["full_name"])):
        name = repo["full_name"]
        row = observations.get(name.casefold())
        links = "、".join(card_link(entities[entity_id]) for entity_id in sorted(repo["entity_ids"]))
        repo_link = "[" + cell(name) + "](<https://github.com/" + name + ">)"
        updates.append("| " + " | ".join([links, repo_link, release_observation(row), repo_observation(row, detailed=True)]) + " |")
    updates.extend(["", '<a id="other-sources"></a>', "", "## 其他工具与资料", "",
                    "以下 " + str(len(excluded)) + " 条资料暂未在本页列出版本。点击名称，查看项目介绍及相关来源。", "",
                    "| 名称（查看详情） | 去哪里查看版本或来源 |", "| --- | --- |"])
    for entity_id in sorted(excluded):
        updates.append("| " + card_link(entities[entity_id]) + " | " + EXCLUSIONS[excluded[entity_id]] + " |")
    return "\n".join(catalog).rstrip() + "\n", "\n".join(updates).rstrip() + "\n"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=ROOT / "data/upstream.json")
    parser.add_argument("--catalog-output", type=Path, default=ROOT / "CATALOG.md")
    parser.add_argument("--updates-output", type=Path, default=ROOT / "UPDATES.md")
    parser.add_argument("--write-manifest", action="store_true", help="rebuild manifest strictly from entity.repository")
    args = parser.parse_args(argv)
    library = read_json(ROOT / LIBRARY_PATH)
    if args.write_manifest:
        manifest = make_manifest(library)
    else:
        manifest = read_json(ROOT / MANIFEST_PATH)
    state = read_json(args.state) if args.state.exists() else {"schema_version": 1, "last_run": None, "repositories": {}}
    catalog, updates = render(library, manifest, state)
    for entity in library:
        if not (ROOT / "export/cards" / (entity["id"] + CARD_SUFFIX)).is_file():
            raise ValueError("missing original card: " + entity["id"])
    if args.write_manifest:
        (ROOT / MANIFEST_PATH).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / MANIFEST_PATH).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    for path, content in ((args.catalog_output, catalog), (args.updates_output, updates)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    print("Rendered %d entities; %d monitored repositories; %d exclusions." % (len(library), len(manifest["repositories"]), len(manifest["excluded"])))


if __name__ == "__main__":
    main()
