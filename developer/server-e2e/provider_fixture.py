"""Container-local test ACME CA and synthetic DeepSeek model-list endpoint.

The production installer and hash-pinned acme.sh run unmodified. The fake CA
consumes a real CSR and verifies the local HTTP-01 challenge before issuing.
No production credential or public certificate is used.
"""
import base64,http.server,json,pathlib,secrets,subprocess,sys,urllib.request
ROOT=pathlib.Path('/opt/e2e-state'); ROOT.mkdir(mode=0o700,exist_ok=True)
BASE='https://acme-v02.api.letsencrypt.org'
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
    def do_HEAD(self):self.reply(200,{})
    def do_GET(self):
        path=self.path.split('?')[0]
        if path=='/deepseek/models':return self.reply(200,{'object':'list','data':[{'id':'deepseek-flash','object':'model'}]})
        if path=='/directory':return self.reply(200,{'newNonce':BASE+'/new-nonce','newAccount':BASE+'/new-account','newOrder':BASE+'/new-order','revokeCert':BASE+'/revoke-cert','keyChange':BASE+'/key-change','meta':{'termsOfService':BASE+'/terms','externalAccountRequired':False}})
        if path=='/new-nonce':return self.reply(200,{})
        self.reply(404,{'type':'urn:ietf:params:acme:error:malformed','detail':'unknown fixture route'})
    def do_POST(self):
        try:
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
            payload=json.loads(decode(body['payload'])) if body.get('payload') else {}
            path=self.path.split('?')[0]
            if path=='/new-account':return self.reply(201,{'status':'valid','orders':BASE+'/orders/1'},BASE+'/account/1')
            if path=='/new-order':
                state.update(domain=payload['identifiers'][0]['value'],challenged=False,finalized=False)
                return self.reply(201,order(),BASE+'/order/1')
            if path=='/authz/1':
                return self.reply(200,{'identifier':{'type':'dns','value':state['domain']},'status':'valid' if state['challenged'] else 'pending','challenges':[{'type':'http-01','url':BASE+'/challenge/1','status':'valid' if state['challenged'] else 'pending','token':'huarun-release-test-token'}]})
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
                return self.reply(200,order(),BASE+'/order/1')
            if path=='/order/1':return self.reply(200,order())
            if path=='/cert/1' and state['finalized']:return self.reply(200,(ROOT/'issued.crt').read_bytes()+(ROOT/'ca.crt').read_bytes())
            self.reply(404,{'detail':'unknown fixture route'})
        except Exception as error:
            print('provider_fixture_error:'+type(error).__name__,flush=True)
            self.reply(400,{'type':'urn:ietf:params:acme:error:malformed','detail':'fixture request failed'})
http.server.ThreadingHTTPServer(('127.0.0.1',14000),Handler).serve_forever()
