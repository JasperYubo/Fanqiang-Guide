"""Managed TCP exit profiles. Explicit changes preserve inbound nodes and policy.

Credentials remain in root-only local files. The model can select an existing
profile; it cannot read its secret or silently fall back to a direct exit.
"""
from __future__ import annotations
import argparse,contextlib,copy,getpass,grp,hashlib,ipaddress,json,os,pathlib,pwd,re,socket,stat,subprocess,sys,tempfile,time
BASE=pathlib.Path('/etc/huarun/egress.json')
STATE=pathlib.Path('/var/lib/huarun-egress')
XRAY=pathlib.Path('/usr/local/etc/xray/config.json')
INFO=pathlib.Path('/etc/huarun/info.json')
TAG='huarun-egress'
class EgressError(Exception):pass

def load(path,default=None):
    if path.is_symlink():raise EgressError('symlink_refused')
    if not path.exists():return copy.deepcopy(default)
    if not path.is_file() or path.stat().st_size>1024*1024:raise EgressError('invalid_local_file')
    return json.loads(path.read_text())
def write(path,value,mode=0o600,*,uid=None,gid=None):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():raise EgressError('symlink_refused')
    raw=value if isinstance(value,bytes) else (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as out:
            if uid is not None or gid is not None:
                current=os.fstat(out.fileno())
                if current.st_uid!=uid or current.st_gid!=gid:os.fchown(out.fileno(),uid,gid)
            os.fchmod(out.fileno(),mode)
            out.write(raw);out.flush();os.fsync(out.fileno())
        os.replace(name,path)
        parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(parent)
        finally:os.close(parent)
    finally:
        if os.path.exists(name):os.unlink(name)
def command(args,timeout=30):
    return subprocess.run(args,capture_output=True,timeout=timeout,check=False)
def xray_config_identity(runner=command):
    """Read the configured systemd identity; never grant world-readable secrets."""
    def property_value(name):
        try:
            result=runner(['systemctl','show','xray.service','--property='+name,'--value'])
            if result.returncode:raise EgressError('xray_service_identity_unavailable')
            value=result.stdout.decode('utf-8') if isinstance(result.stdout,bytes) else result.stdout
            if not isinstance(value,str) or len(value)>256:raise EgressError('xray_service_identity_invalid')
            return value.strip()
        except (OSError,UnicodeError,subprocess.SubprocessError):
            raise EgressError('xray_service_identity_unavailable') from None
    user,group,dynamic=property_value('User'),property_value('Group'),property_value('DynamicUser')
    if dynamic not in ('','no'):raise EgressError('xray_dynamic_identity_unsupported')
    try:
        account=pwd.getpwuid(int(user)) if user.isdigit() else pwd.getpwnam(user or 'root')
        group_id=(int(group) if group.isdigit() else grp.getgrnam(group).gr_gid) if group else account.pw_gid
    except (KeyError,ValueError,OverflowError):
        raise EgressError('xray_service_identity_invalid') from None
    if type(group_id) is not int or not 0<=group_id<2**32-1:raise EgressError('xray_service_identity_invalid')
    # Root owns the installed configuration; only the service group may read it.
    return (0,group_id,0o600 if account.pw_uid==0 else 0o640)


def install_xray_config(path,raw,*,uid,gid,mode):
    """Atomically install checked config bytes with explicit owner/group/mode.

    Ordinary writes use xray_config_identity(); rollback supplies the metadata
    recorded before its transaction. Secret store files still use write(...).
    """
    if (type(uid) is not int or type(gid) is not int or not 0<=uid<2**32-1 or not 0<=gid<2**32-1
            or type(mode) is not int or not 0<=mode<=0o777):
        raise EgressError('xray_configuration_metadata_invalid')
    write(pathlib.Path(path),raw,mode,uid=uid,gid=gid)


def operation_lock():
    sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
    from network import MaintenanceLock as lock
    return lock()
def profile(value):
    if not isinstance(value,dict) or value.get('protocol') not in ('socks5','http-connect'):raise EgressError('unsupported_exit_protocol')
    host=value.get('host','');port=value.get('port')
    if not isinstance(host,str) or not host or len(host)>253 or any(c in host for c in '/@?#\\ \t\n\r'):raise EgressError('invalid_exit_host')
    try:ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',host):raise EgressError('invalid_exit_host')
    if type(port) is not int or not 1<=port<=65535:raise EgressError('invalid_exit_port')
    for key in ('username','password'):
        if not isinstance(value.get(key,''),str) or len(value.get(key,''))>512 or any(ord(c)<32 for c in value.get(key,'')):raise EgressError('invalid_exit_credentials')
    if bool(value.get('username'))!=bool(value.get('password')):raise EgressError('incomplete_exit_credentials')
    if type(value.get('tls',False)) is not bool:raise EgressError('invalid_exit_tls')
    if value.get('tls') and value['protocol']!='http-connect':raise EgressError('tls_requires_http_connect')
    return {k:value[k] for k in ('protocol','host','port','username','password','tls') if k in value}
def outbound(value):
    p=profile(value);server={'address':p['host'],'port':p['port']}
    if p.get('username'):server.update(user=p['username'],**{'pass':p['password']})
    result={'tag':TAG,'protocol':'socks' if p['protocol']=='socks5' else 'http','settings':server}
    if p.get('tls'):result['streamSettings']={'network':'tcp','security':'tls','tlsSettings':{'serverName':p['host'],'allowInsecure':False}}
    return result
def patch_configuration(original,selected):
    cfg=copy.deepcopy(original)
    if not isinstance(cfg,dict) or not isinstance(cfg.get('outbounds'),list) or not isinstance(cfg.get('routing',{}).get('rules'),list):raise EgressError('unsupported_xray_configuration')
    if not any(x.get('tag')=='direct' and x.get('protocol')=='freedom' for x in cfg['outbounds']):raise EgressError('direct_outbound_missing')
    if not any(x.get('tag')=='blocked' and x.get('protocol')=='blackhole' for x in cfg['outbounds']):raise EgressError('whitelist_block_outbound_missing')
    rules=cfg['routing']['rules']
    if not rules or rules[-1].get('outboundTag')!='blocked' or rules[-1].get('port')!='0-65535':raise EgressError('whitelist_default_deny_missing')
    managed=[r for r in rules if r.get('type')=='field' and isinstance(r.get('domain'),list) and r['domain'] and r.get('outboundTag') in ('direct',TAG)]
    if not managed:raise EgressError('whitelist_rule_missing')
    cfg['outbounds']=[o for o in cfg['outbounds'] if o.get('tag')!=TAG]
    if selected is not None:cfg['outbounds'].append(outbound(selected))
    for rule in managed:rule['outboundTag']=TAG if selected is not None else 'direct'
    # No new routing rule, fallback, or inbound mutation is introduced.
    if cfg['inbounds']!=original['inbounds']:raise EgressError('inbound_changed')
    return cfg

def check_xray(path):
    if command(['/usr/local/bin/xray','run','-test','-config',str(path)]).returncode:raise EgressError('xray_configuration_invalid')
def run_probe(out,*,node=False):
    with tempfile.TemporaryDirectory(prefix='huarun-egress-probe-') as tmp:
        root=pathlib.Path(tmp);root.chmod(0o700)
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        cfg={'log':{'loglevel':'error'},'inbounds':[{'listen':'127.0.0.1','port':port,'protocol':'socks','settings':{'auth':'noauth','udp':False}}],'outbounds':[out]}
        path=root/'client.json';write(path,cfg);check_xray(path)
        with (root/'private.log').open('wb') as log:
            child=subprocess.Popen(['/usr/local/bin/xray','run','-config',str(path)],stdout=log,stderr=subprocess.STDOUT)
            try:
                for _ in range(50):
                    if child.poll() is not None:raise EgressError('exit_probe_client_failed')
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                    except OSError:time.sleep(.1)
                else:raise EgressError('exit_probe_timeout')
                url='https://www.cloudflare.com/cdn-cgi/trace'
                result=command(['curl','--fail','--silent','--show-error','--max-time','15','--max-filesize','4096','--noproxy','','--proxy',f'socks5h://127.0.0.1:{port}',url],timeout=20)
                if result.returncode:raise EgressError('exit_connectivity_failed')
                found=re.search(rb'^ip=([^\r\n]+)',result.stdout,re.M)
                if not found:raise EgressError('exit_ip_unavailable')
                try:addr=ipaddress.ip_address(found[1].decode())
                except ValueError:raise EgressError('exit_ip_invalid') from None
                if not addr.is_global:raise EgressError('exit_ip_not_public')
                return {'ok':True,'exit_ip':str(addr),'transport':'tcp','residential_status':'not_verified','path':'installed_node' if node else 'upstream_profile'}
            finally:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()
def probe_node(info=INFO):
    d=load(info)
    if not isinstance(d,dict) or any(not d.get(k) for k in ('uuid','domain','wsPath')):raise EgressError('node_information_missing')
    out={'protocol':'vmess','settings':{'vnext':[{'address':'127.0.0.1','port':443,'users':[{'id':d['uuid'],'alterId':0,'security':'auto'}]}]},'streamSettings':{'network':'ws','security':'tls','tlsSettings':{'serverName':d['domain'],'allowInsecure':False},'wsSettings':{'path':d['wsPath'],'headers':{'Host':d['domain']}}}}
    return run_probe(out,node=True)

class Egress:
    def __init__(self,config=BASE,state=STATE,xray=XRAY,runner=command,probe=run_probe,node_probe=probe_node,lock=operation_lock,check=check_xray,identity_fn=xray_config_identity):
        self.config,self.state,self.xray=config,state,xray;self.runner,self.probe,self.node_probe,self.lock,self.check=runner,probe,node_probe,lock,check
        self.journal=state/'transaction.json';self.status_path=state/'state.json';self.backup=state/'config.backup'
        self.identity_fn=identity_fn
    def status(self):
        config=load(self.config,{'profiles':{}});cfg=load(self.xray,{});state=load(self.status_path,{})
        chain=any(r.get('outboundTag')==TAG for r in cfg.get('routing',{}).get('rules',[]))
        return {'configured':bool(config.get('profiles')),'profiles':[{ 'name':name,'protocol':p['protocol']} for name,p in config.get('profiles',{}).items()], 'active':state.get('active','unknown') if chain else 'direct','chain_enabled':chain,'fallback_to_direct':False,'pending_recovery':self.journal.exists(),'last_verified_exit_ip':state.get('exit_ip'),'transport':'tcp','residential_status':'not_verified'}
    def add(self,name,value):
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,31}',name):raise EgressError('invalid_profile_name')
        with self.lock():
            if self.journal.exists():raise EgressError('recovery_pending')
            c=load(self.config,{'schema_version':1,'profiles':{}})
            if c.get('schema_version')!=1 or not isinstance(c.get('profiles'),dict):raise EgressError('invalid_egress_configuration')
            c['profiles'][name]=profile(value);write(self.config,c)
        return {'saved':True,'profile':name}
    def recover_locked(self):
        journal=load(self.journal)
        if journal is None:return {'status':'no_recovery_needed'}
        if journal.get('schema_version')!=1 or not self.backup.is_file() or self.backup.is_symlink():raise EgressError('recovery_backup_missing')
        raw=self.backup.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=journal.get('before_sha256'):raise EgressError('recovery_backup_mismatch')
        if 'uid' in journal and 'gid' in journal:
            uid,gid,mode=journal['uid'],journal['gid'],journal['mode']
        else:
            # Pre-release journals did not record ownership. Recover readable,
            # private service permissions instead of repeating root-only failure.
            uid,gid,mode=self.identity_fn()
        install_xray_config(self.xray,raw,uid=uid,gid=gid,mode=mode);self.check(self.xray)
        if self.runner(['systemctl','restart','xray']).returncode or self.runner(['systemctl','is-active','--quiet','xray']).returncode:raise EgressError('recovery_service_failed')
        write(self.status_path,journal['previous_status']);self.journal.unlink();self.backup.unlink()
        return {'status':'rolled_back'}
    def recover(self):
        with self.lock():return self.recover_locked()
    def use(self,name):
        with self.lock():
            if self.journal.exists():self.recover_locked()
            c=load(self.config,{'profiles':{}})
            selected=None if name=='direct' else c.get('profiles',{}).get(name)
            if name!='direct' and selected is None:raise EgressError('profile_not_found')
            if selected is not None:self.probe(outbound(selected))
            if self.xray.is_symlink():raise EgressError('symlink_refused')
            raw=self.xray.read_bytes();candidate=patch_configuration(json.loads(raw),selected)
            metadata=self.xray.stat();mode=stat.S_IMODE(metadata.st_mode)
            applied_uid,applied_gid,applied_mode=self.identity_fn()
            self.state.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.state,0o700)
            with tempfile.TemporaryDirectory(prefix='candidate-',dir=self.state) as folder:
                path=pathlib.Path(folder)/'config.json';write(path,candidate);self.check(path)
                before=load(self.status_path,{})
                write(self.backup,raw)
                write(self.journal,{'schema_version':1,'before_sha256':hashlib.sha256(raw).hexdigest(),'mode':mode,
                                    'uid':metadata.st_uid,'gid':metadata.st_gid,'previous_status':before})
                try:
                    install_xray_config(self.xray,path.read_bytes(),uid=applied_uid,gid=applied_gid,mode=applied_mode)
                    if self.runner(['systemctl','restart','xray']).returncode or self.runner(['systemctl','is-active','--quiet','xray']).returncode:raise EgressError('xray_restart_failed')
                    observed=self.node_probe()
                    if observed.get('ok') is not True:raise EgressError('installed_node_probe_failed')
                    state={'active':name,'exit_ip':observed['exit_ip'],'verified_at':int(time.time())}
                    write(self.status_path,state)
                    self.journal.unlink();self.backup.unlink()
                    return {'status':'verified','active':name,**observed,'fallback_to_direct':False}
                except Exception:
                    self.recover_locked()
                    raise EgressError('exit_change_failed_rolled_back') from None
    def probe_current(self):
        with self.lock():
            if self.journal.exists():raise EgressError('recovery_pending')
            return {**self.node_probe(),'active':self.status()['active']}

def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    for name in ('status','probe','recover','direct'):s.add_parser(name)
    use=s.add_parser('use');use.add_argument('profile')
    setup=s.add_parser('setup');setup.add_argument('profile');setup.add_argument('--stdin',action='store_true')
    args=p.parse_args()
    if os.geteuid()!=0:raise EgressError('root_required')
    manager=Egress()
    if args.action=='status':result=manager.status()
    elif args.action=='probe':result=manager.probe_current()
    elif args.action=='recover':result=manager.recover()
    elif args.action in ('use','direct'):result=manager.use(args.profile if args.action=='use' else 'direct')
    elif args.stdin:
        raw=sys.stdin.read(8193)
        if len(raw)>8192:raise EgressError('profile_input_too_large')
        result=manager.add(args.profile,json.loads(raw))
    else:
        if not sys.stdin.isatty():raise EgressError('terminal_required')
        value={'protocol':input('出口类型 socks5 / http-connect: ').strip(),'host':input('出口主机: ').strip(),'port':int(input('端口: ').strip()),'username':input('用户名（可空）: ').strip(),'password':getpass.getpass('密码（隐藏，可空）: ')}
        if value['protocol']=='http-connect':value['tls']=input('连接 HTTP 代理时使用 TLS？[y/N]: ').strip().lower()=='y'
        result=manager.add(args.profile,value)
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except (EgressError,OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print(json.dumps({'error':str(error) if isinstance(error,EgressError) else type(error).__name__}),file=sys.stderr);sys.exit(1)
