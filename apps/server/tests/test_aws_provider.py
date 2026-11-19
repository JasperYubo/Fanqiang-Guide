import copy,json,os,sys,tempfile,unittest
from pathlib import Path
from urllib.error import HTTPError
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import aws_provider as aws
from ip_provider import ProviderError

ACCOUNT='123456789012';INSTANCE='i-0123456789abcdef0';ENI='eni-0123456789abcdef0'
OLD='8.8.4.4';NEW='1.1.1.1';OLD_ID='eipalloc-0123456789abcdef0';NEW_ID='eipalloc-0123456789abcdef1'
CONFIG={'kind':'aws_eip','account_id':ACCOUNT,'instance_id':INSTANCE,'region':'us-east-1',
 'access_key_id':'AKIDEXAMPLE1234567890','secret_access_key':'wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY',
 'auto_rotate':True,'allow_reserved_ip_allocation':True,'allow_downtime':True,
 'max_attempts_per_day':1,'max_elastic_ips':5,'max_monthly_ipv4_usd':20,'cleanup_owned_old_ip':False}

def element(name,fields):
    root=ET.Element(name)
    for key,value in fields.items():ET.SubElement(root,key).text=str(value)
    return root

def add(parent,path,value):
    node=parent
    for part in path.split('/'):
        found=node.find(part)
        node=found if found is not None else ET.SubElement(node,part)
    node.text=str(value)

class Fake:
    def __init__(self):
        self.rows={OLD:{'id':OLD_ID,'ip':OLD,'association':'eipassoc-0123456789abcdef0','instance':INSTANCE,'eni':ENI,'private':'10.0.0.5','owner':ACCOUNT,'border':'us-east-1','tags':{}}}
        self.calls=[];self.owner=ACCOUNT;self.instance=INSTANCE;self.running=True;self.eni=ENI
        self.lose_allocation=False;self.lose_associate=False;self.deny_allocate=False;self.deny_associate=False;self.allocate_invisible=0
    def __call__(self,action,params):
        self.calls.append((action,copy.deepcopy(params)))
        root=ET.Element(action+'Response')
        if action=='DescribeInstances':
            r=ET.SubElement(ET.SubElement(root,'reservationSet'),'item');add(r,'ownerId',self.owner)
            i=ET.SubElement(ET.SubElement(r,'instancesSet'),'item')
            for path,value in {'instanceId':self.instance,'instanceState/name':'running' if self.running else 'stopped','vpcId':'vpc-0123456789abcdef0'}.items():add(i,path,value)
            n=ET.SubElement(ET.SubElement(i,'networkInterfaceSet'),'item')
            for path,value in {'networkInterfaceId':self.eni,'ownerId':self.owner,'attachment/deviceIndex':0,'attachment/instanceId':self.instance,'privateIpAddress':'10.0.0.5'}.items():add(n,path,value)
            a=ET.SubElement(ET.SubElement(n,'privateIpAddressesSet'),'item');add(a,'privateIpAddress','10.0.0.5')
            bound=next((v for v in self.rows.values() if v['association'] and v['eni']==ENI),None)
            add(a,'association/publicIp',bound['ip'] if bound else '9.9.9.9')
        elif action=='DescribeAddresses':
            values=ET.SubElement(root,'addressesSet')
            for row in self.rows.values():
                if row['ip']==NEW and self.allocate_invisible:
                    self.allocate_invisible-=1;continue
                item=ET.SubElement(values,'item')
                for key,field in {'publicIp':'ip','allocationId':'id','associationId':'association','instanceId':'instance','networkInterfaceId':'eni','privateIpAddress':'private','networkInterfaceOwnerId':'owner','networkBorderGroup':'border'}.items():
                    if row.get(field):add(item,key,row[field])
                add(item,'domain','vpc')
                tags=ET.SubElement(item,'tagSet')
                for key,value in row['tags'].items():tags.append(element('item',{'key':key,'value':value}))
        elif action=='AllocateAddress':
            if self.deny_allocate:raise ProviderError('provider_aws_http_403')
            self.rows[NEW]={'id':NEW_ID,'ip':NEW,'association':None,'instance':None,'eni':None,'private':None,'owner':None,'border':params['NetworkBorderGroup'],
                'tags':{params['TagSpecification.1.Tag.1.Key']:params['TagSpecification.1.Tag.1.Value'],params['TagSpecification.1.Tag.2.Key']:params['TagSpecification.1.Tag.2.Value']}}
            if self.lose_allocation:raise TimeoutError('secret must not be emitted')
            add(root,'allocationId',NEW_ID);add(root,'publicIp',NEW)
        elif action=='AssociateAddress':
            if self.deny_associate:raise ProviderError('provider_aws_http_403')
            assert params['AllowReassociation']=='false'
            selected=next(v for v in self.rows.values() if v['id']==params['AllocationId'])
            if selected['association']:raise ProviderError('already_associated')
            for row in self.rows.values():
                if row['eni']==params['NetworkInterfaceId'] and row['private']==params['PrivateIpAddress']:
                    row.update(association=None,instance=None,eni=None,private=None,owner=None)
            selected.update(association='eipassoc-0123456789abcdef1',instance=INSTANCE,eni=ENI,private='10.0.0.5',owner=ACCOUNT)
            if self.lose_associate:raise TimeoutError('secret must not be emitted')
            add(root,'associationId',selected['association'])
        elif action=='DisassociateAddress':
            selected=next(v for v in self.rows.values() if v['association']==params['AssociationId'])
            selected.update(association=None,instance=None,eni=None,private=None,owner=None)
            add(root,'return','true')
        elif action=='ReleaseAddress':
            selected=next(v for v in self.rows.values() if v['id']==params['AllocationId'])
            assert not selected['association']
            del self.rows[selected['ip']];add(root,'return','true')
        else:raise AssertionError(action)
        return root

class AWSRotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.config=copy.deepcopy(CONFIG);self.api=Fake();self.now=1800000000;self.dns=OLD;self.dns_calls=[]
    def tearDown(self):self.tmp.cleanup()
    def provider(self):return aws.AWSElasticRotator(self.config,self.root,request=self.api,clock=lambda:self.now)
    def update(self,ip):self.dns=ip;self.dns_calls.append(ip);return True
    def tick(self,verify=lambda ip:True,update=None,incident='incident-1'):
        self.now+=60
        return self.provider().rotate(incident,verify,update or self.update)
    def finish(self,verify=lambda ip:True,update=None):
        for _ in range(15):
            result=self.tick(verify,update)
            if result['status'] in ('rotated','rolled_back','failed'):return result
        self.fail(result)
    def allocations(self):return [p for a,p in self.api.calls if a=='AllocateAddress']
    def test_success_is_reversible_and_never_detaches_first(self):
        result=self.finish();self.assertEqual(result['status'],'rotated');self.assertEqual(self.dns,NEW)
        self.assertIsNone(self.api.rows[OLD]['association']);self.assertTrue(self.api.rows[NEW]['association']);self.assertTrue(result['old_reserved_ip_retained'])
        self.assertFalse(any(a in ('DisassociateAddress','ReleaseAddress') for a,p in self.api.calls));self.assertEqual(len(self.allocations()),1)
    def test_repeated_incident_does_not_charge_or_reallocate(self):
        first=self.finish();self.assertEqual(self.tick(),first);self.assertEqual(len(self.allocations()),1)
    def test_candidate_failure_restores_original_and_cleans_only_new(self):
        result=self.finish(verify=lambda ip:False)
        self.assertEqual(result['status'],'rolled_back');self.assertTrue(self.api.rows[OLD]['association']);self.assertNotIn(NEW,self.api.rows);self.assertEqual(self.dns,OLD)
    def test_partial_dns_write_rolls_back_dns_before_cleanup(self):
        def partial(ip):
            self.update(ip)
            if ip==NEW:raise TimeoutError('do not print secret')
            return True
        result=self.finish(update=partial);self.assertEqual(result['status'],'rolled_back');self.assertEqual(self.dns_calls,[NEW,OLD]);self.assertNotIn(NEW,self.api.rows)
    def test_dns_rollback_retry_retains_candidate_until_success(self):
        def fail(ip):self.update(ip);return False
        for _ in range(6):self.tick(update=fail)
        self.assertEqual(self.provider()._journal()['phase'],'rollback_dns');self.assertIn(NEW,self.api.rows)
        result=self.finish();self.assertEqual(result['status'],'rolled_back');self.assertNotIn(NEW,self.api.rows)
    def test_lost_allocation_ack_recovers_by_exact_transaction_tags(self):
        self.api.lose_allocation=True;self.assertEqual(self.tick()['status'],'deferred')
        self.assertEqual(self.finish()['status'],'rotated');self.assertEqual(len(self.allocations()),1)
    def test_allocation_denied_never_repeats_allocating_post(self):
        self.api.deny_allocate=True
        for _ in range(4):self.assertEqual(self.tick()['status'],'deferred')
        self.assertEqual(len(self.allocations()),1);self.assertTrue(self.api.rows[OLD]['association'])
    def test_missing_allocation_is_not_adopted_as_an_unrelated_ip(self):
        self.api.lose_allocation=True;self.tick();self.api.rows[NEW]['tags']['huarun-transaction']='foreign'
        for _ in range(3):self.assertEqual(self.tick()['status'],'deferred')
        self.assertEqual(len(self.allocations()),1);self.assertTrue(self.api.rows[OLD]['association'])
    def test_eventual_consistency_after_allocate_is_reconciled(self):
        self.api.allocate_invisible=1;self.assertEqual(self.tick()['status'],'deferred')
        self.assertEqual(self.finish()['status'],'rotated');self.assertEqual(len(self.allocations()),1)
    def test_lost_association_ack_uses_readback_not_second_remap(self):
        self.api.lose_associate=True;self.assertEqual(self.finish()['status'],'rotated')
        self.assertEqual(len([a for a,p in self.api.calls if a=='AssociateAddress']),1)
    def test_association_denied_preserves_original_without_repeating(self):
        self.api.deny_associate=True
        for _ in range(4):self.tick()
        self.assertTrue(self.api.rows[OLD]['association']);self.assertEqual(len([a for a,p in self.api.calls if a=='AssociateAddress']),1)
    def test_foreign_instance_owner_cannot_mutate(self):
        self.api.owner='987654321000';self.assertEqual(self.tick()['status'],'failed');self.assertFalse(self.allocations())
    def test_stopped_instance_cannot_mutate(self):
        self.api.running=False;self.assertEqual(self.tick()['status'],'failed');self.assertFalse(self.allocations())
    def test_instance_identity_changed_midtransaction_does_not_touch_other_eni(self):
        self.tick();self.api.eni='eni-0123456789abcdef9'
        for _ in range(2):result=self.tick()
        self.assertNotEqual(result['status'],'rotated');self.assertEqual(len([a for a,p in self.api.calls if a=='AssociateAddress']),1)
    def test_existing_automatic_ip_is_readable_but_not_replaced_irreversibly(self):
        self.api.rows={};self.assertEqual(self.provider().get_inbound_addresses(),{'A':'9.9.9.9'})
        result=self.tick();self.assertEqual(result['code'],'provider_existing_elastic_ip_required_for_rollback');self.assertFalse(self.allocations())
    def test_foreign_association_is_never_stolen_or_released(self):
        self.api.lose_allocation=True;self.tick();self.api.rows[NEW].update(association='eipassoc-0123456789abcdef9',eni='eni-0123456789abcdef9',instance='i-0123456789abcdef9',owner=ACCOUNT)
        self.assertEqual(self.tick()['code'],'provider_allocation_identity_invalid');self.assertFalse(any(a=='ReleaseAddress' for a,p in self.api.calls))
    def test_budget_applies_to_attached_and_idle_ipv4(self):
        self.config['max_monthly_ipv4_usd']=7
        self.assertEqual(self.tick()['code'],'provider_address_budget_exceeded');self.assertFalse(self.allocations())
    def test_authorization_required_before_billing(self):
        self.config['allow_reserved_ip_allocation']=False
        self.assertIn('not_authorized',self.tick()['code']);self.assertFalse(self.allocations())
    def test_daily_limit_applies_to_next_incident(self):
        self.finish();self.assertEqual(self.tick(incident='another')['code'],'provider_daily_attempt_limit');self.assertEqual(len(self.allocations()),1)
    def test_state_is_private_and_scope_bound(self):
        self.tick();paths=list((self.root/'aws_eip').glob('*.json'));self.assertTrue(paths)
        for path in paths:self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertNotIn(CONFIG['secret_access_key'],path.read_text())
        self.config['account_id']='987654321000';self.assertEqual(self.tick()['code'],'provider_state_scope_mismatch')
    def test_symlink_state_is_refused(self):
        self.provider();path=self.root/'aws_eip'/'ledger.json';other=self.root/'other';other.write_text('{}');path.symlink_to(other)
        self.assertEqual(self.tick()['code'],'provider_state_symlink')

class SigningTests(unittest.TestCase):
    def test_signature_matches_official_botocore_reference(self):
        # This synthetic vector was cross-checked against botocore.auth.SigV4Auth
        # on Linux; no boto dependency is installed on user VPS machines.
        cfg={**CONFIG,'session_token':'synthetic/session+token='}
        req=aws.signed_request(cfg,'DescribeAddresses',{},1440938160)
        self.assertTrue(req.get_header('Authorization').endswith('Signature=192a5802bc595e62fc3af3ad723ba0d3ef439a9f51726f745e6b43b23428d794'))
        self.assertNotIn(cfg['secret_access_key'],req.full_url);self.assertNotIn(cfg['access_key_id'].encode(),req.data)
        self.assertIn('x-amz-security-token',req.get_header('Authorization'))
    def test_unsigned_arbitrary_host_or_action_is_impossible(self):
        for cfg,action in [({**CONFIG,'region':'us-east-1.attacker.test'},'DescribeAddresses'),(CONFIG,'TerminateInstances')]:
            with self.assertRaises(ProviderError):aws.signed_request(cfg,action,{},1440938160)
    def test_china_region_uses_official_dns_suffix(self):
        self.assertEqual(aws.signed_request({**CONFIG,'region':'cn-north-1'},'DescribeAddresses',{},1440938160).full_url,'https://ec2.cn-north-1.amazonaws.com.cn/')
    def test_xml_bounds_namespace_and_identity(self):
        root=aws.xml(b'<DescribeAddressesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/"><addressesSet/></DescribeAddressesResponse>','DescribeAddresses');self.assertIsNotNone(root.find('addressesSet'))
        for raw in (b'<OtherResponse/>',b'<!DOCTYPE x><DescribeAddressesResponse/>',b'<!ENTITY x "y"><DescribeAddressesResponse/>',b'not xml',b'x'*(aws.MAX_RESPONSE+1)):
            with self.assertRaises(ProviderError):aws.xml(raw,'DescribeAddresses')
    def test_http_errors_do_not_return_secret_response_bodies(self):
        class Opener:
            def open(self,req,timeout):raise HTTPError(req.full_url,403,'secret response',{},None)
        with self.assertRaisesRegex(ProviderError,'^provider_aws_http_403$'):aws.EC2API(CONFIG,opener=Opener())('DescribeAddresses',{})
    def test_factory_loads_aws_adapter(self):
        import ip_provider
        with tempfile.TemporaryDirectory() as tmp:
            provider=ip_provider.get_provider(CONFIG,tmp,request=Fake())
            self.assertIsInstance(provider,aws.AWSElasticRotator)
            cap=next(c for c in ip_provider.capabilities() if c['kind']=='aws_eip')
            self.assertIs(cap['automatic_rotation'],True)
            self.assertIs(cap['live_verified'],False)
            self.assertEqual(cap['validation'],'official_contract_tested')

if __name__=='__main__':unittest.main()
