import copy,hashlib,json,pathlib,sys,tempfile,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'apps/server'));sys.path.insert(0,str(ROOT/'developer/server-e2e'))
from generic_provider_fixture import VendorFixture,ResearchFixture
from provider_discovery import DiscoveryProvider
from ip_provider import _Store

class ProviderReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.f=VendorFixture();self.addCleanup(self.f.close);self.addCleanup(self.temp.cleanup)
        self.config=self.f.config();self.clock=lambda:100000
    def provider(self,config=None,model=None):
        return DiscoveryProvider(config or self.config,self.root,clock=self.clock,research_factory=lambda:ResearchFixture(self.f),document_fetch=self.f.document_fetch,model=model or self.f.model,api_transport=self.f.api_transport)
    def ready(self,**kwargs):
        provider=self.provider(**kwargs);self.assertEqual(provider.discover()['status'],'ready');return provider
    def test_owned_limit_matches_execute_guard(self):
        p=self.ready();r=p._provider();r.store.write('ledger.json',{'attempts':[],'finished':{},'owned':{'a':{},'b':{}}})
        status=p.safe_status();self.assertFalse(status['automatic_rotation_ready']);self.assertIn('provider_owned_allocation_limit',status['blockers']);self.assertEqual(status['peak_owned_allocations'],3)
        self.assertEqual(r.rotate('owned',lambda ip:True,lambda ip:True)['code'],'provider_owned_allocation_limit')
    def test_daily_limit_waits_without_suggesting_manual_bypass(self):
        p=self.ready();r=p._provider();r.store.write('ledger.json',{'attempts':[99990,99991,99992],'finished':{},'owned':{}})
        status=p.safe_status();self.assertFalse(status['automatic_rotation_ready']);self.assertEqual(status['recovery_mode'],'waiting');self.assertGreater(status['next_attempt_at'],100000)
        self.assertEqual(r.rotate('daily',lambda ip:True,lambda ip:True)['code'],'provider_daily_attempt_limit')
    def test_recurring_cost_uses_owned_and_new_peak(self):
        quote='Public IP allocation costs 2 USD per month.';self.f.text+=' '+quote
        profile=self.f.profile();profile['cost'].update(amount=2,billing_period='month',quote=quote)
        self.config.update(max_owned_allocations=5,max_cost_per_rotation=4,cost_currency='USD')
        p=self.ready(model=lambda payload:{'decision':'adapter','profile':profile});r=p._provider();r.store.write('ledger.json',{'attempts':[],'finished':{},'owned':{'a':{},'b':{}}})
        status=p.safe_status();self.assertFalse(status['automatic_rotation_ready']);self.assertEqual(status['estimated_cost']['amount'],6);self.assertEqual(status['estimated_cost']['period'],'projected_31_days')
        self.assertEqual(r.rotate('cost',lambda ip:True,lambda ip:True)['code'],'provider_cost_budget_exceeded')
    def test_removed_credentials_do_not_keep_cached_auto_ready(self):
        self.ready();cfg=copy.deepcopy(self.config);cfg['credentials']={};p=self.provider(config=cfg)
        status=p.safe_status();self.assertFalse(status['automatic_rotation_ready']);self.assertEqual(status['missing_credentials'],['token']);self.assertIn('credentials',status['required_configuration'])
    def test_known_refresh_auth_failure_blocks_ready_active_profile(self):
        p=self.ready();p._save('credentials_required','provider_http_401');status=p.safe_status()
        self.assertEqual(status['status'],'ready');self.assertFalse(status['automatic_rotation_ready']);self.assertEqual(status['recovery_mode'],'assisted');self.assertIn('provider_http_401',status['blockers'])
    def test_pending_transaction_never_suggests_another_manual_change(self):
        p=self.ready();r=p._provider();r.store.write('transaction.json',{'scope':r.scope,'profile_digest':r.profile_digest,'phase':'actions'})
        status=p.safe_status();self.assertFalse(status['automatic_rotation_ready']);self.assertTrue(status['pending_recovery']);self.assertEqual(status['recovery_mode'],'recovering')
        self.assertIn('provider_recovery_in_progress',status['blockers'])
    def test_malformed_pending_journal_is_recovery_not_manual(self):
        p=self.ready();p.store.write('transaction.json',{'scope':'wrong','profile_digest':'wrong','phase':'actions'})
        status=p.safe_status();self.assertEqual(status['recovery_mode'],'recovering');self.assertFalse(status['automatic_rotation_ready'])
    def test_status_neither_calls_network_nor_writes_state(self):
        p=self.ready();before={str(x.relative_to(p.store.root)):x.read_bytes() for x in p.store.root.rglob('*') if x.is_file()};events=len(self.f.events)
        with mock.patch.object(_Store,'write',side_effect=AssertionError('status_write')):
            status=p.safe_status()
        self.assertTrue(status['automatic_rotation_ready']);self.assertTrue(status['requires_live_verification']);self.assertEqual(status['assessment_scope'],'local_configuration_and_ledger')
        self.assertEqual(len(self.f.events),events);self.assertEqual(before,{str(x.relative_to(p.store.root)):x.read_bytes() for x in p.store.root.rglob('*') if x.is_file()})
    def test_invalid_limits_and_tampered_profile_cannot_be_ready(self):
        p=self.ready();p.config['max_attempts_per_day']=0;status=p.safe_status();self.assertFalse(status['automatic_rotation_ready']);self.assertIn('provider_attempt_limit_invalid',status['blockers'])
        profile=p.store.read('profile.json',{});profile['cost']['amount']=999;p.store.write('profile.json',profile)
        status=p.safe_status();self.assertFalse(status['automatic_rotation_ready']);self.assertIn('provider_manifest_digest_mismatch',status['blockers'])

if __name__=='__main__':unittest.main()
