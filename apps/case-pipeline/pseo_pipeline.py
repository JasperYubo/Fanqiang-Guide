#!/usr/bin/env python3
"""Private, resumable dialogue-to-case processing; never logs dialogue or keys."""
from __future__ import annotations
import hashlib
import ipaddress
import json
import os
import re
import time
from datetime import datetime, timezone
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

VERSION = "1.0-2026-09-27"
PRO = "deepseek-v4-pro"
FLASH = "deepseek-flash"
BASE = "https://api.deepseek.com/v1"
ROOT = Path(__file__).resolve().parent

class Rejected(Exception):
    pass

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    os.chmod(path, 0o600)

URL_RE = re.compile(r"https?://[^\s<>\"'\\\])}。，；：！？]+")
PRIVATE_URI_RE = re.compile(r"(?i)\b(?:vmess|vless|trojan|ss|ssr|hysteria2|hy2|tuic)://[^\s<>\"']+")
SECRET_RE = re.compile(r"(?i)\b(?:sk-|ghp_|github_pat_|hf_|cfat_)[A-Za-z0-9_-]{12,}|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")
ASSIGN_RE = re.compile(r"(?im)(\b(?:password|passwd|secret|api[_ -]?key|access[_ -]?token|authorization|密码|密钥|订阅链接)\s*[:=：]\s*)([^\s,;，；]+)")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
IP_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])|(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F]{0,4}(?![\w:])")
CONTACT_RE = re.compile(r"(?im)(?:微信|weixin|wechat|QQ|手机号|手机号码|电话|姓名|用户名|昵称|地址|账户|账号)\s*[:=：]\s*[^\n,，;；]+")

def scrub(text, personal_values=(), allowed_urls=()):
    """Mask transport credentials and personal values before model processing."""
    text = str(text)
    for val in sorted({str(v) for v in personal_values if str(v).strip()}, key=len, reverse=True):
        text = text.replace(val, "{{PRIVATE_VALUE}}")
    text = SECRET_RE.sub("{{PRIVATE_SECRET}}", text)
    text = PRIVATE_URI_RE.sub("{{PRIVATE_SUBSCRIPTION}}",text)
    text = re.sub(r"(?m)\bssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/=]{20,}(?:\s+[^\r\n]+)?", "{{PRIVATE_SSH_KEY}}", text)
    text = ASSIGN_RE.sub(lambda m: m[1] + "{{PRIVATE_SECRET}}", text)
    text = EMAIL_RE.sub("{{PRIVATE_EMAIL}}", text)
    text = CONTACT_RE.sub("{{PRIVATE_CONTACT}}", text)
    def ip(m):
        try:
            ipaddress.ip_address(m[0])
            return "{{PRIVATE_IP}}"
        except ValueError:
            return m[0]
    text = IP_RE.sub(ip, text)
    allowed = set(allowed_urls)
    # Only sources explicitly selected in the source manifest may become links.
    text = URL_RE.sub(lambda m: m[0] if m[0] in allowed else "{{PRIVATE_URL}}", text)
    text = re.sub(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)", "{{PRIVATE_PHONE}}", text)
    text = re.sub(r"(?<!\w)\+\d{1,3}[ -](?:\d[ -]?){8,14}\d(?!\d)", "{{PRIVATE_PHONE}}", text)
    return text

def sources_checked(sources):
    result = []
    for src in sources:
        if not isinstance(src, dict) or not src.get("id") or not src.get("url"):
            raise Rejected("invalid_source_manifest")
        parsed = urlsplit(src["url"])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise Rejected("private_or_unsafe_source_url")
        try:
            ipaddress.ip_address(parsed.hostname)
            raise Rejected("source_ip_not_allowed")
        except ValueError:
            pass
        if parsed.hostname in {"localhost", "metadata.google.internal"} or parsed.hostname.endswith(".local"):
            raise Rejected("private_source_host")
        if src.get("selection_verified") is not True:
            raise Rejected("unverified_source_selection")
        result.append({k: src[k] for k in ("id", "url", "title", "review_status", "checked_at", "maintenance_status") if k in src})
    if not result:
        raise Rejected("no_verified_sources")
    return result

def stable_case_key(job):
    # Controlled categories canonicalize paraphrases; original request is never hashed.
    device=str(job.get("device","")).lower();need=str(job.get("dedup_intent") or job.get("intent","")).lower()
    details=str(job.get("constraints",""));combined=need+" "+details.lower()
    if not need or not device:
        raise Rejected("missing_case_identity")
    platform=next((p for p,pattern in (("windows",r"windows|\bwin(?:10|11|\s)|电脑"),("android",r"android|安卓"),("ios",r"ios|iphone|苹果手机"),("macos",r"macos|macbook|苹果电脑"),("router",r"路由|rt-|梅林|openwrt"),("linux",r"linux|debian|ubuntu")) if re.search(pattern,device)),"other")
    goal=next((g for g,pattern in (("troubleshooting",r"故障|排查|不能|连不上|报错|排错"),("router_compatibility",r"支持|兼容|梅林|固件"),("client_selection",r"选|推荐|哪个好|哪种|客户端|软件"),("documentation",r"资料|文档|教程|说明"),("engineering_delivery",r"工程书|交付")) if re.search(pattern,need)),"general_guidance")
    technical=sorted(set(re.findall(r"\b(?:rt-[a-z0-9-]+|windows\s*(?:10|11)|android\s*\d+|ios\s*\d+|v[12]|x86_64|arm64|clash|sing-box|xray|v2ray|vless|reality|openwrt|merlin|shadowrocket|surge|netflix|chatgpt)\b",combined+" "+device)))
    constraints=sorted({name for name,pattern in (("free",r"免费|不付费|零预算"),("paid",r"(?<!不)付费|收费|(?<!零)预算"),("beginner",r"新手|小白|第一次"),("router",r"路由器|梅林|openwrt"),("streaming",r"流媒体|视频|netflix"),("ai_access",r"chatgpt|访问ai|ai工具"),("privacy",r"隐私|匿名"),("speed",r"速度|延迟|快速"),("desktop",r"桌面|电脑")) if re.search(pattern,combined)})
    fields={"platform":platform,"goal":goal,"technical":technical,"constraints":constraints}
    # Unclassified requests remain separate instead of being merged arbitrarily.
    if goal=="general_guidance" or platform=="other":
        fields["unclassified"]=digest({"need":scrub(need),"device":scrub(device),"details":scrub(details)})
    return "case-" + digest(fields)[:20]

def outcome(job):
    feedback = job.get("feedback") or {}
    if feedback.get("resolution") == "resolved" and feedback.get("explicit") is True:
        resolution = "resolved"
    elif feedback.get("resolution") == "unresolved" and feedback.get("explicit") is True:
        resolution = "unresolved"
    else:
        resolution = "unconfirmed"
    execution = {"success":"user_confirmed_success","failure":"user_confirmed_failure"}.get(feedback.get("execution"),"not_verified") if feedback.get("execution_explicit") is True else "not_verified"
    return {"resolution": resolution, "execution": execution, "book_delivered": bool(job.get("book"))}

class DeepSeek:
    def __init__(self, key):
        self.key = key
    def __call__(self, prompt_name, payload, model):
        if model not in {PRO, FLASH}:
            raise Rejected("model_not_allowed")
        prompt = (ROOT / "prompts" / (prompt_name + ".ilang")).read_text(encoding="utf-8")
        req = urllib.request.Request(BASE + "/chat/completions", json.dumps({
            "model": model, "messages": [{"role":"system","content":prompt}, {"role":"user","content":json.dumps(payload, ensure_ascii=False)}],
            "response_format":{"type":"json_object"}, "stream":False, "max_tokens":10000,
            "thinking":{"type":"enabled" if model == PRO else "disabled"},
        }, ensure_ascii=False).encode(), {"Authorization":"Bearer " + self.key,"Content-Type":"application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                data = json.load(response)
            return json.loads(data["choices"][0]["message"]["content"])
        except Exception:
            # Provider bodies and exception text may contain user material.
            raise Rejected("provider_request_failed") from None

def validate_ilang(text):
    if not text.strip().startswith("::ILANG::"):
        raise Rejected("book_not_ilang")
    if "::ILANG::COMPLETE::" not in text:
        raise Rejected("book_ilang_invalid")
    if not re.search(r"(?m)^::(?:MODULE|RULE|STATE|OBJECTIVE|LIST|BOUNDARY)\b",text) or not re.search(r"(?m)^\[TYPE:[^\]]+\]",text):
        raise Rejected("book_ilang_invalid")
    import ilang_grammar_validator as grammar
    diagnostics = grammar.Linter("public-engineering.ilang", text).run()
    if any(row[0] in {grammar.ERROR,grammar.WARN} for row in diagnostics):
        raise Rejected("book_ilang_invalid")

class Pipeline:
    def __init__(self, store, model_call, book_validator=validate_ilang):
        self.store = Path(store)
        self.call = model_call
        self.book_validator = book_validator

    def review_only(self, job):
        """Private closure assessment cannot turn absent feedback into success."""
        jid=str(job.get("job_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",jid):raise Rejected("invalid_job_id")
        folder=self.store / jid
        atomic(folder / "private-job.json",job)
        status=outcome(job)
        values=job.get("personal_values") or []
        payload={k:scrub(job.get(k,""),values) for k in ("intent","device","constraints","book")}
        payload["conversation"]=[{"role":m.get("role"),"content":scrub(m.get("content",""),values)} for m in job.get("conversation",[])]
        payload["outcome"]=status
        final=folder / "private-review.json"
        key=digest(job)
        if final.exists():
            prior=json.loads(final.read_text(encoding="utf-8"))
            if prior["input_hash"]!=key:raise Rejected("job_payload_changed")
            return prior["review"]
        review=self.call("resolution",payload,FLASH)
        if review.get("assessment") not in {"complete","incomplete"} or not isinstance(review.get("missing_points"),list) or any(not isinstance(x,str) for x in review["missing_points"]) or not isinstance(review.get("followup_question"),str) or review.get("outcome")!=status:
            raise Rejected("invalid_closure_review")
        review["published"]=False
        atomic(final,{"input_hash":key,"review":review})
        return review

    def run(self, job):
        if job.get("public_consent") is not True:
            raise Rejected("public_consent_required")
        jid = str(job.get("job_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", jid):
            raise Rejected("invalid_job_id")
        folder = self.store / jid
        input_hash = digest(job)
        prior_state=folder / "state.json"
        if prior_state.exists():
            checkpoint_state=json.loads(prior_state.read_text(encoding="utf-8"))
            if checkpoint_state.get("input_hash") != input_hash:raise Rejected("job_payload_changed")
        final = folder / "result.json"
        if final.exists():
            saved = json.loads(final.read_text(encoding="utf-8"))
            if saved["input_hash"] != input_hash:
                raise Rejected("job_payload_changed")
            return saved["result"]
        atomic(folder / "private-job.json", job)
        atomic(folder / "state.json", {"stage":"started", "input_hash":input_hash})
        source_manifest = sources_checked(job.get("verified_sources") or [])
        urls = [s["url"] for s in source_manifest]
        values = job.get("personal_values") or []
        source_conv = job.get("conversation") or []
        if not source_conv or any(x.get("role") not in {"user", "assistant"} for x in source_conv):
            raise Rejected("invalid_conversation")
        conv = [{"role":x["role"],"content":scrub(x.get("content", ""), values, urls)} for x in source_conv]
        book = scrub(job.get("book") or "", values, urls)
        if not book:
            raise Rejected("missing_book")
        self.book_validator(book)
        identity = {k:scrub(job.get(k, ""), values, urls) for k in ("intent", "device", "constraints","dedup_intent")}
        status = outcome(job)
        payload = {**identity, "conversation":conv,"book":book,"sources":source_manifest,"outcome":status}
        checkpoint = folder / "scrubbed.json"
        if checkpoint.exists():
            payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        else:
            privacy = self.call("privacy", payload, FLASH)
            if privacy.get("unsafe") is not False or not isinstance(privacy.get("sensitive_strings"), list):
                raise Rejected("privacy_review_incomplete")
            for term in privacy["sensitive_strings"]:
                if not isinstance(term, str) or len(term.strip()) < 2:
                    raise Rejected("privacy_invalid_span")
                # Exact-span only: AI cannot rewrite technical facts or fabricate text.
                for m in payload["conversation"]:
                    m["content"] = m["content"].replace(term, "{{PRIVATE_VALUE}}")
                payload["book"] = payload["book"].replace(term, "{{PRIVATE_VALUE}}")
                for k in identity:
                    payload[k] = str(payload[k]).replace(term, "{{PRIVATE_VALUE}}")
            self.book_validator(payload["book"])
            atomic(checkpoint, payload)
        atomic(folder / "state.json", {"stage":"redacted", "input_hash":input_hash})
        key = stable_case_key(payload)
        article_file = folder / "generated.json"
        if article_file.exists():
            article = json.loads(article_file.read_text(encoding="utf-8"))
        else:
            article = self.call("article", payload, PRO)
            atomic(article_file, article)
        for field in ("title", "description", "answer", "article_md"):
            if not isinstance(article.get(field), str) or not article[field].strip():
                raise Rejected("article_missing_" + field)
        if len(article["title"]) > 100 or len(article["description"]) > 240 or len(article["article_md"]) < 300:
            raise Rejected("article_invalid_length")
        if article.get("outcome") != status or not isinstance(article.get("source_ids"), list):
            raise Rejected("article_changed_result")
        if not isinstance(article.get("selection_reasons"), list) or not article["selection_reasons"] or any(not isinstance(x,str) or not x.strip() for x in article["selection_reasons"]):
            raise Rejected("article_invalid_reasons")
        if not isinstance(article.get("sections"), list) or not article["sections"]:
            raise Rejected("article_invalid_sections")
        for section in article["sections"]:
            if not isinstance(section,dict) or not isinstance(section.get("heading"),str) or not isinstance(section.get("paragraphs"),list) or not section["paragraphs"] or any(not isinstance(x,str) for x in section["paragraphs"]):
                raise Rejected("article_invalid_section")
        known_ids = {s["id"] for s in source_manifest}
        if not article["source_ids"] or not set(article["source_ids"]).issubset(known_ids):
            raise Rejected("article_unknown_source")
        all_text = json.dumps(article, ensure_ascii=False)
        if any(u not in urls for u in URL_RE.findall(all_text)):
            raise Rejected("article_unknown_link")
        if scrub(all_text, values, urls) != all_text:
            raise Rejected("article_privacy_residue")
        # A second pass sees the final public artefacts, not just the transcript.
        review = self.call("final_review", {"article":article,"book":payload["book"],"conversation":payload["conversation"],"sources":source_manifest,"outcome":status}, FLASH)
        if review.get("safe_to_publish") is not True or review.get("grounded") is not True or review.get("outcome_matches") is not True:
            raise Rejected("final_review_rejected")
        conversation_md = "\n\n".join("### " + ("用户" if m["role"]=="user" else "助手") + "\n\n" + m["content"] for m in payload["conversation"])
        result = {"schema_version":"1.0","case_key":key,"intent_key":key,"slug":key,"approved":True,"anonymized":True,"title":article["title"],"description":article["description"],"answer":article["answer"],"article_md":article["article_md"],"book":payload["book"],"conversation_md":conversation_md,"outcome":status,"sources":source_manifest,"source_ids":article["source_ids"],"models":{"article":PRO,"review":FLASH},"privacy_reviewed":True}
        confirmed_at=(job.get("feedback") or {}).get("confirmed_at") if status["resolution"] != "unconfirmed" else None
        if confirmed_at:
            try: datetime.fromisoformat(confirmed_at.replace("Z","+00:00"))
            except (ValueError,TypeError): raise Rejected("feedback_invalid_timestamp")
        now=datetime.now(timezone.utc).isoformat()
        conditions=["设备："+payload["device"],"需求："+(payload.get("dedup_intent") or payload["intent"])] + ([x for x in re.split(r"[;；\n]",payload["constraints"]) if x] or ["未提供额外约束"])
        result.update(question=payload["intent"],device=payload["device"],answer_summary=article["answer"],constraints=conditions,selection_reasons=article["selection_reasons"],sections=article["sections"],engineering_book_public=payload["book"],conversation_public=payload["conversation"],publication={"approved":True,"anonymized":True},published_at=now,updated_at=now,
          result={"resolution":status["resolution"],"delivery":"delivered" if status["book_delivered"] else "not_delivered","execution":{"user_confirmed_success":"confirmed_success","user_confirmed_failure":"confirmed_failure"}.get(status["execution"],"unverified"),"confirmed_at":confirmed_at})
        atomic(final, {"input_hash":input_hash,"result":result})
        atomic(folder / "case.json", result)
        for name, content in (("article.md",result["article_md"]),("book.ilang",result["book"]),("conversation.md",conversation_md)):
            fd=os.open(folder / name,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as out:out.write(content)
        atomic(folder / "state.json", {"stage":"complete", "input_hash":input_hash,"case_key":key})
        return result

