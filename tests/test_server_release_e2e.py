import hashlib,importlib.util,json,pathlib,sys,unittest
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('server_release_e2e',ROOT/'developer/server_release_e2e.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.raw=b'#!/bin/bash\nVERSION="1.2.0"\n'
        self.source='a'*40
        self.url='https://github.com/JasperYubo/Fanqiang-Guide/releases/download/release-'+self.source[:12]+'/huarun-install.sh'
        self.release={'id':10,'draft':False,'prerelease':False,'published_at':'2026-11-15T01:00:00Z','target_commitish':self.source,'tag_name':'release-'+self.source[:12],'assets':[{'name':'huarun-install.sh','state':'uploaded','size':len(self.raw),'digest':'sha256:'+hashlib.sha256(self.raw).hexdigest(),'browser_download_url':self.url}]}
    def select(self,release=None):
        with patch.object(m,'fetch',return_value=self.raw) as fetch:
            result=m.select_previous([release or self.release],'b'*40)
            fetch.assert_called_once_with(self.url)
            return result
    def test_pinned_public_baseline(self):
        result=self.select();self.assertEqual(result['release_id'],10);self.assertEqual(result['version'],'1.2.0')
    def test_exclude_current_candidate_and_unpublished(self):
        current={**self.release,'id':20,'target_commitish':'b'*40,'published_at':'2026-11-16T00:00:00Z'}
        draft={**current,'id':30,'target_commitish':'c'*40,'draft':True}
        prerelease={**current,'id':40,'target_commitish':'d'*40,'prerelease':True}
        with patch.object(m,'fetch',return_value=self.raw):self.assertEqual(m.select_previous([draft,current,prerelease,self.release],'b'*40)['release_id'],10)
    def test_missing_stable_fails_closed(self):
        with self.assertRaises(m.AcceptanceError):m.select_previous([],'b'*40)
    def test_non_commit_baseline_fails(self):
        with self.assertRaises(m.AcceptanceError):self.select({**self.release,'target_commitish':'main'})
    def test_tag_identity_required(self):
        with self.assertRaises(m.AcceptanceError):self.select({**self.release,'tag_name':'unrelated'})
    def test_no_untrusted_asset_location(self):
        bad={**self.release,'assets':[{**self.release['assets'][0],'browser_download_url':'https://example.com/malicious.sh'}]}
        with patch.object(m,'fetch') as fetch:
            with self.assertRaises(m.AcceptanceError):m.select_previous([bad],'b'*40)
            fetch.assert_not_called()
    def test_digest_failure_stops_baseline(self):
        bad={**self.release,'assets':[{**self.release['assets'][0],'digest':'sha256:'+'0'*64}]}
        with self.assertRaises(m.AcceptanceError):self.select(bad)
    def test_size_failure_stops_baseline(self):
        bad={**self.release,'assets':[{**self.release['assets'][0],'size':3}]}
        with self.assertRaises(m.AcceptanceError):self.select(bad)
    def test_duplicated_installer_fails(self):
        with self.assertRaises(m.AcceptanceError):self.select({**self.release,'assets':self.release['assets']*2})
    def test_missing_digest_fails(self):
        bad={**self.release,'assets':[{**self.release['assets'][0],'digest':None}]}
        with self.assertRaises(m.AcceptanceError):self.select(bad)
    def test_latest_marker_wins_over_publication_date(self):
        urls=[]
        def fetch(url):
            urls.append(url)
            if url.endswith('/releases/latest'):return json.dumps(self.release).encode()
            if url==self.url:return self.raw
            raise AssertionError('release list must not be consulted when latest differs from candidate')
        with patch.object(m,'PINS',[]),patch.object(m,'fetch',side_effect=fetch):
            result=m.baselines('b'*40)
        self.assertEqual(result[0]['release_id'],10)
        self.assertFalse(any('per_page' in u for u in urls))
    def test_current_latest_uses_previous_stable_list(self):
        current={**self.release,'target_commitish':'b'*40}
        def fetch(url):
            if url.endswith('/releases/latest'):return json.dumps(current).encode()
            if '/releases?per_page=' in url:return json.dumps([current,self.release]).encode()
            if url==self.url:return self.raw
            raise AssertionError(url)
        with patch.object(m,'PINS',[]),patch.object(m,'fetch',side_effect=fetch):self.assertEqual(m.baselines('b'*40)[0]['release_id'],10)
    def test_failure_log_redacts_keys_and_node_credentials(self):
        raw='token sk-secretvalue node vmess://abcd01234 id 12345678-1234-1234-1234-123456789abc Authorization: Bearer top-secret'
        tail=m.safe_log_tail(raw)
        for secret in ['sk-secretvalue','vmess://abcd01234','12345678-1234-1234-1234-123456789abc','top-secret']:self.assertNotIn(secret,tail)
        self.assertIn('redacted',tail)
    def test_cleanup_ignores_expired_execution_deadline(self):
        runner=m.Runner(pathlib.Path('/tmp'));runner.deadline=0;runner.containers=['owned-test']
        with patch.object(m.subprocess,'run',return_value=m.subprocess.CompletedProcess([],0)) as run:
            runner.remove('owned-test');self.assertEqual(runner.containers,[]);self.assertEqual(run.call_args.args[0],['docker','rm','--force','owned-test'])
    def test_never_removes_foreign_container(self):
        runner=m.Runner(pathlib.Path('/tmp'))
        with patch.object(m.subprocess,'run') as run:runner.remove('foreign');run.assert_not_called()
if __name__=='__main__':unittest.main()
