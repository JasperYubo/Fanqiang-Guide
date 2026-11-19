import copy,json,pathlib,sys,tempfile,unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'apps/server'));sys.path.insert(0,str(ROOT/'developer/server-e2e'))
from generic_provider_fixture import VendorFixture,ResearchFixture
from generic_provider import GenericHTTPProvider,validate_profile,contract_check,ProviderError,_ResponseDict

class GenericProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.f=VendorFixture();self.addCleanup(self.f.close);self.addCleanup(self.temp.cleanup)
    def docs(self):return [{'url':self.f.doc,'text':self.f.text}]
    def validated(self,p=None):return validate_profile(p or self.f.profile(),self.docs())
    def runtime(self,p=None,config=None,transport=None):return GenericHTTPProvider(config or self.f.config(),p or self.validated(),self.root,request=transport or self.f.api_transport,clock=lambda:100000)
    def test_generic_unknown_vendor_allocate_attach_verified(self):
        result=self.runtime().rotate('incident',lambda ip:ip==self.f.new_ip,lambda ip:ip==self.f.new_ip)
        self.assertEqual(result['status'],'rotated');self.assertEqual([x['kind'] for x in self.f.events if x['kind'] in ('allocate','attach')],['allocate','attach'])
    def test_restore_cannot_be_in_success_path(self):
        p=self.f.profile();restore=copy.deepcopy(p['rollback'][0]);restore['id']='restore';p['actions'].append(restore)
        with self.assertRaisesRegex(ProviderError,'restore_action_in_success_path'):self.validated(p)
        restore['operation']='ip_attach'
        with self.assertRaisesRegex(ProviderError,'restore_action_in_success_path'):self.validated(p)
    def test_synthetic_contract_and_wrong_identity_guard(self):self.assertTrue(contract_check(self.f.config(),self.validated())['synthetic_identity_guard_passed'])
    def test_operation_http_method_is_part_of_evidence(self):
        p=self.f.profile();p['actions'][0]['request']['method']='PUT'
        with self.assertRaisesRegex(ProviderError,'semantics'):self.validated(p)
    def test_rpc_non_ip_action_rejected(self):
        p=self.f.profile();p['actions'][0]['request']['query']={'action':'StopInstance'}
        with self.assertRaises(ProviderError):self.validated(p)
    def test_cost_negated_free_rejected(self):
        p=self.f.profile();q='IP replacement is not free; costs $5.';self.f.text+=' '+q;p['cost']['quote']=q
        with self.assertRaisesRegex(ProviderError,'free_cost'):self.validated(p)
    def test_cost_number_and_currency_boundaries(self):
        for amount,currency,q in [(10,'USD','IP replacement costs $1.'),(1,'EUR','IP replacement costs 1 USD.')]:
            p=self.f.profile();self.f.text+=' '+q;p['cost'].update(amount=amount,currency=currency,quote=q)
            with self.assertRaisesRegex(ProviderError,'cost_amount'):self.validated(p)
    def test_hourly_charge_not_treated_as_single_fee(self):
        p=self.f.profile();q='IP allocation costs 0.005 USD per hour.';self.f.text+=' '+q;p['cost'].update(amount=.005,billing_period='hour',quote=q)
        cfg=self.f.config();cfg.update(max_cost_per_rotation=.01,cost_currency='USD')
        result=self.runtime(self.validated(p),cfg).rotate('price',lambda ip:True,lambda ip:True)
        self.assertEqual(result['code'],'provider_cost_budget_exceeded');self.assertFalse(any(x['kind']=='allocate' for x in self.f.events))
    def test_synthetic_budget_uses_hourly_holding_cost(self):
        p=self.f.profile();q='IP allocation costs 0.004 USD per hour.';self.f.text+=' '+q;p['cost'].update(amount=.004,billing_period='hour',quote=q)
        cfg=self.f.config();cfg.update(max_cost_per_rotation=10,cost_currency='USD')
        self.assertTrue(contract_check(cfg,self.validated(p))['synthetic_protocol_passed'])
    def test_synthetic_budget_covers_multiple_monthly_allocations(self):
        p=self.f.profile();q='IP allocation costs 2 USD per month.';self.f.text+=' '+q;p['cost'].update(amount=2,billing_period='month',quote=q)
        second=copy.deepcopy(p['actions'][0]);second['id']='allocate_second';p['actions'].insert(1,second)
        cfg=self.f.config();cfg.update(max_cost_per_rotation=10,cost_currency='USD')
        self.assertTrue(contract_check(cfg,self.validated(p))['synthetic_protocol_passed'])
    def test_free_registration_is_not_free_ip_evidence(self):
        p=self.f.profile();q='Free account registration is available to everyone.';self.f.text+=' '+q;p['cost']['quote']=q
        with self.assertRaisesRegex(ProviderError,'cost_not_bound_to_ip'):self.validated(p)
    def test_model_timeout_thinking_and_configured_model_are_explicit(self):
        import provider_discovery as discovery
        with mock.patch.object(discovery,'_ai_settings',return_value=('synthetic-key','configured-model')),mock.patch.object(discovery,'api_request',return_value={'choices':[{'message':{'content':'{"decision":"needs_documents"}'}}]}) as request:
            result=discovery.generate_manifest({'phase':'compile'},timeout=53)
        self.assertEqual(result['decision'],'needs_documents');self.assertEqual(request.call_args.kwargs['timeout'],53)
        body=request.call_args.args[2];self.assertEqual(body['model'],'configured-model');self.assertEqual(body['thinking'],{'type':'disabled'})
    def test_model_timeout_is_clipped_to_discovery_deadline(self):
        import provider_discovery as discovery
        with mock.patch.object(discovery,'generate_manifest',return_value={'decision':'needs_documents'}) as generate:
            d=discovery.DiscoveryProvider(self.f.config(),self.root,clock=lambda:100);d.deadline=135
            d._model({'phase':'compile'})
        self.assertEqual(generate.call_args.kwargs['timeout'],30)
    def test_retained_owned_resources_have_hard_cap(self):
        r=self.runtime();r.store.write('ledger.json',{'attempts':[],'finished':{},'owned':{'a':{},'b':{}}})
        self.assertEqual(r.rotate('cap',lambda ip:True,lambda ip:True)['code'],'provider_owned_allocation_limit')
    def test_parameters_cannot_override_target(self):
        cfg=self.f.config();cfg['parameters']={'instance_id':'wrong'}
        with self.assertRaisesRegex(ProviderError,'parameters_invalid'):self.runtime(config=cfg)
    def test_origin_mention_not_credential_authorization(self):
        p=self.f.profile();p['origin']='https://attacker.invalid';self.f.text+=' https://attacker.invalid'
        with self.assertRaisesRegex(ProviderError,'owner_scope'):self.validated(p)
    def test_owner_can_scope_independent_official_api_origin(self):
        p=self.f.profile();p['origin']='https://api.alt-provider.invalid';self.f.text+=' https://api.alt-provider.invalid'
        self.assertEqual(validate_profile(p,self.docs(),approved_api_origins=[p['origin']])['origin'],p['origin'])
    def test_header_host_cannot_be_replaced(self):
        p=self.f.profile();p['auth'].update(type='header',name='Host')
        with self.assertRaisesRegex(ProviderError,'header_not_allowed'):self.validated(p)
    def test_secret_braces_are_literal(self):
        cfg=self.f.config();cfg['credentials']['token']='a{instance_id}{foo}b';r=self.runtime(config=cfg)
        self.assertEqual(r._secret_template('{secret:token} {instance_id}',{'instance_id':'selected'}),'a{instance_id}{foo}b selected')
    def test_hmac_rfc4231_case2_vector(self):
        p=self.f.profile();p['auth'].update(type='hmac',algorithm='sha256',encoding='hex',canonical='what do ya want for nothing?',headers={'X-Signature':'{signature}'})
        cfg=self.f.config();cfg['credentials']['token']='Jefe';seen=[]
        r=self.runtime(p,cfg,lambda method,url,body,headers:seen.append(headers) or {})
        r._call(p['read'],r.variables)
        self.assertEqual(seen[0]['X-Signature'],'5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843')
    def test_lost_allocation_ack_does_not_repeat_post(self):
        self.f.drop_allocate_ack=True;r=self.runtime()
        self.assertEqual(r.rotate('lost',lambda ip:True,lambda ip:True)['status'],'pending')
        self.assertEqual(r.rotate('lost',lambda ip:True,lambda ip:True)['status'],'rotated')
        self.assertEqual(sum(x['kind']=='allocate' for x in self.f.events),1)
    def test_async_readiness_blocks_dependent_attach(self):
        p=self.f.profile();p['actions'][0]['wait']={'request':copy.deepcopy(p['actions'][0]['reconcile']['request']),'expect':{'/ips/0/status':'ready'}}
        ready=[False]
        def transport(method,url,body,headers):
            result=self.f.api_transport(method,url,body,headers)
            if method=='POST' and url.endswith('/addresses'):result=_ResponseDict(result);result.http_status=202
            if method=='GET' and '/addresses?' in url:
                for row in result['ips']:row['status']='ready' if ready[0] else 'pending'
            return result
        r=self.runtime(self.validated(p),transport=transport)
        self.assertEqual(r.rotate('async',lambda ip:True,lambda ip:True)['status'],'pending');self.assertFalse(any(x['kind']=='attach' for x in self.f.events))
        ready[0]=True;self.assertEqual(r.rotate('async',lambda ip:True,lambda ip:True)['status'],'rotated')
        self.assertEqual(sum(x['kind']=='allocate' for x in self.f.events),1)

if __name__=='__main__':unittest.main()
