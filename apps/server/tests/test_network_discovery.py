"""Unknown provider discovery is wired into the installed network maintenance flow."""
import copy,json,unittest
from unittest.mock import patch
from pathlib import Path
import test_network as fixture
from test_network import FakeProvider,signer,probes,n

class Discovered(FakeProvider):
    def __init__(self,status='ready',pending=False):
        super().__init__(pending=pending,outcome='unsupported')
        self.current='discovery_needed';self.next=status;self.discovered=[];self.fail_read=False
    def discover(self,force=False):
        self.discovered.append(force);self.current=self.next;return self.safe_status()
    def safe_status(self):
        return {'status':self.current,'code':self.current,'vendor_name':'Never Listed VPS'}
    def get_inbound_addresses(self):
        if self.fail_read:raise RuntimeError('private-key-must-not-appear')
        self.inbound_calls+=1;return {'A':'9.9.9.9'}

class DiscoveryIntegrationTests(unittest.TestCase):
    setUp=fixture.NetworkCase.setUp
    install=fixture.NetworkCase.install
    def setup_provider(self,status='ready',pending=False):
        self.provider=Discovered(status,pending)
        self.instance.provider_factory=lambda settings,state:self.provider
        self.cfg['provider']={'kind':'unlisted-vendor','auto_rotate':True,'credentials':{'token':'private-credential'},'vendor_name':'Never Listed VPS'}
        self.install()
    def test_timer_discovers_unknown_and_uses_api_ip_instead_of_static_fallback(self):
        self.setup_provider();self.instance.run()
        self.assertEqual(self.provider.discovered,[False])
        self.assertEqual(self.instance.status()['addresses'],{'A':'9.9.9.9'})
        self.assertEqual(self.instance.status()['provider_discovery']['status'],'ready')
        self.assertNotIn('private-credential',json.dumps(self.instance.status()))
    def test_unavailable_documents_preserve_ddns_and_do_not_claim_no_api(self):
        self.setup_provider('documentation_unavailable');self.instance.run()
        self.assertEqual(self.instance.status()['addresses'],{'A':'8.8.8.8'})
        events=[x['code'] for x in self.instance.state()['events']]
        self.assertIn('provider_discovery_documentation_unavailable',events)
        self.assertNotIn('provider_discovery_no_api_documented',events)
    def test_no_api_is_distinct_and_unchanged_status_does_not_repeat_notification(self):
        self.setup_provider('no_api_documented');self.instance.run();self.clock+=7*3600;self.instance.run()
        events=[x['code'] for x in self.instance.state()['events']]
        self.assertEqual(events.count('provider_discovery_no_api_documented'),1)
    def test_credentials_required_is_distinct_from_missing_api(self):
        self.setup_provider('credentials_required');self.instance.run()
        events=[x['code'] for x in self.instance.state()['events']]
        self.assertIn('provider_discovery_credentials_required',events)
        self.assertNotIn('provider_discovery_no_api_documented',events)
    def test_explicit_discovery_is_forced_but_does_not_mutate_dns(self):
        self.setup_provider();self.cf.calls=[]
        self.assertEqual(self.instance.provider_discover(force=True)['status'],'ready')
        self.assertEqual(self.provider.discovered,[True]);self.assertEqual(self.cf.mutations(),[])
    def test_ready_api_failure_does_not_restore_stale_fallback_or_leak_exception(self):
        self.setup_provider();self.instance.run();self.provider.fail_read=True;self.cf.calls=[]
        result=self.instance.run()
        self.assertEqual(result['last_error'],'provider_address_unavailable')
        self.assertEqual(self.cf.mutations(),[])
        self.assertNotIn('private-key',json.dumps(result))
    def test_existing_adapter_refresh_failure_holds_dns_instead_of_static_fallback(self):
        self.setup_provider();self.instance.run();self.cf.calls=[]
        self.provider.safe_status=lambda:{'status':'adapter_validation_failed','code':'profile_changed','has_active_profile':True}
        self.provider.fail_read=True
        result=self.instance.run()
        self.assertEqual(result['last_error'],'provider_address_unavailable')
        self.assertEqual(self.cf.mutations(),[])
        self.assertEqual(result['addresses'],{'A':'9.9.9.9'})
    def test_pending_transaction_recovers_without_regenerating_adapter(self):
        self.setup_provider(pending=True);self.instance.run()
        self.assertEqual(self.provider.discovered,[])
        self.assertTrue(self.provider.rotations)
    def test_provider_setup_preserves_every_other_field_and_private_mode(self):
        self.setup_provider();before=copy.deepcopy(self.cfg)
        new={'kind':'auto','vendor_name':'Another VPS','credentials':{'api_key':'replacement'},'auto_rotate':True}
        with patch.object(n,'interactive_provider',return_value=new):self.instance.provider_setup()
        actual=self.instance.config()
        for key in before:
            if key!='provider':self.assertEqual(actual[key],before[key])
        self.assertEqual(actual['provider']['expected_current_ipv4'],'8.8.8.8')
        self.assertEqual(self.instance.config_path.stat().st_mode & 0o777,0o600)
    def test_pending_key_repair_preserves_transaction_and_every_noncredential_field(self):
        self.setup_provider(pending=True);before=self.instance.config()
        journal=self.instance.state_dir/'provider'/'discovered'/'current'/'transaction.json'
        journal.parent.mkdir(parents=True);journal.write_text('{"phase":"awaiting_confirmation"}')
        original=journal.read_bytes();candidates=[]
        def factory(settings,state):
            candidates.append(copy.deepcopy(settings));return self.provider
        self.instance.provider_factory=factory
        with patch.object(n,'interactive_credentials',return_value={'token':'new-private-key'}):
            result=self.instance.provider_setup()
        after=self.instance.config();expected=copy.deepcopy(before)
        expected['provider']['credentials']={'token':'new-private-key'}
        self.assertEqual(result['status'],'ready');self.assertEqual(after,expected)
        self.assertEqual(journal.read_bytes(),original);self.assertEqual(self.cf.mutations(),[])
        self.assertEqual(self.provider.rotations,[]);self.assertEqual(self.provider.discovered,[True])
        self.assertNotIn('new-private-key',json.dumps(self.instance.state()))
    def test_pending_invalid_key_keeps_original_configuration(self):
        self.setup_provider('credentials_required',pending=True)
        journal=self.instance.state_dir/'provider'/'discovered'/'current'/'transaction.json'
        journal.parent.mkdir(parents=True);journal.write_text('{}')
        before=self.instance.config_path.read_bytes()
        with patch.object(n,'interactive_credentials',return_value={'token':'bad-key'}):
            result=self.instance.provider_setup()
        self.assertEqual(result['status'],'credentials_required')
        self.assertEqual(self.instance.config_path.read_bytes(),before)
        self.assertEqual(self.cf.mutations(),[]);self.assertEqual(self.provider.rotations,[])
    def test_expired_provider_key_can_be_repaired_using_existing_dns_binding(self):
        self.setup_provider();self.provider.current='ready';self.provider.fail_read=True
        self.cf.add(content='9.9.9.9');before=self.instance.config()
        updated=copy.deepcopy(before['provider']);updated['credentials']={'token':'new-key'}
        with patch.object(n,'interactive_provider',return_value=updated):
            result=self.instance.provider_setup()
        after=self.instance.config();self.assertEqual(result['status'],'ready')
        self.assertEqual(after['provider']['expected_current_ipv4'],'9.9.9.9')
        self.assertEqual(after['address_source']['addresses'],{'A':'9.9.9.9'})
        self.assertEqual(after['cloudflare'],before['cloudflare']);self.assertEqual(self.cf.mutations(),[])
    def test_refresh_credentials_failure_is_notified_even_with_ready_cached_profile(self):
        self.setup_provider()
        self.provider.safe_status=lambda:{'status':'ready','code':'ready','has_active_profile':True,
            'refresh_status':'credentials_required','refresh_code':'provider_credentials_required'}
        self.instance.provider_discover(force=True)
        codes=[e['code'] for e in self.instance.state()['events']]
        self.assertIn('provider_discovery_credentials_required',codes)
    def manual(self):
        self.cfg['probes']=probes();self.instance.probe_transport=signer();self.install()
        self.cf.add(content='8.8.8.8');self.cf.calls=[]
    def test_assisted_confirmation_updates_only_verified_static_ip(self):
        self.manual();before=self.instance.config();result=self.instance.confirm_ip('9.9.9.9')
        expected=copy.deepcopy(before);expected['address_source']['addresses']['A']='9.9.9.9'
        self.assertEqual(self.instance.config(),expected);self.assertEqual(result['status'],'assisted_ip_confirmed')
        self.assertTrue(result['dns_verified']);self.assertEqual(result['client_connectivity'],'not_tested')
        self.instance.run();self.assertEqual(self.instance.status()['addresses']['A'],'9.9.9.9')
        self.assertEqual(self.instance.config_path.stat().st_mode & 0o777,0o600)
    def test_assisted_unverified_new_ip_never_changes_configuration_or_dns(self):
        self.manual();self.instance.probe_transport=signer(False);original=self.instance.config_path.read_bytes()
        with self.assertRaisesRegex(n.NetworkError,'assisted_new_ip_not_verified'):self.instance.confirm_ip('9.9.9.9')
        self.assertEqual(self.instance.config_path.read_bytes(),original);self.assertEqual(self.cf.mutations(),[])
    def test_assisted_missing_second_region_is_not_verified(self):
        self.manual();config=self.instance.config();config['probes']=config['probes'][:1];n.atomic_private(self.instance.config_path,config)
        with self.assertRaisesRegex(n.NetworkError,'assisted_new_ip_not_verified'):self.instance.confirm_ip('9.9.9.9')
        self.assertEqual(self.cf.mutations(),[])
    def test_assisted_pending_setup_or_provider_blocks_changes(self):
        self.manual();before=self.instance.config_path.read_bytes()
        for relative,code in [('setup/transaction.json','domain_recovery_pending'),('provider/discovered/old/transaction.json','provider_recovery_pending')]:
            p=self.instance.state_dir/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
            with self.assertRaisesRegex(n.NetworkError,code):self.instance.confirm_ip('9.9.9.9')
            p.unlink()
        self.assertEqual(self.instance.config_path.read_bytes(),before);self.assertEqual(self.cf.mutations(),[])
    def test_assisted_local_service_failure_never_mutates(self):
        self.manual();self.instance.doctor_fn=lambda fd:False
        with self.assertRaisesRegex(n.NetworkError,'assisted_local_service_unhealthy'):self.instance.confirm_ip('9.9.9.9')
        self.assertEqual(self.cf.mutations(),[])
    def test_assisted_active_provider_cannot_be_bypassed(self):
        self.setup_provider();self.provider.current='ready';self.cfg['probes']=probes();self.install()
        self.instance.probe_transport=signer();self.cf.calls=[]
        with self.assertRaisesRegex(n.NetworkError,'confirmed_ip_provider_mismatch'):self.instance.confirm_ip('8.8.4.4')
        self.assertEqual(self.cf.mutations(),[])
    def test_assisted_inactive_discovery_binds_future_adapter_to_verified_new_ip(self):
        self.setup_provider('no_api_documented');self.cfg['probes']=probes();self.install()
        self.instance.probe_transport=signer();self.instance.confirm_ip('8.8.4.4')
        actual=self.instance.config()
        self.assertEqual(actual['provider']['expected_current_ipv4'],'8.8.4.4')
        self.assertEqual(actual['provider']['credentials'],{'token':'private-credential'})
        self.assertEqual(actual['address_source']['addresses']['A'],'8.8.4.4')
    def test_assisted_consensus_source_must_agree_with_new_ip(self):
        self.manual();config=self.instance.config();config['address_source']={'mode':'consensus','no_nat_confirmed':True};n.atomic_private(self.instance.config_path,config)
        with self.assertRaisesRegex(n.NetworkError,'confirmed_ip_source_mismatch'):self.instance.confirm_ip('9.9.9.9')
        self.assertEqual(self.cf.mutations(),[])
    def test_assisted_dns_failure_retries_verified_ip_without_restoring_stale_ip(self):
        self.manual();original=self.instance.transport;failure=[True]
        def request(method,url,body=None,headers=None):
            if failure[0] and method=='PATCH':raise n.NetworkError('upstream_http_503')
            return original(method,url,body,headers)
        self.instance.transport=request
        with self.assertRaisesRegex(n.NetworkError,'assisted_dns_update_pending'):self.instance.confirm_ip('9.9.9.9')
        self.assertEqual(self.instance.config()['address_source']['addresses']['A'],'9.9.9.9')
        self.assertEqual(self.instance.status()['assisted_recovery']['status'],'dns_pending')
        failure[0]=False;self.instance.run()
        self.assertEqual(self.instance.status()['addresses']['A'],'9.9.9.9')
        self.assertEqual(self.instance.status()['assisted_recovery']['status'],'dns_verified')
    def test_assisted_private_ip_rejected_before_any_provider_or_dns_call(self):
        self.manual();before=self.instance.config_path.read_bytes()
        for ip in ['127.0.0.1','10.0.0.1','224.0.0.1','not-an-ip','2001:4860:4860::8888']:
            with self.assertRaises(n.NetworkError):self.instance.confirm_ip(ip)
        self.assertEqual(self.cf.calls,[]);self.assertEqual(self.instance.config_path.read_bytes(),before)
    def test_provider_setup_refuses_to_replace_credentials_during_pending_recovery(self):
        self.setup_provider();original=self.instance.config_path.read_bytes()
        journal=self.instance.state_dir/'provider'/'discovered'/'any-vendor'/'transaction.json'
        journal.parent.mkdir(parents=True);journal.write_text('{}')
        with self.assertRaisesRegex(n.NetworkError,'provider_recovery_pending'):
            self.instance.provider_setup()
        self.assertEqual(self.instance.config_path.read_bytes(),original)

if __name__=='__main__':unittest.main()
