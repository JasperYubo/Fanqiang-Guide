"""Verify the published setup-book interfaces through the official MCP SDK."""
import argparse, asyncio, gzip, hashlib, json, pathlib, urllib.request
from datetime import datetime, timezone
from mcp import ClientSession
from mcp.shared.exceptions import McpError
from mcp.client.streamable_http import streamable_http_client

def fetch(url, compressed=False):
    req=urllib.request.Request(url,headers={"User-Agent":"Fanqiang-Autosetup-Release-Verification","Accept-Encoding":"gzip" if compressed else "identity"})
    with urllib.request.urlopen(req,timeout=25) as r:
        raw=r.read(2*1024*1024)
        if r.headers.get("Content-Encoding")=="gzip": raw=gzip.decompress(raw)
        return raw,dict(r.headers)

async def check(args):
    expected=args.book.read_bytes()
    digest=hashlib.sha256(expected).hexdigest()
    evidence={"checked_at":datetime.now(timezone.utc).isoformat(),"endpoint":args.origin+"/mcp",
              "book_sha256":digest,"checks":[]}
    def expect(name,value):
        if not value: raise AssertionError(name)
        evidence["checks"].append(name)
    async with streamable_http_client(args.origin+"/mcp") as (read,write,_):
        async with ClientSession(read,write) as session:
            init=await session.initialize()
            expect("service_version",init.serverInfo.version=="1.2.0")
            listing=await session.list_tools()
            expect("existing_and_setup_tools",{"search","get","get_setup_book"}=={t.name for t in listing.tools})
            setup=next(t for t in listing.tools if t.name=="get_setup_book")
            expect("read_only_no_arguments",setup.annotations.readOnlyHint is True and setup.inputSchema.get("additionalProperties") is False and setup.inputSchema["properties"]=={})
            result=await session.call_tool("get_setup_book",{})
            expect("tool_success",result.isError is not True)
            payload=result.structuredContent or json.loads(result.content[0].text)
            expect("tool_exact_book",payload["content"].encode()==expected and payload["sha256"]==digest and payload["version"]=="1.1")
            expect("retrieval_not_execution",payload["execution_status"]=="not_run" and payload["executor"]=="user_agent")
            resources=await session.list_resources()
            expect("resource_discovery",any(str(r.uri)=="fanqiang://books/autosetup" for r in resources.resources))
            resource=await session.read_resource("fanqiang://books/autosetup")
            expect("resource_exact_payload",json.loads(resource.contents[0].text)==payload)
            prompts=await session.list_prompts()
            expect("prompt_discovery",any(p.name=="setup_device" for p in prompts.prompts))
            prompt=await session.get_prompt("setup_device",{})
            expect("prompt_exact_book",prompt.messages[-1].content.text.encode()==expected)
            try:
                wrong=await session.call_tool("get_setup_book",{"extra":"SYNTHETIC-NONPRIVATE-ARGUMENT"})
                rejected=wrong.isError is True
                rejection=wrong.model_dump_json()
            except McpError as exc:
                rejected=exc.error.code==-32602
                rejection=str(exc)
            expect("extra_arguments_rejected",rejected)
            expect("rejected_value_not_echoed","SYNTHETIC-NONPRIVATE-ARGUMENT" not in rejection)
            result=await session.call_tool("search",{"query":"sing-box","limit":3})
            value=result.structuredContent or json.loads(result.content[0].text)
            expect("existing_search_works",bool(value["items"]))
            ident=value["items"][0]["id"]
            result=await session.call_tool("get",{"id":ident})
            value=result.structuredContent or json.loads(result.content[0].text)
            expect("existing_get_works",value["item"]["id"]==ident and bool(value["item"]["source_url"]))
    raw,headers=fetch(args.origin+"/api/agent/setup-book")
    expect("http_exact_payload",json.loads(raw)==payload)
    expect("http_not_cached","no-store" in next((v for k,v in headers.items() if k.lower()=="cache-control"),""))
    manifest=json.loads(fetch(args.origin+"/ai/books/autosetup.json")[0])
    expect("static_metadata_equal",manifest=={k:v for k,v in payload.items() if k!="content"})
    path="/ai/books/fanqiang-autosetup-v1.1.ilang.md"
    expect("download_exact_bytes",fetch(args.origin+path)[0]==expected)
    expect("compressed_download_exact_bytes",fetch(args.origin+path,True)[0]==expected)
    for path in ["/ai/","/ai/index.md","/ai/index.ilang","/ai/skills/library-lookup/SKILL.md","/llms.txt"]:
        raw,_=fetch(args.origin+path)
        expect(path+"_discovery",b"get_setup_book" in raw and b"fanqiang-autosetup-v1.1.ilang.md" in raw)
    card=json.loads(fetch(args.origin+"/.well-known/mcp/server-card.json")[0])
    expect("server_card_capabilities",card["serverInfo"]["version"]=="1.2.0" and {"tools","resources","prompts"}<=set(card["capabilities"]))
    health=json.loads(fetch(args.origin+"/api/agent/health")[0])
    expect("health",health["status"]=="ok" and health["version"]=="1.2.0")
    evidence["ok"]=True
    evidence["checks_passed"]=len(evidence["checks"])
    args.output.write_text(json.dumps(evidence,indent=2)+"\n")
    print(json.dumps(evidence))

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origin",default="https://fanqiang.guide")
    p.add_argument("--book",type=pathlib.Path,required=True)
    p.add_argument("--output",type=pathlib.Path,required=True)
    args=p.parse_args()
    if args.output.exists(): raise ValueError("Output must be new")
    asyncio.run(check(args))
