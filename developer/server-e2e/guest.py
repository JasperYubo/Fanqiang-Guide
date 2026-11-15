"""Real installed-service probes; output contains hashes and booleans only."""
import hashlib,json,pathlib,socket,stat,subprocess,sys,time,uuid
FILES={'node_config':'/usr/local/etc/xray/config.json','whitelist':'/usr/local/etc/xray/whitelist.txt','key':'/etc/huarun/assistant/.security.yml','memory':'/etc/huarun/assistant/workspace/memory/release-preservation.txt','nginx_config':'/etc/nginx/conf.d/huarun.conf','connection_info':'/etc/huarun/info.json'}
def cmd(args,check=True,timeout=30):return subprocess.run(args,capture_output=True,text=True,check=check,timeout=timeout)
def snapshot():
    return {k:{'sha256':hashlib.sha256(pathlib.Path(v).read_bytes()).hexdigest(),'mode':stat.S_IMODE(pathlib.Path(v).stat().st_mode)} for k,v in FILES.items()}
def processes():
    return {name:cmd(['systemctl','show',name,'-p','MainPID','-p','ExecMainStartTimestampMonotonic']).stdout for name in ['xray','nginx']}
def customize():
    cmd(['/usr/local/bin/huarun','whitelist','add','preserve.example'])
    p=pathlib.Path(FILES['node_config']);data=json.loads(p.read_text());data['inbounds'][0]['settings']['clients'].append({'id':str(uuid.uuid4()),'email':'owner-preserved@example.invalid'});p.write_text(json.dumps(data,indent=2)+'\n')
    # This restart happens before the preservation baseline; the upgrade must not restart it.
    cmd(['systemctl','restart','xray'])
    p=pathlib.Path(FILES['key']);p.write_text(p.read_text()+'\n# owner custom comment retained verbatim\n');p.chmod(0o640)
    p=pathlib.Path(FILES['memory']);p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Owner memory: preserve this exact text.\n');p.chmod(0o640)
    return {'snapshot':snapshot(),'processes':processes()}
def probe():
    info=json.loads(pathlib.Path(FILES['connection_info']).read_text())
    config={'log':{'loglevel':'error'},'inbounds':[{'listen':'127.0.0.1','port':10880,'protocol':'socks','settings':{'auth':'noauth','udp':False}}],'outbounds':[{'protocol':'vmess','settings':{'vnext':[{'address':'127.0.0.1','port':443,'users':[{'id':info['uuid'],'alterId':0,'security':'auto'}]}]},'streamSettings':{'network':'ws','security':'tls','tlsSettings':{'serverName':info['domain'],'certificates':[{'certificateFile':'/opt/e2e-state/ca.crt','usage':'verify'}]},'wsSettings':{'path':info['wsPath'],'headers':{'Host':info['domain']}}}}]}
    client_path=pathlib.Path('/opt/e2e-state/client.json');client_path.write_text(json.dumps(config));client_path.chmod(0o600)
    client=subprocess.Popen(['/usr/local/bin/xray','run','-c',str(client_path)],stdout=open('/opt/e2e-state/client.log','wb'),stderr=subprocess.STDOUT)
    try:
        for attempt in range(60):
            if client.poll() is not None:raise RuntimeError('proxy_client_exited')
            try:
                with socket.create_connection(('127.0.0.1',10880),timeout=.2):break
            except OSError:time.sleep(.1)
        def fetch(url):
            return cmd(['/usr/bin/curl','--silent','--show-error','--max-time','15','--noproxy','','--proxy','socks5h://127.0.0.1:10880','-o','/dev/null','-w','%{http_code}',url],check=False,timeout=20)
        access_log=pathlib.Path('/var/log/xray/access.log')
        access_offset=access_log.stat().st_size
        direct=cmd(['/usr/bin/curl','--fail','--silent','--show-error','--max-time','15','--noproxy','*','-o','/dev/null','-w','%{http_code}','https://example.com/'],check=False,timeout=20)
        allowed=fetch('https://www.google.com/generate_204');blocked=fetch('https://example.com/')
        route_blocked=False
        for _ in range(20):
            new_access=access_log.read_bytes()[access_offset:].decode('utf-8',errors='replace')
            route_blocked=any('tcp:example.com:443' in line and '[vmess-ws -> blocked]' in line for line in new_access.splitlines())
            if route_blocked:break
            time.sleep(.1)
        direct_reachable=direct.returncode==0 and direct.stdout=='200' 
        health=json.loads(cmd(['/usr/local/bin/huarun','doctor','--json']).stdout)
        services=all(cmd(['systemctl','is-active','--quiet',name],check=False).returncode==0 for name in ['xray','nginx'])
        mandatory_checks=('xray','nginx','port443','xray_config','nginx_config','cert','cron','firewall','dns','disk')
        checks=health.get('checks',{})
        healthy_checks=isinstance(checks,dict) and all(isinstance(checks.get(k),dict) and checks[k].get('ok') is True for k in mandatory_checks)
        timer=cmd(['systemctl','is-enabled','--quiet','huarun-auto-update.timer'],check=False).returncode==0
        active=cmd(['systemctl','is-active','--quiet','huarun-auto-update.timer'],check=False).returncode==0
        # Genuine TLS verification, issued from the real CSR by the isolated CA.
        tls=cmd(['/usr/bin/curl','--silent','--show-error','--max-time','8','--noproxy','*','--cacert','/opt/e2e-state/ca.crt','-o','/dev/null','https://'+info['domain']],check=False)
        return {'version':cmd(['/usr/local/bin/huarun','version']).stdout.strip(),'services_healthy':services and healthy_checks,'doctor_checks':{k:v.get('ok') for k,v in health.get('checks',{}).items()},'timer_enabled':timer,'timer_active':active,'proxy_diagnostic':{'returncode':allowed.returncode,'error':allowed.stderr,'bytes':len(allowed.stdout)},'proxy_allowed':allowed.returncode==0 and allowed.stdout=='204','blocked_target_reachable':direct_reachable,'proxy_block_route_verified':route_blocked,'proxy_blocked':direct_reachable and route_blocked and blocked.returncode!=0 and blocked.stdout=='000','tls_verified':tls.returncode==0,'processes':processes()}
    finally:
        client.terminate()
        try:client.wait(timeout=5)
        except subprocess.TimeoutExpired:client.kill();client.wait()
        client_path.unlink(missing_ok=True)
if sys.argv[1]=='customize':result=customize()
elif sys.argv[1]=='snapshot':result={'snapshot':snapshot(),'processes':processes()}
elif sys.argv[1]=='probe':result=probe()
else:raise SystemExit(2)
print(json.dumps(result,sort_keys=True))
