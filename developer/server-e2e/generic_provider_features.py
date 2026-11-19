"""Installed 1.4 generic discovery/rotation acceptance against real local HTTP.

The model, provider docs/APIs, observers and Telegram are explicit HTTP fixtures.
Production discovery, profile validation, transactions, network orchestration and
Cloudflare write/readback code execute from the installed distribution. This is
not evidence of a live cloud allocation or of paid model inference.
"""
import argparse,copy,hashlib,json,pathlib,stat,subprocess,sys,time,urllib.request
sys.path.insert(0,'/usr/local/lib/huarun')
import network,provider_discovery,generic_provider,ip_provider
from generic_provider_fixture import VendorFixture,ResearchFixture
import guest
ROOT=pathlib.Path('/opt/e2e-state/generic-providers')
PROBE_KEY='synthetic-release-probe-key-32-bytes-minimum'
BOT='123456789:synthetic_release_telegram_token_only'

def require(value,code):
    if value is not True:raise RuntimeError(code)
def fixture(path,body=None):
    req=urllib.request.Request('http://127.0.0.1:14000/'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as response:return json.load(response)
def local_probe(url,payload,key):
    region='region-a' if 'region-a.' in url else 'region-b'
    request=urllib.request.Request('http://127.0.0.1:14000/probe/'+region,data=network.encoded(payload),headers={'Content-Type':'application/json','X-HuaRun-Signature':network.probe_signature(key,payload)})
    with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)
def control(reachable=False,candidate=True):fixture('fixture-control',{'probe_reachable':reachable,'probe_candidate_reachable':candidate,'telegram_fail':False})
def cloud_address(domain):
    rows=[r for r in fixture('fixture-state')['records'] if r['name']==domain and r['type']=='A']
    require(len(rows)==1,'generic_dns_record_not_unique');return rows[0]['content']

class Case:
    def __init__(self,shape='json_bearer',mode='adapter',missing=False):
        self.f=VendorFixture(shape,mode);self.clock=[time.time()]
        self.folder=ROOT/self.f.name;self.folder.mkdir(parents=True,mode=0o700)
        settings=self.f.config()
        if shape=='query_key':settings['kind']=self.f.name
        if missing:settings['credentials']={}
        self.config={'schema_version':1,'domain':json.loads(pathlib.Path('/etc/huarun/info.json').read_bytes())['domain'],'cloudflare':{'account_id':'1'*32,'zone_id':'2'*32,'api_token':'synthetic-cloudflare-token-fixture-only','proxied':False},'address_source':{'mode':'static','addresses':{'A':self.f.old_ip}},'provider':settings,'notification':{'kind':'telegram','bot_token':BOT,'chat_id':'123456789'},'probes':[{'region':r,'url':'https://'+r+'.release.invalid/probe','key':PROBE_KEY} for r in ('region-a','region-b')]}
        self.path=self.folder/'network.json';network.atomic_private(self.path,network.validate_config(self.config))
        def factory(config,state_dir):
            # Exercise the actual generic fallback of the distributed factory.
            p=ip_provider.get_provider(config,state_dir,clock=lambda:self.clock[0])
            require(isinstance(p,provider_discovery.DiscoveryProvider),'unknown_vendor_not_dispatched_to_discovery')
            p.research_factory=lambda:ResearchFixture(self.f);p.document_fetch=self.f.document_fetch;p.model=self.f.model;p.default_model=False;p.api_transport=self.f.api_transport
            self.f.profile_path=p.store.root/'profile.json'
            return p
        self.net=network.Network(config_path=self.path,state_dir=self.folder/'network-state',clock=lambda:self.clock[0],probe_transport=local_probe,provider_factory=factory)
        self.provider=lambda:self.net.provider(self.config)
    def close(self):self.f.close()
    def commit(self,ip):
        cf=network.Cloudflare(self.config,self.net.transport);cf.sync({'A':ip})
        return cloud_address(self.config['domain'])==ip
    def verify(self,ip):return self.net.confirmed(self.net.observations(self.config,ip),True)
    def mutation_events(self):return [e for e in self.f.events if e['kind'] in ('allocate','attach','restore','unexpected_request')]
    def discover(self):return self.net.provider_discover(force=True)
    def ready(self):
        r=self.discover();require(r.get('status')=='ready','generic_discovery_not_ready:'+str(r.get('code')));return r

def connected_case(shape):
    case=Case(shape)
    try:
        control(False,True)
        for _ in range(network.HEALTH_FAILURES):status=case.net.run()
        require(status.get('provider_discovery',{}).get('status')=='ready','generic_automatic_discovery_failed:'+str(status.get('last_error')))
        require(status.get('provider_result',{}).get('status')=='rotated','generic_automatic_rotation_failed:'+str(status.get('provider_result')))
        require(cloud_address(case.config['domain'])==case.f.new_ip,'generic_dns_not_replaced')
        p=case.provider();receipt=p.store.read('receipt.json',{});profile=p.store.read('profile.json',{})
        required_validation=('schema_and_evidence','synthetic_protocol_passed','synthetic_identity_guard_passed')
        require(all(receipt.get('validation',{}).get(k) is True for k in required_validation),'generic_profile_validation_missing')
        require(receipt.get('binding_verified') is True,'generic_instance_binding_missing')
        docsha=hashlib.sha256(case.f.text.encode()).hexdigest()
        require(any(s['url']==case.f.doc and s['sha256']==docsha for s in receipt['sources']),'generic_official_document_digest_missing')
        events=case.f.events;kinds=[e['kind'] for e in events];first_mutation=min(i for i,x in enumerate(kinds) if x in ('allocate','attach'))
        reads=[e for e in events if e['kind']=='read'];require(reads and reads[0].get('active_profile_exists') is False,'generic_activation_preceded_read_probe')
        require(kinds.index('read')<first_mutation and kinds.index('model')<kinds.index('read'),'generic_readonly_probe_order_invalid')
        research=[e['phase'] for e in events if e['kind']=='research'];require(research==['mcp','search'],'generic_research_order_invalid')
        require(case.f.token not in json.dumps(case.f.model_payloads) and case.f.instance not in json.dumps(case.f.model_payloads),'generic_model_received_owner_secret')
        require(not any(e['kind']=='unexpected_request' for e in events),'generic_unexpected_api_action')
        control(True,True);case.clock[0]+=1000
        healthy=case.net.run();require(healthy['status']=='healthy','generic_recovery_recheck_failed')
        result={'name':case.f.name,'api_shape':shape,'document_sha256':docsha,'profile_sha256':hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest(),'read_requests':len(reads),'mutation_requests':len(case.mutation_events()),'read_before_mutation':True,'dns_readback_verified':cloud_address(case.config['domain'])==case.f.new_ip,'passed':True}
        require(result['profile_sha256']==receipt['profile_sha256'],'generic_profile_digest_not_bound')
        return result
    finally:case.close()

def decision_case(mode,expected,missing=False):
    case=Case(mode=mode,missing=missing)
    try:
        before=len(fixture('fixture-state')['events']);result=case.discover()
        require(result.get('status')==expected,'generic_decision_wrong:'+mode+':'+str(result.get('status'))+':'+str(result.get('code')))
        require(not case.mutation_events(),'generic_unready_provider_mutated')
        require(case.f.external_origin_attempts==0,'generic_foreign_origin_received_credential_attempt')
        require(not case.provider().store.read('profile.json',{}),'generic_unready_provider_activated')
        events=fixture('fixture-state')['events'][before:]
        sent=[e for e in events if e['kind']=='notification_delivered']
        require(bool(sent),'generic_decision_notification_missing')
        if mode=='no_api':require(any('未提供可用的换 IP API' in e.get('text','') for e in sent),'generic_no_api_notification_wrong')
        else:require(not any('未提供可用的换 IP API' in e.get('text','') for e in sent),'generic_error_misreported_as_no_api')
        return True
    finally:case.close()

def recovery_cases():
    result={}
    case=Case()
    try:
        control(False,True);case.ready();case.commit(case.f.old_ip);case.f.drop_allocate_ack=True
        p=case.provider();first=p.rotate('lost-allocation-ack',case.verify,case.commit)
        require(first['status']=='pending' and p.pending(),'generic_ambiguous_write_not_journalled')
        second=case.provider().rotate('lost-allocation-ack',case.verify,case.commit)
        require(second['status']=='rotated' and cloud_address(case.config['domain'])==case.f.new_ip,'generic_ambiguous_write_recovery_failed')
        events=case.f.events
        result['ambiguous_replace_not_repeated']=sum(e['kind']=='allocate' for e in events)==1 and any(e['kind']=='reconcile' for e in events)
    finally:case.close()
    case=Case('query_key')
    try:
        control(False,True);case.ready();case.commit(case.f.old_ip)
        def failed_dns(ip):case.commit(ip);return ip==case.f.old_ip
        first=case.provider().rotate('post-dns-failure',case.verify,failed_dns)
        require(first['status']=='pending' and cloud_address(case.config['domain'])==case.f.new_ip,'generic_dns_failure_not_recoverable')
        second=case.provider().rotate('post-dns-failure',case.verify,failed_dns)
        result['failed_replacement_rolled_back']=(second['status']=='rolled_back' and case.f.current_ip==case.f.old_ip and cloud_address(case.config['domain'])==case.f.old_ip and not case.provider().pending() and sum(e['kind']=='allocate' for e in case.f.events)==1 and sum(e['kind']=='restore' for e in case.f.events)==1)
    finally:case.close()
    return result


def assisted_cases():
    result={};protected=guest.snapshot()
    def immutable_config(case):
        value=copy.deepcopy(network.load_private(case.path));value['address_source']['addresses'].pop('A',None)
        value.get('provider',{}).pop('expected_current_ipv4',None)
        st=case.path.stat()
        return {'config':value,'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
    def denied(case,ip,expected):
        before=case.path.read_bytes();previous_dns=cloud_address(case.config['domain'])
        try:case.net.confirm_ip(ip)
        except network.NetworkError as error:code=str(error)
        else:raise RuntimeError('assisted_unverified_change_accepted')
        require(code==expected,'assisted_wrong_rejection:'+code)
        require(case.path.read_bytes()==before,'assisted_rejection_modified_config')
        require(cloud_address(case.config['domain'])==previous_dns,'assisted_rejection_modified_dns')
        require(not case.mutation_events(),'assisted_confirmation_called_cloud_mutation')
        return code
    # No API is documented. The owner changes the external VPS address; confirm_ip
    # validates signed regional TLS/WS observations and the installed local node.
    case=Case(mode='no_api')
    try:
        control(True,True);case.commit(case.f.old_ip)
        require(case.discover().get('status')=='no_api_documented','assisted_no_api_fixture_wrong')
        original=immutable_config(case);case.f.current_ip=case.f.new_ip
        accepted=case.net.confirm_ip(case.f.new_ip)
        result['manual_ip_validated']=(accepted.get('status')=='assisted_ip_confirmed' and accepted.get('ip')==case.f.new_ip and accepted.get('server_verified') is True and accepted.get('client_connectivity')=='not_tested')
        result['static_address_persisted']=(network.load_private(case.path)['address_source']['addresses']['A']==case.f.new_ip and network.load_private(case.path)['provider']['expected_current_ipv4']==case.f.new_ip)
        result['dns_readback_verified']=accepted.get('dns_verified') is True and cloud_address(case.config['domain'])==case.f.new_ip
        case.clock[0]+=1000;case.net.run()
        result['next_timer_keeps_new_ip']=cloud_address(case.config['domain'])==case.f.new_ip and network.load_private(case.path)['address_source']['addresses']['A']==case.f.new_ip
        require(immutable_config(case)==original and not case.mutation_events(),'assisted_changed_credentials_or_called_provider_write')
    finally:case.close()
    case=Case(mode='no_api')
    try:
        control(True,False);case.commit(case.f.old_ip)
        denied(case,case.f.new_ip,'assisted_new_ip_not_verified');result['unverified_ip_rejected']=True
        control(True,True)
        for name,relative,expected in (('pending_setup_rejected','setup/transaction.json','domain_recovery_pending'),('pending_provider_rejected','provider/discovered/held/transaction.json','provider_recovery_pending')):
            marker=case.net.state_dir/relative;network.atomic_private(marker,{'fixture_pending':True})
            try:denied(case,case.f.new_ip,expected);result[name]=True
            finally:marker.unlink()
    finally:case.close()
    # A verified API cannot be bypassed by confirming an unrelated public IP.
    case=Case()
    try:
        control(True,True);case.ready();case.commit(case.f.old_ip)
        denied(case,case.f.new_ip,'confirmed_ip_provider_mismatch');result['api_binding_cannot_be_bypassed']=True
    finally:case.close()
    case=Case(mode='no_api')
    try:
        control(True,True);case.commit(case.f.old_ip);case.discover()
        original=immutable_config(case);fixture('fixture-control',{'dns_write_failures':1})
        try:case.net.confirm_ip(case.f.new_ip)
        except network.NetworkError as error:require(str(error)=='assisted_dns_update_pending','assisted_wrong_transient_dns_error')
        else:raise RuntimeError('assisted_dns_outage_not_exercised')
        state=case.net.state()
        result['dns_failure_keeps_new_ip']=(network.load_private(case.path)['address_source']['addresses']['A']==case.f.new_ip and network.load_private(case.path)['provider']['expected_current_ipv4']==case.f.new_ip and cloud_address(case.config['domain'])==case.f.old_ip and state.get('status')=='assisted_dns_pending' and state.get('assisted_recovery',{}).get('status')=='dns_pending')
        fixture('fixture-control',{'dns_write_failures':0});case.clock[0]+=1000;case.net.run()
        result['dns_retry_recovers_new_ip']=(cloud_address(case.config['domain'])==case.f.new_ip and network.load_private(case.path)['address_source']['addresses']['A']==case.f.new_ip and case.net.state().get('assisted_recovery',{}).get('status')=='dns_verified')
        require(immutable_config(case)==original and not case.mutation_events(),'assisted_dns_retry_changed_credentials')
    finally:
        fixture('fixture-control',{'dns_write_failures':0});case.close()
    result['configuration_and_keys_preserved']=guest.snapshot()==protected
    result['passed']=all(value is True for value in result.values())
    require(result['passed'],'assisted_recovery_acceptance_failed:'+str({k:v for k,v in result.items() if v is not True}))
    return result

def run_cases(assisted=False):
    result={};protected=guest.snapshot()
    cases=[connected_case(shape) for shape in ('json_bearer','query_key')]
    result.update(unknown_json_provider_auto_connected=cases[0]['passed'],unknown_query_provider_auto_connected=cases[1]['passed'],official_docs_read=True,official_docs_digest_bound=True,read_only_probe_before_activation=True,generated_adapter_validated=True,provider_credentials_not_sent_to_model=True,ip_replacement_verified=True,dns_readback_verified=all(x['dns_readback_verified'] for x in cases),no_vendor_allowlist=len({x['name'] for x in cases})==2)
    result['no_api_notified']=decision_case('no_api','no_api_documented')
    result['docs_unavailable_distinguished']=decision_case('unavailable','documentation_unavailable')
    result['missing_credentials_distinguished']=decision_case('adapter','credentials_required',missing=True)
    result['malicious_document_rejected']=decision_case('malicious','identity_unconfirmed')
    result.update(recovery_cases())
    require(guest.snapshot()==protected,'generic_tests_changed_owner_files')
    result['passed']=all(x is True for x in result.values())
    result.update(providers=cases,scope='installed_runtime_http_fixtures',live_cloud_rotation=False)
    if assisted:result['assisted']=assisted_cases()
    require(result['passed'],'generic_provider_acceptance_failed')
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--assisted',action='store_true');args=parser.parse_args()
    for module in (network,provider_discovery,generic_provider,ip_provider):
        require(pathlib.Path(module.__file__).parent==pathlib.Path('/usr/local/lib/huarun'),'generic_test_not_using_installed_modules')
    guest.cmd(['systemctl','stop','huarun-network.timer']);guest.cmd(['systemctl','stop','huarun-network.service'],check=False)
    try:
        with network.MaintenanceLock():result=run_cases(assisted=args.assisted)
    finally:
        control(True,None);guest.cmd(['systemctl','start','huarun-network.timer'])
    observed=guest.probe();require(all(observed[k] is True for k in ('services_healthy','proxy_allowed','proxy_blocked','tls_verified')),'generic_final_installed_node_unhealthy')
    print(json.dumps(result,sort_keys=True))
if __name__=='__main__':main()
