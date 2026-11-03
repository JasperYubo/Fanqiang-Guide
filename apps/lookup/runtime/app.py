#!/usr/bin/env python3
"""Public lookup with the maintained official MCP Python SDK."""
from __future__ import annotations
import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import parse_qs

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn

from setup_book import (BOOK_RESOURCE_URI, BOOK_TITLE, NO_ARGUMENTS_SCHEMA,
    SETUP_BOOK_DESCRIPTION, SETUP_PROMPT_DESCRIPTION, setup_book_manifest, setup_book_payload,
    setup_book_prompt_intro, BOOK_REGISTRY, BOOK_RESOURCE_TEMPLATE,
    RULES_RESOURCE_URI, answer_rules_text, answer_rules_manifest, book_catalog, book_payload)

from library_query import normalize_query, QueryValidationError, QUERY_INPUT_SCHEMA

from library_core import (Library, LookupError, VERSION, ORIGIN, MAX_BODY, MAX_RESPONSE,
    MAX_PATH, SOURCE_REVISION, SEARCH_DESCRIPTION, GET_DESCRIPTION, INSTRUCTIONS,
    encode, openapi, server_card, QUERY_DESCRIPTION)


class Guard:
    """HTTP bounds around the SDK; JSON-RPC remains entirely SDK-managed."""
    def __init__(self, app, allowed_origins):
        self.app, self.origins, self.active = app, set(allowed_origins), 0

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = [(k.lower(), v) for k, v in scope.get("headers", [])]
        origins = [v.decode("latin1") for k, v in headers if k == b"origin"]
        async def error(status, code, extra=None):
            await JSONResponse({"error": code}, status_code=status,
                headers={"Cache-Control": "no-store", **(extra or {})})(scope, receive, send)
        if len(origins) > 1 or (origins and origins[0] not in self.origins):
            return await error(403, "invalid_origin")
        hosts = [v.decode("latin1") for k, v in headers if k == b"host"]
        if len(hosts) != 1 or not (hosts[0] in ("fanqiang.guide", "www.fanqiang.guide") or
                re.fullmatch(r"(127\.0\.0\.1|localhost):[0-9]{1,5}", hosts[0])):
            return await error(400, "invalid_host")
        if len(scope.get("raw_path", b"")) + len(scope.get("query_string", b"")) > MAX_PATH:
            return await error(414, "uri_too_long")
        path = scope.get("path", "")
        if path == "/mcp" and scope["method"] in ("GET", "HEAD", "DELETE"):
            return await error(405, "method_not_allowed", {"Allow": "POST, OPTIONS"})
        if self.active >= 8:
            return await error(503, "busy", {"Retry-After": "1"})
        if scope["method"] == "OPTIONS":
            methods = "POST, OPTIONS" if path == "/mcp" else "GET, HEAD, OPTIONS"
            await JSONResponse({}, headers={"Access-Control-Allow-Origin": origins[0] if origins else ORIGIN,
                "Vary": "Origin", "Access-Control-Allow-Methods": methods,
                "Access-Control-Allow-Headers": "Content-Type, Accept, MCP-Protocol-Version",
                "Cache-Control": "no-store"})(scope, receive, send)
            return
        self.active += 1
        start, chunks, size = None, [], 0
        async def bounded_send(message):
            nonlocal start, size
            if message["type"] == "http.response.start":
                start = dict(message)
                start["headers"] = [(k, v) for k, v in start.get("headers", [])
                    if k.lower() not in (b"cache-control", b"access-control-allow-origin", b"vary")]
                start["headers"].extend([(b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"), (b"vary", b"Origin")])
                if origins:
                    start["headers"].append((b"access-control-allow-origin", origins[0].encode()))
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                size += len(chunk)
                if size > MAX_RESPONSE:
                    raise LookupError("Result exceeds response budget", 500, "result_limit")
                chunks.append(chunk)
                if not message.get("more_body", False):
                    await send(start)
                    await send({"type": "http.response.body", "body": b"".join(chunks), "more_body": False})
        try:
            await asyncio.wait_for(self.app(scope, receive, bounded_send), timeout=15)
        except LookupError:
            await error(500, "result_limit")
        except asyncio.TimeoutError:
            await error(408, "request_timeout")
        finally:
            self.active -= 1


class SetupBookInputGuard:
    """Reject private input to the two no-argument interfaces before SDK logging.

    This narrow preflight does not execute JSON-RPC or validate legacy tools.
    The enclosing Guard supplies the deadline and concurrency/response bounds.
    Valid and unrelated requests are replayed unchanged to the official SDK.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/mcp" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_BODY:
                return await JSONResponse({"error": "request_too_large"}, status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        try:
            request = json.loads(body)
        except (ValueError, UnicodeError):
            request = None
        if isinstance(request, dict):
            params = request.get("params")
            if not isinstance(request.get("method"), str):
                valid_id = type(request.get("id")) in (str, int)
                return await JSONResponse({"jsonrpc": "2.0", "id": request.get("id") if valid_id else None,
                    "error": {"code": -32600, "message": "Invalid public lookup request envelope"}})(scope, receive, send)
            if request.get("method") in {"resources/read", "tools/call", "prompts/get"} and not isinstance(params, dict):
                valid_id = type(request.get("id")) in (str, int)
                return await JSONResponse({"jsonrpc": "2.0", "id": request.get("id") if valid_id else None,
                    "error": {"code": -32602, "message": "Invalid public lookup parameters"}})(scope, receive, send)
            # Resource identifiers and structured query fields are public selectors.
            # Reject malformed values before SDK error formatting can reflect them.
            if isinstance(params, dict) and (
                    request.get("method") == "resources/read" or
                    (request.get("method") == "tools/call" and params.get("name") == "query")):
                valid_id = type(request.get("id")) in (str, int)
                code, message = -32602, "Invalid public lookup parameters; do not send private data"
                valid = (request.get("jsonrpc") == "2.0" and valid_id and
                         not set(request) - {"jsonrpc", "id", "method", "params"})
                if not valid:
                    code, message = -32600, "Invalid public lookup request envelope"
                elif request.get("method") == "resources/read":
                    valid = (not set(params) - {"uri", "_meta"} and
                        isinstance(params.get("uri"), str) and params.get("uri") in {RULES_RESOURCE_URI, *("fanqiang://books/" + key for key in BOOK_REGISTRY)})
                else:
                    valid = not set(params) - {"name", "arguments", "_meta"}
                    if valid:
                        try:
                            normalize_query(params.get("arguments", {}))
                        except QueryValidationError:
                            valid = False
                metadata = params.get("_meta")
                if metadata is not None and (type(metadata) is not dict or
                        (metadata.get("progressToken") is not None and
                        type(metadata["progressToken"]) not in (str, int))):
                    valid = False
                if not valid:
                    return await JSONResponse({"jsonrpc": "2.0",
                        "id": request.get("id") if valid_id else None,
                        "error": {"code": code, "message": message}})(scope, receive, send)
            if isinstance(params, dict) and (
                    (request.get("method") == "tools/call" and params.get("name") == "get_setup_book") or
                    (request.get("method") == "prompts/get" and params.get("name") == "setup_device")):
                # Validate only the recognized new request envelopes. Invalid
                # protocol values must not reach SDK error formatting, and an
                # invalid id must never be reflected as the error response id.
                valid_id = type(request.get("id")) in (str, int)
                if (request.get("jsonrpc") != "2.0" or not valid_id or
                        set(request) - {"jsonrpc", "id", "method", "params"}):
                    return await JSONResponse({
                        "jsonrpc": "2.0", "id": request.get("id") if valid_id else None,
                        "error": {"code": -32600,
                            "message": "Invalid setup-book request envelope"},
                    })(scope, receive, send)
                arguments = params.get("arguments")
                metadata = params.get("_meta")
                # Standard progress metadata may be present, but malformed values
                # must not reach SDK validation logs either.
                bad_metadata = metadata is not None and (
                    type(metadata) is not dict or
                    (metadata.get("progressToken") is not None and
                     type(metadata["progressToken"]) not in (str, int)))
                if (set(params) - {"name", "arguments", "_meta"} or bad_metadata or
                        (arguments is not None and (type(arguments) is not dict or arguments))):
                    return await JSONResponse({
                        "jsonrpc": "2.0", "id": request.get("id"),
                        "error": {"code": -32602,
                            "message": "This setup-book interface accepts no arguments; do not send private data"},
                    })(scope, receive, send)
        replayed = False
        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()
        return await self.app(scope, replay, send)


class SetupBookMCP(FastMCP):
    """Strict empty arguments only for the new public book interfaces.

    FastMCP's compatibility conversion permits extra tool arguments by default.
    Public SDK handlers are overridden here so rejected values never reach
    Pydantic error formatting or the prompt manager's exception logger.
    """
    @staticmethod
    def _no_arguments(arguments):
        if arguments is not None and arguments != {}:
            raise ValueError("This setup-book interface accepts no arguments; do not send private data")

    async def list_tools(self):
        tools = [tool for tool in await super().list_tools() if tool.name != "get_setup_book"]
        for tool in tools:
            if tool.name == "query":
                tool.inputSchema = QUERY_INPUT_SCHEMA
        return tools

    async def call_tool(self, name, arguments):
        if name == "get_setup_book":
            self._no_arguments(arguments)
        elif name == "query":
            normalize_query(arguments)
        return await super().call_tool(name, arguments)

    async def get_prompt(self, name, arguments=None):
        if name == "setup_device":
            self._no_arguments(arguments)
        return await super().get_prompt(name, arguments)


def create_app(library, allowed_origins=()):
    origins = [ORIGIN, "https://www.fanqiang.guide", *allowed_origins]
    mcp = SetupBookMCP("guide.fanqiang/library-lookup", instructions=INSTRUCTIONS, website_url=ORIGIN,
        stateless_http=True, json_response=True, streamable_http_path="/mcp",
        max_request_body_size=MAX_BODY, log_level="ERROR",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=["fanqiang.guide", "www.fanqiang.guide", "127.0.0.1:*", "localhost:*"],
            allowed_origins=origins))
    # FastMCP v1 has no version argument; its underlying official Server owns this field.
    mcp._mcp_server.version = VERSION
    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
        idempotentHint=True, openWorldHint=False)

    @mcp.tool(name="search", description=SEARCH_DESCRIPTION, annotations=annotations, structured_output=True)
    def search(query: Annotated[str, Field(max_length=160)] = "",
               platform: Annotated[str, Field(max_length=64)] = "",
               kind: Annotated[str, Field(max_length=64)] = "",
               verification: Annotated[str, Field(max_length=64)] = "",
               limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 10,
               offset: Annotated[int, Field(strict=True, ge=0, le=10000)] = 0) -> dict[str, Any]:
        return library.search({"query": query, "platform": platform, "kind": kind,
            "verification": verification, "limit": limit, "offset": offset})

    @mcp.tool(name="get", description=GET_DESCRIPTION, annotations=annotations, structured_output=True)
    def get(id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9._-]*$")]) -> dict[str, Any]:
        return library.get({"id": id})

    @mcp.tool(name="query", description=QUERY_DESCRIPTION, annotations=annotations, structured_output=True)
    def structured_query(platform: Annotated[str | None, Field(max_length=32)] = None,
            kind: Annotated[str | None, Field(max_length=32)] = None,
            protocol: Annotated[str | None, Field(max_length=32)] = None,
            feature: Annotated[str | None, Field(max_length=32)] = None,
            os_version: Annotated[str | None, Field(max_length=32)] = None,
            include_unknown: bool = False,
            limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 10,
            offset: Annotated[int, Field(strict=True, ge=0, le=10000)] = 0) -> dict[str, Any]:
        return library.query({"platform": platform, "kind": kind, "protocol": protocol, "feature": feature,
            "os_version": os_version, "include_unknown": include_unknown, "limit": limit, "offset": offset})

    # Hidden compatibility adapter for already copied v1 requests.
    @mcp.tool(name="get_setup_book", description=SETUP_BOOK_DESCRIPTION,
              annotations=annotations, structured_output=True)
    def get_setup_book() -> dict[str, Any]:
        return setup_book_payload()

    def resource_reader(book_id):
        def read() -> str:
            return encode(book_payload(book_id)).decode("utf-8")
        return read
    for book_id in sorted(BOOK_REGISTRY):
        metadata = book_payload(book_id)
        mcp.resource("fanqiang://books/" + book_id, name="book-" + book_id,
            title=metadata["title"], description=SETUP_PROMPT_DESCRIPTION,
            mime_type="application/json", meta={k: v for k, v in metadata.items() if k != "content"})(
                resource_reader(book_id))

    @mcp.resource(BOOK_RESOURCE_TEMPLATE, name="engineering-book",
                  description="Read a registered book_id from resources/list. No arbitrary path or URL.",
                  mime_type="application/json")
    def engineering_book(book_id: str) -> str:
        return encode(book_payload(book_id)).decode("utf-8")

    @mcp.resource(RULES_RESOURCE_URI, name="answer-rules", title="Complete public answer rules",
                  mime_type="text/plain", meta=answer_rules_manifest())
    def answer_rules() -> str:
        return answer_rules_text()

    @mcp.prompt(name="setup_device", title=BOOK_TITLE, description=SETUP_PROMPT_DESCRIPTION)
    def setup_device() -> list[dict[str, Any]]:
        payload = setup_book_payload()
        metadata = {key: value for key, value in payload.items() if key != "content"}
        introduction = setup_book_prompt_intro(metadata)
        return [
            {"role": "user", "content": {"type": "text", "text": introduction}},
            {"role": "user", "content": {"type": "text", "text": answer_rules_text()}},
            {"role": "user", "content": {"type": "text", "text": payload["content"]}},
        ]

    def parse_query(request):
        try:
            parsed = parse_qs(request.url.query, keep_blank_values=True, strict_parsing=True,
                encoding="utf-8", errors="strict", max_num_fields=10)
        except (ValueError, UnicodeError):
            raise LookupError("Malformed query parameters")
        if any(len(v) != 1 for v in parsed.values()):
            raise LookupError("Duplicate parameters are not supported")
        return {k: v[0] for k, v in parsed.items()}

    async def lookup_route(request: Request):
        try:
            params = parse_query(request)
            if request.url.path.endswith("/query"):
                result = library.query(params, http=True)
            elif request.url.path.endswith("/search"):
                result = library.search(params, http=True)
            else:
                result = library.get(params)
            return JSONResponse(result)
        except (LookupError, QueryValidationError) as exc:
            return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)

    mcp.custom_route("/api/agent/search", methods=["GET", "HEAD"])(lookup_route)
    mcp.custom_route("/api/agent/item", methods=["GET", "HEAD"])(lookup_route)
    mcp.custom_route("/api/agent/query", methods=["GET", "HEAD"])(lookup_route)

    @mcp.custom_route("/api/agent/books", methods=["GET", "HEAD"])
    @mcp.custom_route("/api/agent/books/{book_id}", methods=["GET", "HEAD"])
    @mcp.custom_route("/api/agent/setup-book", methods=["GET", "HEAD"])
    async def setup_book_route(request: Request):
        # Reject all query/body inputs, with fixed messages that cannot echo secrets.
        if (request.scope.get("query_string") or
                request.headers.get("content-length", "0") != "0" or
                request.headers.get("transfer-encoding")):
            return JSONResponse({"error": "invalid_parameter",
                "message": "Setup book accepts no query parameters or request body"}, status_code=400)
        async for chunk in request.stream():
            if chunk:
                return JSONResponse({"error": "invalid_parameter",
                    "message": "Setup book accepts no request body"}, status_code=400)
        if request.url.path == "/api/agent/books":
            return JSONResponse(book_catalog())
        try:
            result = book_payload(request.path_params.get("book_id", "autosetup"))
        except ValueError:
            return JSONResponse({"error": "not_found", "message": "Unknown book id"}, status_code=404)
        return JSONResponse(result)

    @mcp.custom_route("/api/agent/freshness", methods=["GET", "HEAD"])
    async def freshness(request):
        if request.scope.get("query_string"):
            return JSONResponse({"error": "invalid_parameter", "message": "Freshness accepts no parameters"}, status_code=400)
        return JSONResponse(library.freshness.public_snapshot())

    @mcp.custom_route("/api/agent/health", methods=["GET", "HEAD"])
    async def health(request):
        return JSONResponse({"status": "ok", "version": VERSION, "snapshot": library.snapshot, "filters": library.filters,
            "source_freshness": library.freshness.summary()})

    @mcp.custom_route("/openapi.json", methods=["GET", "HEAD"])
    async def spec(request):
        return JSONResponse(openapi())

    @mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET", "HEAD"])
    async def card(request):
        return JSONResponse(server_card())

    app = Guard(SetupBookInputGuard(mcp.streamable_http_app()), origins)
    app.mcp = mcp
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).with_name("library.json"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source-revision", default=SOURCE_REVISION)
    parser.add_argument("--freshness-file", type=Path)
    parser.add_argument("--allow-origin", action="append", default=[])
    parser.add_argument("--export-metadata", type=Path)
    args = parser.parse_args()
    library = Library(args.data, args.source_revision, args.freshness_file)
    if args.export_metadata:
        args.export_metadata.mkdir(parents=True, exist_ok=True)
        for name, data in [("openapi.json", openapi()), ("server-card.json", server_card())]:
            (args.export_metadata / name).write_bytes(encode(data) + b"\n")
        return
    uvicorn.run(create_app(library, args.allow_origin), host="127.0.0.1", port=args.port,
        access_log=False, log_level="warning", limit_concurrency=16, timeout_keep_alive=5)


if __name__ == "__main__":
    main()
