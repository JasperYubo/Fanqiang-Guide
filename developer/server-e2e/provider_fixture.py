"""Container-local test ACME CA and synthetic DeepSeek model-list endpoint.

The production installer and hash-pinned acme.sh run unmodified. The fake CA
consumes a real CSR and verifies the local HTTP-01 challenge before issuing.
No production credential or public certificate is used.
"""
import base64,hashlib,hmac,http.server,json,pathlib,secrets,subprocess,sys,urllib.request
from urllib.parse import urlsplit,parse_qs
ROOT=pathlib.Path('/opt/e2e-state'); ROOT.mkdir(mode=0o700,exist_ok=True)
BASE='https://acme-v02.api.letsencrypt.org'
records={}
events=[]
control={'telegram_fail':False,'probe_reachable':True,'probe_candidate_reachable':None,'fail_order_domain':None}
PROBE_KEY='synthetic-release-probe-key-32-bytes-minimum'
CF_ACCOUNT='1'*32
CF_ZONE='2'*32
state={'challenged':False,'finalized':False,'domain':None}
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','40','-keyout',str(ROOT/'ca.key'),'-out',str(ROOT/'ca.crt'),'-subj','/CN=HuaRun isolated release test CA'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
(ROOT/'ca.key').chmod(0o600)
pathlib.Path('/usr/local/share/ca-certificates/huarun-e2e.crt').write_bytes((ROOT/'ca.crt').read_bytes())
subprocess.run(['update-ca-certificates'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def decode(value):
    return base64.urlsafe_b64decode(value+'='*((-len(value))%4))
def order():
    return {'status':'valid' if state['finalized'] else ('ready' if state['challenged'] else 'pending'),'expires':'2030-01-01T00:00:00Z','identifiers':[{'type':'dns','value':state['domain']}],'authorizations':[BASE+'/authz/1'],'finalize':BASE+'/finalize/1',**({'certificate':BASE+'/cert/1'} if state['finalized'] else {})}
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,value,location=None):
        raw=value if isinstance(value,bytes) else json.dumps(value,separators=(',',':')).encode()
        self.send_response(status);self.send_header('Content-Type','application/pem-certificate-chain' if isinstance(value,bytes) else 'application/json')
        self.send_header('Content-Length',str(len(raw)));self.send_header('Replay-Nonce',secrets.token_urlsafe(24));self.send_header('Link','<'+BASE+'/directory>;rel="index"')
        if location:self.send_header('Location',location)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(raw)
    def cf(self):
        path=urlsplit(self.path).path
        base='/cf/zones/'+CF_ZONE+'/dns_records'
        if path=='/cf/accounts/'+CF_ACCOUNT+'/tokens/verify':return self.reply(200,{'success':True,'result':{'status':'active'}})
        if path=='/cf/zones/'+CF_ZONE:return self.reply(200,{'success':True,'result':{'id':CF_ZONE,'status':'active','name':'release.invalid','account':{'id':CF_ACCOUNT}}})
        if path.startswith(base):
            ident=path[len(base):].strip('/')
            if self.command=='GET':
                name=parse_qs(urlsplit(self.path).query).get('name',[None])[0]
                value=records.get(ident) if ident else [r for r in records.values() if not name or r['name']==name]
            elif self.command in ('POST','PATCH'):
                value=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                ident=ident or secrets.token_hex(16)
                value={**records.get(ident,{}),**value,'id':ident};records[ident]=value
                events.append({'kind':'dns_write','method':self.command,'type':value['type'],'name':value['name'],'content':value['content']})
            elif self.command=='DELETE':
                previous=records.pop(ident,None);value={'id':ident}
                events.append({'kind':'dns_delete','type':previous.get('type') if previous else None,'name':previous.get('name') if previous else None})
            return self.reply(200,{'success':True,'result':value,'result_info':{'total_pages':1}})
        return self.reply(404,{'success':False})
    def do_PATCH(self):return self.cf()
    def do_DELETE(self):return self.cf()
    def do_HEAD(self):self.reply(200,{})
    def do_GET(self):
        if self.path.startswith('/cf/'):return self.cf()
        if self.path=='/fixture-state':return self.reply(200,{'records':list(records.values()),'events':events,'control':control})
        if self.path.startswith('/dns-query'):
            query=parse_qs(urlsplit(self.path).query);name=query.get('name',[''])[0].rstrip('.')
            return self.reply(200,{'Status':0,'Answer':[{'name':r['name']+'.','type':16,'TTL':120,'data':r['content']} for r in records.values() if r['type']=='TXT' and r['name']==name]})
        path=self.path.split('?')[0]
        if path=='/deepseek/models':return self.reply(200,{'object':'list','data':[{'id':'deepseek-flash','object':'model'}]})
        if path=='/directory':return self.reply(200,{'newNonce':BASE+'/new-nonce','newAccount':BASE+'/new-account','newOrder':BASE+'/new-order','revokeCert':BASE+'/revoke-cert','keyChange':BASE+'/key-change','meta':{'termsOfService':BASE+'/terms','externalAccountRequired':False}})
        if path=='/new-nonce':return self.reply(200,{})
        self.reply(404,{'type':'urn:ietf:params:acme:error:malformed','detail':'unknown fixture route'})
    def do_POST(self):
        if self.path.startswith('/cf/'):return self.cf()
        if self.path=='/fixture-control':
            value=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            if set(value)-set(control):return self.reply(400,{'error':'unknown control'})
            control.update(value);return self.reply(200,{'ok':True})
        if self.path=='/telegram/sendMessage':
            payload=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            if control['telegram_fail']:
                events.append({'kind':'notification_failure'})
                return self.reply(503,{'ok':False,'description':'simulated transport outage'})
            events.append({'kind':'notification_delivered','text':payload.get('text','')})
            return self.reply(200,{'ok':True,'result':{'message_id':len(events)}})
        if self.path in ('/probe/region-a','/probe/region-b'):
            payload=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            def sign(value):return hmac.new(PROBE_KEY.encode(),(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(self.headers.get('X-HuaRun-Signature',''),sign(payload)):return self.reply(403,{'error':'probe signature mismatch'})
            reachable=control['probe_candidate_reachable'] if payload.get('connect_ip') and control['probe_candidate_reachable'] is not None else control['probe_reachable']
            result={**payload,'tcp_ok':reachable,'tls_ok':reachable,'websocket_ok':reachable}
            return self.reply(200,{'result':result,'signature':sign(result)})
        try:
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            payload=json.loads(decode(body['payload'])) if body.get('payload') else {}
            path=self.path.split('?')[0]
            protected=json.loads(decode(body['protected']))
            if 'jwk' in protected:state['thumbprint']=base64.urlsafe_b64encode(hashlib.sha256(json.dumps(protected['jwk'],sort_keys=True,separators=(',',':')).encode()).digest()).decode().rstrip('=')
            if path=='/new-account':return self.reply(201,{'status':'valid','orders':BASE+'/orders/1'},BASE+'/account/1')
            if path=='/new-order':
                if payload['identifiers'][0]['value']==control['fail_order_domain']:return self.reply(400,{'type':'urn:ietf:params:acme:error:rejectedIdentifier','detail':'deliberate isolated migration failure'})
                state.update(domain=payload['identifiers'][0]['value'],challenged=False,finalized=False)
                # Exercise valid base64url DNS TXT values beginning with '-' on every run.
                for suffix in range(4096):
                    token='huarun-release-dns-token-'+str(suffix)
                    value=base64.urlsafe_b64encode(hashlib.sha256((token+'.'+state['thumbprint']).encode()).digest()).decode().rstrip('=')
                    if value.startswith('-'):
                        state['dns_token']=token;break
                else:raise ValueError('fixture_challenge_selection_failed')
                return self.reply(201,order(),BASE+'/order/1')
            if path=='/authz/1':
                return self.reply(200,{'identifier':{'type':'dns','value':state['domain']},'status':'valid' if state['challenged'] else 'pending','challenges':[{'type':'http-01','url':BASE+'/challenge/1','status':'valid' if state['challenged'] else 'pending','token':'huarun-release-test-token'},{'type':'dns-01','url':BASE+'/challenge/dns','status':'valid' if state['challenged'] else 'pending','token':state['dns_token']}]})
            if path=='/challenge/dns':
                expected=base64.urlsafe_b64encode(hashlib.sha256((state['dns_token']+'.'+state['thumbprint']).encode()).digest()).decode().rstrip('=')
                if not any(r['type']=='TXT' and r['name']=='_acme-challenge.'+state['domain'] and r['content']==expected for r in records.values()):raise ValueError('dns01_token_missing')
                state['challenged']=True
                events.append({'kind':'dns01_verified','domain':state['domain']})
                return self.reply(200,{'type':'dns-01','url':BASE+'/challenge/dns','status':'valid','token':state['dns_token']})
            if path=='/challenge/1':
                # The actual acme.sh standalone server must serve the token.
                with urllib.request.urlopen('http://127.0.0.1/.well-known/acme-challenge/huarun-release-test-token',timeout=5) as response: token=response.read()
                if not token.startswith(b'huarun-release-test-token.'):raise ValueError('http01_token_missing')
                state['challenged']=True
                return self.reply(200,{'type':'http-01','url':BASE+'/challenge/1','status':'valid','token':'huarun-release-test-token'})
            if path=='/finalize/1':
                if not state['challenged']:raise ValueError('http01_not_validated')
                (ROOT/'csr.der').write_bytes(decode(payload['csr']))
                subprocess.run(['openssl','req','-inform','DER','-in',str(ROOT/'csr.der'),'-out',str(ROOT/'csr.pem')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                subprocess.run(['openssl','x509','-req','-in',str(ROOT/'csr.pem'),'-CA',str(ROOT/'ca.crt'),'-CAkey',str(ROOT/'ca.key'),'-CAcreateserial','-out',str(ROOT/'issued.crt'),'-days','30','-sha256','-copy_extensions','copy'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                state['finalized']=True
                events.append({'kind':'certificate_issued','domain':state['domain']})
                return self.reply(200,order(),BASE+'/order/1')
            if path=='/order/1':return self.reply(200,order())
            if path=='/cert/1' and state['finalized']:return self.reply(200,(ROOT/'issued.crt').read_bytes()+(ROOT/'ca.crt').read_bytes())
            self.reply(404,{'detail':'unknown fixture route'})
        except Exception as error:
            print('provider_fixture_error:'+str(error) if isinstance(error,ValueError) and str(error) in {'dns01_token_missing','http01_token_missing','http01_not_validated','fixture_challenge_selection_failed'} else 'provider_fixture_error:'+type(error).__name__,flush=True)
            self.reply(400,{'type':'urn:ietf:params:acme:error:malformed','detail':'fixture request failed'})
http.server.ThreadingHTTPServer(('127.0.0.1',14000),Handler).serve_forever()
