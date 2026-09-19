#!/usr/bin/env python3
"""Public lookup with the maintained official MCP Python SDK."""
from __future__ import annotations
import argparse
import asyncio
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

from library_core import (Library, LookupError, VERSION, ORIGIN, MAX_BODY, MAX_RESPONSE,
    MAX_PATH, SOURCE_REVISION, SEARCH_DESCRIPTION, GET_DESCRIPTION, INSTRUCTIONS,
    encode, openapi, server_card)


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


def create_app(library, allowed_origins=()):
    origins = [ORIGIN, "https://www.fanqiang.guide", *allowed_origins]
    mcp = FastMCP("guide.fanqiang/library-lookup", instructions=INSTRUCTIONS, website_url=ORIGIN,
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

    def query(request):
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
            result = library.search(query(request), http=True) if request.url.path.endswith("/search") else library.get(query(request))
            return JSONResponse(result)
        except LookupError as exc:
            return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)

    mcp.custom_route("/api/agent/search", methods=["GET", "HEAD"])(lookup_route)
    mcp.custom_route("/api/agent/item", methods=["GET", "HEAD"])(lookup_route)

    @mcp.custom_route("/api/agent/health", methods=["GET", "HEAD"])
    async def health(request):
        return JSONResponse({"status": "ok", "version": VERSION, "snapshot": library.snapshot, "filters": library.filters})

    @mcp.custom_route("/openapi.json", methods=["GET", "HEAD"])
    async def spec(request):
        return JSONResponse(openapi())

    @mcp.custom_route("/.well-known/mcp/server-card.json", methods=["GET", "HEAD"])
    async def card(request):
        return JSONResponse(server_card())

    app = Guard(mcp.streamable_http_app(), origins)
    app.mcp = mcp
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path(__file__).with_name("library.json"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source-revision", default=SOURCE_REVISION)
    parser.add_argument("--allow-origin", action="append", default=[])
    parser.add_argument("--export-metadata", type=Path)
    args = parser.parse_args()
    library = Library(args.data, args.source_revision)
    if args.export_metadata:
        args.export_metadata.mkdir(parents=True, exist_ok=True)
        for name, data in [("openapi.json", openapi()), ("server-card.json", server_card())]:
            (args.export_metadata / name).write_bytes(encode(data) + b"\n")
        return
    uvicorn.run(create_app(library, args.allow_origin), host="127.0.0.1", port=args.port,
        access_log=False, log_level="warning", limit_concurrency=16, timeout_keep_alive=5)


if __name__ == "__main__":
    main()
