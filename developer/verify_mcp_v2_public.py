"""Read-only public acceptance checks for Fanqiang Guide MCP 2.0.

Only public selectors and synthetic invalid values are sent. No device setup,
node testing, subscriptions, credentials, diagnostic reports or writes occur.
--book selects the local canonical v2 book; its sibling v1.1 book and evidence,
and ../answer-rules.ilang, are the comparison sources.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

VERSION = "2.0.0"
BOOK_URI = "fanqiang://books/autosetup"
RULES_URI = "fanqiang://rules/answer"
TEMPLATE = "fanqiang://books/{book_id}"
OLD_BOOK = "fanqiang-autosetup-v1.1.ilang.md"
OLD_SHA = "96425a3f6bf75c7c9ecbfdc657be74b053df2f323ba6cf5a5a621064bbabf98a"
MAX_BYTES = 5 * 1024 * 1024
USER_AGENT = "Fanqiang-MCP-v2-Public-Acceptance/1.0"
SYNTHETIC = "SYNTHETIC_NONPRIVATE_REJECTION_PROBE_93472"
DISCOVERY_PATHS = (
    "/ai/", "/ai/index.md", "/ai/index.ilang",
    "/ai/skills/library-lookup/SKILL.md", "/llms.txt",
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def fetch(origin, path, *, body=None, compressed=False):
    headers = {"User-Agent": USER_AGENT,
               "Accept-Encoding": "gzip" if compressed else "identity"}
    if body is not None:
        headers.update({"Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "MCP-Protocol-Version": "2025-11-25"})
        body = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(origin + path, data=body, headers=headers)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        response = opener.open(request, timeout=25)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Public response exceeds verification budget")
        result_headers = {key.lower(): value for key, value in response.headers.items()}
        if result_headers.get("content-encoding") == "gzip":
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as zipped:
                raw = zipped.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Decoded response exceeds verification budget")
        return response.status, raw, result_headers


def timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.utcoffset() is not None
    except ValueError:
        return False


def payload(result):
    if result.isError is True:
        raise AssertionError("MCP tool returned isError")
    content = json.loads(result.content[0].text)
    if result.structuredContent is not None and result.structuredContent != content:
        raise AssertionError("MCP structured and text payloads differ")
    return result.structuredContent or content


def stable_query(value):
    """Source checks may refresh between transports; compare the query snapshot."""
    value = json.loads(json.dumps(value))
    for item in value["items"]:
        item.pop("source_freshness", None)
    return value


async def verify(args, evidence):
    expected = args.book.read_bytes()
    expected_rules = (args.book.parent.parent / "answer-rules.ilang").read_text(encoding="utf-8")
    expected_old = (args.book.parent / OLD_BOOK).read_bytes()
    expected_validation = json.loads(args.book.with_name(
        args.book.name.replace(".ilang.md", ".evidence.json")).read_text(encoding="utf-8"))
    digest = hashlib.sha256(expected).hexdigest()
    evidence.update({"book_sha256": digest, "book_bytes": len(expected)})
    rules_block = expected_rules[
        expected_rules.index("::MODULE{ANSWER_RULES}"):
        expected_rules.rindex("::ILANG::COMPLETE::")].rstrip()

    def expect(name, condition):
        evidence["last_check"] = name
        if not condition:
            raise AssertionError(name)
        evidence["checks"].append(name)

    def get_json(path, name, *, no_store=True):
        evidence["last_check"] = name + "_fetch"
        status, raw, headers = fetch(args.origin, path)
        expect(name + "_status", status == 200)
        if no_store:
            expect(name + "_no_store", "no-store" in headers.get("cache-control", "").lower())
            expect(name + "_not_edge_hit", headers.get("cf-cache-status", "").upper() not in {"HIT", "STALE", "UPDATING"})
        return json.loads(raw)

    expect("local_book_v2", b"[VERSION:2.0]" in expected and args.book.name == "fanqiang-autosetup-v2.0.ilang.md")
    expect("local_rules_complete", expected_rules.count("[MUST]") == 9)
    expect("local_legacy_digest", hashlib.sha256(expected_old).hexdigest() == OLD_SHA)
    expect("local_evidence_book_digest", expected_validation["book_sha256"] == digest)

    query_params = {"kind": "client", "platform": "android", "protocol": "VLESS-Reality",
                    "feature": "tun", "os_version": "14", "limit": 3}
    async with httpx.AsyncClient(timeout=httpx.Timeout(25), follow_redirects=False,
            headers={"User-Agent": USER_AGENT}) as http_client:
        async with streamable_http_client(args.origin + "/mcp", http_client=http_client) as (read, write, _):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                init = await session.initialize()
                expect("mcp_version", init.serverInfo.version == VERSION)
                expect("mcp_complete_answer_rules", rules_block in init.instructions)
                expect("mcp_capabilities", all(getattr(init.capabilities, key, None) is not None
                       for key in ("tools", "resources", "prompts")))
                tools = (await session.list_tools()).tools
                expect("mcp_tools_exact", {tool.name for tool in tools} == {"search", "get", "query"})
                query_tool = next(tool for tool in tools if tool.name == "query")
                expect("query_strict_schema", query_tool.inputSchema.get("additionalProperties") is False
                    and set(query_tool.inputSchema["properties"]) ==
                    {"kind", "platform", "protocol", "feature", "os_version", "include_unknown", "limit", "offset"})
                expect("query_readonly", query_tool.annotations.readOnlyHint is True
                    and query_tool.annotations.destructiveHint is False)
                strict = payload(await session.call_tool("query", query_params))
                expect("query_AND_expansion", strict["filter_operator"] == "AND"
                    and strict["filters"]["protocol"] == "vless"
                    and set(strict["filters"]["required_features"]) == {"reality", "tun"})
                expect("exact_os_not_certified", strict["total"] == 0 and strict["excluded_unknown"] > 0
                    and bool(strict["notices"]))
                candidates = payload(await session.call_tool("query", {**query_params, "include_unknown": True}))
                expect("unknown_candidates_available", candidates["total"] == strict["excluded_unknown"]
                    and candidates["excluded_unknown"] == 0 and bool(candidates["items"]))
                expect("unknown_candidates_not_passes", all(
                    item["kind"] == "client" and item["match_status"] == "unknown" and item["combination_status"] == "not_tested"
                    and any(c["field"] == "os_version" and c["state"] == "unknown" for c in item["criteria"])
                    for item in candidates["items"]))
                expect("candidate_ordering", candidates["ordering"] ==
                    ["platform_matched_first", "matched_condition_count_desc", "id_asc"])
                expect("query_dates_semantics", candidates["date_semantics"] == {
                    "last_updated": "knowledge_record_updated_at",
                    "checked_at": "record_source_review_date",
                    "sources_checked_at": "specific_evidence_review_date"})
                expect("candidate_freshness_scope", all(
                    item["source_freshness"]["scope"] == "repository_metadata_only"
                    and item["source_freshness"]["does_not_revalidate_compatibility"] is True
                    and "source_checked_at" in item["source_freshness"]
                    and "last_attempt_at" in item["source_freshness"] for item in candidates["items"]))
                ident = candidates["items"][0]["id"]
                old_get = payload(await session.call_tool("get", {"id": ident}))["item"]
                expect("old_get_preserves_candidate_id", old_get["id"] == ident and bool(old_get["source_url"]))
                expect("record_and_source_dates_separate", old_get["last_updated"] == old_get.get("updated_at")
                    and candidates["items"][0]["checked_at"] == old_get.get("verification", {}).get("checked_at")
                    and candidates["items"][0]["last_updated"] == old_get.get("updated_at"))
                search = payload(await session.call_tool("search", {"query": "sing-box", "limit": 2}))
                expect("old_search_works", bool(search["items"]))

                resources = (await session.list_resources()).resources
                expect("resource_catalog", {BOOK_URI, RULES_URI} <= {str(resource.uri) for resource in resources})
                templates = (await session.list_resource_templates()).resourceTemplates
                expect("book_resource_template", TEMPLATE in {str(template.uriTemplate) for template in templates})
                resource = await session.read_resource(BOOK_URI)
                expect("book_resource_mime", len(resource.contents) == 1
                    and resource.contents[0].mimeType == "application/json")
                book = json.loads(resource.contents[0].text)
                manifest = {key: value for key, value in book.items() if key != "content"}
                expect("resource_exact_book", book["content"].encode("utf-8") == expected
                    and book["sha256"] == digest and book["byte_length"] == len(expected)
                    and book["version"] == "2.0" and book["book_id"] == "autosetup")
                expect("resource_metadata", next(r for r in resources if str(r.uri) == BOOK_URI).meta == manifest)
                expect("book_execution_scope", book["executor"] == "user_agent"
                    and book["validation"]["mobile_hotspot"]["status"] == "not_tested")
                rules_resource = await session.read_resource(RULES_URI)
                expect("rules_resource_exact", len(rules_resource.contents) == 1
                    and rules_resource.contents[0].text == expected_rules
                    and rules_resource.contents[0].mimeType == "text/plain")
                rules_manifest = next(r for r in resources if str(r.uri) == RULES_URI).meta
                expect("rules_metadata_digest", rules_manifest["sha256"] ==
                    hashlib.sha256(expected_rules.encode("utf-8")).hexdigest()
                    and rules_manifest["rule_count"] == 9)
                prompts = (await session.list_prompts()).prompts
                expect("setup_prompt_discovered", any(prompt.name == "setup_device" and not prompt.arguments for prompt in prompts))
                prompt = await session.get_prompt("setup_device", {})
                expect("setup_prompt_three_messages", len(prompt.messages) == 3)
                expect("setup_prompt_full_rules", prompt.messages[1].content.text == expected_rules)
                expect("setup_prompt_full_book", prompt.messages[2].content.text.encode("utf-8") == expected
                    and digest in prompt.messages[0].content.text)
                expect("setup_prompt_scope", "not extra authorization" in prompt.messages[0].content.text)
                adapter = payload(await session.call_tool("get_setup_book", {}))
                expect("hidden_legacy_tool_adapter", adapter == book)

    catalog = get_json("/api/agent/books", "http_books")
    expect("http_catalog_contract", catalog["resource_template"] == TEMPLATE and manifest in catalog["books"])
    expect("http_book_exact", get_json("/api/agent/books/autosetup", "http_book") == book)
    expect("http_legacy_book_exact", get_json("/api/agent/setup-book", "http_legacy_book") == book)
    encoded = urllib.parse.urlencode({**query_params, "include_unknown": "true"})
    http_query = get_json("/api/agent/query?" + encoded, "http_query")
    expect("http_query_matches_mcp", stable_query(http_query) == stable_query(candidates))
    freshness = get_json("/api/agent/freshness", "http_freshness")
    expect("freshness_snapshot_valid", timestamp(freshness["generated_at"])
        and freshness["snapshot_load_status"] == "ok" and bool(freshness["records"]))
    expect("freshness_states_and_limits", all(
        item["status"] in {"current", "stale", "unknown", "unmonitored"}
        and item["does_not_revalidate_compatibility"] is True
        for item in freshness["records"].values()))
    expect("freshness_has_successful_checks", any(
        item["status"] == "current" and timestamp(item.get("source_checked_at"))
        for item in freshness["records"].values()))
    health = get_json("/api/agent/health", "http_health")
    expect("health_version", health["status"] == "ok" and health["version"] == VERSION)
    expect("health_freshness_counts", health["source_freshness"]["record_count"] == len(freshness["records"])
        and health["source_freshness"]["knowledge_facts_are_not_revalidated_by_release_checks"] is True)

    static_catalog = get_json("/ai/books/index.json", "static_catalog", no_store=False)
    expect("static_catalog_matches", static_catalog == catalog)
    static_manifest = get_json("/ai/books/autosetup.json", "static_manifest", no_store=False)
    expect("static_manifest_matches", static_manifest == manifest)
    public_evidence = get_json("/ai/books/" + args.book.name.replace(".ilang.md", ".evidence.json"),
                              "static_evidence", no_store=False)
    expect("public_evidence_exact", public_evidence == expected_validation
        and public_evidence["validation_summary"] == book["validation"])
    for compressed in (False, True):
        status, raw, _ = fetch(args.origin, "/ai/books/" + args.book.name, compressed=compressed)
        expect("book_download_" + ("gzip" if compressed else "identity"), status == 200 and raw == expected)
    status, old_raw, _ = fetch(args.origin, "/ai/books/" + OLD_BOOK)
    expect("legacy_v1_1_download_unchanged", status == 200 and old_raw == expected_old)
    status, raw, _ = fetch(args.origin, "/ai/answer-rules.ilang")
    expect("static_rules_exact", status == 200 and raw == expected_rules.encode("utf-8"))
    for path in DISCOVERY_PATHS:
        status, raw, _ = fetch(args.origin, path)
        text = html.unescape(raw.decode("utf-8"))
        expect("static_discovery:" + path, status == 200 and all(marker in text for marker in (
            BOOK_URI, TEMPLATE, RULES_URI, args.book.name, "query")))
        if path in ("/ai/", "/ai/index.md", "/ai/index.ilang"):
            expect("static_complete_rules:" + path, rules_block in text)
    # Published discovery documents may use the existing CDN metadata cache.
    # Their version and manifest equality checks remain mandatory below.
    card = get_json("/.well-known/mcp/server-card.json", "server_card", no_store=False)
    expect("server_card_v2", card["serverInfo"]["version"] == VERSION
        and {"tools", "resources", "prompts"} <= set(card["capabilities"]))
    expect("server_card_manifests", card["setupBook"] == manifest and card["books"] == catalog
        and card["answerRules"] == rules_manifest)
    spec = get_json("/openapi.json", "openapi", no_store=False)
    expect("openapi_v2_paths", spec["info"]["version"] == VERSION and {
        "/api/agent/query", "/api/agent/books", "/api/agent/books/{book_id}",
        "/api/agent/freshness", "/api/agent/search", "/api/agent/item"} <= set(spec["paths"]))

    probes = (
        ("method_array", {"method": [SYNTHETIC], "params": {}}, -32600),
        ("resource_object", {"method": "resources/read", "params": {"uri": {"value": SYNTHETIC}}}, -32602),
        ("resource_params_string", {"method": "resources/read", "params": SYNTHETIC}, -32602),
        ("query_extra", {"method": "tools/call", "params": {"name": "query", "arguments": {SYNTHETIC: "x"}}}, -32602),
        ("query_meta", {"method": "tools/call", "params": {"name": "query", "_meta": {"progressToken": [SYNTHETIC]}}}, -32602),
        ("unknown_book", {"method": "resources/read", "params": {"uri": "fanqiang://books/" + SYNTHETIC}}, -32602),
        ("prompt_extra", {"method": "prompts/get", "params": {"name": "setup_device", "arguments": {"extra": SYNTHETIC}}}, -32602),
    )
    for name, partial, code in probes:
        status, raw, _ = fetch(args.origin, "/mcp", body={"jsonrpc": "2.0", "id": 1934, **partial})
        expect("fixed_rejection:" + name, status == 200 and SYNTHETIC.encode() not in raw
            and json.loads(raw).get("error", {}).get("code") == code)
    for name, path, expected_status in (
        ("query", "/api/agent/query?platform=" + SYNTHETIC, 400),
        ("query_kind", "/api/agent/query?kind=" + SYNTHETIC, 400),
        ("books", "/api/agent/books?value=" + SYNTHETIC, 400),
        ("unknown_book", "/api/agent/books/" + SYNTHETIC, 404),
    ):
        status, raw, _ = fetch(args.origin, path)
        expect("http_fixed_rejection:" + name, status == expected_status and SYNTHETIC.encode() not in raw
            and json.loads(raw).get("error") in {"invalid_parameter", "not_found"})

    evidence["ok"] = True
    evidence["scope"] = "Public read-only interface and byte-consistency acceptance; no target-device or hotspot execution"
    evidence["checks_passed"] = len(evidence["checks"])
    evidence["finished_at"] = datetime.now(timezone.utc).isoformat()


def origin(value):
    value = value.rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    allowed = parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
    if (not allowed or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError("Use an HTTPS origin without credentials/path/query, or a loopback HTTP origin")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", type=origin, default="https://fanqiang.guide")
    parser.add_argument("--book", type=Path, required=True, help="Canonical v2 book with adjacent evidence/legacy book and ../answer-rules.ilang")
    parser.add_argument("--output", type=Path, required=True, help="New private JSON evidence file; never overwrites")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must not already exist")
    if not args.output.parent.is_dir():
        parser.error("--output parent directory must exist")
    evidence = {"checked_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.origin + "/mcp", "ok": False, "checks": []}
    try:
        asyncio.run(verify(args, evidence))
    except Exception as error:
        # No response bodies or exception text are copied into failure reports.
        evidence.update({"ok": False, "error_type": type(error).__name__,
            "checks_passed": len(evidence["checks"]),
            "finished_at": datetime.now(timezone.utc).isoformat()})
    with args.output.open("x", encoding="utf-8") as target:
        target.write(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    args.output.chmod(0o600)
    print(json.dumps({"ok": evidence["ok"], "checks_passed": evidence["checks_passed"],
                      "last_check": evidence.get("last_check"), "output": str(args.output)}))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
