"""Offline, bounded public snapshot sync tests. No external network or services."""
from contextlib import redirect_stderr
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
def load(name, relative):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
syncer=load('freshness_sync','developer/sync_source_freshness.py')
projection_tests=load('freshness_projection_fixtures','tests/test_refresh_knowledge_sources.py')
NOW=datetime(2026,11,3,2,tzinfo=timezone.utc)

class Response:
    def __init__(self,body,url=syncer.SOURCE_URL,headers=None,status=200):
        self.body,self.url,self.headers,self.status,self.offset=body,url,headers or {},status,0
    def geturl(self):return self.url
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):
        data=self.body[self.offset:self.offset+n];self.offset+=len(data);return data
    read1=read

class Opener:
    def __init__(self,response=None,error=None):self.response,self.error,self.calls=response,error,[]
    def open(self,request,timeout):
        self.calls.append((request,timeout))
        if self.error:raise self.error
        return self.response

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.library,self.manifest,self.state=projection_tests.fixture()
        self.library[0]['repository']='https://github.com/2dust/v2rayNG'
        self.library_path=self.root/'library.json';self.library_path.write_text(json.dumps(self.library))
        hashes={'library':hashlib.sha256(self.library_path.read_bytes()).hexdigest(),'manifest':'a'*64,'upstream':'b'*64}
        self.data=projection_tests.freshness.build_projection(self.library,self.manifest,self.state,as_of=projection_tests.NOW,input_sha256=hashes)
        self.output=self.root/'source-freshness.json';self.original=json.dumps(self.data).encode();self.output.write_bytes(self.original)
    def tearDown(self):self.temp.cleanup()
    def newer(self):
        data=deepcopy(self.data);data['generated_at']=data['source_run_at']='2026-11-03T01:00:00Z'
        row=data['records']['v2rayng'];row.update(source_checked_at=data['generated_at'],last_attempt_at=data['generated_at'],expires_at='2026-11-05T01:00:00Z')
        row['repository']['checked_at']=row['latest_release']['checked_at']=data['generated_at']
        return data
    def run_sync(self,data=None,response=None,error=None,monotonic=None):
        opener=Opener(response or Response(json.dumps(data or self.data).encode()),error)
        kwargs={'opener':opener,'now':NOW}
        if monotonic:kwargs['monotonic']=monotonic
        result=syncer.sync(self.library_path,self.output,**kwargs)
        return result,opener
    def reject(self,data):
        with self.assertRaises((syncer.SyncError,ValueError,TypeError,KeyError)):self.run_sync(data)
        self.assertEqual(self.output.read_bytes(),self.original)
    def test_valid_new_snapshot_atomic_update_and_fixed_unauthenticated_request(self):
        inode=self.output.stat().st_ino;result,opener=self.run_sync(self.newer())
        self.assertEqual(result['status'],'updated');self.assertNotEqual(self.output.stat().st_ino,inode)
        request,timeout=opener.calls[0];self.assertEqual(request.full_url,syncer.SOURCE_URL)
        self.assertEqual(timeout,10);self.assertIsNone(request.get_header('Authorization'))
        self.assertEqual(self.library_path.read_text(),json.dumps(self.library))
    def test_identical_snapshot_does_not_replace_inode(self):
        inode=self.output.stat().st_ino;result,_=self.run_sync()
        self.assertEqual(result['status'],'unchanged');self.assertEqual(self.output.stat().st_ino,inode)
    def test_reviewed_library_summary_upgrade_fetches_and_accepts_new_bound_snapshot(self):
        self.library[0]['summary']='Updated reviewed public summary'
        self.library_path.write_text(json.dumps(self.library));data=self.newer()
        data['input_sha256']['library']=hashlib.sha256(self.library_path.read_bytes()).hexdigest()
        result,opener=self.run_sync(data)
        self.assertEqual(result['status'],'updated');self.assertEqual(len(opener.calls),1)
        self.assertEqual(json.loads(self.output.read_text())['input_sha256']['library'],data['input_sha256']['library'])

    def test_library_id_addition_is_allowed_only_with_exact_current_ids_and_hash(self):
        item={'id':'new-record','verification':{'checked_at':'2026-11-02'}}
        self.library.append(item);self.library_path.write_text(json.dumps(self.library));data=self.newer()
        data['input_sha256']['library']=hashlib.sha256(self.library_path.read_bytes()).hexdigest()
        data['records']['new-record']=deepcopy(data['records']['no-repository'])
        data['records']['new-record']['knowledge_checked_at']='2026-11-02'
        data['record_count']+=1;data['counts']['unmonitored']+=1
        result,_=self.run_sync(data);self.assertEqual(result['status'],'updated')

    def test_library_id_removal_keeps_time_floor_for_remaining_records(self):
        self.library=self.library[:1];self.library_path.write_text(json.dumps(self.library));data=self.newer()
        data['input_sha256']['library']=hashlib.sha256(self.library_path.read_bytes()).hexdigest()
        del data['records']['no-repository'];data['record_count']-=1;data['counts']['unmonitored']-=1
        result,_=self.run_sync(data);self.assertEqual(result['status'],'updated')

    def test_library_upgrade_does_not_bypass_new_hash_or_old_time_floor(self):
        self.library[0]['summary']='Reviewed change';self.library_path.write_text(json.dumps(self.library))
        for case in ['new_hash','old_time']:
            with self.subTest(case=case):
                data=self.newer()
                if case=='old_time':
                    data['input_sha256']['library']=hashlib.sha256(self.library_path.read_bytes()).hexdigest()
                    data['generated_at']=data['source_run_at']='2026-10-31T00:00:00Z'
                self.reject(data)

    def test_malformed_old_schema_is_not_discarded_to_enable_migration(self):
        old=deepcopy(self.data);old['arbitrary_log']='DO-NOT-ACCEPT';self.output.write_text(json.dumps(old));before=self.output.read_bytes()
        opener=Opener(Response(json.dumps(self.newer()).encode()))
        with self.assertRaises(syncer.SyncError):syncer.sync(self.library_path,self.output,opener=opener,now=NOW)
        self.assertEqual(opener.calls,[]);self.assertEqual(self.output.read_bytes(),before)

    def test_successful_release_identity_must_match_repository_but_stale_failure_can_retain_old_identity(self):
        data=self.newer();row=data['records']['v2rayng'];other='official/another-repository'
        row['latest_release']['repository_full_name']=other
        row['latest_release']['url']='https://github.com/'+other+'/releases/tag/2.3.14'
        row['release_resolution']={'full_name':other,'checked_at':row['latest_release']['checked_at'],
            'api_redirect_chain':['https://api.github.com/repos/2dust/v2rayNG','https://api.github.com/repos/'+other]}
        self.reject(data)
        row['status']='stale';row['release_status']='error';row['error_code']='network_error'
        data['counts']['current']=0;data['counts']['stale']=1
        result,_=self.run_sync(data);self.assertEqual(result['status'],'updated')

    def test_first_valid_sync_can_initialize_absent_state(self):
        self.output.unlink();result,_=self.run_sync();self.assertEqual(result['status'],'updated')
    def test_top_or_row_unknown_fields_are_rejected(self):
        for where in ['top','row']:
            with self.subTest(where=where):
                data=self.newer();target=data if where=='top' else data['records']['v2rayng'];target['raw_log']='do not accept';self.reject(data)
    def test_ids_knowledge_date_and_repository_cannot_drift(self):
        for case in ['id','date','repository','hash']:
            with self.subTest(case=case):
                data=self.newer();row=data['records']['v2rayng']
                if case=='id':data['records']['unreviewed']=data['records'].pop('v2rayng')
                elif case=='date':row['knowledge_checked_at']='2026-11-03'
                elif case=='repository':row['requested_repository']='attacker/repo'
                else:data['input_sha256']['library']='0'*64
                self.reject(data)
    def test_generation_run_and_observation_times_must_not_regress(self):
        for key in ['generated_at','source_run_at','repository']:
            with self.subTest(key=key):
                data=self.newer()
                if key=='repository':data['records']['v2rayng']['repository']['checked_at']='2026-10-31T00:00:00Z'
                else:data[key]='2026-10-31T00:00:00Z'
                self.reject(data)
    def test_cannot_fake_new_source_check_using_old_evidence(self):
        data=self.newer();data['records']['v2rayng']['latest_release']['checked_at']=projection_tests.NOW;self.reject(data)
    def test_successful_evidence_cannot_disappear_as_unmonitored(self):
        data=self.newer();data['records']['v2rayng']=deepcopy(data['records']['no-repository']);data['counts']={'unmonitored':2,'current':0,'unknown':0,'stale':0};data['repository_count']=0;self.reject(data)
    def test_future_timestamp_or_forged_expiry_rejected(self):
        for case in ['future','expiry']:
            with self.subTest(case=case):
                data=self.newer()
                if case=='future':data['generated_at']='2027-01-01T00:00:00Z'
                else:data['records']['v2rayng']['expires_at']='2027-01-01T00:00:00Z'
                self.reject(data)
    def test_arbitrary_urls_and_invalid_counts_rejected(self):
        for case in ['url','count']:
            with self.subTest(case=case):
                data=self.newer()
                if case=='url':data['records']['v2rayng']['latest_release']['url']='https://attacker.invalid/file'
                else:data['counts']['current']+=1
                self.reject(data)
    def test_unknown_and_stale_states_remain_explicit(self):
        data=self.newer();row=data['records']['v2rayng'];row['status']='stale';row['release_status']='error';row['error_code']='rate_limited';data['counts']['current']=0;data['counts']['stale']=1
        result,_=self.run_sync(data);self.assertEqual(result['status'],'updated')
        self.assertEqual(json.loads(self.output.read_text())['records']['v2rayng']['status'],'stale')
    def test_redirects_and_changed_effective_origin_are_blocked(self):
        error=urllib.error.HTTPError(syncer.SOURCE_URL,302,'sensitive message',{'Location':'https://attacker.invalid/'},None)
        for kwargs in [{'error':error},{'response':Response(self.original,url='https://attacker.invalid/')}]:
            with self.subTest(kwargs=list(kwargs)):
                with self.assertRaises(syncer.SyncError):self.run_sync(**kwargs)
                self.assertEqual(self.output.read_bytes(),self.original)
        self.assertIsNone(syncer.NoRedirects().redirect_request(None,None,302,'',{},'https://attacker.invalid/'))
    def test_response_size_compression_and_timeout_budgets(self):
        variants=[{'response':Response(b'x',headers={'Content-Length':str(syncer.MAX_BYTES+1)})},
                  {'response':Response(b'x'*(syncer.MAX_BYTES+1))},
                  {'response':Response(self.original,headers={'Content-Encoding':'gzip'})},
                  {'response':Response(self.original),'monotonic':iter([0,11]).__next__}]
        for kwargs in variants:
            with self.subTest(headers=kwargs.get('response').headers):
                with self.assertRaises(syncer.SyncError):self.run_sync(**kwargs)
                self.assertEqual(self.output.read_bytes(),self.original)
    def test_network_and_malformed_json_leave_previous_file(self):
        for kwargs in [{'error':urllib.error.URLError('SECRET-MUST-NOT-LEAK')},{'response':Response(b'{invalid-json')}]:
            with self.subTest(case=list(kwargs)):
                with self.assertRaises((syncer.SyncError,ValueError)):self.run_sync(**kwargs)
                self.assertEqual(self.output.read_bytes(),self.original)
    def test_failed_atomic_replace_retains_old_state_and_removes_stage(self):
        with patch.object(syncer.os,'replace',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.run_sync(self.newer())
        self.assertEqual(self.output.read_bytes(),self.original)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['library.json','source-freshness.json'])
    def test_cannot_overwrite_library_or_follow_output_symlink(self):
        with self.assertRaises(syncer.SyncError):syncer.sync(self.library_path,self.library_path,now=NOW)
        self.output.unlink();self.output.symlink_to(self.library_path)
        with self.assertRaises(syncer.SyncError):self.run_sync()
    def test_cli_error_logs_are_fixed_and_do_not_echo_network_payloads(self):
        stream=io.StringIO()
        with patch.object(syncer,'sync',side_effect=syncer.SyncError('SECRET-MUST-NOT-LEAK')),redirect_stderr(stream):
            result=syncer.main(['--library',str(self.library_path),'--output',str(self.output)])
        self.assertEqual(result,1);self.assertNotIn('SECRET',stream.getvalue())
        self.assertEqual(json.loads(stream.getvalue())['error_code'],'freshness_sync_failed')

if __name__=='__main__':unittest.main()
