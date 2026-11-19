"""Version 1.4 requires installed generic-provider evidence and state preservation."""
import copy,hashlib,importlib.util,json,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_release_acceptance import a,accepted_network_fixture

def accepted_generic_fixture():
    report,expected,previous=accepted_network_fixture()
    report['candidate_version']=expected['candidate_version']='1.4.0'
    report['fresh_install']['installed_version']='1.4.0'
    report['network_fault_tests']['suites']=list(a.GENERIC_FAULT_SUITES)
    cases=[]
    for number,shape in enumerate(('json_bearer','query_key')):
        cases.append({'name':'qa-vps-'+str(number)*12,'api_shape':shape,'document_sha256':'d'*64,'profile_sha256':'e'*64,'read_requests':2,'mutation_requests':1,'passed':True,'dns_readback_verified':True,'read_before_mutation':True})
    report['fresh_install']['generic_provider_features']={**{k:True for k in a.GENERIC_PROVIDER_CHECKS},'scope':'installed_runtime_http_fixtures','live_cloud_rotation':False,'providers':cases}
    entries={'a'*64:{'kind':'directory','mode':0o700,'uid':0,'gid':0,'sha256':None},'a'*64+'/profile.json':{'kind':'file','mode':0o600,'uid':0,'gid':0,'sha256':'f'*64}}
    tree={'exists':True,'sha256':hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'mode':0o700,'uid':0,'gid':0,'entries':entries}
    for case in report['upgrades']:
        case['to_version']='1.4.0';case['preserved']['generic_provider_state']=True
        for side in ('before','after'):case['preservation_checks'][side]['generic_provider_state']=copy.deepcopy(tree)
    uc=report['unconfigured_upgrade'];uc['to_version']='1.4.0';uc['generic_provider_state_absent']=True;uc['preserved']['generic_provider_state']=True
    for side in ('before','after'):uc['preservation_checks'][side]['generic_provider_state']={'exists':False,'sha256':None,'mode':None,'uid':None,'gid':None}
    return report,expected,previous

class GenericReleaseAcceptanceTests(unittest.TestCase):
    def setUp(self):self.report,self.expected,self.previous=accepted_generic_fixture()
    def validate(self):return a.validate_report(self.report,self.expected,self.previous)
    def test_complete_generic_evidence_passes(self):
        summary=self.validate();self.assertEqual(summary['generic_provider_features'],list(a.GENERIC_PROVIDER_CHECKS));self.assertIn('generic_provider_state',summary['preserved'])
    def test_every_generic_observation_is_mandatory(self):
        for key in a.GENERIC_PROVIDER_CHECKS:
            for value in (False,None,1,'true'):
                with self.subTest(key=key,value=value):
                    self.setUp();self.report['fresh_install']['generic_provider_features'][key]=value
                    with self.assertRaises(a.AcceptanceError):self.validate()
    def test_generic_feature_report_cannot_be_omitted(self):
        del self.report['fresh_install']['generic_provider_features']
        with self.assertRaises(a.AcceptanceError):self.validate()
    def test_generic_fault_suites_must_be_executed(self):
        self.report['network_fault_tests']['suites']=list(a.NETWORK_FAULT_SUITES)
        with self.assertRaisesRegex(a.AcceptanceError,'fault_suites'):self.validate()
    def test_fixture_evidence_must_not_claim_real_cloud_rotation(self):
        self.report['fresh_install']['generic_provider_features']['live_cloud_rotation']=True
        with self.assertRaisesRegex(a.AcceptanceError,'scope'):self.validate()
    def test_two_distinct_unknown_providers_and_api_shapes_required(self):
        for change in ('missing','same-name','known-name','same-shape','wrong-shape','missing-digest','no-read','no-mutation','mutation-before-read'):
            with self.subTest(change=change):
                self.setUp();p=self.report['fresh_install']['generic_provider_features']['providers']
                if change=='missing':p.pop()
                elif change=='same-name':p[1]['name']=p[0]['name']
                elif change=='known-name':p[0]['name']='digitalocean'
                elif change=='same-shape':p[1]['api_shape']=p[0]['api_shape']
                elif change=='wrong-shape':p[1]['api_shape']='unknown'
                elif change=='missing-digest':p[0].pop('document_sha256')
                elif change=='no-read':p[0]['read_requests']=0
                elif change=='no-mutation':p[0]['mutation_requests']=0
                else:p[0]['read_before_mutation']=False
                with self.assertRaises(a.AcceptanceError):self.validate()
    def test_entire_generic_state_tree_is_preserved_and_bound(self):
        for change in ('missing','false','file-changed','mode-changed','owner-changed','digest-claimed','unsafe-path','exposed-secret','empty'):
            with self.subTest(change=change):
                self.setUp();case=self.report['upgrades'][0];before=case['preservation_checks']['before']['generic_provider_state'];after=case['preservation_checks']['after']['generic_provider_state'];file=after['entries']['a'*64+'/profile.json']
                if change=='missing':case['preservation_checks']['after'].pop('generic_provider_state')
                elif change=='false':case['preserved']['generic_provider_state']=False
                elif change=='file-changed':file['sha256']='a'*64
                elif change=='mode-changed':file['mode']=0o400
                elif change=='owner-changed':file['uid']=1
                elif change=='digest-claimed':before['sha256']=after['sha256']='b'*64
                elif change=='unsafe-path':before['entries']['../escape']=copy.deepcopy(file)
                elif change=='exposed-secret':before['entries']['a'*64+'/profile.json']['mode']=0o644
                else:before['entries']={}
                with self.assertRaises(a.AcceptanceError):self.validate()
    def test_unconfigured_upgrade_keeps_generic_state_absent(self):
        for value in (False,None,1):
            with self.subTest(value=value):
                self.setUp();self.report['unconfigured_upgrade']['generic_provider_state_absent']=value
                with self.assertRaises(a.AcceptanceError):self.validate()
        self.setUp();self.report['unconfigured_upgrade']['preservation_checks']['after']['generic_provider_state']['exists']=True
        with self.assertRaises(a.AcceptanceError):self.validate()
    def test_historical_13_report_remains_valid(self):
        report,expected,previous=accepted_network_fixture()
        result=a.validate_report(report,expected,previous)
        self.assertNotIn('generic_provider_features',result)
        self.assertNotIn('generic_provider_state',result['preserved'])

if __name__=='__main__':unittest.main()
