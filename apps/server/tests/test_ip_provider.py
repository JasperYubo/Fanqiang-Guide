#!/usr/bin/env python3
"""Provider contract and failure tests. No cloud credentials or external I/O."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('ip_provider', Path(__file__).resolve().parents[1] / 'ip_provider.py')
p = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(p)
OLD = '8.8.8.8'; NEW = '8.8.4.4'; OTHER = '1.1.1.1'

class FakeClock:
    def __init__(self): self.value = 1000000
    def __call__(self): return self.value
    def step(self): self.value += 31

class FakeDO:
    def __init__(self, reserved=False):
        self.ips = {OLD: self.row(OLD, 123)} if reserved else {}
        self.actions = {}; self.events = []; self.lost_allocation = False
        self.lost_action = False; self.action_fail = False; self.stale_polls = 0
    def row(self, ip, target=None): return {'ip':ip, 'region':{'slug':'nyc3'}, 'droplet': None if target is None else {'id':target}}
    def __call__(self, method, path, data=None):
        self.events.append((method,path,copy.deepcopy(data)))
        if path == '/droplets/123':
            return {'droplet':{'id':123,'region':{'slug':'nyc3'},'status':'active','networks':{'v4':[{'type':'public','ip_address':OLD}]}}}
        if path.startswith('/reserved_ips?'): return {'reserved_ips':copy.deepcopy(list(self.ips.values()))}
        if path == '/reserved_ips' and method == 'POST':
            assert data == {'region':'nyc3'}
            self.ips[NEW] = self.row(NEW)
            if self.lost_allocation: raise RuntimeError('secret-api-key-in-error')
            return {'reserved_ip':copy.deepcopy(self.ips[NEW])}
        bits = path.split('/'); ip = bits[2]
        if method == 'GET' and len(bits) == 3: return {'reserved_ip':copy.deepcopy(self.ips.get(ip))}
        if method == 'DELETE':
            assert len(bits) == 3
            self.ips.pop(ip,None); return {}
        if method == 'POST' and bits[3] == 'actions':
            target = data.get('droplet_id') if data['type'] == 'assign' else None
            if target is not None:
                assert not any(v['droplet'] == {'id': target} for k,v in self.ips.items() if k != ip)
            ident = len(self.actions)+1
            self.actions[ident] = {'id':ident,'status':'errored' if self.action_fail else 'completed','ip':ip,'target':target}
            if not self.action_fail and not self.stale_polls: self.ips[ip]['droplet'] = None if target is None else {'id':target}
            if self.lost_action:
                self.lost_action = False; raise RuntimeError('secret-api-key-in-error')
            return {'action':{'id':ident,'status':'in-progress'}}
        if method == 'GET' and bits[3] == 'actions':
            action = self.actions[int(bits[4])]
            if self.stale_polls:
                self.stale_polls -= 1
                if not self.stale_polls: self.ips[ip]['droplet'] = None if action['target'] is None else {'id':action['target']}
            return {'action':copy.deepcopy(action)}
        raise AssertionError((method,path,data))

class FakeLocal:
    def __init__(self): self.values = {OLD:24}; self.events = []
    def addresses(self): return dict(self.values)
    def ensure(self, ip):
        self.events.append(('add',ip))
        if ip in self.values and self.values[ip] != 32: raise p.ProviderError('provider_guest_address_conflict')
        self.values[ip] = 32
    def remove(self, ip):
        self.events.append(('del',ip)); self.values.pop(ip,None)

class FakeHetzner:
    def __init__(self): self.rows = {}; self.actions={}; self.events=[]; self.lost_allocation=False; self.lost_action=False; self.fail_action=False
    def row(self, ident, ip, server=None, labels=None):
        return {'id':ident,'ip':ip,'type':'ipv4','server':server,'home_location':{'name':'fsn1'},'labels':labels or {}}
    def __call__(self, method, path, data=None):
        self.events.append((method,path,copy.deepcopy(data)))
        if path == '/servers/123':
            return {'server':{'id':123,'status':'running','datacenter':{'location':{'name':'fsn1'}},'public_net':{'ipv4':{'ip':OLD}}}}
        if path.startswith('/floating_ips?'): return {'floating_ips':copy.deepcopy(list(self.rows.values()))}
        if path == '/floating_ips' and method == 'POST':
            assert data['type'] == 'ipv4' and data['home_location'] == 'fsn1'
            self.rows[2] = self.row(2,NEW,labels=data['labels'])
            if self.lost_allocation: raise RuntimeError('sensitive-provider-error')
            return {'floating_ip':copy.deepcopy(self.rows[2])}
        if path.startswith('/actions/'):
            return {'action':copy.deepcopy(self.actions[int(path.split('/')[-1])])}
        bits=path.split('/'); ident=int(bits[2])
        if method == 'DELETE': self.rows.pop(ident,None); return {}
        if method == 'POST' and bits[3] == 'actions':
            target=data['server'] if bits[4]=='assign' else None
            action_id=len(self.actions)+1
            self.actions[action_id]={'id':action_id,'status':'error' if self.fail_action else 'success'}
            if not self.fail_action: self.rows[ident]['server']=target
            if self.lost_action: self.lost_action=False; raise RuntimeError('sensitive-provider-error')
            return {'action':{'id':action_id,'status':'running'}}
        raise AssertionError((method,path,data))

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.clock=FakeClock(); self.api=FakeDO(); self.dns=[]; self.verify=[]
        self.config={'kind':'digitalocean','instance_id':123,'region':'nyc3','auto_rotate':True,'allow_reserved_ip_allocation':True,'allow_downtime':True}
    def provider(self): return p.DigitalOceanRotator(self.config,self.tmp.name,request=self.api,clock=self.clock)
    def good_verify(self, ip): self.verify.append(ip); return True
    def good_dns(self, ip): self.dns.append(ip); return True
    def finish(self, verify=None, dns=None, incident='test', factory=None):
        factory=factory or self.provider
        for _ in range(35):
            # Recreate the process for every timer tick to exercise on-disk resume.
            result=factory().rotate(incident,verify or self.good_verify,dns or self.good_dns)
            self.clock.step()
            if result['status'] in ('rotated','rolled_back','failed'): return result
        return result
    def allocations(self): return [x for x in self.api.events if x[:2]==('POST','/reserved_ips')]
    def test_primary_to_reserved_after_verification(self):
        r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(self.dns,[NEW]); self.assertEqual(self.verify,[NEW]); self.assertEqual(len(self.allocations()),1)
        self.assertEqual(self.provider().current_ip(),NEW); self.assertFalse(self.provider().pending())
    def test_old_foreign_reserved_retained(self):
        self.api=FakeDO(True); r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertIn(OLD,self.api.ips); self.assertIsNone(self.api.ips[OLD]['droplet'])
        self.assertFalse(any(x[0]=='DELETE' for x in self.api.events)); self.assertTrue(r['old_reserved_ip_retained'])
    def test_cached_incident_never_reallocates(self):
        self.finish(); r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(len(self.allocations()),1)
    def test_dns_partial_failure_restores_old_binding_and_dns(self):
        self.api=FakeDO(True)
        def dns(ip): self.dns.append(ip); return ip==OLD
        r=self.finish(dns=dns)
        self.assertEqual(r['status'],'rolled_back'); self.assertEqual(self.dns,[NEW,OLD]); self.assertEqual(self.api.ips[OLD]['droplet'],{'id':123}); self.assertNotIn(NEW,self.api.ips)
    def test_dns_exception_restores(self):
        def dns(ip):
            self.dns.append(ip)
            if ip==NEW: raise RuntimeError('token secret')
            return True
        r=self.finish(dns=dns); self.assertEqual(r['status'],'rolled_back'); self.assertEqual(self.dns,[NEW,OLD]); self.assertNotIn('secret',str(r))
    def test_probe_failure_never_publishes(self):
        r=self.finish(verify=lambda ip:False); self.assertEqual(r['status'],'rolled_back'); self.assertEqual(self.dns,[]); self.assertNotIn(NEW,self.api.ips)
    def test_allocation_lost_response_never_retries(self):
        self.api.lost_allocation=True; r=self.finish(); self.assertEqual(r['code'],'provider_allocation_requires_reconciliation'); self.assertEqual(len(self.allocations()),1); self.assertEqual(self.dns,[])
    def test_action_lost_response_reconciles_state(self):
        self.api.lost_action=True; r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(len([x for x in self.api.events if x[0]=='POST' and x[1].endswith('/actions')]),1)
    def test_completed_action_stale_resource_never_reposts(self):
        self.api.stale_polls=3; r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(len([x for x in self.api.events if x[0]=='POST' and x[1].endswith('/actions')]),1)
    def test_authorizations_checked_before_allocating(self):
        for key in ('auto_rotate','allow_reserved_ip_allocation','allow_downtime'):
            with self.subTest(key=key):
                self.config[key]=False; r=self.finish(); self.assertEqual(r['status'],'failed'); self.assertEqual(self.allocations(),[]); self.config[key]=True
    def test_monthly_and_resource_caps(self):
        self.api.ips[OTHER]=self.api.row(OTHER); self.config['max_monthly_unassigned_usd']=5
        r=self.finish(); self.assertEqual(r['code'],'provider_unassigned_budget_exceeded'); self.assertEqual(self.allocations(),[])
    def test_daily_limit_before_second_incident(self):
        self.finish(); r=self.finish(incident='second'); self.assertEqual(r['code'],'provider_daily_attempt_limit'); self.assertEqual(len(self.allocations()),1)
    def test_wrong_instance_or_region_never_mutates(self):
        self.config['region']='sfo3'; r=self.finish(); self.assertEqual(r['status'],'failed'); self.assertEqual(self.allocations(),[])
    def test_external_binding_preserved(self):
        adapter=self.provider(); adapter.rotate('test',self.good_verify,self.good_dns)
        self.api.ips[NEW]['droplet']={'id':999}
        r=self.finish(); self.assertEqual(r['status'],'deferred'); self.assertEqual(self.api.ips[NEW]['droplet'],{'id':999}); self.assertFalse(any(x[0]=='DELETE' for x in self.api.events))
    def test_scope_change_is_controlled(self):
        self.finish(); self.config['instance_id']=321; r=self.finish(); self.assertEqual(r['code'],'provider_state_scope_mismatch')
    def test_owned_only_deletion(self):
        self.api.ips[OTHER]=self.api.row(OTHER)
        with self.assertRaisesRegex(p.ProviderError,'provider_delete_not_owned'): self.provider()._delete_created({},OTHER)
        self.assertIn(OTHER,self.api.ips)
    def test_state_no_secret_and_private_mode(self):
        self.config['token']='secret-do-token'; self.finish()
        for file in Path(self.tmp.name).rglob('*.json'):
            self.assertNotIn('secret-do-token',file.read_text()); self.assertEqual(file.stat().st_mode & 0o777,0o600)
    def test_url_paths_reject_token_exfiltration(self):
        for cls in (p.DigitalOceanAPI,p.HetznerAPI):
            api=cls('secret-fake-token')
            for path in ('https://evil.test/','//evil.test/','/reserved_ips/1.2.3.4?token=x','/servers/123/actions/poweroff'):
                with self.assertRaisesRegex(p.ProviderError,'provider_api_path_invalid'): api('GET',path)
    def test_invalid_ips(self):
        for ip in ('127.0.0.1','10.0.0.1','::1','169.254.169.254','1.2.3.4/x',None):
            with self.assertRaises(p.ProviderError): p._ipv4(ip)

    def test_action_failure_rolls_back(self):
        self.api.action_fail=True
        r=self.finish(); self.assertEqual(r['status'],'rolled_back'); self.assertNotIn(NEW,self.api.ips); self.assertEqual(self.dns,[])
    def test_old_reserved_counts_in_peak_unassigned_cap(self):
        self.api=FakeDO(True); self.config['max_unassigned_ips']=1
        r=self.finish(); self.assertEqual(r['code'],'provider_unassigned_budget_exceeded'); self.assertFalse(self.allocations())
    def test_cleanup_only_tool_owned_old_reserved(self):
        self.api=FakeDO(True); self.config['cleanup_owned_old_ip']=True
        adapter=self.provider(); ledger=adapter._ledger(); ledger['owned'][OLD]={'created_at':1,'incident':'old'}; adapter.store.write('ledger.json',ledger)
        r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertNotIn(OLD,self.api.ips); self.assertIn(NEW,self.api.ips)
    def test_crash_after_verified_requires_recheck_before_dns(self):
        class Crash(BaseException): pass
        adapter=self.provider(); adapter.rotate('test',self.good_verify,self.good_dns)
        adapter=self.provider(); original=adapter._save
        def save(journal):
            original(journal)
            if journal['phase']=='commit_dns': raise Crash()
        adapter._save=save
        with self.assertRaises(Crash): adapter.rotate('test',self.good_verify,self.good_dns)
        self.assertEqual(self.dns,[])
        r=self.finish(verify=lambda ip:False)
        self.assertEqual(r['status'],'rolled_back'); self.assertEqual(self.dns,[]); self.assertEqual(len(self.allocations()),1)
    def test_raw_api_exception_never_echoed(self):
        def bad(*args,**kwargs): raise RuntimeError('token TOP-SECRET')
        self.api=bad; r=self.finish(); self.assertNotIn('TOP-SECRET',json.dumps(r)); self.assertEqual(r['code'],'provider_operation_failed')
    def test_state_symlink_refused(self):
        link=Path(self.tmp.name)/'digitalocean'; target=Path(self.tmp.name)/'outside'; target.mkdir(); link.symlink_to(target,target_is_directory=True)
        with self.assertRaisesRegex(p.ProviderError,'provider_state_symlink'): self.provider()

class HetznerTests(ProviderTests):
    # Do not inherit provider-specific test methods; suite below loads only own.
    def setUp(self):
        super().setUp(); self.api=FakeHetzner(); self.local=FakeLocal()
        self.config={'kind':'hetzner_floating','instance_id':123,'region':'fsn1','interface':'eth0','auto_rotate':True,'allow_floating_ip_allocation':True,'allow_guest_network_changes':True}
    def provider(self): return p.HetznerFloatingRotator(self.config,self.tmp.name,request=self.api,clock=self.clock,local=self.local)
    def allocations(self): return [x for x in self.api.events if x[:2]==('POST','/floating_ips')]
    def test_hetzner_new_ip_preserves_primary_and_recovers_after_reboot(self):
        r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(self.local.values[OLD],24); self.assertEqual(self.local.values[NEW],32); self.assertEqual(self.provider().current_ip(),NEW)
        self.local.values.pop(NEW); self.assertEqual(self.provider().restore_local_address()['status'],'restored'); self.assertIn(NEW,self.local.values)
        self.assertEqual(len(self.allocations()),1)
    def test_hetzner_lost_allocation_recovers_by_labels(self):
        self.api.lost_allocation=True; r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(len(self.allocations()),1)
    def test_hetzner_dns_failure_removes_new_only(self):
        def dns(ip): self.dns.append(ip); return ip==OLD
        r=self.finish(dns=dns); self.assertEqual(r['status'],'rolled_back'); self.assertNotIn(NEW,self.local.values); self.assertIn(OLD,self.local.values); self.assertFalse(self.api.rows); self.assertEqual(self.dns,[NEW,OLD])
    def test_hetzner_probe_failure_cleanup(self):
        r=self.finish(verify=lambda ip:False); self.assertEqual(r['status'],'rolled_back'); self.assertFalse(self.api.rows); self.assertEqual(self.dns,[])
    def test_hetzner_old_foreign_floating_remains_assigned(self):
        self.api.rows[1]=self.api.row(1,OTHER,123); self.config['managed_ip']=OTHER
        r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(self.api.rows[1]['server'],123)
        self.assertFalse(any(x[0]=='POST' and x[1]=='/floating_ips/1/actions/unassign' for x in self.api.events))
    def test_hetzner_guest_collision_not_deleted(self):
        self.local.values[NEW]=24; r=self.finish(); self.assertEqual(r['status'],'rolled_back'); self.assertEqual(self.local.values[NEW],24)
    def test_hetzner_resource_cap(self):
        self.config['max_monthly_floating_eur']=2; r=self.finish(); self.assertEqual(r['code'],'provider_floating_budget_exceeded'); self.assertEqual(self.allocations(),[])
    def test_hetzner_existing_primary_not_overwritten(self):
        self.config['allow_guest_network_changes']=False; r=self.finish(); self.assertEqual(r['status'],'failed'); self.assertEqual(self.local.events,[]); self.assertEqual(self.allocations(),[])
    def test_hetzner_label_mismatch_blocks_deletion(self):
        self.finish(); self.api.rows[2]['labels']['huarun-operation']='foreign'
        with self.assertRaisesRegex(p.ProviderError,'provider_delete_identity_mismatch'): self.provider()._delete_created({},NEW)
        self.assertIn(2,self.api.rows)
    def test_hetzner_guest_commands_are_fixed(self):
        calls=[]; values=[]
        def run(args,**kwargs):
            calls.append(args)
            if 'add' in args: values.append({'family':'inet','local':NEW,'prefixlen':32})
            if 'del' in args: values.clear()
            return SimpleNamespace(returncode=0,stdout=json.dumps([{'ifname':'eth0','addr_info':list(values)}]))
        local=p.LocalIPv4Alias('eth0',run=run); local.ensure(NEW); local.remove(NEW)
        self.assertTrue(any(x[1:]==['-4','address','add',NEW+'/32','dev','eth0'] for x in calls))
        self.assertFalse(any('restart' in x for call in calls for x in call))
        with self.assertRaises(p.ProviderError): p.LocalIPv4Alias('eth0;reboot',run=run)

    def test_hetzner_crash_before_dns_restores_candidate_alias(self):
        class Crash(BaseException): pass
        adapter=self.provider(); adapter.rotate('test',self.good_verify,self.good_dns)
        adapter=self.provider(); original=adapter._save
        def save(journal):
            original(journal)
            if journal['phase']=='commit_dns': raise Crash()
        adapter._save=save
        with self.assertRaises(Crash): adapter.rotate('test',self.good_verify,self.good_dns)
        self.local.values.pop(NEW); self.assertEqual(self.provider().restore_local_address()['status'],'pending')
        self.assertEqual(self.local.values[NEW],32)
        r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(self.dns,[NEW])
    def test_hetzner_action_failure_rolls_back_candidate(self):
        self.api.fail_action=True; r=self.finish(); self.assertEqual(r['status'],'rolled_back'); self.assertFalse(self.api.rows); self.assertEqual(self.local.values,{OLD:24})
    def test_hetzner_owned_old_cleanup_after_new_verified(self):
        incident='a'*64; self.api.rows[1]=self.api.row(1,OTHER,123,{'huarun-instance':'123','huarun-operation':incident[:32]})
        self.config.update(managed_ip=OTHER,cleanup_owned_old_ip=True); self.local.values[OTHER]=32
        adapter=self.provider(); ledger=adapter._ledger(); ledger['owned'][OTHER]={'id':1,'incident':incident,'alias_owned':True}; ledger['active_ip']=OTHER; adapter.store.write('ledger.json',ledger)
        r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertNotIn(1,self.api.rows); self.assertNotIn(OTHER,self.local.values); self.assertIn(NEW,self.local.values)

INSTANCE_UUID='11111111-1111-4111-8111-111111111111'
RESOURCE_UUID='22222222-2222-4222-8222-222222222222'
OLD_RESOURCE_UUID='33333333-3333-4333-8333-333333333333'

class FakeVultr:
    def __init__(self):
        self.rows={}; self.events=[]; self.lost_allocation=False; self.lost_action=False; self.hide_binding=0
    def row(self,ident,ip,target=None,label=''):
        return {'id':ident,'subnet':ip,'subnet_size':32,'ip_type':'v4','region':'sea','instance_id':target or '', 'label':label}
    def __call__(self,method,path,data=None):
        self.events.append((method,path,copy.deepcopy(data)))
        if path=='/instances/'+INSTANCE_UUID:
            return {'instance':{'id':INSTANCE_UUID,'region':'sea','status':'active','power_status':'running','main_ip':OLD}}
        if path=='/reserved-ips?per_page=100':
            rows=copy.deepcopy(list(self.rows.values()))
            if self.hide_binding:
                self.hide_binding-=1
                for row in rows:
                    if row['id']==RESOURCE_UUID: row['instance_id']=''
            return {'reserved_ips':rows,'meta':{'links':{'next':''}}}
        if path=='/reserved-ips' and method=='POST':
            assert data['region']=='sea' and data['ip_type']=='v4'
            self.rows[RESOURCE_UUID]=self.row(RESOURCE_UUID,NEW,label=data['label'])
            if self.lost_allocation: raise RuntimeError('token=secret')
            return {'reserved_ip':copy.deepcopy(self.rows[RESOURCE_UUID])}
        bits=path.split('/'); ident=bits[2]
        if method=='DELETE': self.rows.pop(ident,None); return {}
        if method=='POST' and len(bits)==4:
            self.rows[ident]['instance_id']=data['instance_id'] if bits[3]=='attach' else ''
            if self.lost_action:
                self.lost_action=False; raise RuntimeError('provider token secret')
            return {}
        raise AssertionError((method,path,data))

class VultrTests(ProviderTests):
    def setUp(self):
        super().setUp(); self.api=FakeVultr(); self.local=FakeLocal()
        self.config={'kind':'vultr','instance_id':INSTANCE_UUID,'region':'sea','interface':'eth0','auto_rotate':True,
                     'allow_reserved_ip_allocation':True,'allow_guest_network_changes':True}
    def provider(self): return p.VultrReservedRotator(self.config,self.tmp.name,request=self.api,clock=self.clock,local=self.local)
    def allocations(self): return [x for x in self.api.events if x[:2]==('POST','/reserved-ips')]
    def test_vultr_allocate_attach_verify_dns_and_restart(self):
        r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(self.provider().current_ip(),NEW)
        self.assertEqual(self.local.values[OLD],24); self.assertEqual(self.api.rows[RESOURCE_UUID]['instance_id'],INSTANCE_UUID)
        self.local.values.pop(NEW); self.provider().restore_local_address(); self.assertEqual(self.local.values[NEW],32)
        self.assertEqual(len(self.allocations()),1)
    def test_vultr_old_foreign_reserved_is_preserved(self):
        self.api.rows[OLD_RESOURCE_UUID]=self.api.row(OLD_RESOURCE_UUID,OTHER,INSTANCE_UUID)
        self.config['managed_ip']=OTHER; r=self.finish(); self.assertEqual(r['status'],'rotated')
        self.assertEqual(self.api.rows[OLD_RESOURCE_UUID]['instance_id'],INSTANCE_UUID)
        self.assertFalse(any(x[0]=='DELETE' for x in self.api.events))
    def test_vultr_lost_allocation_reconciled_by_label(self):
        self.api.lost_allocation=True; r=self.finish(); self.assertEqual(r['status'],'rotated'); self.assertEqual(len(self.allocations()),1)
    def test_vultr_lost_attach_response_no_duplicate(self):
        self.api.lost_action=True; r=self.finish(); self.assertEqual(r['status'],'rotated')
        self.assertEqual(len([x for x in self.api.events if x[0]=='POST' and x[1].endswith('/attach')]),1)
    def test_vultr_failed_probe_removes_only_candidate(self):
        r=self.finish(verify=lambda ip:False); self.assertEqual(r['status'],'rolled_back'); self.assertFalse(self.api.rows)
        self.assertEqual(self.local.values,{OLD:24}); self.assertEqual(self.dns,[])
    def test_vultr_partial_dns_failure_restores_dns(self):
        def dns(ip): self.dns.append(ip); return ip==OLD
        r=self.finish(dns=dns); self.assertEqual(r['status'],'rolled_back'); self.assertEqual(self.dns,[NEW,OLD]); self.assertFalse(self.api.rows)
    def test_vultr_budget_blocks_before_allocation(self):
        self.config['max_monthly_reserved_usd']=2
        r=self.finish(); self.assertEqual(r['code'],'provider_reserved_budget_exceeded'); self.assertFalse(self.allocations())
    def test_vultr_full_inventory_required(self):
        api=self.api
        def paginated(method,path,data=None):
            result=api(method,path,data)
            if path.startswith('/reserved-ips?'): result['meta']['links']['next']='https://api.vultr.com/v2/reserved-ips?cursor=x'
            return result
        self.api=paginated; r=self.finish(); self.assertEqual(r['code'],'provider_ip_list_limit'); self.assertFalse(any(x[0]=='POST' for x in api.events))
    def test_vultr_endpoint_excludes_reboot_and_baremetal(self):
        api=p.VultrAPI('fake-secret-token')
        for method,path in [('POST','/instances/'+INSTANCE_UUID+'/reboot'),('GET','/bare-metals/'+INSTANCE_UUID),('DELETE','/instances/'+INSTANCE_UUID)]:
            with self.assertRaisesRegex(p.ProviderError,'provider_api_path_invalid'): api(method,path)

# Avoid running DigitalOcean-only cases against Hetzner through inheritance.
def load_tests(loader, tests, pattern):
    suite=unittest.TestSuite(loader.loadTestsFromTestCase(ProviderTests))
    suite.addTests(HetznerTests(name) for name in HetznerTests.__dict__ if name.startswith('test_'))
    suite.addTests(VultrTests(name) for name in VultrTests.__dict__ if name.startswith('test_'))
    return suite

if __name__=='__main__': unittest.main()
