"""Publish only the public allowlist, build the original static site, and deploy it."""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tarfile,time,urllib.request
from pseo_pipeline import Rejected,atomic

REPO=Path(os.environ.get('PSEO_REPO','/opt/fanqiang-pseo/repo'))
STATE=Path(os.environ.get('PSEO_STATE_DIR','/var/lib/fanqiang-pseo'))
REMOTE='https://github.com/JasperYubo/Fanqiang-Guide.git'
BASE=Path(__file__).resolve().parent
JOURNAL=STATE/'publish'/'source-transaction.json'
OWNERS=STATE/'public-owners'

def git(*args):
    env=dict(os.environ)
    token=env['PSEO_GITHUB_TOKEN']
    env.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0',
      GIT_CONFIG_COUNT='2',GIT_CONFIG_KEY_0='credential.helper',GIT_CONFIG_VALUE_0='',
      GIT_CONFIG_KEY_1='http.'+REMOTE+'.extraheader',
      GIT_CONFIG_VALUE_1='Authorization: Basic '+base64.b64encode(('x-access-token:'+token).encode()).decode())
    for k in ('PSEO_GITHUB_TOKEN','PSEO_ORIGIN_PASSWORD','PSEO_CF_TOKEN','DEEPSEEK_API_KEY','CASE_PIPELINE_TOKEN'):
        env.pop(k,None)
    call=subprocess.run(['git',*args],cwd=REPO if REPO.exists() else REPO.parent,env=env,capture_output=True,text=True,timeout=180)
    if call.returncode:raise Rejected('publisher_git_failed')
    return call.stdout.strip()

def broker(jid,suffix,body):
    req=urllib.request.Request('https://fanqiang.guide/api/chat/internal/cases/'+jid+'/'+suffix,json.dumps(body).encode(),{'Authorization':'Bearer '+os.environ['CASE_PIPELINE_TOKEN'],'Content-Type':'application/json','Origin':'https://fanqiang.guide','Referer':'https://fanqiang.guide/','User-Agent':'Fanqiang-PSEO/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
    except Exception:raise Rejected('publisher_lease_not_valid') from None

def check_lease(jid):
    token=os.environ.get('PSEO_JOB_LEASE_TOKEN')
    if not token:raise Rejected('publisher_missing_lease')
    broker(jid,'heartbeat',{'leaseToken':token})

def load_normalizer():
    spec=importlib.util.spec_from_file_location('case_public_contract',REPO/'apps/site/cases_v10.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module.normalize

def ship_static(folder,jid):
    import paramiko
    stamp=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())
    name='cases-v1.0-'+stamp+'-'+jid[:12]
    archive=STATE/'publish'/name/(name+'.tar.gz');archive.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tarfile.open(archive,'w:gz') as tar:
        for p in sorted(folder.rglob('*')):
            if p.is_file():tar.add(p,arcname='public/'+p.relative_to(folder).as_posix(),recursive=False)
    check_lease(jid)
    c=paramiko.SSHClient();c.load_host_keys(str(BASE/'origin-known-hosts'))
    c.set_missing_host_key_policy(paramiko.RejectPolicy())
    c.connect(os.environ['PSEO_ORIGIN_HOST'],username='root',password=os.environ['PSEO_ORIGIN_PASSWORD'],look_for_keys=False,allow_agent=False,timeout=20)
    try:
        path='/root/fanqiang-cases-v1.0-2026-09-27/'+name+'.tar.gz'
        with c.open_sftp() as s:
            s.put(str(archive),path)
            s.put(str(BASE/'deploy_static.py'),'/root/fanqiang-cases-v1.0-2026-09-27/deploy_static.py')
        check_lease(jid)
        _,out,err=c.exec_command('python3 /root/fanqiang-cases-v1.0-2026-09-27/deploy_static.py --archive '+path+' --name '+name,timeout=120)
        data=out.read();err.read()
        if out.channel.recv_exit_status():raise Rejected('publisher_origin_failed')
        result=json.loads(data)
    finally:c.close()
    atomic(archive.parent/'deployment.json',result)
    return result

def purge(urls):
    req=urllib.request.Request('https://api.cloudflare.com/client/v4/zones/'+os.environ['PSEO_CF_ZONE']+'/purge_cache',json.dumps({'files':urls}).encode(),{'Authorization':'Bearer '+os.environ['PSEO_CF_TOKEN'],'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:result=json.load(r)
    if not result.get('success'):raise Rejected('publisher_cache_failed')

def owner_path(slug):
    return OWNERS/(slug+'.json')

def read_owner(slug):
    p=owner_path(slug)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None

def restore_owner(slug,previous):
    if previous is None:owner_path(slug).unlink(missing_ok=True)
    else:atomic(owner_path(slug),previous)

def source_hash(target):
    return hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None

def reset_case(relative):
    # Restore only the publisher's recorded case path. Other local edits are not touched.
    if not re.fullmatch(r'apps/site/content/cases/public/[a-z0-9]+(?:-[a-z0-9]+)*/case\.json',relative):
        raise Rejected('publisher_invalid_journal_path')
    target=REPO/relative
    # A newly staged file has no HEAD entry: unstage first, then check HEAD.
    git('reset','--quiet','HEAD','--',relative)
    if git('ls-tree','--name-only','HEAD','--',relative):git('restore','--source=HEAD','--worktree','--',relative)
    elif target.exists():target.unlink()
    if target.parent.is_dir() and not any(target.parent.iterdir()):target.parent.rmdir()

def recover_source():
    if JOURNAL.exists():
        txn=json.loads(JOURNAL.read_text(encoding='utf-8'))
        reset_case(txn['relative'])
        # If Git has committed the expected source, ownership follows that source;
        # otherwise restore the previous owner after discarding the interrupted edit.
        committed=git('rev-parse','HEAD')!=txn['before_head'] and source_hash(REPO/txn['relative'])==txn['expected_hash']
        if not committed:restore_owner(txn['slug'],txn['previous_owner'])
        JOURNAL.unlink()
    if git('status','--porcelain'):raise Rejected('publisher_worktree_not_clean')

def refresh_source(jid):
    git('fetch','origin','main')
    ahead=git('log','--format=%s','origin/main..HEAD').splitlines()
    if any(not s.startswith(('更新脱敏咨询案例 ','撤回公开咨询案例 ')) for s in ahead):
        raise Rejected('publisher_unexpected_local_commit')
    if ahead:
        check_lease(jid)
        try:git('-c','user.name=Fanqiang Guide','-c','user.email=fanqiang-guide@users.noreply.github.com','rebase','origin/main')
        except Exception:
            git('rebase','--abort')
            raise Rejected('publisher_rebase_conflict') from None
    else:git('merge','--ff-only','origin/main')

def persist_source(jid):
    # Retry already-committed source even when this run has no diff/new commit.
    for attempt in range(2):
        check_lease(jid)
        try:
            git('push','origin','HEAD:main')
            return
        except Rejected:
            if attempt:raise
            refresh_source(jid)

def publish(kind,input_path,jid):
    if not re.fullmatch('[A-Za-z0-9_-]{1,100}',jid):raise Rejected('invalid_job_id')
    REPO.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not REPO.exists():git('clone',REMOTE,str(REPO))
    recover_source()
    refresh_source(jid)
    raw=json.loads(input_path.read_text(encoding='utf-8'))
    if kind=='publish':
        public=load_normalizer()(raw);slug=public['slug'];url='https://fanqiang.guide/cases/'+slug+'/'
        check_lease(jid)
        broker(jid,'publishing',{'leaseToken':os.environ['PSEO_JOB_LEASE_TOKEN'],'publicUrl':url})
    else:
        url=raw.get('publicUrl','')
        m=re.fullmatch(r'https://fanqiang\.guide/cases/([a-z0-9]+(?:-[a-z0-9]+)*)/',url)
        if not m:raise Rejected('invalid_retraction_url')
        slug=m[1]
        original=raw.get('sourceJobId')
        if not isinstance(original,str) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',original):raise Rejected('publisher_retract_source_required')
        owner=read_owner(slug)
        if owner and owner['job_id']!=original:
            # A newer consultation fully replaced this slug. It contains no old turns.
            check_lease(jid)
            return {'outcome':'retracted','publicUrl':url,'slug':slug}
        if not owner and (REPO/('apps/site/content/cases/public/'+slug+'/case.json')).exists():raise Rejected('publisher_owner_unknown')
    relative='apps/site/content/cases/public/'+slug+'/case.json'
    target=REPO/relative
    previous=read_owner(slug)
    if kind=='publish':
        if target.exists():
            old=load_normalizer()(json.loads(target.read_text(encoding='utf-8')))
            public['published_at']=old['published_at']
        body=json.dumps(public,ensure_ascii=False,indent=2)+'\n'
        expected=hashlib.sha256(body.encode()).hexdigest()
    else:body=None;expected=None
    txn={'relative':relative,'slug':slug,'before_head':git('rev-parse','HEAD'),'previous_owner':previous,'expected_hash':expected}
    atomic(JOURNAL,txn)
    committed=False
    try:
        if kind=='publish':
            atomic(owner_path(slug),{'job_id':jid,'source_hash':expected})
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(body,encoding='utf-8',newline='\n')
        elif target.exists():target.unlink()
        check_lease(jid)
        if target.exists() or git('ls-files','--',relative):git('add','-A','--',relative)
        changed=git('diff','--cached','--name-only')
        if changed:
            if changed!=relative:raise Rejected('publisher_unexpected_staged_path')
            git('-c','user.name=Fanqiang Guide','-c','user.email=fanqiang-guide@users.noreply.github.com','commit','-m',('更新脱敏咨询案例 ' if kind=='publish' else '撤回公开咨询案例 ')+slug)
        committed=True
        if kind=='publish':atomic(owner_path(slug),{'job_id':jid,'source_hash':expected,'commit':git('rev-parse','HEAD')})
        persist_source(jid)
    finally:
        reset_case(relative)
        if not committed:restore_owner(slug,previous)
        JOURNAL.unlink(missing_ok=True)
    check_lease(jid)
    build=STATE/'publish'/('build-'+jid)
    if build.exists():shutil.rmtree(build)
    run=subprocess.run([sys.executable,str(REPO/'developer/build_apps.py'),'--output',str(build)],capture_output=True,timeout=180)
    if run.returncode:raise Rejected('publisher_build_failed')
    ship_static(build/'site',jid)
    purge(['https://fanqiang.guide/','https://fanqiang.guide/index.html','https://fanqiang.guide/index.md','https://fanqiang.guide/cases/','https://fanqiang.guide/cases/index.html','https://fanqiang.guide/cases/index.md','https://fanqiang.guide/data/cases.json','https://fanqiang.guide/llms.txt','https://fanqiang.guide/llms-full.txt','https://fanqiang.guide/sitemap.xml','https://fanqiang.guide/.well-known/ai-catalog.json',url,url+'index.html',url+'index.md',url+'case.json',url+'conversation.md',url+'engineering.ilang'])
    # Case KB uses only the same public source, never this private job envelope.
    # A separate timer retries pending sync; it does not fail the public page.
    sync=BASE/'weknora_cases.py'
    if sync.exists():
        try:subprocess.run([sys.executable,str(sync),'--soft-fail'],capture_output=True,timeout=180)
        except subprocess.TimeoutExpired:pass
    return {'outcome':'published' if kind=='publish' else 'retracted','publicUrl':url,'slug':slug}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--kind',choices=['publish','retract'],required=True);parser.add_argument('--input',type=Path,required=True);parser.add_argument('--job-id',required=True);args=parser.parse_args()
    print(json.dumps(publish(args.kind,args.input,args.job_id)))

if __name__=='__main__':
    try:main()
    except Exception:print('publisher_failed',file=sys.stderr);raise SystemExit(1)
