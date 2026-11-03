#!/usr/bin/env python3
"""Collect pinned primary evidence and hash archives without executing or extracting them.

This evidence builder accesses the network only in online mode. Runtime matching never does.
A new upstream install.sh requires an explicit review of INSTALL_SHA before publication.
KoolCenter release bodies are used transiently; the published matrix stores facts/hashes,
not forum text, account data or firmware binaries.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import io
import json
from pathlib import Path
import re
import tarfile
import time
from urllib.parse import urlsplit, urljoin, unquote
from urllib.request import Request, urlopen
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
OBSERVED_AT = {}
PIN = "b19e82cb6a05e08990a96905353921819d44d134"
INSTALL_SHA = "200573e858acdac47be0432121aac5233eeba798c785c6eb4d761b18f21d151d"
PLATFORMS = {
    "arm": {"architectures": ["armv7l"], "kernel_series": ["2.6"], "installer_lines": [666, 728]},
    "hnd": {"architectures": ["armv7l", "aarch64"], "kernel_series": ["4.1", "4.19"], "installer_lines": [730, 792],
            "note": "The installer permits 32-bit hnd on aarch64 with a warning; the model README prefers hnd_v8 for its listed 64-bit models."},
    "hnd_v8": {"architectures": ["aarch64"], "kernel_series": ["4.1", "4.19"], "installer_lines": [794, 852]},
    "qca": {"architectures": ["armv7l"], "kernel_series": ["4.4"], "installer_lines": [854, 916],
            "note": "README documents the actual 32-bit firmware ABI; CPU bitness is not sufficient."},
    "mtk": {"architectures": ["aarch64"], "kernel_series": ["5.4"], "installer_lines": [918, 978],
            "installer_models": ["TX-AX6000", "TUF-AX4200Q", "RT-AX57_Go", "GS7", "ZenWiFi_BT8P", "GS7_Air", "GS-BE7200X"]},
    "ipq32": {"architectures": ["armv7l"], "kernel_series": ["5.4"], "installer_lines": [980, 1042],
              "installer_models": ["ZenWiFi_BD4"]},
    "ipq64": {"architectures": ["aarch64"], "kernel_series": ["5.4"], "installer_lines": [1044, 1110],
              "installer_models": ["TUF_6500"]},
}
TOPICS = {
    "kool-102-current": {"url": "https://www.koolcenter.com/t/topic/31125.json", "branch": "3006.102",
        "models": ["RT-BE58_GO","RT-AX86U_PRO","RT-AX88U_PRO","RT-BE86U","RT-BE88U","RT-BE92U","RT-BE96U","GT-AX11000_PRO","GT-AX6000","GT-AXE16000","GT-BE98_PRO","XT12"]},
    "kool-388-current": {"url": "https://www.koolcenter.com/t/topic/5978.json", "branch": "3004.388",
        "models": ["RT-AX58U","RT-AX68U","RT-AX86U","RT-AX88U","GT-AX11000","GT-AXE11000"]},
    "kool-gnuton-388": {"url": "https://www.koolcenter.com/t/topic/7351.json", "branch": "3004.388",
        "models": ["RT-AX82U","RT-AX82U_V2","RT-AX92U","TUF-AX5400","TUF-AX3000","TUF-AX3000_V2","RT-AX58U_V2","RT-AX5400","RT-AX95Q","RT-AXE95Q"]},
    "kool-102-historical": {"url": "https://www.koolcenter.com/t/topic/5072.json", "branch": "3006.102",
        "models": ["RT-BE58_GO","RT-AX86U_PRO","RT-AX88U_PRO","RT-BE86U","RT-BE88U","RT-BE92U","RT-BE96U","GT-AX11000_PRO","GT-AX6000","GT-AXE16000","GT-BE98_PRO","XT12"],
        "historical": True},
}
DIRECTORIES = {
    "kool-dir-r6300v2": {"url": "https://fw.koolcenter.com/KoolCenter_Merlin_New_Gen_386/Netgear/R6300v2/", "model":"R6300V2","family":"koolcenter-merlin-mod","branch":"386"},
    "kool-dir-ac2900": {"url": "https://fw.koolcenter.com/KoolCenter_Merlin_New_Gen_386/GT-AC2900/", "model":"GT-AC2900","family":"koolcenter-merlin-mod","branch":"386"},
    "kool-dir-ax86-pro-388": {"url": "https://fw.koolcenter.com/KoolCenter_Merlin_New_Gen_388/RT-AX86U_PRO/", "model":"RT-AX86U_PRO","family":"koolcenter-merlin-mod","branch":None},
    "kool-dir-ax58-v2": {"url": "https://fw.koolcenter.com/KoolCenter_Merlin_New_Gen_388/RT-AX58U_V2/", "model":"RT-AX58U_V2","family":"koolcenter-merlin-mod","branch":"3004.388"},
    "kool-dir-tuf-be6500": {"url":"https://fw20.koolcenter.com/KoolCenter_ASUS_Official_Mod/TUF-BE6500/","model":"TUF-BE6500","family":"koolcenter-asuswrt-mod","branch":"3006.102"},
    "kool-dir-ax86-stockmod": {"url":"https://fw20.koolcenter.com/KoolCenter_ASUS_Official_Mod/RT-AX86U/","model":"RT-AX86U","family":"koolcenter-asuswrt-mod","branch":None},
    "kool-dir-ax86-pro-stockmod": {"url":"https://fw20.koolcenter.com/KoolCenter_ASUS_Official_Mod/RT-AX86U_Pro/","model":"RT-AX86U_PRO","family":"koolcenter-asuswrt-mod","branch":"3004.388"},
    "kool-dir-bd4": {"url":"https://fw20.koolcenter.com/KoolCenter_ASUS_Official_Mod/ZenWiFi_BD4/","model":"ZenWiFi_BD4","family":"koolcenter-asuswrt-mod","branch":None},
}
# Explicit spelling pairs seen in the two publishers; no separator-erasing matcher.
DOCUMENTED_SPELLINGS = {"RT-AX86U PRO":"RT-AX86U_PRO", "GT-AX11000 PRO":"GT-AX11000_PRO"}

def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

class Collector:
    def __init__(self, cache, offline=False):
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True);self.offline=offline
    def fetch(self,url,limit=2_000_000):
        key=hashlib.sha256(url.encode()).hexdigest()
        p=self.cache/(key+".bin")
        legacy=self.cache/("kool-"+key[:16]+".txt")
        if not p.exists() and legacy.exists():
            p.write_bytes(legacy.read_bytes())
        # Online checks must not silently reuse old mutable publisher evidence.
        # Offline mode alone reuses the cache, preserving its original timestamp.
        if self.offline and p.exists():
            content=p.read_bytes()
            if len(content)>limit:raise ValueError("Cached source exceeds size limit")
            OBSERVED_AT[url]=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
            return content
        if self.offline:raise ValueError("Source not present in offline cache")
        last=None
        for attempt in range(2):
            try:
                req=Request(url,headers={"User-Agent":"Mozilla/5.0 (compatible; Fanqiang-Guide-SourceCheck/1.0)",
                                         "Accept":"application/json,text/html,*/*"})
                with urlopen(req,timeout=18) as response:
                    final=urlsplit(response.url)
                    if final.scheme!="https" or final.hostname not in {"raw.githubusercontent.com","www.koolcenter.com","fw.koolcenter.com","fw20.koolcenter.com","www.asusgo.com","doc.asusgo.com"}:
                        raise ValueError("Unexpected source redirect")
                    content=response.read(limit+1)
                if len(content)>limit:raise ValueError("Source exceeds size limit")
                p.write_bytes(content)
                OBSERVED_AT[url]=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
                return content
            except (OSError,URLError,ValueError) as exc:last=exc
        raise ValueError("Source unavailable: "+type(last).__name__)

def source_record(key,url,content,checked,commit=None):
    out={"id":key,"url":url,"checked_at":OBSERVED_AT.get(url,checked),"sha256":hashlib.sha256(content).hexdigest(),"status":"retrieved","bytes":len(content)}
    if commit:out["commit"]=commit
    return out

def parse_readme(text):
    rows=[]
    for line_no,line in enumerate(text.splitlines(),1):
        cells=[x.strip() for x in line.strip().strip("|").split("|")]
        if len(cells)!=7 or not re.fullmatch(r"fancyss_(arm|hnd|hnd_v8|qca|mtk|ipq32|ipq64)",cells[-1]):continue
        if cells[1] not in ("\u6885\u6539","\u5b98\u6539"):continue
        m=re.fullmatch(r"\[([^\]]+)\]\((https://[^)]+)\)",cells[0])
        model,url=(m.group(1),m.group(2)) if m else (cells[0],None)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,63}",model):raise ValueError("Invalid model in upstream table")
        platform=cells[-1].removeprefix("fancyss_")
        rows.append({
            "id":"fancyss-"+re.sub(r"[^a-z0-9]+","-",model.lower()).strip("-")+"-"+("merlin" if cells[1]=="\u6885\u6539" else "asuswrt"),
            "router_model":model,"hardware_revision":None,
            "aliases":[DOCUMENTED_SPELLINGS[model]] if model in DOCUMENTED_SPELLINGS else [],
            "firmware_family":"koolcenter-merlin-mod" if cells[1]=="\u6885\u6539" else "koolcenter-asuswrt-mod",
            "platform_label":cells[2],"cpu":cells[3],"documented_architecture":re.sub(r"\[\^\d+\]","",cells[4]),
            "documented_kernel":cells[5],"package_platform":platform,"readme_line":line_no,
            "installer_model_status":"unresolved_alias" if platform in ("mtk","ipq32","ipq64") and model not in PLATFORMS[platform]["installer_models"] else "consistent",
            "source_ids":["fancyss-readme","fancyss-install"],
            "firmware":{"status":"not_independently_verified","branches":[],"versions":[],
                        "publisher_sources":[],"legacy_links":[{"url":url,"status":"legacy_link_unverified"}] if url else [],
                        "download_visibility":"unknown","excluded_hardware_revisions":[]}
        })
    if not 45<=len(rows)<=90 or len({r["id"] for r in rows})!=len(rows):raise ValueError("Unexpected model table layout")
    return rows

def package_record(collector,commit,platform,variant,version,manifest,checked):
    key=platform+"_"+variant
    url=f"https://raw.githubusercontent.com/hq450/fancyss/{commit}/packages/fancyss_{key}.tar.gz"
    content=collector.fetch(url,32*1024*1024)
    md5=hashlib.md5(content).hexdigest()
    if md5!=manifest["md5_"+key]:raise ValueError("Publisher MD5 differs for "+key)
    with tarfile.open(fileobj=io.BytesIO(content),mode="r:gz") as archive:
        members={m.name:m for m in archive.getmembers()}
        if len(members)>20000:raise ValueError("Archive member count exceeds budget")
        def read(name,limit):
            m=members.get(name)
            if not m or not m.isfile() or m.size>limit:raise ValueError("Unsafe or missing archive metadata")
            stream=archive.extractfile(m)
            return stream.read(limit+1)
        valid=read("shadowsocks/.valid",100).decode().strip()
        install=read("shadowsocks/install.sh",300000)
        page=read("shadowsocks/webs/Module_shadowsocks.asp",2_000_000).decode()
        arch=re.search(r'var\s+PKG_ARCH\s*=\s*"([^"]+)"',page)
        typ=re.search(r'var\s+PKG_TYPE\s*=\s*"([^"]+)"',page)
        if valid!=platform or not arch or arch[1]!=platform or not typ or typ[1]!=variant:raise ValueError("Package platform/variant mismatch")
        if hashlib.sha256(install).hexdigest()!=INSTALL_SHA:raise ValueError("Package installer changed; review its gates before publication")
        expanded=sum(m.size for m in members.values() if m.isfile())
    return key,{"platform":platform,"variant":variant,"version":version,"filename":"fancyss_"+key+".tar.gz",
        "download_url":url,"upstream_commit":commit,"checked_at":OBSERVED_AT.get(url,checked),"bytes":len(content),
        "unpacked_file_bytes":expanded,"sha256":hashlib.sha256(content).hexdigest(),
        "author_md5":md5,"author_md5_source":"fancyss-manifest","manifest_md5_matches":True,
        "archive_metadata_matches":True,"installer_sha256":INSTALL_SHA,
        "checksum_scope":"observed_bytes_and_author_manifest_not_digital_signature",
        "executed":False,"device_tested":False}

def plain_html(text):
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",text))).strip()


def discover_model_directories(collector, checked, rows):
    """Enumerate publisher roots, then join only exact documented model spellings."""
    found, sources, misses = {}, {}, []
    root_url="https://fw.koolcenter.com/"
    try:
        root_bytes=collector.fetch(root_url)
        sources["kool-mirror-root"]=source_record("kool-mirror-root",root_url,root_bytes,checked)
        roots=[]
        for link in re.findall(r'href="([^"]+)"',root_bytes.decode()):
            label=unquote(link)
            if not label.startswith("KoolCenter_") or not link.endswith("/"):continue
            if "3006.102" in label:family,branch="koolcenter-merlin-mod","3006.102"
            elif "3004.388" in label:family,branch="koolcenter-merlin-mod","3004.388"
            elif "3004.386" in label:family,branch="koolcenter-merlin-mod","3004.386"
            elif "\u534e\u7855\u5b98\u6539" in label:family,branch="koolcenter-asuswrt-mod",None
            else:continue
            resolved_roots={"3004.388":"https://fw20.koolcenter.com/KoolCenter_Merlin_New_Gen_388/","3004.386":"https://fw20.koolcenter.com/KoolCenter_Merlin_New_Gen_386/"}
            canonical_root=resolved_roots.get(branch, "https://fw20.koolcenter.com/KoolCenter_ASUS_Official_Mod/" if family=="koolcenter-asuswrt-mod" else urljoin("https://fw20.koolcenter.com/",link))
            roots.append((canonical_root,family,branch))
        if len(roots)!=4:raise ValueError("Expected the four reviewed firmware roots")
        def list_root(spec):
            url,family,branch=spec
            key="kool-root-"+("asuswrt" if family=="koolcenter-asuswrt-mod" else branch.replace(".","-"))
            try:
                content=collector.fetch(url)
                src=source_record(key,url,content,checked)
                entries=[]
                for href in re.findall(r'href="([^"]+)"',content.decode()):
                    if href.startswith(("/","?","#","..")) or not href.endswith("/"):continue
                    child=urljoin(url,href)
                    if urlsplit(child).hostname not in ("fw.koolcenter.com","fw20.koolcenter.com"):continue
                    label=unquote(href).strip("/")
                    if label.lower()=="netgear":
                        nested=collector.fetch(child)
                        for nested_href in re.findall(r'href="([^"]+)"',nested.decode()):
                            if nested_href.startswith(("/","?","#","..")) or not nested_href.endswith("/"):continue
                            entries.append((unquote(nested_href).strip("/"),urljoin(child,nested_href),family,branch,key))
                    else:entries.append((label,child,family,branch,key))
                src["model_directory_count"]=len(entries)
                return key,src,entries
            except (ValueError,UnicodeError) as exc:
                return key,{"id":key,"url":url,"checked_at":checked,"status":"unavailable_or_unverified","error_code":type(exc).__name__},[]
        with ThreadPoolExecutor(max_workers=4) as pool:listed=list(pool.map(list_root,roots))
        all_entries=[]
        for key,src,entries in listed:sources[key]=src;all_entries.extend(entries)
        for row in rows:
            names={x.upper() for x in (row["router_model"],*row.get("aliases",[]))}
            matches=[entry for entry in all_entries if entry[0].upper() in names and entry[2]==row["firmware_family"]]
            if not matches:
                misses.append({"router_model":row["router_model"],"firmware_family":row["firmware_family"],
                               "reason":"no_exact_model_directory_in_observed_roots_not_proof_of_no_support"})
            for label,url,family,branch,root_id in matches:
                key="kool-model-dir-"+hashlib.sha256(url.encode()).hexdigest()[:14]
                found[key]={"url":url,"model":row["router_model"],"family":family,"branch":branch,"root_source":root_id}
    except (ValueError,KeyError,UnicodeError) as exc:
        sources["kool-mirror-root"]={"id":"kool-mirror-root","url":root_url,"checked_at":checked,"status":"unavailable_or_unverified","error_code":type(exc).__name__}
    return found,sources,misses


def collect_firmware(collector,checked,rows):
    discovered, sources, misses=discover_model_directories(collector,checked,rows)
    facts=[]
    def topic_task(pair):
        key,spec=pair
        try:
            content=collector.fetch(spec["url"],3_000_000);obj=json.loads(content)
            first=obj["post_stream"]["posts"][0]
            if first.get("post_number")!=1:raise ValueError("Not the release first post")
            text=plain_html(first["cooked"]);title=obj["title"]
            match=re.search(r"(?:102|388)[.][0-9]+_[0-9]+",title)
            if not match:raise ValueError("Release version absent from title")
            heads=list(re.finditer(r"<h[1-6][ >].*?</h[1-6]>",first["cooked"],re.S))
            support=[(i,m) for i,m in enumerate(heads) if plain_html(m[0])=="\u652f\u6301\u673a\u578b"]
            if len(support)!=1:raise ValueError("Exact support heading missing or ambiguous")
            index,heading=support[0]
            end=heads[index+1].start() if index+1<len(heads) else len(first["cooked"])
            section=plain_html(first["cooked"][heading.end():end])
            models=[model for model in spec["models"] if re.search(r"(?<![A-Za-z0-9_-])"+re.escape(model)+r"(?![A-Za-z0-9_-])",section)]
            if not models:raise ValueError("No exact models in support section")
            source=source_record(key,spec["url"],content,checked)
            source.update({"title":title,"scope":"first_post_release_model_list","post_updated_at":first.get("updated_at"),
                           "public_url":spec["url"].removesuffix(".json")+"/1"})
            visible_links=re.findall(r'href="([^"]+)"',first["cooked"])
            hidden=bool(re.search(r"\u8d5e\u52a9|\u652f\u6301\u6211\u4eec|\u9690\u85cf",text))
            visibility="current_download_access_restricted" if key in ("kool-102-current","kool-388-current","kool-gnuton-388") and hidden else "release_post_observed_download_not_verified"
            return key,source,[{"models":models,"family":"koolcenter-merlin-mod","branch":spec["branch"],"versions":[match[0]],
                               "source_id":key,"historical":spec.get("historical",False),"download_visibility":visibility,
                               "excluded_revisions":{"RT-AX58U":["V2"]} if key=="kool-388-current" else {}}]
        except (ValueError,KeyError,TypeError,IndexError) as exc:
            return key,{"id":key,"url":spec["url"],"checked_at":checked,"status":"unavailable_or_unverified","error_code":type(exc).__name__},[]
    def directory_task(pair):
        key,spec=pair
        try:
            content=collector.fetch(spec["url"]);text=content.decode("utf-8");plain=plain_html(text)
            files=[html.unescape(v) for v in re.findall(r'href="([^"]+)"',text) if re.search(r"[.](?:w|trx|pkgtb)(?:$|[?])",v)]
            files=[v for v in files if urlsplit(v).scheme in ("","https") and ".." not in v]
            source=source_record(key,spec["url"],content,checked)
            source.update({"scope":"exact_model_public_mirror_directory","observed_firmware_files":files[:20],"directory_empty":not files,
                           "not_latest_release_guarantee":True})
            branch=spec["branch"]
            if not files:return key,source,[]
            if branch is None:
                observed=[]
                for number in ("384","386","388"):
                    if re.search(r"(?:^|[^0-9])"+number+r"(?:[._]|[^0-9])", " ".join(files)):observed.append("3004."+number)
                if re.search(r"(?:3[._]0[._]0[._]6[._]102|3006[._]102)", " ".join(files)):observed.append("3006.102")
            else:observed=[branch]
            if not observed:return key,source,[]
            facts=[]
            for observed_branch in observed:
                family_number=observed_branch.split(".")[-1]
                matching_files=[f for f in files if re.search(r"(?<![0-9])"+family_number+r"[._]",f)]
                if not matching_files:continue
                versions=sorted(set(re.findall(r"(?<![0-9])(?:384|386|388|102)[._][0-9]+(?:_[0-9]+)?"," ".join(matching_files))))
                facts.append({"models":[spec["model"]],"family":spec["family"],"branch":observed_branch,"versions":versions,
                              "source_id":key,"historical":True,"download_visibility":"public_historical_mirror_not_latest","excluded_revisions":{}})
            return key,source,facts
        except (ValueError,KeyError,TypeError) as exc:
            return key,{"id":key,"url":spec["url"],"checked_at":checked,"status":"unavailable_or_unverified","error_code":type(exc).__name__},[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        topic_results=list(pool.map(topic_task,TOPICS.items()))
        directory_results=list(pool.map(directory_task,{**DIRECTORIES,**discovered}.items()))
    for key,source,entries in topic_results+directory_results:sources[key]=source;facts.extend(entries)
    return sources,facts,misses

def build(cache,output,offline=False,commit=PIN,checked=None):
    if commit!=PIN:raise ValueError("New upstream commit requires code/evidence gate review; update PIN and INSTALL_SHA together")
    checked=checked or utc()
    stamp=datetime.fromisoformat(checked.replace("Z","+00:00"))
    if stamp.tzinfo is None or stamp>datetime.now(timezone.utc):raise ValueError("Invalid or future checked_at")
    collector=Collector(cache,offline)
    upstream="https://raw.githubusercontent.com/hq450/fancyss/"+commit+"/"
    payloads={name:collector.fetch(upstream+path,3_000_000) for name,path in
              (("fancyss-readme","README.md"),("fancyss-install","fancyss/install.sh"),("fancyss-manifest","packages/version.json.js"))}
    if hashlib.sha256(payloads["fancyss-install"]).hexdigest()!=INSTALL_SHA:raise ValueError("Unreviewed installer gate")
    sources={name:source_record(name,upstream+path,payloads[name],checked,commit) for name,path in
              (("fancyss-readme","README.md"),("fancyss-install","fancyss/install.sh"),("fancyss-manifest","packages/version.json.js"))}
    manifest=json.loads(payloads["fancyss-manifest"]);version=manifest["version"]
    if not re.fullmatch(r"[0-9]+[.][0-9]+[.][0-9]+",version):raise ValueError("Invalid package version")
    rows=parse_readme(payloads["fancyss-readme"].decode())
    with ThreadPoolExecutor(max_workers=4) as pool:
        pairs=list(pool.map(lambda pv:package_record(collector,commit,*pv,version,manifest,checked),
                            [(p,v) for p in PLATFORMS for v in ("full","lite")]))
    packages=dict(pairs)
    firmware_sources,facts,misses=collect_firmware(collector,checked,rows);sources.update(firmware_sources)
    for row in rows:
        if row["router_model"] == "ZenWiFi_XT8" and sources.get("kool-gnuton-388", {}).get("status") == "retrieved":
            row["aliases"] += ["RT-AX95Q", "ZenWiFi-XT8"]
            row["source_ids"].append("kool-gnuton-388")
    alias_url="https://doc.asusgo.com/zh/guide/asus/changelog/m_102.6_0.html"
    try:
        alias_content=collector.fetch(alias_url)
        if b"ZenWiFi_Pro_XT12" not in alias_content:raise ValueError("XT12 explicit alias not present")
        sources["kool-xt12-name"]=source_record("kool-xt12-name",alias_url,alias_content,checked)
        for row in rows:
            if row["router_model"]=="ZenWiFi_Pro_XT12":
                row["aliases"].append("XT12");row["source_ids"].append("kool-xt12-name")
    except ValueError:
        sources["kool-xt12-name"]={"id":"kool-xt12-name","url":alias_url,"checked_at":checked,"status":"unavailable_or_unverified"}
    for row in rows:
        spellings={row["router_model"],*row["aliases"]}
        applicable=[f for f in facts if row["firmware_family"]==f["family"] and spellings.intersection(f["models"])]
        current=[f for f in applicable if not f["historical"]]
        effective=current or applicable
        if effective:
            firm=row["firmware"];firm["status"]="publisher_documented"
            firm["branches"]=sorted({f["branch"] for f in applicable})
            firm["current_branches"]=sorted({f["branch"] for f in current})
            firm["historical_branches"]=sorted({f["branch"] for f in applicable if f["historical"]})
            firm["branch_scope"]="observed_release_sources_not_exhaustive_compatibility_range"
            firm["versions"]=sorted({v for f in applicable for v in f["versions"]})
            firm["observed_builds"]=[{"branch":f["branch"],"version":v,"source_id":f["source_id"],"historical":f["historical"]} for f in applicable for v in f["versions"]]
            firm["publisher_sources"]=sorted({f["source_id"] for f in applicable})
            firm["download_visibility"]=";".join(sorted({f["download_visibility"] for f in effective}))
            firm["excluded_hardware_revisions"]=sorted({rev for f in effective for m in spellings for rev in f["excluded_revisions"].get(m,[])})
            row["source_ids"]+=firm["publisher_sources"]
        row["source_ids"]=sorted(set(row["source_ids"]))
        for source_id in row["source_ids"]:
            if source_id not in sources:raise ValueError("Unresolved source reference")
    observed=max([v["checked_at"] for v in sources.values() if v.get("status")=="retrieved"]+[v["checked_at"] for v in packages.values()])
    data={"schema_version":"1.0","checked_at":observed,"fancyss_commit":commit,"package_version":version,
          "scope":"exact_publisher_model_rows_plus_independent_firmware_release_sources_and_offline_package_hashes",
          "not_device_tested":True,"platforms":PLATFORMS,
          "variant_rules":{"common_protocols":["shadowsocks","ssr","vmess","vless","trojan","hysteria2","xray-json"],
                           "full_only_protocols":["naiveproxy","tuic"],"source_id":"fancyss-readme","source_lines":[89,112]},
          "sources":sources,"packages":packages,"rows":rows,"firmware_catalog":facts,"directory_lookup_gaps":misses}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(data,ensure_ascii=False,indent=2)+"\n";output.write_text(text)
    return {"ok":True,"rows":len(rows),"platforms":len(PLATFORMS),"packages":len(packages),
            "firmware_documented_rows":sum(r["firmware"]["status"]=="publisher_documented" for r in rows),
            "firmware_source_count":len(firmware_sources),"unverified_source_count":sum(v["status"]!="retrieved" for v in firmware_sources.values()),
            "sha256":hashlib.sha256(text.encode()).hexdigest(),"bytes":len(text.encode())}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir",type=Path,required=True)
    parser.add_argument("--output",type=Path,default=ROOT/"data/router-compatibility.json")
    parser.add_argument("--offline",action="store_true")
    parser.add_argument("--commit",default=PIN)
    parser.add_argument("--checked-at")
    opts=parser.parse_args()
    print(json.dumps(build(opts.cache_dir,opts.output,opts.offline,opts.commit,opts.checked_at),ensure_ascii=True))
if __name__=="__main__":main()
