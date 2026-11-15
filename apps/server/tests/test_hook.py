import importlib.util
import json
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'assistant/hook.py'
spec = importlib.util.spec_from_file_location('huarun_hook', MODULE)
hook = importlib.util.module_from_spec(spec); spec.loader.exec_module(hook)

class Client:
    def __init__(self, docs=True): self.queries=[]; self.searches=[]; self.docs=docs
    def query_mcp(self, query):
        self.queries.append(query)
        return {'mcp_attempted':True,'query_id':'receipt','documents':[{'text':'reference'}] if self.docs else []}
    def search_deepseek(self, query, reason, query_id=None):
        assert query_id=='receipt'
        self.searches.append((query,reason))
        return {'items':[{'url':'https://example.com','title':'reference'}],'errors':[]}

class HookTests(unittest.TestCase):
    def setUp(self):
        self.client=Client(); self.checks=[]
        self.engine=hook.HookEngine(lambda:self.client,self.check,audit_dir=False)
    def check(self, command):
        self.checks.append(command)
        return {'exit_code':0,'data':{'all_ok':True} if command=='doctor' else {'xray':'active','nginx':'active','port443':True,'renew_cron':True}}
    def start(self, turn='one', question='证书错误'):
        return self.engine.dispatch('hook.before_llm',{'meta':{'TurnID':turn},'messages':[{'role':'system','content':'身份与权限保留'}, {'role':'user','content':question}], 'tools':[]})
    def params(self, command,turn='one',**extra):
        return {'meta':{'TurnID':turn},'tool':'exec','arguments':{'action':'run','command':command,**extra}}
    def test_every_turn_fetches_mcp_once_before_llm_and_preserves_request(self):
        first=self.start();self.start();self.start('two')
        self.assertEqual(len(self.client.queries),2)
        self.assertEqual(first['action'],'modify');self.assertEqual(first['request']['tools'],[])
        self.assertEqual(first['request']['messages'][0],{'role':'system','content':'身份与权限保留'})
        self.assertEqual(first['request']['messages'][-1]['role'],'user')
        self.assertIn('HUARUN_RESEARCH_CONTEXT',first['request']['messages'][-1]['content'])
    def test_plain_command_rejected_without_current_turn_mcp(self):
        self.assertFalse(self.engine.approve(self.params('huarun fix'))['approved'])
        self.start();self.assertFalse(self.engine.approve(self.params('huarun fix',turn='unresearched'))['approved'])
    def test_search_requires_actual_mcp_and_explicit_gap(self):
        command="huarun research-web --query 'Xray TLS issue' --reason '本站缺少该版本错误的说明'"
        result=self.engine.before_tool(self.params(command));self.assertTrue(result['result']['is_error'])
        self.start();result=self.engine.before_tool(self.params(command))
        self.assertFalse(result['result']['is_error']);self.assertEqual(len(self.client.searches),1)
        self.assertFalse(self.engine.approve(self.params(command))['approved'])
    def test_search_injection_is_not_executed(self):
        self.start()
        for command in ["huarun research-web --query 'tls' --reason 'lack docs' ; id", "huarun research-web --query 'tls' --reason ''"]:
            self.assertTrue(self.engine.before_tool(self.params(command))['result']['is_error'])
        self.assertEqual(self.client.searches,[])
    def test_mcp_failure_keeps_readonly_diagnostics_and_requires_web_for_mutation(self):
        self.client.docs=False;self.start()
        self.assertTrue(self.engine.approve(self.params('huarun doctor --json'))['approved'])
        self.assertFalse(self.engine.approve(self.params('huarun fix'))['approved'])
        self.engine.before_tool(self.params("huarun research-web --query 'TLS' --reason '本站MCP不可用需要官方资料'"))
        self.assertTrue(self.engine.approve(self.params('huarun fix'))['approved'])
    def test_mutation_always_rechecks_and_preserves_pico_result_envelope(self):
        self.start();p=self.params('huarun fix')
        self.assertTrue(self.engine.approve(p)['approved'])
        self.assertFalse(self.engine.approve(p)['approved'])
        p['result']={'for_llm':'修复命令返回','is_error':False}
        result=self.engine.after_tool(p)
        self.assertEqual(self.checks,['doctor','status'])
        self.assertEqual(result['result']['meta']['TurnID'],'one')
        self.assertIn('client_connectivity',result['result']['result']['for_llm'])
        self.assertFalse(result['result']['result']['is_error'])
    def test_status_failure_or_invalid_json_never_reports_pass(self):
        for data in [{'error':'non_json_check_output'}, {'xray':False,'nginx':False,'port443':False,'renew_cron':False}]:
            engine=hook.HookEngine(lambda:self.client,lambda c:{'exit_code':0,'data':{'all_ok':True} if c=='doctor' else data},audit_dir=False)
            state={'pending_verification':True}
            self.assertFalse(engine.verify('test',state)['server_checks_passed'])
    def test_pending_verification_recovers_before_next_llm(self):
        self.start();self.engine.approve(self.params('huarun fix'))
        output=self.start()
        self.assertEqual(self.checks,['doctor','status'])
        self.assertIn('server_checks_passed',output['request']['messages'][-1]['content'])
    def test_final_answer_cannot_skip_pending_verification(self):
        self.start();self.engine.approve(self.params('huarun fix'))
        result=self.engine.dispatch('hook.after_llm',{'meta':{'TurnID':'one'},'response':{'content':'已修好'}})
        self.assertEqual(result['action'],'abort_turn');self.assertEqual(self.checks,['doctor','status'])
    def test_old_dangerous_commands_remain_blocked(self):
        self.start()
        for command in ['bash -c id','huarun uninstall --yes','huarun whitelist reset','huarun fix; id','huarun fix\nwhoami']:
            self.assertFalse(self.engine.approve(self.params(command))['approved'])
    def test_known_secrets_not_in_query_or_context(self):
        r=self.start(question='key=sk-secretABC123 vmess://connection-secret')
        retrieved=json.dumps(self.client.queries)+r['request']['messages'][-1]['content']
        self.assertNotIn('sk-secretABC123',retrieved);self.assertNotIn('connection-secret',retrieved)

if __name__=='__main__':unittest.main()
