import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pseo_pipeline import Pipeline
from test_pipeline import job,FakeModel,URL
from weknora_cases import Sync,SyncError,normalized_case,blob_sha,PATH,GitHub

MODELS={"knowledge_base_id":"guide","catalog_knowledge_base_id":"catalog","embedding_model_id":"jina-existing","chat_model_id":"deepseek-existing"}
def public_case():
    with tempfile.TemporaryDirectory() as directory:
        j=job();j["verified_sources"][0]["title"]="Windows官方资料"
        return Pipeline(directory,FakeModel()).run(j)

class FakeGitHub:
    def __init__(self,case):self.update(case)
    def update(self,case):
        self.rows={};self.raw={}
        if case:
            slug=case["slug"];raw=json.dumps(case,ensure_ascii=False).encode()
            self.raw[slug]=raw;self.rows[slug]={"path":"apps/site/content/cases/public/"+slug+"/case.json","blob_sha":blob_sha(raw),"commit_sha":"a"*40}
    def snapshot(self):return "a"*40,copy.deepcopy(self.rows)
    def read(self,row):return self.raw[row["path"].split("/")[-2]]

class FakeAPI:
    def __init__(self):self.docs={};self.creates=[];self.uploads=[];self.deletes=[];self.fail_parse=False
    def call(self,method,path,obj=None):
        if method=="GET" and path=="/knowledge-bases":return 200,{"data":[]}
        if method=="POST" and path=="/knowledge-bases":self.creates.append(obj);return 201,{"data":{"id":"case-kb"}}
        raise AssertionError((method,path))
    def upload(self,kb,name,raw,meta):
        kid="doc-"+str(len(self.uploads)+1);self.uploads.append({"kb":kb,"name":name,"content":raw,"metadata":meta});self.docs[kid]={"knowledge_base_id":kb,"parse_status":"failed" if self.fail_parse else "completed"};return kid
    def detail(self,kid):return (200,self.docs[kid]) if kid in self.docs else (404,{})
    def delete(self,kid):self.deletes.append(kid);self.docs.pop(kid,None);return 204

class CaseKBTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/"case-kb-state.json";self.api=FakeAPI();self.github=FakeGitHub(public_case());self.sync=Sync(self.github,self.api,MODELS,self.path,poll_seconds=0,timeout=1)
    def tearDown(self):self.temp.cleanup()
    def test_only_public_source_paths(self):
        self.assertIsNone(PATH.fullmatch("apps/site/content/cases/private/raw.json"));self.assertIsNone(PATH.fullmatch("apps/site/content/cases/public/../../private/case.json"));self.assertIsNotNone(PATH.fullmatch("apps/site/content/cases/public/case-abc/case.json"))
    def test_download_pinned_commit_not_tree_sha(self):
        case=public_case();slug=case["slug"];raw=json.dumps(case).encode();row={"path":"apps/site/content/cases/public/"+slug+"/case.json","type":"blob","sha":blob_sha(raw),"size":len(raw)}
        calls=[]
        def request(method,url,*args):
            calls.append(url)
            if url.endswith("/commits/main"):return 200,json.dumps({"sha":"a"*40,"commit":{"tree":{"sha":"b"*40}}}).encode()
            if "/git/trees/" in url:return 200,json.dumps({"sha":"b"*40,"tree":[row]}).encode()
            return 200,raw
        with patch("weknora_cases.request",request):
            github=GitHub();commit,rows=github.snapshot();self.assertEqual(commit,"a"*40);self.assertEqual(github.read(rows[slug]),raw)
        self.assertIn("/"+"a"*40+"/",calls[-1]);self.assertNotIn("/"+"b"*40+"/",calls[-1])
    def test_third_kb_is_separate_and_idempotent(self):
        one=self.sync.run();two=self.sync.run();self.assertEqual(one["documents"],1);self.assertEqual(two["changed"],0);self.assertEqual(len(self.api.uploads),1)
        self.assertEqual(self.api.creates[0]["embedding_model_id"],"jina-existing");self.assertEqual(self.api.creates[0]["summary_model_id"],"deepseek-existing");self.assertEqual(self.api.uploads[0]["kb"],"case-kb")
    def test_retraction_deletes_knowledge(self):
        self.sync.run();self.github.update(None);result=self.sync.run();self.assertEqual(result["removed"],1);self.assertEqual(self.api.deletes,["doc-1"]);self.assertEqual(self.sync.state["documents"],{})
    def test_failed_replacement_keeps_old(self):
        self.sync.run();case=public_case();case["answer_summary"]+=" 增补已核对说明。";self.github.update(case);self.api.fail_parse=True
        with self.assertRaisesRegex(SyncError,"parse_failed"):self.sync.run()
        self.assertIn("doc-1",self.api.docs);self.assertEqual(self.api.deletes,[]);self.assertEqual(len(self.sync.state["pending"]),1)
    def test_withdrawal_removes_pending_and_old(self):
        self.sync.run();case=public_case();case["answer_summary"]+=" 增补。";self.github.update(case);self.api.fail_parse=True
        with self.assertRaises(SyncError):self.sync.run()
        self.github.update(None);self.sync.run();self.assertEqual(set(self.api.deletes),{"doc-1","doc-2"})
    def test_revert_discards_failed_pending_replacement(self):
        original=json.loads(next(iter(self.github.raw.values())))
        self.sync.run();changed=copy.deepcopy(original);changed["answer_summary"]+=" 增补。";self.github.update(changed);self.api.fail_parse=True
        with self.assertRaises(SyncError):self.sync.run()
        self.github.update(original);self.sync.run();self.assertEqual(self.api.deletes,["doc-2"]);self.assertEqual(self.sync.state["pending"],{})
    def test_existing_guide_kb_protected(self):
        self.sync.state["knowledge_base_id"]="guide";self.sync.save()
        with self.assertRaisesRegex(SyncError,"protected"):Sync(self.github,self.api,MODELS,self.path)
    def test_cross_kb_document_delete_refused(self):
        self.sync.run();self.api.docs["doc-1"]["knowledge_base_id"]="guide";self.github.update(None)
        with self.assertRaisesRegex(SyncError,"boundary"):self.sync.run()
        self.assertEqual(self.api.deletes,[])
    def test_public_allowlist_removes_private_extra(self):
        case=public_case();case["private_raw"]="private@example.com";slug=case["slug"];out=normalized_case(json.dumps(case).encode(),slug);self.assertNotIn("private_raw",out)
        case["publication"]["approved"]=False
        with self.assertRaisesRegex(SyncError,"approved"):normalized_case(json.dumps(case).encode(),slug)
    def test_bad_public_secret_refused(self):
        case=public_case();case["answer_summary"]="sk-"+"x"*32
        with self.assertRaisesRegex(SyncError,"privacy"):normalized_case(json.dumps(case).encode(),case["slug"])

if __name__=="__main__":unittest.main()
