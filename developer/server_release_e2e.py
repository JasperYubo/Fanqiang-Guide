"""Mandatory Linux installation/upgrade acceptance using isolated real services.

Only DeepSeek account authentication and public ACME issuance use explicit local
fixtures. The installer, hash-pinned dependencies, systemd, Nginx, Xray, TLS,
PicoClaw, manager and upgrade code run as distributed. No customer secret is used.
"""
from __future__ import annotations
import argparse,hashlib,http.client,json,os,pathlib,re,secrets,subprocess,sys,tempfile,time,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'developer/server-e2e'
REPO='JasperYubo/Fanqiang-Guide'
PINS=[{'roles':['legacy-1.0'],'source_sha':'c89b724428683237d037239fd17f8a08473d16a1','installer_sha256':'0a8dd67be1838b0fe674edc51ed75636bd41843e6b9ece8cf26ba38ba380e7c1','version':'1.0.0'},
      {'roles':['legacy-1.1'],'source_sha':'e3d9a186ce961fb12c3b3401e00bc22621fe7242','installer_sha256':'cdb22951eb5c34053fd99863e1d38bafec200217cdc426adfb8c3b7f5b368f6c','version':'1.1.0'}]
class AcceptanceError(Exception):pass
def sha(raw):return hashlib.sha256(raw).hexdigest()
def version(raw):
    match=re.search(rb'^VERSION="([0-9]+\.[0-9]+\.[0-9]+)"$',raw,re.M)
    if not match:raise AcceptanceError('installer_version_missing')
    return match[1].decode()
# Set only by main(), then removed from the environment before any child starts.
# This token can read this repository in CI; it never reaches installers/fixtures.
_API_READ_TOKEN=''
FETCH_ATTEMPTS=3
FETCH_MAX_BYTES=2*1024*1024
class BaselineFetchError(AcceptanceError):
    def __init__(self,diagnostic):
        self.diagnostic=diagnostic
        super().__init__('baseline_fetch_failed:'+diagnostic['source']+':'+diagnostic['category']+':'+str(diagnostic.get('status')))
def fetch_source(url):
    """Allow only pinned public installers and this repository's release metadata."""
    api='https://api.github.com/repos/'+REPO+'/releases'
    if url==api+'/latest':return 'previous_stable_metadata',True
    if url==api+'?per_page=100':return 'previous_stable_list',True
    legacy=re.fullmatch(re.escape('https://raw.githubusercontent.com/'+REPO+'/')+r'([a-f0-9]{40})/apps/server/install\.sh',url)
    if legacy and any(pin['source_sha']==legacy.group(1) for pin in PINS):return 'legacy_installer:'+legacy.group(1)[:12],False
    asset=re.fullmatch(re.escape('https://github.com/'+REPO+'/releases/download/release-')+r'([a-f0-9]{12})/huarun-install\.sh',url)
    if asset:return 'previous_stable_installer:'+asset.group(1),False
    raise AcceptanceError('baseline_fetch_source_not_allowed')
class RedirectIdentityError(AcceptanceError):
    def __init__(self,status):
        self.status=status
        super().__init__('baseline_redirect_not_allowed')
class BaselineRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections=3
    max_repeats=1
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        # API and raw origins must resolve directly. Release downloads alone use
        # GitHub's observed CDN; never forward Authorization, even same-origin.
        old=urllib.parse.urlsplit(req.full_url);new=urllib.parse.urlsplit(newurl)
        if (old.hostname not in {'github.com','release-assets.githubusercontent.com'}
                or new.scheme!='https' or new.netloc!='release-assets.githubusercontent.com' or new.fragment or '\\' in newurl):
            if fp is not None:fp.close()
            raise RedirectIdentityError(code)
        redirected=super().redirect_request(req,fp,code,msg,headers,newurl)
        if redirected is not None:
            redirected.remove_header('Authorization')
        return redirected
def retry_delay(headers,attempt):
    value=headers.get('Retry-After','') if headers else ''
    # Bound both server-directed waits and exponential backoff. A long quota
    # reset fails visibly after this budget; it cannot hang a release job.
    return min(10,max(1,int(value))) if value.isdigit() else min(10,2**attempt)
def fetch(url):
    source,api=fetch_source(url)
    headers={'User-Agent':'HuaRun-Linux-Release-Acceptance/1.0','Accept':'application/vnd.github+json'}
    if api and _API_READ_TOKEN:headers['Authorization']='Bearer '+_API_READ_TOKEN
    opener=urllib.request.build_opener(BaselineRedirectHandler())
    for attempt in range(1,FETCH_ATTEMPTS+1):
        request=urllib.request.Request(url,headers=headers)
        try:
            with opener.open(request,timeout=40) as response:
                if response.status!=200:raise urllib.error.HTTPError(url,response.status,'unexpected_baseline_status',response.headers,None)
                raw=response.read(FETCH_MAX_BYTES+1)
                length=response.headers.get('Content-Length','')
                if len(raw)<=FETCH_MAX_BYTES and length.isdigit() and len(raw)!=int(length):raise http.client.IncompleteRead(raw)
            if len(raw)>FETCH_MAX_BYTES:raise AcceptanceError('baseline_response_too_large:'+source)
            print(json.dumps({'baseline_fetch':{'source':source,'status':200,'attempt':attempt,'bytes':len(raw)}}),flush=True)
            return raw
        except urllib.error.HTTPError as error:
            status=error.code
            rate_limited=status==429 or (status==403 and (error.headers.get('X-RateLimit-Remaining')=='0' or error.headers.get('Retry-After')))
            category='rate_limited' if rate_limited else 'authentication' if status in (401,403) else 'http'
            retryable=bool(rate_limited or 500<=status<=599)
            diagnostic={'source':source,'category':category,'status':status,'attempt':attempt,'retryable':retryable}
            delay=retry_delay(error.headers,attempt);error.close()
        except (urllib.error.URLError,TimeoutError,ConnectionError,http.client.IncompleteRead) as error:
            diagnostic={'source':source,'category':'transport','status':None,'attempt':attempt,'retryable':True}
            delay=retry_delay(None,attempt)
        except AcceptanceError as error:
            diagnostic={'source':source,'category':'identity' if isinstance(error,RedirectIdentityError) else 'size','status':getattr(error,'status',None),'attempt':attempt,'retryable':False}
            raise BaselineFetchError(diagnostic) from None
        print(json.dumps({'baseline_fetch':diagnostic}),flush=True)
        if not diagnostic['retryable'] or attempt==FETCH_ATTEMPTS:raise BaselineFetchError(diagnostic) from None
        time.sleep(delay)
    raise AcceptanceError('baseline_fetch_retry_budget_exhausted')
def select_previous(releases,source_sha):
    if not isinstance(releases,list):raise AcceptanceError('baseline_release_list_invalid')
    candidates=[r for r in releases if isinstance(r,dict) and r.get('draft') is False and r.get('prerelease') is False and r.get('target_commitish')!=source_sha]
    candidates.sort(key=lambda r:(str(r.get('published_at','')),r.get('id',0)),reverse=True)
    if not candidates:raise AcceptanceError('previous_stable_release_missing')
    release=candidates[0];source=release.get('target_commitish','');tag='release-'+source[:12]
    if not re.fullmatch(r'[a-f0-9]{40}',source) or release.get('tag_name')!=tag or type(release.get('id')) is not int:raise AcceptanceError('baseline_source_not_pinned')
    assets=[a for a in release.get('assets',[]) if a.get('name')=='huarun-install.sh']
    if len(assets)!=1:raise AcceptanceError('baseline_installer_asset_missing')
    asset=assets[0];url='https://github.com/'+REPO+'/releases/download/'+tag+'/huarun-install.sh'
    if asset.get('browser_download_url')!=url or asset.get('state')!='uploaded' or not isinstance(asset.get('digest'),str) or not re.fullmatch(r'sha256:[a-f0-9]{64}',asset.get('digest','')):raise AcceptanceError('baseline_asset_identity_invalid')
    raw=fetch(url)
    if len(raw)!=asset.get('size') or sha(raw)!=asset['digest'][7:]:raise AcceptanceError('baseline_asset_digest_mismatch')
    return {'roles':['previous-stable'],'source_sha':source,'installer_sha256':sha(raw),'version':version(raw),'release_id':release['id'],'raw':raw}
def baselines(source_sha):
    result=[]
    for item in PINS:
        item={**item,'roles':list(item['roles'])}
        git=subprocess.run(['git','-C',str(ROOT),'show',item['source_sha']+':apps/server/install.sh'],capture_output=True)
        raw=git.stdout if git.returncode==0 else fetch('https://raw.githubusercontent.com/'+REPO+'/'+item['source_sha']+'/apps/server/install.sh')
        if sha(raw)!=item['installer_sha256'] or version(raw)!=item['version']:raise AcceptanceError('legacy_installer_pin_mismatch')
        item['raw']=raw;result.append(item)
    latest=json.loads(fetch('https://api.github.com/repos/'+REPO+'/releases/latest'))
    releases=json.loads(fetch('https://api.github.com/repos/'+REPO+'/releases?per_page=100')) if latest.get('target_commitish')==source_sha else [latest]
    previous=select_previous(releases,source_sha)
    duplicate=next((b for b in result if b['source_sha']==previous['source_sha'] and b['installer_sha256']==previous['installer_sha256']),None)
    if duplicate:
        duplicate['roles'].append('previous-stable');duplicate['release_id']=previous['release_id']
    else:result.append(previous)
    return result
def safe_log_tail(raw):
    text=raw.decode('utf-8',errors='replace') if isinstance(raw,bytes) else str(raw)
    text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',text)
    text=re.sub(r'sk-[A-Za-z0-9_-]+','[redacted-key]',text)
    text=re.sub(r'(?i)vmess://\S+','[redacted-node-link]',text)
    text=re.sub(r'(?i)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}','[redacted-node-id]',text)
    text=re.sub(r'(?i)(authorization[=: ]+bearer\s+)\S+',r'\1[redacted]',text)
    return '\n'.join(text.splitlines()[-25:])[-5000:]
class Runner:
    def __init__(self,work):self.work=work;self.containers=[];self.deadline=time.monotonic()+3300;self.last_failure=None
    def command(self,args,*,timeout=60,input=None,log=None,check=True):
        left=int(self.deadline-time.monotonic())
        if left<=0:raise AcceptanceError('acceptance_deadline_exceeded')
        try:
            result=subprocess.run(args,input=input,capture_output=True,timeout=min(timeout,left))
        except subprocess.TimeoutExpired as error:
            self.last_failure={'stage':str(log or pathlib.Path(args[0]).name),'exit_code':None,'timeout':True,'log_tail':safe_log_tail((error.stdout or b'')+(error.stderr or b''))}
            print(json.dumps({'acceptance_failure':self.last_failure},ensure_ascii=False),flush=True)
            raise AcceptanceError('command_timeout:'+str(log or pathlib.Path(args[0]).name)) from None
        if log:
            path=self.work/log;path.write_bytes(result.stdout+result.stderr);path.chmod(0o600)
        if check and result.returncode:
            self.last_failure={'stage':str(log or pathlib.Path(args[0]).name),'exit_code':result.returncode,'timeout':False,'log_tail':safe_log_tail(result.stdout+result.stderr)}
            print(json.dumps({'acceptance_failure':self.last_failure},ensure_ascii=False),flush=True)
            raise AcceptanceError('command_failed:'+str(log or pathlib.Path(args[0]).name))
        return result
    def build(self):
        key=sha((FIXTURES/'Dockerfile').read_bytes())[:16];self.image='huarun-release-e2e:'+key
        self.command(['docker','build','--tag',self.image,str(FIXTURES)],timeout=600,log='image-build.log')
    def guest(self,name,*args,timeout=60,log=None,input=None,check=True):
        return self.command(['docker','exec','-i',name,*args],timeout=timeout,log=log,input=input,check=check)
    def start(self,label):
        name='huarun-release-e2e-'+secrets.token_hex(6)+'-'+label
        self.command(['docker','run','-d','--name',name,'--label','huarun.release-e2e=true','--privileged','--cgroupns=host','--tmpfs','/run','--tmpfs','/run/lock','--tmpfs','/tmp','-v','/sys/fs/cgroup:/sys/fs/cgroup:rw',self.image],timeout=45)
        self.containers.append(name)
        for attempt in range(100):
            result=self.guest(name,'systemctl','is-system-running',check=False)
            if result.stdout.strip() in (b'running',b'degraded'):break
            time.sleep(.2)
        else:raise AcceptanceError('systemd_not_ready')
        self.command(['docker','cp',str(FIXTURES),name+':/opt/e2e'],timeout=30)
        self.command(['docker','cp',str(ROOT/'apps/server/tests/egress_live_probe.py'),name+':/opt/e2e/exit_fixture.py'],timeout=30)
        self.guest(name,'bash','-c','install -m 755 /opt/e2e/curl /usr/local/bin/curl; install -m 644 /opt/e2e/sitecustomize.py /usr/lib/python3.11/sitecustomize.py; printf "127.0.0.1 qa.release.invalid migrated.release.invalid rollback.release.invalid preserve.example\\n" >> /etc/hosts')
        self.command(['docker','exec','-d',name,'bash','-c','exec python3 /opt/e2e/provider_fixture.py >/opt/provider-fixture.log 2>&1'])
        for attempt in range(100):
            if self.guest(name,'/usr/bin/curl','-fsS','http://127.0.0.1:14000/directory',check=False).returncode==0:break
            time.sleep(.1)
        else:raise AcceptanceError('provider_fixture_not_ready')
        return name
    def install(self,name,raw,label):
        script=self.work/(label+'.sh');script.write_bytes(raw);script.chmod(0o600)
        self.command(['docker','cp',str(script),name+':/opt/installer.sh'])
        new_network=tuple(int(x) for x in version(raw).split('.'))>=(1,3,0)
        config={'schema_version':1,'domain':'qa.release.invalid','cloudflare':{'account_id':'1'*32,'zone_id':'2'*32,'api_token':'synthetic-cloudflare-token-fixture-only','proxied':False},'address_source':{'mode':'static','addresses':{'A':'8.8.8.8'}},'notification':{'kind':'none'},'probes':[]}
        flags=' --network-config-stdin' if new_network else ''
        self.guest(name,'bash','-c','export HUARUN_API_KEY=sk-release-test-fixture-not-a-production-key; exec bash /opt/installer.sh --yes --no-swap --domain qa.release.invalid --site 4'+flags,timeout=720,log=label+'-install.log',input=json.dumps(config).encode() if new_network else None)
        actual=self.guest(name,'sha256sum','/opt/installer.sh').stdout.decode().split()[0]
        if actual!=sha(raw):raise AcceptanceError('executed_installer_digest_mismatch')
    def probe(self,name):return json.loads(self.guest(name,'python3','/opt/e2e/guest.py','probe',timeout=90).stdout)
    def fresh(self,raw):
        name=self.start('fresh')
        try:
            self.install(name,raw,'fresh');probe=self.probe(name)
            result={k:probe[k] for k in ['version','timer_enabled','timer_active','services_healthy','proxy_allowed','proxy_blocked','tls_verified','blocked_target_reachable','proxy_block_route_verified','doctor_checks']}
            result['installed_version']=result['version']
            if tuple(int(x) for x in version(raw).split('.'))>=(1,3,0):
                result['network_features']=json.loads(self.guest(name,'python3','/opt/e2e/network_features.py',timeout=900,log='network-features.log').stdout)
                if result['network_features'].get('passed') is not True:raise AcceptanceError('network_feature_checks_failed')
            if tuple(int(x) for x in version(raw).split('.'))>=(1,4,0):
                assisted_args=['--assisted'] if tuple(int(x) for x in version(raw).split('.'))>=(1,4,1) else []
                result['generic_provider_features']=json.loads(self.guest(name,'python3','/opt/e2e/generic_provider_features.py',*assisted_args,timeout=600,log='generic-provider-features.log').stdout)
                if result['generic_provider_features'].get('passed') is not True:raise AcceptanceError('generic_provider_feature_checks_failed')
            result['passed']=result['version']==version(raw) and all(result[k] is True for k in ['timer_enabled','timer_active','services_healthy','proxy_allowed','proxy_blocked','tls_verified','blocked_target_reachable','proxy_block_route_verified'])
            if not result['passed']:raise AcceptanceError('fresh_install_checks_failed:'+json.dumps(result,sort_keys=True))
            return result
        finally:self.remove(name)
    def upgrade(self,candidate,baseline,*,seed_network=True):
        name=self.start('upgrade')
        label='upgrade-'+baseline['version']
        try:
            self.install(name,baseline['raw'],label)
            before_version=self.guest(name,'/usr/local/bin/huarun','version').stdout.decode().strip()
            if before_version!=baseline['version']:raise AcceptanceError('installed_baseline_version_mismatch')
            new_network=tuple(int(x) for x in version(candidate).split('.'))>=(1,3,0)
            extras=['--network-configs'] if seed_network and new_network else []
            generic_release=tuple(int(x) for x in version(candidate).split('.'))>=(1,4,0)
            if seed_network and generic_release:extras.append('--generic-state')
            before=json.loads(self.guest(name,'python3','/opt/e2e/guest.py','customize',*extras,timeout=60).stdout)
            # Verify that the custom baseline already has an operational proxy.
            baseline_probe=self.probe(name)
            if not all(baseline_probe[k] is True for k in ['services_healthy','proxy_allowed','proxy_blocked','tls_verified','blocked_target_reachable','proxy_block_route_verified']):raise AcceptanceError('legacy_baseline_unhealthy:'+json.dumps(baseline_probe,sort_keys=True))
            script=self.work/'candidate.sh';script.write_bytes(candidate);script.chmod(0o600)
            self.command(['docker','cp',str(script),name+':/opt/candidate.sh'])
            self.guest(name,'bash','/opt/candidate.sh','--upgrade-assistant','--yes',timeout=720,log=label+'-upgrade.log')
            after=json.loads(self.guest(name,'python3','/opt/e2e/guest.py','snapshot').stdout);probe=self.probe(name)
            preserved={key:before['snapshot'][key]==after['snapshot'][key] for key in before['snapshot']}
            result={'roles':baseline['roles'],'from_version':before_version,'to_version':probe['version'],'baseline_source_sha':baseline['source_sha'],'baseline_installer_sha256':baseline['installer_sha256'],'preserved':preserved,'preservation_checks':{'before':before['snapshot'],'after':after['snapshot']},'network_processes_unchanged':before['processes']==after['processes']}
            if 'release_id' in baseline:result['baseline_release_id']=baseline['release_id']
            result.update({k:probe[k] for k in ['timer_enabled','timer_active','services_healthy','proxy_allowed','proxy_blocked','tls_verified','blocked_target_reachable','proxy_block_route_verified','doctor_checks']})
            result['passed']=result['to_version']==version(candidate) and all(preserved.values()) and all(result[k] is True for k in ['network_processes_unchanged','timer_enabled','timer_active','services_healthy','proxy_allowed','proxy_blocked','tls_verified','blocked_target_reachable','proxy_block_route_verified'])
            if new_network:
                result.update({k:probe[k] for k in ['network_timer_enabled','network_timer_active']})
                result['passed']=result['passed'] and result['network_timer_enabled'] and result['network_timer_active']
                if not seed_network:
                    status=json.loads(self.guest(name,'/usr/local/bin/huarun','network','status').stdout)
                    result.update(network_config_absent=not after['snapshot']['network_config']['exists'],egress_config_absent=not after['snapshot']['egress_config']['exists'],network_status_not_configured=status.get('configured') is False and status.get('status')=='not_configured')
                    result['passed']=result['passed'] and all(result[k] is True for k in ['network_config_absent','egress_config_absent','network_status_not_configured'])
                    if generic_release:
                        result['generic_provider_state_absent']=not after['snapshot']['generic_provider_state']['exists']
                        result['passed']=result['passed'] and result['generic_provider_state_absent']
            if not result['passed']:raise AcceptanceError('upgrade_checks_failed:'+json.dumps(result,sort_keys=True))
            return result
        finally:self.remove(name)
    def remove(self,name):
        if name not in self.containers:return
        # Exact names generated by this process; never select or delete foreign containers.
        result=subprocess.run(['docker','rm','--force',name],capture_output=True,timeout=30)
        if result.returncode:raise AcceptanceError('container_cleanup_failed')
        self.containers.remove(name)
    def close(self):
        for name in list(self.containers):self.remove(name)
def main():
    global _API_READ_TOKEN
    _API_READ_TOKEN=os.environ.pop('HUARUN_BASELINE_GITHUB_TOKEN','')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-sha',required=True);parser.add_argument('--output',required=True,type=pathlib.Path);parser.add_argument('--allow-dirty',action='store_true',help='Local development only; emitted evidence cannot authorize publication')
    args=parser.parse_args();output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    raw=(ROOT/'apps/server/install.sh').read_bytes()
    report={'schema_version':1,'kind':'huarun-linux-release-e2e','source_sha':args.source_sha,'installer_sha256':sha(raw),'candidate_version':version(raw),'platform':'linux','run_id':os.environ.get('GITHUB_RUN_ID','local'),'run_attempt':int(os.environ.get('GITHUB_RUN_ATTEMPT','1')),'skipped':0,'started_at':datetime.now(timezone.utc).isoformat(),'passed':False,'fresh_install':None,'upgrades':[],'limitations':['DeepSeek account authentication uses a synthetic Key and local model-list fixture; paid model inference is outside this release gate.','Public ACME issuance uses an isolated test CA; real hash-pinned acme.sh validates HTTP-01 or Cloudflare DNS-01 fixture records and submits a real CSR. Cloudflare HTTP contracts use a synthetic account and token. For loopback .release.invalid node probes only, the harness adds its test CA to the original real-Xray probe; unknown-CA and wrong-SAN negative controls must reject.','Notification failure/recovery and two-region probes use local signed HTTP contracts; no live Telegram delivery or live regional observer claim. SOCKS5/HTTP CONNECT use real authenticated local proxy servers and external HTTPS targets.','For 1.4 generic discovery, official documents/search/model responses and VPS APIs use explicit local HTTP contracts. The installed discovery/interpreter/network code executes unchanged; paid model inference, live vendor API conformance, and cloud allocation are not established by this fixture evidence.','Linux Debian 12 amd64 systemd containers; other OS/architectures and public DNS propagation are outside this acceptance run.']}
    if args.allow_dirty:report['development_only']=True
    runner=None
    try:
        if sys.platform!='linux' or not re.fullmatch(r'[a-f0-9]{40}',args.source_sha):raise AcceptanceError('linux_source_identity_required')
        if args.allow_dirty and os.environ.get('GITHUB_ACTIONS')=='true':raise AcceptanceError('development_mode_forbidden_in_ci')
        head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
        if head!=args.source_sha:raise AcceptanceError('source_head_mismatch')
        if not args.allow_dirty:
            if subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain']).strip():raise AcceptanceError('source_checkout_dirty')
            if subprocess.check_output(['git','-C',str(ROOT),'show',args.source_sha+':apps/server/install.sh'])!=raw:raise AcceptanceError('source_installer_mismatch')
        try:selected=baselines(args.source_sha)
        finally:_API_READ_TOKEN=''
        print('Linux release acceptance: '+str(len(selected))+' pinned upgrade baselines',flush=True)
        with tempfile.TemporaryDirectory(prefix='huarun-release-e2e-') as temp:
            work=pathlib.Path(temp);work.chmod(0o700);runner=Runner(work)
            try:
                if tuple(int(x) for x in version(raw).split('.'))>=(1,3,0):
                    fault_args=['--assisted'] if tuple(int(x) for x in version(raw).split('.'))>=(1,4,1) else ['--generic'] if tuple(int(x) for x in version(raw).split('.'))>=(1,4,0) else []
                    report['network_fault_tests']=json.loads(runner.command([sys.executable,str(FIXTURES/'fault_suites.py'),*fault_args],timeout=300,log='network-fault-suites.log').stdout)
                    if report['network_fault_tests'].get('passed') is not True or report['network_fault_tests'].get('skipped')!=0:raise AcceptanceError('network_fault_suite_failed')
                    print('network fault suites passed without skips',flush=True)
                runner.build();report['fresh_install']=runner.fresh(raw);print('fresh_install passed',flush=True)
                for baseline in selected:
                    report['upgrades'].append(runner.upgrade(raw,baseline));print('upgrade '+baseline['version']+' passed',flush=True)
                if tuple(int(x) for x in version(raw).split('.'))>=(1,3,0):
                    legacy=next(b for b in selected if 'legacy-1.0' in b['roles'])
                    report['unconfigured_upgrade']=runner.upgrade(raw,legacy,seed_network=False)
                    print('unconfigured legacy upgrade passed',flush=True)
                report['passed']=True
            except Exception:
                # The logs contain synthetic test credentials only. Keep private logs
                # on failure for diagnosis; never upload them with public evidence.
                logdir=output.parent/(output.stem+'-private-logs');logdir.mkdir(mode=0o700,exist_ok=True)
                for path in work.glob('*.log'):
                    target=logdir/path.name;target.write_bytes(path.read_bytes());target.chmod(0o600)
                raise
            finally:runner.close()
    except Exception as error:
        report['error']=str(error) if isinstance(error,AcceptanceError) else type(error).__name__
        if isinstance(error,BaselineFetchError):report['baseline_failure']=error.diagnostic
        if runner is not None and runner.last_failure is not None:report['last_failure']=runner.last_failure
        report['passed']=False
    finally:
        _API_READ_TOKEN=''
        report['completed_at']=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'output':str(output),'error':report.get('error')},ensure_ascii=False))
    return 0 if report['passed'] else 1
if __name__=='__main__':sys.exit(main())
