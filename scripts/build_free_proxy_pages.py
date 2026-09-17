"""Build dated reader pages from public-feed observations, without node credentials."""
import argparse
from datetime import datetime, timedelta, timezone
import html
import json
import os
from pathlib import Path
import re
import tempfile

import free_proxy_sources

ROOT = Path(__file__).resolve().parents[1]
BEIJING = timezone(timedelta(hours=8))
DAY_NAME = re.compile(r"\d{4}-\d{2}-\d{2}\.md\Z")
FORMATS = {"base64_uri": "通用订阅（Base64）", "plain_uri": "节点链接列表", "plain_proxy": "代理地址列表"}
PROTOCOLS = {"http": "HTTP", "https": "HTTPS", "socks": "SOCKS", "socks4": "SOCKS4", "socks5": "SOCKS5",
             "ss": "Shadowsocks", "ssr": "ShadowsocksR", "vmess": "VMess", "vless": "VLESS",
             "trojan": "Trojan", "hysteria": "Hysteria", "hysteria2": "Hysteria2", "tuic": "TUIC"}


def cell(value):
    text = re.sub(r"[\x00-\x1f\x7f\u2028\u2029]+", " ", str(value))
    text = html.escape(" ".join(text.split()), quote=True)
    for char in "\\|`[]*_{}()":
        text = text.replace(char, "&#%d;" % ord(char))
    return text


def local_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(BEIJING)


def display_time(value):
    return local_time(value).strftime("%Y-%m-%d %H:%M") + "（北京时间）" if value else "暂无记录"


def aligned_feeds(manifest, state):
    free_proxy_sources.validate_manifest(manifest)
    free_proxy_sources.validate_state(state)
    expected = {feed["id"] for source in manifest["sources"] for feed in source["feeds"]}
    if set(state["feeds"]) != expected:
        raise ValueError("state_manifest_coverage_mismatch")
    rows = []
    for source in manifest["sources"]:
        for feed in source["feeds"]:
            row = state["feeds"][feed["id"]]
            if (row["source_id"] != source["id"] or row["url"] != feed["url"] or row["format"] != feed["format"]
                    or row["checked_at"] != state["last_run"]["checked_at"]):
                raise ValueError("state_manifest_identity_mismatch")
            if feed["format"] == "plain_proxy" and row.get("protocol_counts"):
                if set(row["protocol_counts"]) != {feed["protocol"]}:
                    raise ValueError("state_manifest_protocol_mismatch")
            rows.append((source, feed, row))
    if not any(row["status"] == "ok" for _, _, row in rows):
        raise ValueError("no_current_source_results")
    return rows


def render_day(manifest, state):
    rows = aligned_feeds(manifest, state)
    date = local_time(state["last_run"]["checked_at"]).date().isoformat()
    lines = ["# " + date + " 免费节点与代理", "",
             "[返回日期目录](README.md) · [选择客户端](../README.md)", "",
             "整理时间：" + display_time(state["last_run"]["checked_at"]) + "。", "",
             "按订阅格式选择来源，点击链接可打开或复制原始订阅地址。", ""]
    for category, title, tip in (
        ("subscription", "免费节点订阅", "通用订阅与 Clash YAML 是不同格式，请按客户端支持的格式导入。"),
        ("proxy_list", "HTTP / SOCKS 代理列表", "这类地址用于支持 HTTP 或 SOCKS 代理的工具，与 V2Ray 节点订阅分别使用。"),
    ):
        current = [(source, feed, row) for source, feed, row in rows
                   if source.get("category", "subscription") == category and row["status"] == "ok"]
        if not current:
            continue
        lines += ["## " + title, "", tip, "",
                  "| 来源 | 订阅格式 | 包含协议 | 条目数 | 订阅入口 |",
                  "| --- | --- | --- | ---: | --- |"]
        for source, feed, row in current:
            source_link = "[" + cell(source["name"]) + "](" + source["repository"] + ")"
            label = feed["label"]
            format_label = FORMATS[feed["format"]]
            if category == "proxy_list":
                format_label = "HTTP / SOCKS 地址" if feed["format"] == "plain_uri" else PROTOCOLS[feed["protocol"]] + " 地址"
            protocols = "、".join(PROTOCOLS.get(key, key) for key in sorted(row["protocol_counts"]))
            lines.append("| " + " | ".join((source_link, cell(format_label), cell(protocols), str(row["unique_count"]),
                                            "[" + cell(label) + "](" + feed["url"] + ")")) + " |")
        lines.append("")
    failed = [(source, feed, row) for source, feed, row in rows if row["status"] != "ok"]
    if failed:
        lines += ["## 本次暂未更新的来源", "", "以下来源本次没有取得有效内容，可前往项目页面查看。", "",
                  "| 来源 | 订阅 | 上次取得内容的时间 |", "| --- | --- | --- |"]
        for source, feed, row in failed:
            lines.append("| [" + cell(source["name"]) + "](" + source["repository"] + ") | " + cell(feed["label"])
                         + " | " + display_time(row.get("last_success_at")) + " |")
        lines.append("")
    lines += ["## 使用提示", "",
              "条目数已在各订阅内去重，不同来源之间可能重复；这里只确认订阅内容可解析，尚未实测节点连通性。", "",
              "本页记录当天整理结果，订阅链接由来源维护，会继续更新；历史页面不保存当天的节点配置。", ""]
    return date, "\n".join(lines)


def valid_dates(filenames):
    dates = set()
    for filename in filenames:
        if DAY_NAME.fullmatch(filename):
            try:
                datetime.strptime(filename[:-3], "%Y-%m-%d")
            except ValueError:
                continue
            dates.add(filename[:-3])
    return sorted(dates, reverse=True)


def render_index(filenames):
    dates = valid_dates(filenames)
    lines = ["# 每日免费节点与代理", "",
             "按日期查看公开节点订阅和 HTTP / SOCKS 代理来源，最新日期在前。", "",
             "[返回翻墙指南](../README.md)", ""]
    if dates:
        lines += ["**最新一期：[" + dates[0] + "](" + dates[0] + ".md)**", "", "## 按日期浏览", ""]
        lines.extend("- [" + date + "](" + date + ".md)" for date in dates)
    else:
        lines.append("暂无日期记录。")
    return "\n".join(lines) + "\n"


def atomic_text(path, text):
    raw = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == raw:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".page-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def write_pages(manifest, state, output_dir):
    date, page = render_day(manifest, state)
    output_dir = Path(output_dir)
    existing = [path.name for path in output_dir.glob("*.md")] if output_dir.is_dir() else []
    index = render_index([*existing, date + ".md"])
    atomic_text(output_dir / (date + ".md"), page)
    atomic_text(output_dir / "README.md", index)
    return date


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "config/free-proxy-sources.json")
    parser.add_argument("--state", type=Path, default=ROOT / "data/free-proxy-sources.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "free-proxies")
    args = parser.parse_args(argv)
    try:
        date = write_pages(free_proxy_sources.read_json(args.manifest), free_proxy_sources.read_json(args.state), args.output_dir)
        print("Dated reader page and index generated: " + date)
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print("Cannot generate dated pages: invalid or unavailable source observations.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
