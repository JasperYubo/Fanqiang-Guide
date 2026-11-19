"""Installed 1.3 network acceptance; provider boundaries use local contracts.

Production modules, DNS transaction code, real acme.sh, Nginx, Xray and installed
node probes execute unmodified. The two region observers and Telegram endpoint
are explicit local contracts, never evidence of live regional/Telegram delivery.
"""
import copy,hashlib,json,pathlib,re,socket,stat,subprocess,sys,threading,time,urllib.request
sys.path.insert(0,'/usr/local/lib/huarun')
import network
import network_setup
import egress
from exit_fixture import Proxy,USER,PASSWORD
import guest
ROOT=pathlib.Path('/opt/e2e-state')
PROBE_KEY='synthetic-release-probe-key-32-bytes-minimum'
CF_TOKEN='synthetic-cloudflare-token-fixture-only'
BOT='123456789:synthetic_release_telegram_token_only'

REAL_RUN_PROBE=egress.run_probe
TEST_DOMAINS={'qa.release.invalid','migrated.release.invalid','rollback.release.invalid'}
def fixture_node_probe(out,**kwargs):
    adapted=copy.deepcopy(out)
    servers=adapted.get('settings',{}).get('vnext',[])
    tls=adapted.get('streamSettings',{}).get('tlsSettings',{})
    if (adapted.get('protocol')=='vmess' and len(servers)==1 and servers[0].get('address')=='127.0.0.1'
            and servers[0].get('port')==443 and tls.get('serverName') in TEST_DOMAINS):
        if tls.get('allowInsecure',False) is not False:raise RuntimeError('fixture_insecure_tls_forbidden')
        # Xray defaults to bundled public roots; add only this isolated test CA.
        # Original run_probe still executes the actual binary and all TLS checks.
        tls['certificates']=[{'certificateFile':'/opt/e2e-state/ca.crt','usage':'verify'}]
    return REAL_RUN_PROBE(adapted,**kwargs)
egress.run_probe=fixture_node_probe

def stock_node_outbound():
    info=json.loads(pathlib.Path('/etc/huarun/info.json').read_bytes())
    return {'protocol':'vmess','settings':{'vnext':[{'address':'127.0.0.1','port':443,'users':[{'id':info['uuid'],'alterId':0,'security':'auto'}]}]},'streamSettings':{'network':'ws','security':'tls','tlsSettings':{'serverName':info['domain'],'allowInsecure':False},'wsSettings':{'path':info['wsPath'],'headers':{'Host':info['domain']}}}}

def trust_cases():
    source=stock_node_outbound();require(fixture_node_probe(source,node=True).get('ok') is True,'fixture_ca_positive_control_failed')
    try:REAL_RUN_PROBE(source,node=True)
    except egress.EgressError as error:unknown=str(error)=='exit_connectivity_failed'
    else:unknown=False
    wrong=copy.deepcopy(source);wrong['streamSettings']['tlsSettings'].update(serverName='wrong.release.invalid',certificates=[{'certificateFile':'/opt/e2e-state/ca.crt','usage':'verify'}])
    try:REAL_RUN_PROBE(wrong,node=True)
    except egress.EgressError as error:wrong_san=str(error)=='exit_connectivity_failed'
    else:wrong_san=False
    return {'fixture_unknown_ca_rejected':unknown,'fixture_wrong_san_rejected':wrong_san}

def require(condition,code):
    if condition is not True:raise RuntimeError(code)
def fixture(path,body=None):
    request=urllib.request.Request('http://127.0.0.1:14000/'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)
def file_state(path):
    path=pathlib.Path(path)
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mode':stat.S_IMODE(path.stat().st_mode)}
def identity():
    info=json.loads(pathlib.Path('/etc/huarun/info.json').read_bytes())
    return {'uuid':info['uuid'],'wsPath':info['wsPath'],'files':{name:file_state(path) for name,path in {'node_config':'/usr/local/etc/xray/config.json','whitelist':'/usr/local/etc/xray/whitelist.txt','key':'/etc/huarun/assistant/.security.yml'}.items()}}
def local_probe(url,payload,key):
    region='region-a' if 'region-a.' in url else 'region-b'
    request=urllib.request.Request('http://127.0.0.1:14000/probe/'+region,data=network.encoded(payload),headers={'Content-Type':'application/json','X-HuaRun-Signature':network.probe_signature(key,payload)})
    with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)
def node_fetch(url,seconds=12):
    info=json.loads(pathlib.Path('/etc/huarun/info.json').read_bytes())
    with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    config={'log':{'loglevel':'error'},'inbounds':[{'listen':'127.0.0.1','port':port,'protocol':'socks','settings':{'auth':'noauth','udp':False}}],'outbounds':[{'protocol':'vmess','settings':{'vnext':[{'address':'127.0.0.1','port':443,'users':[{'id':info['uuid'],'alterId':0,'security':'auto'}]}]},'streamSettings':{'network':'ws','security':'tls','tlsSettings':{'serverName':info['domain'],'allowInsecure':False,'certificates':[{'certificateFile':'/opt/e2e-state/ca.crt','usage':'verify'}]},'wsSettings':{'path':info['wsPath'],'headers':{'Host':info['domain']}}}}]}
    path=ROOT/'feature-client.json';egress.write(path,config)
    with (ROOT/'feature-client.log').open('wb') as log:
        child=subprocess.Popen(['/usr/local/bin/xray','run','-config',str(path)],stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(60):
                require(child.poll() is None,'node_client_exited')
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('node_client_timeout')
            return guest.cmd(['/usr/bin/curl','--fail','--silent','--show-error','--max-time',str(seconds),'--noproxy','','--proxy',f'socks5h://127.0.0.1:{port}',url],check=False,timeout=seconds+5)
        finally:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
            path.unlink(missing_ok=True)
def trace_ok(result):return result.returncode==0 and re.search(r'^ip=.+$',result.stdout,re.M) is not None

def domain_runner(args,**kwargs):
    result=subprocess.run(args,**kwargs)
    if result.returncode:
        diagnostic={'program':pathlib.Path(args[0]).name,'exit_code':result.returncode,'stderr_tail':result.stderr.decode('utf-8',errors='replace')[-1500:]}
        print(json.dumps({'domain_command_diagnostic':diagnostic}),file=sys.stderr,flush=True)
    return result

def observed_node_probe():
    try:return egress.probe_node()
    except egress.EgressError as error:
        observed=node_fetch('https://www.cloudflare.com/cdn-cgi/trace')
        log=(ROOT/'feature-client.log').read_text(errors='replace') if (ROOT/'feature-client.log').exists() else ''
        safe=[line for line in log.splitlines() if any(word in line.lower() for word in ('certificate','x509','tls','failed','error'))]
        print(json.dumps({'installed_probe_diagnostic':{'code':str(error),'control_exit':observed.returncode,'control_stderr':observed.stderr,'xray_errors':safe[-8:]}}),file=sys.stderr,flush=True)
        raise

def network_cases():
    result={}
    initial=fixture('fixture-state');domain='qa.release.invalid'
    events=initial['events']
    result['cloudflare_dns01']=any(x['kind']=='dns01_verified' and x['domain']==domain for x in events) and any(x['kind']=='certificate_issued' and x['domain']==domain for x in events)
    result['cloudflare_txt_created']=any(x['kind']=='dns_write' and x['type']=='TXT' and x['name']=='_acme-challenge.'+domain for x in events)
    result['dns01_leading_dash_value']=any(x['kind']=='dns_write' and x['type']=='TXT' and x['name']=='_acme-challenge.'+domain and x.get('content','').startswith('-') for x in events)
    result['cloudflare_txt_removed']=any(x['kind']=='dns_delete' and x['type']=='TXT' and x['name']=='_acme-challenge.'+domain for x in events) and not any(x['type']=='TXT' for x in initial['records'])
    timer=lambda action:guest.cmd(['systemctl',action,'--quiet','huarun-network.timer'],check=False).returncode==0
    require(timer('is-enabled') and timer('is-active'),'network_timer_not_running')
    guest.cmd(['systemctl','stop','huarun-network.timer'])
    guest.cmd(['systemctl','stop','huarun-network.service'],check=False)
    try:
        with network.MaintenanceLock() as lock:
            protected=identity()
            settings=network.load_private(pathlib.Path('/etc/huarun/network.json'))
            require(settings['domain']==domain,'fresh_network_domain_wrong')
            settings['address_source']={'mode':'static','addresses':{'A':'1.1.1.1'}}
            net=network.Network();net.lock_fd=lock.fd if lock.inherited else None
            net.configure(settings);status=net.run()
            live=fixture('fixture-state')
            a=[r for r in live['records'] if r['type']=='A' and r['name']==domain]
            result['ddns_address_changed']=len(a)==1 and a[0]['content']=='1.1.1.1'
            result['ddns_readback_verified']=result['ddns_address_changed'] and status['addresses'].get('A')==a[0]['content'] and net.state()['records']['A']['record_id']==a[0]['id']
            require(identity()==protected,'ddns_changed_node_identity')
            settings['notification']={'kind':'telegram','bot_token':BOT,'chat_id':'123456789'}
            settings['probes']=[{'region':r,'url':'https://'+r+'.release.invalid/probe','key':PROBE_KEY} for r in ('region-a','region-b')]
            clock=[time.time()]
            net=network.Network(clock=lambda:clock[0],probe_transport=local_probe);net.lock_fd=lock.fd if lock.inherited else None
            net.configure(settings)
            fixture('fixture-control',{'telegram_fail':True,'probe_reachable':False})
            for _ in range(network.HEALTH_FAILURES):net.run()
            pending=net.state()
            result['notification_retry_queued']=bool(pending.get('outbox')) and pending.get('last_notification',{}).get('status')=='retry_pending' and any(x.get('attempts',0)>0 and x.get('next_attempt',0)>clock[0] for x in pending['outbox'])
            fixture('fixture-control',{'telegram_fail':False,'probe_reachable':True})
            clock[0]+=1000
            recovered=net.run();after=net.state();events=fixture('fixture-state')['events']
            result['notification_recovered_delivered']=recovered['status']=='healthy' and after['outbox']==[] and after.get('last_notification',{}).get('status')=='delivered' and any(x['code']=='recovered' for x in after['events']) and any(x['kind']=='notification_delivered' and '已恢复' in x.get('text','') for x in events)
            require(identity()==protected,'notification_changed_node_identity')
            # Domain migration invokes actual ACME DNS-01, cert validation, reload and installed node probe.
            settings['notification']={'kind':'none'};settings['probes']=[];settings['domain']='migrated.release.invalid'
            migration=network_setup.Setup(runner=domain_runner,probe=observed_node_probe).apply(settings,lock)
            result['domain_migration_verified']=migration.get('status')=='verified' and json.loads(pathlib.Path('/etc/huarun/info.json').read_bytes())['domain']==settings['domain'] and egress.probe_node().get('ok') is True
            result['domain_identity_preserved']=identity()==protected
            before={name:file_state(path) for name,path in {'info':'/etc/huarun/info.json','nginx':'/etc/nginx/conf.d/huarun.conf','network':'/etc/huarun/network.json','state':'/var/lib/huarun-network/state.json'}.items()}
            fixture('fixture-control',{'fail_order_domain':'rollback.release.invalid'})
            failed_settings={**settings,'domain':'rollback.release.invalid'}
            try:network_setup.Setup(runner=domain_runner,probe=observed_node_probe).apply(failed_settings,lock)
            except network.NetworkError as error:failure=str(error)=='domain_setup_failed_local_configuration_restored'
            else:failure=False
            after={name:file_state(path) for name,path in {'info':'/etc/huarun/info.json','nginx':'/etc/nginx/conf.d/huarun.conf','network':'/etc/huarun/network.json','state':'/var/lib/huarun-network/state.json'}.items()}
            result['domain_migration_rollback']=failure and before==after and identity()==protected and not pathlib.Path('/var/lib/huarun-network/setup/transaction.json').exists() and egress.probe_node().get('ok') is True
            fixture('fixture-control',{'fail_order_domain':None})
    finally:
        pass
    return result

def chain_cases():
    manager=egress.Egress();results={};all_denied=True;all_closed=True
    for protocol in ('socks5','http-connect'):
        server=Proxy(protocol);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        name='e2e-'+protocol;stopped=False
        try:
            value={'protocol':protocol,'host':'127.0.0.1','port':server.server_address[1],'username':USER,'password':PASSWORD}
            require(manager.add(name,value).get('saved') is True,'chain_profile_not_saved')
            require(stat.S_IMODE(pathlib.Path('/etc/huarun/egress.json').stat().st_mode)==0o600,'egress_secret_mode_invalid')
            before=identity();installed=manager.use(name)
            require(installed.get('status')=='verified' and installed.get('fallback_to_direct') is False,'chain_switch_not_verified')
            require(identity()['uuid']==before['uuid'] and identity()['wsPath']==before['wsPath'],'chain_changed_node_identity')
            require(identity()['files']['key']==before['files']['key'] and identity()['files']['whitelist']==before['files']['whitelist'],'chain_changed_owner_policy')
            tunnels=len(server.tunnels);allowed=node_fetch('https://www.cloudflare.com/cdn-cgi/trace')
            results['socks5_chain_verified' if protocol=='socks5' else 'http_connect_chain_verified']=trace_ok(allowed) and len(server.tunnels)>tunnels and manager.status()['active']==name
            access=pathlib.Path('/var/log/xray/access.log');offset=access.stat().st_size;tunnels=len(server.tunnels)
            blocked=node_fetch('https://example.com/',seconds=6)
            lines=access.read_bytes()[offset:].decode('utf-8',errors='replace')
            all_denied=all_denied and blocked.returncode!=0 and len(server.tunnels)==tunnels and any('tcp:example.com:443' in line and '[vmess-ws -> blocked]' in line for line in lines.splitlines())
            manager.add(name+'-wrong',{**value,'password':'wrong-synthetic-exit-password'})
            old_config=file_state('/usr/local/etc/xray/config.json');tunnels=len(server.tunnels)
            try:manager.use(name+'-wrong')
            except egress.EgressError as error:wrong_rejected=str(error)=='exit_connectivity_failed'
            else:wrong_rejected=False
            unchanged=old_config==file_state('/usr/local/etc/xray/config.json') and manager.status()['active']==name and len(server.tunnels)==tunnels and server.denied>0
            server.shutdown();server.server_close();stopped=True
            offset=access.stat().st_size
            failed=node_fetch('https://www.cloudflare.com/cdn-cgi/trace',seconds=6)
            lines=access.read_bytes()[offset:].decode('utf-8',errors='replace')
            direct=guest.cmd(['/usr/bin/curl','--fail','--silent','--show-error','--max-time','15','--noproxy','*','https://www.cloudflare.com/cdn-cgi/trace'],check=False,timeout=20)
            all_closed=all_closed and wrong_rejected and unchanged and failed.returncode!=0 and trace_ok(direct) and manager.status()['chain_enabled'] is True and manager.status()['fallback_to_direct'] is False and any('www.cloudflare.com:443' in line and '[vmess-ws -> huarun-egress]' in line for line in lines.splitlines())
            require(manager.use('direct').get('status')=='verified','explicit_direct_restore_failed')
        finally:
            if not stopped:server.shutdown();server.server_close()
            if manager.status().get('chain_enabled'):manager.use('direct')
    results['chain_whitelist_enforced']=all_denied;results['chain_failure_closed']=all_closed
    return results

def main():
    try:
        result=trust_cases();result.update(network_cases());result.update(chain_cases())
    finally:guest.cmd(['systemctl','start','huarun-network.timer'])
    result['network_timer_enabled']=guest.cmd(['systemctl','is-enabled','--quiet','huarun-network.timer'],check=False).returncode==0
    result['network_timer_active']=guest.cmd(['systemctl','is-active','--quiet','huarun-network.timer'],check=False).returncode==0
    result['passed']=all(value is True for value in result.values())
    result['scope']='installed-runtime-real-tls-and-xray; local Cloudflare/ACME/Telegram/two-region contracts; no live provider or Telegram claim'
    print(json.dumps(result,sort_keys=True))
    require(result['passed'],'network_features_not_all_passed')
if __name__=='__main__':main()
