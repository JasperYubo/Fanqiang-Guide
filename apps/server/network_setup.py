"""Explicit fixed-domain migration; ordinary upgrades never invoke this module."""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,re,stat,subprocess,sys,time
from network import Network,MaintenanceLock,NetworkError,interactive_config,hostname,load_private,private_file,MAX_BYTES
from egress import write,probe_node
INFO=pathlib.Path('/etc/huarun/info.json')
NGINX=pathlib.Path('/etc/nginx/conf.d/huarun.conf')
CONFIG=pathlib.Path('/etc/huarun/network.json')
STATE=pathlib.Path('/var/lib/huarun-network/setup')
ACME='/usr/local/lib/huarun/acme.sh'
ACME_HOME='/etc/huarun/acme'

def nginx_domain(raw,old,new,cert):
    text=raw.decode(); old=hostname(old);new=hostname(new)
    text,count=re.subn(r'(?m)^(\s*server_name\s+)'+re.escape(old)+r';',lambda m:m[1]+new+';',text)
    if count!=2:raise NetworkError('nginx_domain_layout_unsupported')
    text,c1=re.subn(r'(?m)^(\s*ssl_certificate\s+)[^;]+;',lambda m:m[1]+str(cert/'fullchain.cer')+';',text)
    text,c2=re.subn(r'(?m)^(\s*ssl_certificate_key\s+)[^;]+;',lambda m:m[1]+str(cert/(new+'.key'))+';',text)
    if (c1,c2)!=(1,1):raise NetworkError('nginx_certificate_layout_unsupported')
    return text.encode()

class Setup:
    def __init__(self,info=INFO,nginx=NGINX,config=CONFIG,state=STATE,runner=subprocess.run,probe=probe_node,cert_root=pathlib.Path('/etc/nginx/ssl/huarun'),network_state=pathlib.Path('/var/lib/huarun-network')):
        self.info,self.nginx,self.config,self.state=info,nginx,config,state
        self.cert_root,self.network_state=cert_root,network_state
        self.provider_state=network_state/'provider'
        self.runner,self.probe=runner,probe;self.journal=state/'transaction.json'
    def invoke(self,args,lock,timeout=60,acceptable=(0,)):
        env=os.environ.copy();env['HUARUN_NETWORK_LOCK_FD']=str(lock.network_fd)
        if lock.inherited:env['HUARUN_UPDATE_LOCK_FD']=str(lock.fd)
        else:env.pop('HUARUN_UPDATE_LOCK_FD',None)
        result=self.runner(args,capture_output=True,env=env,pass_fds=(lock.fd,lock.network_fd),timeout=timeout)
        if result.returncode not in acceptable:raise NetworkError('domain_setup_command_failed')
        return result
    def snapshot(self):
        if self.provider_state.is_symlink():raise NetworkError("provider_state_symlink")
        if self.provider_state.exists() and any(self.provider_state.rglob('transaction.json')):
            raise NetworkError("provider_recovery_pending")
        if self.journal.exists():raise NetworkError('domain_recovery_pending')
        self.state.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(self.state,0o700)
        entries=[]
        for i,path in enumerate((self.info,self.nginx,self.config,self.network_state/'state.json')):
            if path.is_symlink():raise NetworkError('symlink_refused')
            entry={'slot':i,'exists':path.exists()}
            if path.exists():
                entry['mode']=stat.S_IMODE(path.stat().st_mode)
                raw=path.read_bytes();entry['sha256']=hashlib.sha256(raw).hexdigest()
                write(self.state/f'backup-{i}',raw)
            entries.append(entry)
        write(self.journal,{'schema_version':1,'entries':entries,'started_at':int(time.time())})
    def recover(self,lock):
        if not self.journal.exists():return {'status':'no_recovery_needed'}
        j=load_private(self.journal)
        if j.get('schema_version')!=1 or [e.get('slot') for e in j.get('entries',[])]!=[0,1,2,3]:raise NetworkError('domain_recovery_invalid')
        restored={}
        for entry in j['entries']:
            if type(entry.get('exists')) is not bool:raise NetworkError('domain_recovery_invalid')
            if entry['exists']:
                backup=self.state/f"backup-{entry['slot']}"
                if private_file(backup,limit=MAX_BYTES) is None:raise NetworkError('domain_recovery_backup_missing')
                raw=backup.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=entry.get('sha256'):raise NetworkError('domain_recovery_backup_mismatch')
                if type(entry.get('mode')) is not int or not 0<=entry['mode']<=0o777:raise NetworkError('domain_recovery_invalid')
                restored[entry['slot']]=raw
        for e,path in zip(j['entries'],(self.info,self.nginx,self.config,self.network_state/'state.json')):
            if path.is_symlink():raise NetworkError('symlink_refused')
            if e['exists']:write(path,restored[e['slot']],e['mode'])
            elif path.exists():path.unlink()
        self.invoke(['nginx','-t'],lock)
        self.invoke(['systemctl','reload','nginx'],lock)
        if self.probe().get('ok') is not True:raise NetworkError('restored_node_probe_failed')
        self.clear()
        return {'status':'rolled_back','dns_records':'retained_for_owner_review'}
    def clear(self):
        self.journal.unlink()
        for i in range(4):
            p=self.state/f'backup-{i}'
            if p.exists():p.unlink()
    def certificate_valid(self,cert,domain,lock):
        paths=(cert/'fullchain.cer',cert/(domain+'.key'))
        if any(not p.is_file() or p.is_symlink() for p in paths):return False
        try:
            self.invoke(['openssl','x509','-in',str(paths[0]),'-noout','-checkhost',domain,'-checkend','0'],lock)
        except NetworkError:return False
        return True
    def apply(self,value,lock):
        if self.journal.exists():self.recover(lock)
        old=json.loads(self.info.read_bytes());new=hostname(value['domain'])
        same=new==hostname(old['domain'])
        old_cert=pathlib.Path(old.get('certDir') or self.cert_root)
        reuse_current=same and self.certificate_valid(old_cert,new,lock)
        cert=old_cert if reuse_current else self.cert_root/new
        candidate=None if reuse_current else nginx_domain(self.nginx.read_bytes(),old['domain'],new,cert)
        self.snapshot()
        try:
            network=Network(config_path=self.config,state_dir=self.network_state)
            network.configure(value,allow_domain_change=True,info_path=str(self.info))
            network.prepare(new)
            if not reuse_current:
                cert.mkdir(parents=True,exist_ok=True,mode=0o700)
                if not self.certificate_valid(cert,new,lock):
                    # acme.sh returns 2 when a cached certificate is not due.
                    # Install that cached certificate and verify it below.
                    self.invoke([ACME,'--home',ACME_HOME,'--issue','-d',new,'--keylength','ec-256','--dns','dns_huarun','--server','letsencrypt'],lock,timeout=900,acceptable=(0,2))
                    self.invoke([ACME,'--home',ACME_HOME,'--install-cert','-d',new,'--ecc','--key-file',str(cert/(new+'.key')),'--fullchain-file',str(cert/'fullchain.cer'),'--reloadcmd','systemctl is-active --quiet nginx && systemctl reload nginx || true'],lock)
                if not self.certificate_valid(cert,new,lock):
                    raise NetworkError('domain_certificate_invalid')
                write(self.nginx,candidate,0o644)
                self.invoke(['nginx','-t'],lock)
                updated={**old,'domain':new,'certDir':str(cert)}
                write(self.info,updated,stat.S_IMODE(self.info.stat().st_mode))
                self.invoke(['systemctl','reload','nginx'],lock)
            observed=self.probe()
            if observed.get('ok') is not True:raise NetworkError('domain_node_probe_failed')
            self.clear()
            return {'status':'verified','domain':new,'node_identity_preserved':True,'whitelist_preserved':True,'key_preserved':True,'probe':observed}
        except Exception:
            try:self.recover(lock)
            except Exception:raise NetworkError('domain_setup_failed_recovery_pending') from None
            raise NetworkError('domain_setup_failed_local_configuration_restored') from None

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['setup','recover']);p.add_argument('--stdin',action='store_true');p.add_argument('--domain');a=p.parse_args()
    if os.geteuid()!=0:raise NetworkError('root_required')
    with MaintenanceLock() as lock:
        setup=Setup()
        if a.command=='recover':result=setup.recover(lock)
        else:
            if a.stdin:
                raw=sys.stdin.buffer.read(65537)
                if len(raw)>65536:raise NetworkError('configuration_too_large')
                value=json.loads(raw)
            else:value=interactive_config(a.domain)
            result=setup.apply(value,lock)
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except (NetworkError,OSError,ValueError,KeyError,subprocess.SubprocessError) as error:
        print(json.dumps({'error':str(error) if isinstance(error,NetworkError) else type(error).__name__}),file=sys.stderr);sys.exit(1)
