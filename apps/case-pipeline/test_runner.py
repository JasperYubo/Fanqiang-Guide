import copy
import tempfile
import unittest
from pseo_pipeline import Pipeline
from runner import adapt, process_one
from test_pipeline import FakeModel, BOOK, URL

class FakeBroker:
    def __init__(self,job):self.job=job;self.calls=[]
    def call(self,path,body):
        self.calls.append((path,body))
        if path=="/claim":return {"job":self.job}
        return {"ok":True}

def claimed(kind="review_only"):
    return {"jobId":"worker-1","kind":kind,"leaseToken":"lease-private","payload":{"intake":{"originalRequest":"选 Windows 客户端","device":"Windows 11","details":"免费"},"messages":[{"role":"user","content":"希望选一个软件"},{"role":"assistant","content":"根据资料先核对设备","sources":[{"url":URL}]}],"artifact":{"content":BOOK},"resolution":"unconfirmed","execution":"not_reported","publicationConsent":False}}

class RunnerTests(unittest.TestCase):
    def test_no_source_trust_from_user_links(self):
        j=claimed("publish");self.assertEqual(adapt(j,{})["verified_sources"],[])
        trusted={URL:{"id":"windows","review_status":"primary_reviewed"}}
        self.assertTrue(adapt(j,trusted)["verified_sources"][0]["selection_verified"])
    def test_review_only_ack_no_pro(self):
        with tempfile.TemporaryDirectory() as dest:
            model=FakeModel();broker=FakeBroker(claimed())
            self.assertTrue(process_one(broker,Pipeline(dest,model),{},"",dest))
            self.assertEqual([x[0] for x in model.calls],["resolution"])
            done=broker.calls[-1];self.assertEqual(done[0],"/worker-1/complete");self.assertEqual(done[1]["outcome"],"reviewed");self.assertEqual(done[1]["review"]["resolution"],"unconfirmed")
    def test_publish_no_consent_needs_review(self):
        with tempfile.TemporaryDirectory() as dest:
            model=FakeModel();broker=FakeBroker(claimed("publish"))
            process_one(broker,Pipeline(dest,model),{},"",dest)
            self.assertEqual([x[0] for x in model.calls],["resolution"]);self.assertEqual(broker.calls[-1][1]["outcome"],"needs_review")

if __name__=="__main__":unittest.main()
