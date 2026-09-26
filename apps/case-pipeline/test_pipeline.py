import copy
import json
import tempfile
import unittest
from pathlib import Path
from pseo_pipeline import Pipeline, Rejected, PRO, FLASH, scrub, outcome, sources_checked, validate_ilang

URL="https://github.com/JasperYubo/Fanqiang-Guide/blob/main/apps/site/public/guides/windows.md"
BOOK="::ILANG::v4.0\n[TYPE:command][LANG:zh]\n::MODULE{DELIVERY}\n  请先核对 Windows 版本；用户用自己的 AI 执行。\n::ILANG::COMPLETE::"
def job():
    return {"job_id":"test-1","public_consent":True,"intent":"Windows 新手如何选客户端","device":"Windows 11","constraints":"免费;有自己的 AI","feedback":{"resolution":"resolved","explicit":True,"confirmed_at":"2026-09-27T08:00:00Z"},"book":BOOK,"conversation":[{"role":"user","content":"我的邮件 private@example.com，节点 https://sub.example/a?token=private"},{"role":"assistant","content":"请参考 " + URL}],"verified_sources":[{"id":"windows","url":URL,"selection_verified":True,"review_status":"primary_reviewed","maintenance_status":"unknown","checked_at":"2026-09-11"}]}

class FakeModel:
    def __init__(self):self.calls=[];self.mutate=None
    def __call__(self,name,payload,model):
        self.calls.append((name,model))
        if name=="privacy":return {"unsafe":False,"sensitive_strings":[]}
        if name=="resolution":return {"assessment":"complete","missing_points":[],"followup_question":"","outcome":copy.deepcopy(payload["outcome"])}
        if name=="final_review":return {"safe_to_publish":True,"grounded":True,"outcome_matches":True}
        data={"title":"Windows 新手客户端选型案例","description":"基于设备条件与公开资料的选型案例。","answer":"先核对 Windows 版本，再确认客户端维护状态。","article_md":"# Windows 新手客户端选型\n\n"+("这是用户实际提出的选型需求，文章依据提供的资料说明适用条件。工程书已脱敏，实际执行尚未验证。"*9),"source_ids":["windows"],"outcome":copy.deepcopy(payload["outcome"]),"selection_reasons":["用户已确认设备为 Windows 11。"],"sections":[{"heading":"选择依据","paragraphs":["应根据 Windows 11 和用户已有 AI 的条件选择。"]}]}
        if self.mutate:self.mutate(data)
        return data

class Tests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.model=FakeModel();self.pipe=Pipeline(self.tmp.name,self.model)
    def tearDown(self):self.tmp.cleanup()
    def test_secrets_and_private_urls(self):
        text="sk-"+"a"*32+" private@example.com 192.168.1.7 https://sub.example/a?token=abc 微信：hello"
        got=scrub(text,[],[URL]);self.assertNotIn("example.com",got);self.assertNotIn("192.168",got);self.assertNotIn("sub.example",got);self.assertNotIn("hello",got);self.assertNotIn("a"*32,got)
        self.assertNotIn("uuid-secret",scrub("vless://uuid-secret@host.example:443?security=tls"))
        self.assertIn("PRIVATE_PHONE",scrub("contact +1 604 123 4567"))
    def test_explicit_only_resolution(self):
        j=job();j["feedback"]={"resolution":"resolved","explicit":False};self.assertEqual(outcome(j)["resolution"],"unconfirmed");self.assertEqual(outcome(j)["execution"],"not_verified")
    def test_source_query_rejected(self):
        src=job()["verified_sources"];src[0]["url"]+="?token=secret"
        with self.assertRaisesRegex(Rejected,"unsafe_source"):sources_checked(src)
    def test_no_consent_no_model(self):
        j=job();j["public_consent"]=False
        with self.assertRaisesRegex(Rejected,"consent"):self.pipe.run(j)
        self.assertEqual(self.model.calls,[])
    def test_duplicate_job_idempotent(self):
        j=job();one=self.pipe.run(j);two=self.pipe.run(j);self.assertEqual(one,two);self.assertEqual(self.model.calls,[("privacy",FLASH),("article",PRO),("final_review",FLASH)])
        self.assertTrue(one["publication"]["approved"]);self.assertEqual(one["result"]["execution"],"unverified")
    def test_duplicate_mutation_rejected(self):
        j=job();self.pipe.run(j);j["device"]="Android"
        with self.assertRaisesRegex(Rejected,"payload_changed"):self.pipe.run(j)
    def test_failed_checkpoint_cannot_mix_new_payload(self):
        j=job();self.model.mutate=lambda x:x.update(sections=[])
        with self.assertRaises(Rejected):self.pipe.run(j)
        j["device"]="Android"
        with self.assertRaisesRegex(Rejected,"payload_changed"):self.pipe.run(j)
    def test_fake_success_rejected(self):
        self.model.mutate=lambda x:x["outcome"].update(execution="user_confirmed_success")
        with self.assertRaisesRegex(Rejected,"changed_result"):self.pipe.run(job())
    def test_invented_link_rejected(self):
        self.model.mutate=lambda x:x.update(article_md=x["article_md"]+" https://evil.example/fake")
        with self.assertRaisesRegex(Rejected,"unknown_link"):self.pipe.run(job())
    def test_invalid_generation_rejected(self):
        self.model.mutate=lambda x:x.update(sections=[])
        with self.assertRaisesRegex(Rejected,"invalid_sections"):self.pipe.run(job())
    def test_real_ilang_validation(self):
        validate_ilang(BOOK)
        with self.assertRaisesRegex(Rejected,"book_ilang_invalid"):validate_ilang("::ILANG::v4.0\n这是普通中文不是工程书\n")
    def test_case_dedup_across_jobs(self):
        one=self.pipe.run(job());j=job();j["job_id"]="test-2";j["conversation"][0]["content"]="另一个匿名用户，需求相同";two=self.pipe.run(j)
        self.assertEqual(one["case_key"],two["case_key"])
    def test_review_without_consent_never_article(self):
        j=job();j["public_consent"]=False;j["feedback"]={};result=self.pipe.review_only(j)
        self.assertEqual(result["outcome"]["resolution"],"unconfirmed");self.assertFalse(result["published"])
        self.assertEqual(self.model.calls,[("resolution",FLASH)])
        self.pipe.review_only(j);self.assertEqual(len(self.model.calls),1)
    def test_variable_redacted_book_valid(self):
        source=BOOK.replace("请先核对","password=supersecret\n  host=192.168.1.8\n  请先核对")
        redacted=scrub(source)
        self.assertIn("{{PRIVATE_SECRET}}",redacted);self.assertIn("{{PRIVATE_IP}}",redacted);validate_ilang(redacted)
    def test_paraphrases_same_category_dedup(self):
        from pseo_pipeline import stable_case_key
        one={"intent":"Windows 11 新手客户端哪个好","device":"Windows 11","constraints":"免费"}
        two={"intent":"推荐适合 Windows 11 的客户端，新手","device":"Windows 11","constraints":"不付费"}
        self.assertEqual(stable_case_key(one),stable_case_key(two))

if __name__=="__main__":unittest.main()
