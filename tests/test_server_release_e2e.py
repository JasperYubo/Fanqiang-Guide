import contextlib,hashlib,importlib.util,io,json,os,pathlib,sys,tempfile,types,unittest,urllib.error,urllib.request
from unittest.mock import MagicMock,patch
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
class FetchTests(unittest.TestCase):
    API='https://api.github.com/repos/JasperYubo/Fanqiang-Guide/releases/latest'
    ASSET='https://github.com/JasperYubo/Fanqiang-Guide/releases/download/release-eb97d143b054/huarun-install.sh'
    CDN='https://release-assets.githubusercontent.com/github-production-release-asset/test?sig=private-signed-url'
    TOKEN='synthetic_ci_read_secret'
    def response(self,raw=b'ok',headers=None):
        result=MagicMock();result.__enter__.return_value=result;result.read.return_value=raw;result.headers=headers or {};result.status=200;return result
    def error(self,code,headers=None):
        return urllib.error.HTTPError(self.API,code,'body-must-not-leak',headers or {},io.BytesIO(b'secret-body'))
    def request(self,outcomes,url=None):
        opener=MagicMock();opener.open.side_effect=outcomes
        output=io.StringIO()
        with patch.object(m.urllib.request,'build_opener',return_value=opener),patch.object(m.time,'sleep') as sleep,patch.object(m,'_API_READ_TOKEN',self.TOKEN),contextlib.redirect_stdout(output):
            try:result=m.fetch(url or self.API)
            except m.AcceptanceError as error:result=error
        return result,opener,sleep,output.getvalue()
    def test_retry_503_then_success(self):
        errors=[self.error(503),self.error(503)]
        result,opener,sleep,logs=self.request([*errors,self.response()])
        self.assertEqual(result,b'ok');self.assertEqual(opener.open.call_count,3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[2,4])
        self.assertTrue(all(e.fp.closed for e in errors))
        for secret in [self.TOKEN,'secret-body','body-must-not-leak']:self.assertNotIn(secret,logs)
    def test_http_identity_and_authentication_fail_without_retry(self):
        for code in [401,403,404]:
            with self.subTest(code=code):
                result,opener,sleep,logs=self.request([self.error(code)])
                self.assertIsInstance(result,m.BaselineFetchError);self.assertEqual(result.diagnostic['status'],code)
                self.assertEqual(opener.open.call_count,1);sleep.assert_not_called()
                self.assertIn('previous_stable_metadata',str(result));self.assertNotIn(self.TOKEN,str(result))
    def test_transient_http_retry_budget_and_wait_cap(self):
        for code,headers in [(429,{'Retry-After':'1000000'}),(503,{}),(403,{'X-RateLimit-Remaining':'0'})]:
            with self.subTest(code=code):
                result,opener,sleep,logs=self.request([self.error(code,headers) for _ in range(3)])
                self.assertIsInstance(result,m.BaselineFetchError);self.assertEqual(opener.open.call_count,3)
                self.assertEqual(sleep.call_count,2);self.assertTrue(all(c.args[0]<=10 for c in sleep.call_args_list))
                self.assertEqual(result.diagnostic['attempt'],3)
    def test_retry_after_malformed_and_negative_are_bounded(self):
        for value in ['-1','garbage','Wed, 21 Oct 2030 07:28:00 GMT','999999','0']:
            self.assertGreaterEqual(m.retry_delay({'Retry-After':value},1),1)
            self.assertLessEqual(m.retry_delay({'Retry-After':value},1),10)
    def test_network_timeout_retries_and_never_prints_reason(self):
        result,opener,sleep,logs=self.request([urllib.error.URLError(self.CDN),TimeoutError(self.TOKEN),self.response()])
        self.assertEqual(result,b'ok');self.assertEqual(opener.open.call_count,3)
        self.assertNotIn(self.TOKEN,logs);self.assertNotIn('private-signed-url',logs)
    def test_size_and_truncated_responses_fail(self):
        result,opener,sleep,logs=self.request([self.response(b'x'*(m.FETCH_MAX_BYTES+1))])
        self.assertIsInstance(result,m.BaselineFetchError);self.assertEqual(result.diagnostic['category'],'size');sleep.assert_not_called()
        result,opener,sleep,logs=self.request([self.response(b'partial',{'Content-Length':'100'}) for _ in range(3)])
        self.assertIsInstance(result,m.BaselineFetchError);self.assertEqual(result.diagnostic['category'],'transport');self.assertEqual(opener.open.call_count,3)
    def test_token_scoped_to_exact_api_read_endpoints(self):
        raw='https://raw.githubusercontent.com/'+m.REPO+'/'+m.PINS[0]['source_sha']+'/apps/server/install.sh'
        for url,authorized in [(self.API,True),(self.API.replace('/latest','?per_page=100'),True),(raw,False),(self.ASSET,False)]:
            result,opener,sleep,logs=self.request([self.response()],url)
            request=opener.open.call_args.args[0]
            self.assertEqual(request.get_header('Authorization'),('Bearer '+self.TOKEN) if authorized else None)
    def test_untrusted_url_is_rejected_before_network(self):
        invalid=[self.API+'#frag',self.API+'?extra=1',self.API.replace('https:','http:'),self.API.replace('api.github.com','api.github.com:443'),self.API.replace('api.github.com','user@api.github.com'),self.API.replace('releases/latest','%72eleases/latest'),self.API.replace('/latest','/123/assets'),self.API.replace('JasperYubo','untrusted'),self.API.replace('api.github.com','api.github.com.evil')]
        for url in invalid:
            with self.subTest(url=url),patch.object(m.urllib.request,'build_opener') as opener:
                with self.assertRaises(m.AcceptanceError):m.fetch(url)
                opener.assert_not_called()
    def test_api_and_raw_redirects_never_follow(self):
        handler=m.BaselineRedirectHandler()
        for url in [self.API,self.API.replace('api.github.com','raw.githubusercontent.com')]:
            request=urllib.request.Request(url,headers={'Authorization':'Bearer '+self.TOKEN})
            for target in [self.API,self.CDN,'https://evil.invalid/']:
                fp=io.BytesIO()
                with self.assertRaises(m.AcceptanceError):handler.redirect_request(request,fp,302,'',{},target)
                self.assertTrue(fp.closed)
    def test_asset_redirect_is_anonymous_and_cdns_cannot_escape(self):
        handler=m.BaselineRedirectHandler();request=urllib.request.Request(self.ASSET,headers={'Authorization':'Bearer '+self.TOKEN})
        redirected=handler.redirect_request(request,None,302,'',{},self.CDN)
        self.assertIsNone(redirected.get_header('Authorization'))
        self.assertEqual(redirected.full_url,self.CDN)
        for target in [self.API,self.ASSET,self.CDN.replace('https:','http:'),self.CDN.replace('.com/','.com.evil/'),self.CDN+'#fragment',self.CDN.replace('.com/','.com:443/')]:
            with self.subTest(target=target),self.assertRaises(m.AcceptanceError):handler.redirect_request(redirected,None,302,'',{},target)
        self.assertEqual(handler.max_redirections,3);self.assertEqual(handler.max_repeats,1)
    def test_redirect_failure_is_controlled_and_not_retried(self):
        result,opener,sleep,logs=self.request([m.RedirectIdentityError(302)])
        self.assertIsInstance(result,m.BaselineFetchError);self.assertEqual(result.diagnostic['category'],'identity');self.assertEqual(result.diagnostic['status'],302);sleep.assert_not_called()
    def test_main_scrubs_token_before_any_child_and_report_on_success_and_failure(self):
        for fail in [False,True]:
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as directory:
                root=pathlib.Path(directory);(root/'apps/server').mkdir(parents=True)
                raw=b'VERSION="1.2.0"\n';(root/'apps/server/install.sh').write_bytes(raw)
                source='a'*40;output=root/'report.json';args=types.SimpleNamespace(source_sha=source,output=output,allow_dirty=False)
                observed=[]
                def child(*unused,**kwargs):
                    observed.append('HUARUN_BASELINE_GITHUB_TOKEN' not in os.environ)
                    return source+'\n' if kwargs.get('text') else b'' if 'status' in unused[0] else raw
                def baseline(*unused):
                    self.assertNotIn('HUARUN_BASELINE_GITHUB_TOKEN',os.environ)
                    self.assertEqual(m._API_READ_TOKEN,self.TOKEN)
                    if fail:raise m.BaselineFetchError({'source':'previous_stable_metadata','category':'authentication','status':403,'attempt':1,'retryable':False})
                    return []
                runner=MagicMock();runner.fresh.return_value={'passed':True};runner.last_failure=None
                with patch.dict(os.environ,{'HUARUN_BASELINE_GITHUB_TOKEN':self.TOKEN}),patch.object(m,'ROOT',root),patch.object(m.argparse.ArgumentParser,'parse_args',return_value=args),patch.object(m.subprocess,'check_output',side_effect=child),patch.object(m,'baselines',side_effect=baseline),patch.object(m,'Runner',return_value=runner),contextlib.redirect_stdout(io.StringIO()) as logs:
                    self.assertEqual(m.main(),1 if fail else 0)
                    self.assertNotIn('HUARUN_BASELINE_GITHUB_TOKEN',os.environ)
                    self.assertEqual(m._API_READ_TOKEN,'')
                report=output.read_text();self.assertNotIn(self.TOKEN,report);self.assertNotIn(self.TOKEN,logs.getvalue())
                self.assertTrue(observed);self.assertTrue(all(observed))
                self.assertEqual(json.loads(report)['passed'],not fail)
if __name__=='__main__':unittest.main()
