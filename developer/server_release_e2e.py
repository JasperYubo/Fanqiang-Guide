"""Mandatory Linux installation/upgrade acceptance using isolated real services.

Only DeepSeek account authentication and public ACME issuance use explicit local
fixtures. The installer, hash-pinned dependencies, systemd, Nginx, Xray, TLS,
PicoClaw, manager and upgrade code run as distributed. No customer secret is used.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,re,secrets,subprocess,sys,tempfile,time,urllib.request
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
def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'HuaRun-Linux-Release-Acceptance/1.0','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=40) as response:
        raw=response.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise AcceptanceError('baseline_response_too_large')
    return raw
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
        self.guest(name,'bash','-c','install -m 755 /opt/e2e/curl /usr/local/bin/curl; printf "127.0.0.1 qa.release.invalid preserve.example\\n" >> /etc/hosts')
        self.command(['docker','exec','-d',name,'bash','-c','exec python3 /opt/e2e/provider_fixture.py >/opt/provider-fixture.log 2>&1'])
        for attempt in range(100):
            if self.guest(name,'/usr/bin/curl','-fsS','http://127.0.0.1:14000/directory',check=False).returncode==0:break
            time.sleep(.1)
        else:raise AcceptanceError('provider_fixture_not_ready')
        return name
    def install(self,name,raw,label):
        script=self.work/(label+'.sh');script.write_bytes(raw);script.chmod(0o600)
        self.command(['docker','cp',str(script),name+':/opt/installer.sh'])
        self.guest(name,'bash','-c','export HUARUN_API_KEY=sk-release-test-fixture-not-a-production-key; exec bash /opt/installer.sh --yes --no-swap --domain qa.release.invalid --site 4',timeout=720,log=label+'-install.log')
        actual=self.guest(name,'sha256sum','/opt/installer.sh').stdout.decode().split()[0]
        if actual!=sha(raw):raise AcceptanceError('executed_installer_digest_mismatch')
    def probe(self,name):return json.loads(self.guest(name,'python3','/opt/e2e/guest.py','probe',timeout=90).stdout)
    def fresh(self,raw):
        name=self.start('fresh')
        try:
            self.install(name,raw,'fresh');probe=self.probe(name)
            result={k:probe[k] for k in ['version','timer_enabled','timer_active','services_healthy','proxy_allowed','proxy_blocked','tls_verified','blocked_target_reachable','proxy_block_route_verified','doctor_checks']}
            result['installed_version']=result['version']
            result['passed']=result['version']==version(raw) and all(result[k] is True for k in ['timer_enabled','timer_active','services_healthy','proxy_allowed','proxy_blocked','tls_verified','blocked_target_reachable','proxy_block_route_verified'])
            if not result['passed']:raise AcceptanceError('fresh_install_checks_failed:'+json.dumps(result,sort_keys=True))
            return result
        finally:self.remove(name)
    def upgrade(self,candidate,baseline):
        name=self.start('upgrade')
        label='upgrade-'+baseline['version']
        try:
            self.install(name,baseline['raw'],label)
            before_version=self.guest(name,'/usr/local/bin/huarun','version').stdout.decode().strip()
            if before_version!=baseline['version']:raise AcceptanceError('installed_baseline_version_mismatch')
            before=json.loads(self.guest(name,'python3','/opt/e2e/guest.py','customize',timeout=60).stdout)
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
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-sha',required=True);parser.add_argument('--output',required=True,type=pathlib.Path);parser.add_argument('--allow-dirty',action='store_true',help='Local development only; emitted evidence cannot authorize publication')
    args=parser.parse_args();output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    raw=(ROOT/'apps/server/install.sh').read_bytes()
    report={'schema_version':1,'kind':'huarun-linux-release-e2e','source_sha':args.source_sha,'installer_sha256':sha(raw),'candidate_version':version(raw),'platform':'linux','run_id':os.environ.get('GITHUB_RUN_ID','local'),'run_attempt':int(os.environ.get('GITHUB_RUN_ATTEMPT','1')),'skipped':0,'started_at':datetime.now(timezone.utc).isoformat(),'passed':False,'fresh_install':None,'upgrades':[],'limitations':['DeepSeek account authentication uses a synthetic Key and local model-list fixture; paid model inference is outside this release gate.','Public ACME issuance uses an isolated test CA; the real hash-pinned acme.sh validates local HTTP-01 and submits a real CSR.','Linux Debian 12 amd64 systemd containers; other OS/architectures and public DNS propagation are outside this acceptance run.']}
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
        selected=baselines(args.source_sha)
        print('Linux release acceptance: '+str(len(selected))+' pinned upgrade baselines',flush=True)
        with tempfile.TemporaryDirectory(prefix='huarun-release-e2e-') as temp:
            work=pathlib.Path(temp);work.chmod(0o700);runner=Runner(work)
            try:
                runner.build();report['fresh_install']=runner.fresh(raw);print('fresh_install passed',flush=True)
                for baseline in selected:
                    report['upgrades'].append(runner.upgrade(raw,baseline));print('upgrade '+baseline['version']+' passed',flush=True)
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
        if runner is not None and runner.last_failure is not None:report['last_failure']=runner.last_failure
        report['passed']=False
    finally:
        report['completed_at']=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'output':str(output),'error':report.get('error')},ensure_ascii=False))
    return 0 if report['passed'] else 1
if __name__=='__main__':sys.exit(main())
