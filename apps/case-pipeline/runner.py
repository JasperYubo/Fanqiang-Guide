#!/usr/bin/env python3
"""Outbound-only leased broker runner. No public listener; raw logs stay private."""
from __future__ import annotations
import argparse
import contextlib
try:
    import fcntl
except ImportError:
    fcntl=None
import json
import os
import re
import shlex
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from pseo_pipeline import Pipeline, DeepSeek, Rejected, atomic

class Broker:
    def __init__(self, base, token):
        if not base.startswith("https://"):raise Rejected("broker_https_required")
        self.base=base.rstrip("/");self.token=token
    def call(self,path,body):
        req=urllib.request.Request(self.base+path,json.dumps(body).encode(),{"Authorization":"Bearer "+self.token,"Content-Type":"application/json","Origin":"https://fanqiang.guide","Referer":"https://fanqiang.guide/","User-Agent":"Fanqiang-PSEO/1.0"})
        try:
            with urllib.request.urlopen(req,timeout=45) as response:return json.load(response)
        except urllib.error.HTTPError as exc:raise Rejected("broker_http_"+str(exc.code)) from None
        except Exception:raise Rejected("broker_connection_failed") from None

def adapt(job, trusted_sources):
    p=job.get("payload") or {};intake=p.get("intake") or {}
    messages=p.get("messages") or []
    selected=[];seen=set()
    for m in messages:
        for src in m.get("sources") or []:
            if src.get("url") in trusted_sources and src["url"] not in seen:
                selected.append({**trusted_sources[src["url"]],"url":src["url"],"selection_verified":True});seen.add(src["url"])
    resolution=p.get("resolution","unconfirmed")
    execution=p.get("execution","not_reported")
    # Resolution/execution fields are supplied by explicit Worker feedback controls.
    return {"job_id":job["jobId"],"public_consent":p.get("publicationConsent") is True,
      "intent":intake.get("originalRequest") or intake.get("need") or "",
      "dedup_intent":intake.get("need") or "","device":intake.get("device") or "","constraints":";".join(str(x) for x in (intake.get("details") or [])) if isinstance(intake.get("details"),list) else str(intake.get("details") or ""),
      "conversation":[{"role":m.get("role"),"content":m.get("content","")} for m in messages if m.get("role") in {"user","assistant"}],
      "book":(p.get("artifact") or {}).get("content", ""),"verified_sources":selected,
      "feedback":{"resolution":{"needs_more":"unresolved"}.get(resolution,resolution),"explicit":p.get("feedbackExplicit") is True and resolution in {"resolved","needs_more"},"execution":{"succeeded":"success","failed":"failure"}.get(execution,execution),"execution_explicit":p.get("feedbackExplicit") is True and execution in {"succeeded","failed"},"confirmed_at":p.get("feedbackConfirmedAt")},
      "personal_values":[]}

def publisher(command, kind, path, job):
    if not command:raise Rejected("publisher_unconfigured")
    argv=shlex.split(command)+["--kind",kind,"--input",str(path),"--job-id",job["jobId"]]
    environment=os.environ.copy();environment["PSEO_JOB_LEASE_TOKEN"]=job["leaseToken"]
    run=subprocess.run(argv,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=900,env=environment)
    if run.returncode:raise Rejected("publisher_failed")
    try:result=json.loads(run.stdout)
    except Exception:raise Rejected("publisher_invalid_output") from None
    if result.get("outcome") not in {"published","retracted","needs_review"}:raise Rejected("publisher_invalid_outcome")
    return result

class Heartbeat:
    def __init__(self,broker,job):self.broker=broker;self.job=job;self.stop=threading.Event();self.lost=False
    def loop(self):
        while not self.stop.wait(60):
            try:self.broker.call("/"+self.job["jobId"]+"/heartbeat",{"leaseToken":self.job["leaseToken"]})
            except Exception:self.lost=True;return
    def __enter__(self):self.thread=threading.Thread(target=self.loop,daemon=True);self.thread.start();return self
    def __exit__(self,*args):self.stop.set();self.thread.join(timeout=5)

def review_summary(result):
    status=result.get("outcome") or {}
    return {"resolution":{"unresolved":"needs_more"}.get(status.get("resolution"),status.get("resolution","unconfirmed")),
      "execution":{"user_confirmed_success":"succeeded","user_confirmed_failure":"failed"}.get(status.get("execution"),"not_reported"),
      "evidenceComplete":result.get("assessment")=="complete" or result.get("privacy_reviewed") is True,
      "summary":scrub_summary(result)}

def scrub_summary(result):
    from pseo_pipeline import scrub
    items=result.get("missing_points") or []
    text="；".join(items)+("。"+result["followup_question"] if result.get("followup_question") else "")
    if not text and result.get("assessment")=="complete":text="已检查本次回答的完整性，实际执行结果仍以你的反馈为准。"
    return scrub(text)[:500]

def process_one(broker,pipeline,trusted_sources,publish_cmd,root):
    answer=broker.call("/claim",{"workerId":"hub-pseo"});job=answer.get("job")
    if not job:return False
    jid=job.get("jobId","")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",jid):raise Rejected("broker_invalid_job")
    private=Path(root)/jid;atomic(private/"broker-job.json",job)
    with Heartbeat(broker,job) as lease:
        try:
            kind=job.get("kind")
            if kind=="review_only":
                result=pipeline.review_only(adapt(job,trusted_sources));done={"outcome":"reviewed","review":review_summary(result)}
            elif kind=="publish":
                normalized=adapt(job,trusted_sources)
                # An unsupported artifact/source stays private, while the feedback remains valid.
                try:result=pipeline.run(normalized)
                except Rejected as exc:
                    if str(exc) in {"public_consent_required","no_verified_sources","book_ilang_invalid","book_not_ilang","missing_book"}:
                        result=pipeline.review_only({**normalized,"job_id":jid+"-review"})
                        done={"outcome":"needs_review","review":review_summary(result)}
                    else:raise
                else:
                    if lease.lost:raise Rejected("lease_lost")
                    published=publisher(publish_cmd,"publish",private/"case.json",job)
                    done={"outcome":published["outcome"],"publicUrl":published.get("publicUrl"),"review":review_summary(result),"redaction":{"verified":True}}
            elif kind=="retract":
                atomic(private/"retract.json",{"publicUrl":(job.get("payload") or {}).get("publicUrl"),"jobId":jid,"sourceJobId":(job.get("payload") or {}).get("sourceJobId")})
                done=publisher(publish_cmd,"retract",private/"retract.json",job)
                done={k:v for k,v in done.items() if k in {"outcome","publicUrl"}}
                done["review"]={"resolution":"unconfirmed","execution":"not_reported","evidenceComplete":False}
            else:raise Rejected("unsupported_job_kind")
            if lease.lost:raise Rejected("lease_lost")
            done["leaseToken"]=job["leaseToken"]
            broker.call("/"+jid+"/complete",done)
            atomic(private/"broker-state.json",{"status":"complete","outcome":done["outcome"]})
        except Exception as exc:
            code=str(exc) if isinstance(exc,Rejected) and re.fullmatch(r"[a-z0-9_]{1,80}",str(exc)) else "processing_failed"
            atomic(private/"broker-state.json",{"status":"failed","error_code":code})
            if not lease.lost:
                broker.call("/"+jid+"/fail",{"leaseToken":job["leaseToken"],"errorCode":code,"retryable":code in {"provider_request_failed","publisher_failed","broker_connection_failed"}})
    return True

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--once",action="store_true");parser.add_argument("--interval",type=int,default=30);args=parser.parse_args()
    root=Path(os.environ.get("PSEO_STATE_DIR","/var/lib/fanqiang-pseo"));root.mkdir(parents=True,exist_ok=True,mode=0o700)
    token=os.environ.get("CASE_PIPELINE_TOKEN","");key=os.environ.get("DEEPSEEK_API_KEY","")
    if not token or not key:raise Rejected("missing_credentials")
    source_file=Path(os.environ.get("PSEO_TRUSTED_SOURCES","/opt/fanqiang-pseo/trusted-sources.json"))
    trusted=json.loads(source_file.read_text(encoding="utf-8"))
    broker=Broker(os.environ.get("PSEO_BROKER_URL","https://fanqiang.guide/api/chat/internal/cases"),token)
    pipeline=Pipeline(root,DeepSeek(key))
    with (root/"runner.lock").open("w") as lock:
        if fcntl is None:raise Rejected("runner_requires_linux")
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Rejected("runner_already_active") from None
        while True:
            try:
                found=process_one(broker,pipeline,trusted,os.environ.get("PSEO_PUBLISH_COMMAND",""),root)
                atomic(root/"runner-state.json",{"status":"running","last_poll":time.time(),"job_found":found})
            except Exception as exc:
                code=str(exc) if isinstance(exc,Rejected) and re.fullmatch(r"[a-z0-9_]{1,80}",str(exc)) else "runner_failed"
                atomic(root/"runner-state.json",{"status":"error","last_poll":time.time(),"error_code":code})
                if args.once:raise Rejected(code) from None
            if args.once:break
            time.sleep(max(5,args.interval))

if __name__=="__main__":
    try:main()
    except Rejected as exc:print(str(exc));raise SystemExit(1)
