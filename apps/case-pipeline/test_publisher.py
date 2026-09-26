"""Real local Git publication recovery tests; no networks or public test cases."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import publisher as pub
from pseo_pipeline import Rejected,atomic

REAL_RUN=subprocess.run
REL='apps/site/content/cases/public/windows-choice/case.json'
URL='https://fanqiang.guide/cases/windows-choice/'

def command(args,cwd):
    r=REAL_RUN(['git',*args],cwd=cwd,capture_output=True,text=True,encoding='utf-8')
    if r.returncode:raise Rejected('publisher_git_failed')
    return r.stdout.strip()

class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.remote=self.root/'remote.git';self.seed=self.root/'seed';self.repo=self.root/'repo';self.state=self.root/'state'
        self.seed.mkdir();command(['init','--bare','--initial-branch=main',str(self.remote)],self.root)
        command(['init','--initial-branch=main'],self.seed)
        command(['config','user.name','fixture'],self.seed);command(['config','user.email','fixture@localhost'],self.seed)
        (self.seed/'README.md').write_text('Test only',encoding='utf-8')
        command(['add','.'],self.seed);command(['commit','-m','fixture base'],self.seed)
        command(['remote','add','origin',str(self.remote)],self.seed);command(['push','origin','main'],self.seed)
        command(['clone',str(self.remote),str(self.repo)],self.root)
        self.input=self.root/'case-input.json'
        self.input.write_text(json.dumps({'slug':'windows-choice','published_at':'2026-09-27','title':'fixture','private_raw_session':'NEVER-SHIP'}),encoding='utf-8')
        self.retract=self.root/'retract.json'
        self.retract.write_text(json.dumps({'publicUrl':URL,'sourceJobId':'job-a'}),encoding='utf-8')
        self.calls=[];self.build_fail=False;self.push_fail=0;self.commit_fail=False;self.cancel_check=None;self.checks=0
        def local_git(*args):
            self.calls.append(args)
            if args[0]=='push' and self.push_fail:self.push_fail-=1;raise Rejected('publisher_git_failed')
            if 'commit' in args and self.commit_fail:raise Rejected('publisher_git_failed')
            return command(list(args),self.repo)
        def check(jid):
            self.checks+=1
            if self.cancel_check==self.checks:raise Rejected('publisher_lease_not_valid')
        self.stack=[]
        for name,value in [('REPO',self.repo),('STATE',self.state),('JOURNAL',self.state/'publish/source-transaction.json'),('OWNERS',self.state/'public-owners'),('git',local_git),('check_lease',check),('broker',lambda *a:{'ok':True}),('load_normalizer',lambda:lambda d:{k:d[k] for k in ('slug','published_at','title')}),('ship_static',lambda *a:{'ok':True}),('purge',lambda *a:None)]:
            p=patch.object(pub,name,value);p.start();self.stack.append(p)
        self.env=patch.dict(pub.os.environ,{'PSEO_JOB_LEASE_TOKEN':'test-lease'});self.env.start()
        self.build=patch.object(pub.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1 if self.build_fail else 0));self.build.start()
    def tearDown(self):
        self.build.stop();self.env.stop()
        for p in reversed(self.stack):p.stop()
        self.temp.cleanup()
    def published(self,job='job-a'):return pub.publish('publish',self.input,job)
    def count(self):return int(command(['rev-list','--count','HEAD'],self.repo))
    def test_public_source_allowlist_and_duplicate_retry(self):
        self.assertEqual(self.published()['outcome'],'published')
        self.assertNotIn('NEVER-SHIP',(self.repo/REL).read_text())
        count=self.count();self.published();self.assertEqual(self.count(),count)
        self.assertEqual(command(['status','--porcelain'],self.repo),'')
    def test_committed_push_failure_retries_push_without_duplicate_commit(self):
        self.push_fail=2
        with self.assertRaises(Rejected):self.published()
        count=self.count();self.published()
        self.assertEqual(self.count(),count)
        self.assertEqual(command(['rev-parse','HEAD'],self.repo),command(['rev-parse','refs/heads/main'],self.remote))
    def test_build_failure_retains_source_and_rebuilds_without_commit(self):
        self.build_fail=True
        with self.assertRaisesRegex(Rejected,'publisher_build_failed'):self.published()
        count=self.count();self.build_fail=False;self.published();self.assertEqual(self.count(),count)
    def test_cancel_before_commit_removes_case_and_restores_owner(self):
        self.cancel_check=2
        with self.assertRaisesRegex(Rejected,'publisher_lease_not_valid'):self.published()
        self.assertFalse((self.repo/REL).exists());self.assertIsNone(pub.read_owner('windows-choice'))
        self.assertEqual(command(['status','--porcelain'],self.repo),'')
    def test_newly_staged_file_commit_failure_is_cleaned(self):
        self.commit_fail=True
        with self.assertRaises(Rejected):self.published()
        self.assertFalse((self.repo/REL).exists());self.assertFalse(pub.JOURNAL.exists())
        self.assertEqual(command(['status','--porcelain'],self.repo),'')
    def test_retraction_idempotent_and_old_owner_keeps_new_case(self):
        self.published();self.published('job-b');count=self.count()
        self.assertEqual(pub.publish('retract',self.retract,'retract-old')['outcome'],'retracted')
        self.assertTrue((self.repo/REL).exists());self.assertEqual(self.count(),count)
        self.retract.write_text(json.dumps({'publicUrl':URL,'sourceJobId':'job-b'}),encoding='utf-8')
        pub.publish('retract',self.retract,'retract-new');count=self.count()
        self.assertFalse((self.repo/REL).exists())
        pub.publish('retract',self.retract,'retract-new');self.assertEqual(self.count(),count)
    def test_crash_journal_recovers_staged_uncommitted_source(self):
        before=command(['rev-parse','HEAD'],self.repo);target=self.repo/REL;target.parent.mkdir(parents=True)
        target.write_text('partial');command(['add',REL],self.repo)
        atomic(pub.owner_path('windows-choice'),{'job_id':'crashed'})
        atomic(pub.JOURNAL,{'relative':REL,'slug':'windows-choice','before_head':before,'previous_owner':None,'expected_hash':'notcommitted'})
        pub.recover_source();self.assertFalse(target.exists());self.assertIsNone(pub.read_owner('windows-choice'))
    def test_dirty_unrelated_file_not_changed(self):
        (self.repo/'README.md').write_text('User change')
        with self.assertRaisesRegex(Rejected,'publisher_worktree_not_clean'):self.published()
        self.assertEqual((self.repo/'README.md').read_text(),'User change')
    def test_remote_daily_update_is_rebased_before_retry(self):
        self.push_fail=2
        with self.assertRaises(Rejected):self.published()
        (self.seed/'catalog.txt').write_text('Latest source');command(['add','.'],self.seed);command(['commit','-m','Daily catalog refresh'],self.seed);command(['push','origin','main'],self.seed)
        self.published();self.assertEqual((self.repo/'catalog.txt').read_text(),'Latest source')
        self.assertEqual(command(['rev-parse','HEAD'],self.repo),command(['rev-parse','refs/heads/main'],self.remote))

if __name__=='__main__':unittest.main()
