"""Vendor-independent, declarative HTTP IP recovery. No generated code is executed."""
from __future__ import annotations
import pathlib,base64,copy,hashlib,hmac,http.client,ipaddress,json,math,re,secrets,socket,ssl,time
from urllib.parse import urlsplit,urlencode,quote,parse_qsl
from ip_provider import ProviderError,_Store,_ipv4,_safe_id
MAX_BYTES=2*1024*1024
VARIABLE=re.compile(r'\{([a-z][a-z0-9_]{0,63})\}')
SECRET=re.compile(r'\{secret:([a-z][a-z0-9_]{0,63})\}')
NAME=re.compile(r'[a-z][a-z0-9_]{0,63}')
FORBIDDEN=re.compile(r'(?i)(?:^|[/_\W])(?:delete|destroy|terminate|rebuild|reinstall|resize|poweroff|shutdown|stop|reboot|suspend|password|sshkeys?)')
RESERVED={'instance_id','region','incident','old_ip','method','path','query','body','body_sha256','timestamp','date','nonce','signature'}

class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip,timeout):
        super().__init__(host,timeout=timeout,context=ssl.create_default_context());self._ip=ip
    def connect(self):
        self.sock=socket.create_connection((self._ip,443),self.timeout)
        self.sock=self._context.wrap_socket(self.sock,server_hostname=self.host)

def public_url(url):
    if not isinstance(url,str) or len(url)>4096 or any(c in url for c in ('\\','\r','\n')):raise ProviderError('provider_url_invalid')
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443) or p.fragment:raise ProviderError('provider_https_required')
    try:
        ipaddress.ip_address(p.hostname)
    except ValueError:pass
    else:raise ProviderError('provider_hostname_required')
    if not re.fullmatch(r'[a-z0-9.-]+',p.hostname) or '.' not in p.hostname:raise ProviderError('provider_hostname_invalid')
    return p

def public_fetch(url,method='GET',payload=None,headers=None,limit=MAX_BYTES,include_status=False,timeout=20):
    p=public_url(url)
    if type(timeout) not in (int,float) or not 1<=timeout<=90:raise ProviderError('provider_timeout_invalid')
    deadline=time.monotonic()+timeout
    try:
        ips=sorted({row[4][0] for row in socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)})
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):raise ProviderError('provider_private_endpoint_rejected')
        connection=_PinnedHTTPS(p.hostname,ips[0],timeout)
        supplied={'User-Agent':'HuaRun-Provider-Discovery/1.0',**(headers or {})}
        raw=None if payload is None else (urlencode(payload).encode() if supplied.get('Content-Type')=='application/x-www-form-urlencoded' else json.dumps(payload,separators=(',',':'),sort_keys=True).encode())
        connection.request(method,p.path+('?' +p.query if p.query else ''),body=raw,headers=supplied)
        connection.sock.settimeout(max(.1,deadline-time.monotonic()))
        response=connection.getresponse();chunks=[];size=0
        while size<=limit:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError()
            if connection.sock is not None:connection.sock.settimeout(remaining)
            chunk=response.read(min(65536,limit+1-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
        body=b''.join(chunks)
        if response.status<200 or response.status>=300:raise ProviderError('provider_http_'+str(response.status))
        if len(body)>limit:raise ProviderError('provider_response_too_large')
        return (body,response.getheader('Content-Type',''),response.status) if include_status else (body,response.getheader('Content-Type',''))
    except ProviderError:raise
    except Exception:raise ProviderError('provider_network_unavailable') from None
    finally:
        if 'connection' in locals():connection.close()

class _ResponseDict(dict):pass
class _ResponseList(list):pass

def api_request(method,url,payload,headers,timeout=20):
    raw,_,status=public_fetch(url,method,payload,headers,include_status=True,timeout=timeout)
    try:value=json.loads(raw) if raw else {}
    except (ValueError,UnicodeError):raise ProviderError('provider_invalid_json') from None
    if not isinstance(value,(dict,list)):raise ProviderError('provider_invalid_response')
    result=_ResponseDict(value) if isinstance(value,dict) else _ResponseList(value);result.http_status=status
    return result

def pointer(value,path):
    if not isinstance(path,str) or not path.startswith('/') or len(path)>300:raise ProviderError('provider_selector_invalid')
    try:
        for token in path[1:].split('/'):
            token=token.replace('~1','/').replace('~0','~')
            value=value[int(token)] if isinstance(value,list) and token.isdigit() else value[token]
        return value
    except (KeyError,IndexError,TypeError,ValueError):raise ProviderError('provider_response_selector_missing') from None

def render(value,variables,path=False):
    if isinstance(value,str):
        if SECRET.search(value):raise ProviderError('provider_secret_outside_auth')
        def replacement(m):
            if m[1] not in variables:raise ProviderError('provider_variable_missing')
            s=str(variables[m[1]])
            return quote(s,safe='') if path else s
        if '{' in VARIABLE.sub('',value) or '}' in VARIABLE.sub('',value):raise ProviderError('provider_template_invalid')
        return VARIABLE.sub(replacement,value)
    if isinstance(value,list):return [render(x,variables) for x in value]
    if isinstance(value,dict):return {k:render(v,variables) for k,v in value.items()}
    if value is None or type(value) in (bool,int,float):return value
    raise ProviderError('provider_template_invalid')

def _refs(value):return set(VARIABLE.findall(json.dumps(value)))
def _normalize_path(path):return re.sub(r'\{[^{}]+\}','{}',path)

def validate_profile(value,documents,*,official_url=None,approved_api_origins=()):
    """Evidence binds operation paths to fetched official pages, never to model claims."""
    if not isinstance(value,dict) or value.get('schema_version')!=1:raise ProviderError('provider_manifest_schema_invalid')
    p=copy.deepcopy(value);origin=p.get('origin');url=public_url(origin)
    if url.path not in ('','/') or url.query:raise ProviderError('provider_origin_invalid')
    p['origin']=origin.rstrip('/')
    docs={d['url']:d['text'] for d in documents}
    anchor=public_url(official_url or documents[0]['url']).hostname
    if anchor.startswith('www.'):anchor=anchor[4:]
    approved=set()
    for value in approved_api_origins:
        parsed=public_url(value)
        if parsed.path not in ('','/') or parsed.query:raise ProviderError('provider_approved_origin_invalid')
        approved.add(value.rstrip('/'))
    if not (url.hostname==anchor or url.hostname.endswith('.'+anchor) or p['origin'] in approved):raise ProviderError('provider_api_origin_requires_owner_scope')
    if not docs or not any(p['origin'] in text for text in docs.values()):raise ProviderError('provider_api_origin_not_documented')
    auth=p.get('auth',{})
    if auth.get('type') not in ('none','bearer','header','query','basic','hmac'):raise ProviderError('provider_auth_contract_unsupported')
    if auth.get('type')!='none':
        source=docs.get(auth.get('source'),'');quote_text=auth.get('quote')
        if not isinstance(quote_text,str) or len(quote_text)<8 or quote_text not in source:raise ProviderError('provider_auth_evidence_missing')
    required=['username','password'] if auth.get('type')=='basic' else ['credential'] if auth.get('type')!='none' else []
    if any(not NAME.fullmatch(str(auth.get(name,''))) for name in required):raise ProviderError('provider_credential_reference_invalid')
    for name in ('credential','username','password'):
        if name in auth and not NAME.fullmatch(str(auth[name])):raise ProviderError('provider_credential_reference_invalid')
    if any(not isinstance(auth.get(k,''),str) or '\r' in auth.get(k,'') or '\n' in auth.get(k,'') for k in ('prefix','key_prefix')):raise ProviderError('provider_auth_template_invalid')
    if auth.get('type')=='header' and str(auth.get('name','')).lower() in ('host','cookie','proxy-authorization','content-length'):raise ProviderError('provider_auth_header_not_allowed')
    if auth.get('type') in ('header','query') and not re.fullmatch('[A-Za-z0-9_-]{1,64}',str(auth.get('name',''))):raise ProviderError('provider_auth_field_invalid')
    if any(not isinstance(auth.get(k,{}),dict) or len(auth.get(k,{}))>20 for k in ('headers','query')):raise ProviderError('provider_auth_template_invalid')
    if any(not re.fullmatch('[A-Za-z0-9_-]{1,64}',k) or not isinstance(v,str) or '\r' in v or '\n' in v for field in ('headers','query') for k,v in auth.get(field,{}).items()):raise ProviderError('provider_auth_template_invalid')
    if auth.get('type')=='hmac':
        if any(k.lower() in ('host','cookie','proxy-authorization','content-length') for k in auth.get('headers',{})):raise ProviderError('provider_auth_header_not_allowed')
        if auth.get('signature_query') and not re.fullmatch('[A-Za-z0-9_-]{1,64}',str(auth['signature_query'])):raise ProviderError('provider_auth_field_invalid')
        if auth.get('algorithm') not in ('sha1','sha256','sha512') or auth.get('encoding') not in ('hex','base64'):raise ProviderError('provider_signature_contract_unsupported')
        if not isinstance(auth.get('canonical'),str) or len(auth['canonical'])>2000:raise ProviderError('provider_signature_contract_unsupported')
        if not isinstance(auth.get('key_steps',[]),list) or len(auth.get('key_steps',[]))>5 or any(not isinstance(v,str) for v in auth.get('key_steps',[])):raise ProviderError('provider_signature_contract_unsupported')
        allowed=RESERVED|{'body_sha1','timestamp_ms'}
        if _refs([auth['canonical'],auth.get('key_steps',[])])-allowed:raise ProviderError('provider_signature_contract_unsupported')
        if SECRET.search(auth['canonical']) or SECRET.search(json.dumps(auth.get('key_steps',[]))):raise ProviderError('provider_secret_in_signature_message')
    cost=p.get('cost')
    if not isinstance(cost,dict) or type(cost.get('amount')) not in (int,float) or not math.isfinite(cost['amount']) or cost['amount']<0 or not re.fullmatch('[A-Z]{3}',str(cost.get('currency',''))):raise ProviderError('provider_cost_contract_missing')
    if not isinstance(cost.get('quote'),str) or len(cost['quote'])<8 or cost['quote'] not in docs.get(cost.get('source'),''):raise ProviderError('provider_cost_evidence_missing')
    if cost.get('billing_period') not in ('one_time','hour','month'):raise ProviderError('provider_cost_period_missing')
    quote_text=cost['quote'];currency=cost['currency']
    if not re.search(r'(?i)\bIP(?:v[46])?\b|public (?:IP )?address|公网(?:IP|地址)',quote_text):raise ProviderError('provider_cost_not_bound_to_ip')
    if cost['billing_period']=='hour' and not re.search(r'(?i)hour|小时|/h\b',quote_text):raise ProviderError('provider_cost_period_not_documented')
    if cost['billing_period']=='month' and not re.search(r'(?i)month|每月|/mo\b',quote_text):raise ProviderError('provider_cost_period_not_documented')
    if cost['billing_period']=='one_time' and re.search(r'(?i)per hour|hourly|/h\b|per month|monthly|/mo\b|每小时|每月',quote_text):raise ProviderError('provider_recurring_cost_not_one_time')
    money=[float(v) for v in re.findall(r'(?:'+re.escape(currency)+r'\s*|'+(r'\$\s*' if currency=='USD' else r'(?!)')+r')([0-9]+(?:\.[0-9]+)?)',quote_text,re.I)]
    money += [float(v) for v in re.findall(r'([0-9]+(?:\.[0-9]+)?)\s*'+re.escape(currency)+r'\b',quote_text,re.I)]
    if cost['amount']==0:
        positive=re.search(r'(?i)\bfree\b|no (?:additional )?charge|no (?:additional )?cost|免费|不收费',quote_text)
        negative=re.search(r'(?i)not.{0,30}free|not.{0,20}免费|非免费|不是免费|free trial|试用',quote_text)
        if negative or any(v>0 for v in money) or not (positive or money and all(v==0 for v in money)):raise ProviderError('provider_free_cost_not_documented')
    elif cost['amount'] not in money:raise ProviderError('provider_cost_amount_not_documented')
    if p.get('online') is not True:raise ProviderError('provider_external_controller_required')
    if not isinstance(p.get('parameters',[]),list) or len(p.get('parameters',[]))>20:raise ProviderError('provider_parameters_invalid')
    known={'instance_id','region','incident','old_ip'}|set(p.get('parameters',[]))
    if not all(NAME.fullmatch(str(x)) and x not in RESERVED for x in p.get('parameters',[])):raise ProviderError('provider_parameters_invalid')
    def request(spec,mutating,known):
        if not isinstance(spec,dict):raise ProviderError('provider_request_invalid')
        if spec.get('method') not in (('POST','PUT','PATCH') if mutating else ('GET',)):raise ProviderError('provider_method_not_allowed')
        path=spec.get('path','')
        if not isinstance(path,str) or not path.startswith('/') or path.startswith('//') or any(x in path for x in ('..','?','#','%','\\','\r','\n')):raise ProviderError('provider_path_invalid')
        if FORBIDDEN.search(path) or (mutating and FORBIDDEN.search(re.sub(r'([a-z])([A-Z])',r'\1_\2',json.dumps([spec.get('body',{}),spec.get('query',{})])))):raise ProviderError('provider_non_ip_action_rejected')
        text=docs.get(spec.get('source'),'');documented=spec.get('documented_path','')
        if not isinstance(documented,str) or not documented.startswith('/') or documented not in text or _normalize_path(documented)!=_normalize_path(path):raise ProviderError('provider_operation_not_documented')
        if SECRET.search(json.dumps(spec)):raise ProviderError('provider_secret_outside_auth')
        if _refs({k:spec.get(k) for k in ('path','query','body','headers')})-known:raise ProviderError('provider_request_unknown_variable')
        if not isinstance(spec.get('query',{}),dict) or not isinstance(spec.get('headers',{}),dict):raise ProviderError('provider_request_invalid')
        if any(k.lower() in ('authorization','host','cookie','proxy-authorization') or not re.fullmatch('[A-Za-z0-9_-]{1,64}',k) for k in spec.get('headers',{})):raise ProviderError('provider_request_header_not_allowed')
        if any(not isinstance(v,str) or '\r' in v or '\n' in v for v in spec.get('headers',{}).values()):raise ProviderError('provider_request_header_invalid')
        if any(not isinstance(v,(str,int,float,bool)) for v in spec.get('query',{}).values()):raise ProviderError('provider_query_contract_unsupported')
        if spec.get('encoding','json') not in ('json','form'):raise ProviderError('provider_encoding_contract_unsupported')
    def operation_evidence(action,rollback=False):
        operation=action.get('operation')
        verbs={'ip_allocate':r'allocat|reserv|creat|申请|分配|预留','ip_attach':r'attach|assign|associat|绑定|关联','ip_replace':r'replac|chang|rotat|更换|替换','ip_restore':r'restor|reassign|恢复|重新绑定'}
        if operation not in verbs or (rollback and operation=='ip_allocate'):raise ProviderError('provider_operation_scope_invalid')
        evidence=action.get('quote','');spec=action.get('request',{})
        if not isinstance(evidence,str) or not 16<=len(evidence)<=5000 or evidence not in docs.get(spec.get('source'),''):raise ProviderError('provider_operation_semantics_missing')
        if spec.get('documented_path','') not in evidence or not re.search(r'\b'+re.escape(str(spec.get('method')))+r'\b',evidence) or not re.search(r'(?i)\bip(?:v[46])?\b|public address|公网地址',evidence) or not re.search(verbs[operation],evidence,re.I):raise ProviderError('provider_operation_semantics_missing')
    read=p.get('read',{});request(read,False,known)
    for key in ('identity','address'):
        if not isinstance(read.get(key),str) or not read[key].startswith('/'):raise ProviderError('provider_read_contract_invalid')
    if '{instance_id}' not in json.dumps({k:read.get(k) for k in ('path','query')}):raise ProviderError('provider_instance_scope_missing')
    def capture(spec):
        captures=spec.get('capture',{})
        if not isinstance(captures,dict) or len(captures)>12:raise ProviderError('provider_capture_invalid')
        for name,path in captures.items():
            if not NAME.fullmatch(name) or name in RESERVED or not isinstance(path,str) or not path.startswith('/') or re.search(r'(?i)secret|password|token|credential|api.?key',name+' '+path):raise ProviderError('provider_capture_invalid')
        return set(captures)
    known |= capture(read)
    actions=p.get('actions')
    if not isinstance(actions,list) or not 1<=len(actions)<=8:raise ProviderError('provider_actions_invalid')
    ids=set()
    for action in actions:
        if not isinstance(action,dict) or not NAME.fullmatch(str(action.get('id',''))) or action['id'] in ids:raise ProviderError('provider_action_id_invalid')
        ids.add(action['id'])
        if action.get('operation')=='ip_restore' or (action.get('operation')=='ip_attach' and _refs(action.get('request',{})).intersection({'old_ip','old_resource_id'})):raise ProviderError('provider_restore_action_in_success_path')
        operation_evidence(action);request(action.get('request'),True,known)
        if action['operation']!='ip_allocate' and 'instance_id' not in _refs(action['request']):raise ProviderError('provider_mutation_instance_scope_missing')
        if 'reconcile' in action:
            reconcile=action['reconcile'];request(reconcile.get('request'),False,known)
            selected=reconcile.get('select')
            if selected is not None:
                if not isinstance(selected,dict) or not all(isinstance(selected.get(k),str) for k in ('path','where','equals')) or _refs(selected['equals'])-known:raise ProviderError('provider_reconcile_invalid')
            if capture(reconcile)!=capture(action):raise ProviderError('provider_reconcile_capture_mismatch')
            expect=reconcile.get('expect',{})
            if not isinstance(expect,dict) or any(not str(k).startswith('/') for k in expect) or _refs(expect)-known:raise ProviderError('provider_reconcile_invalid')
            markers=_refs([expect,selected])
            if action['operation']=='ip_allocate' and ('incident' not in markers or 'incident' not in _refs(action['request'])):raise ProviderError('provider_allocation_reconcile_ownership_missing')
            if action['operation']!='ip_allocate' and not markers.intersection({'instance_id','incident'}):raise ProviderError('provider_reconcile_identity_missing')
        if action['operation']=='ip_allocate' and 'resource_id' not in capture(action):raise ProviderError('provider_allocation_identity_capture_required')
        known |= capture(action)
        if 'wait' in action:
            wait=action['wait'];request(wait.get('request'),False,known)
            if not isinstance(wait.get('expect'),dict) or not wait['expect'] or any(not str(k).startswith('/') for k in wait['expect']) or _refs(wait['expect'])-known:raise ProviderError('provider_async_readiness_contract_missing')
    rollback=p.get('rollback',[])
    if not isinstance(rollback,list) or len(rollback)>8:raise ProviderError('provider_rollback_invalid')
    for action in rollback:
        operation_evidence(action,rollback=True);request(action.get('request'),True,known)
        if 'reconcile' in action:request(action['reconcile'].get('request'),False,known)
    encoded=json.dumps(p,separators=(',',':'),sort_keys=True)
    if len(encoded)>64000:raise ProviderError('provider_manifest_too_large')
    p['evidence']=[{'url':d['url'],'sha256':hashlib.sha256(d['text'].encode()).hexdigest()} for d in documents]
    return p

def credential_names(profile):
    auth=profile['auth'];names=set(SECRET.findall(json.dumps(auth)))
    for key in ('credential','username','password'):
        if auth.get(key):names.add(auth[key])
    return names

class GenericHTTPProvider:
    def __init__(self,config,profile,state_dir,request=None,clock=time.time):
        self.config,self.profile,self.clock=dict(config),profile,clock
        self.request=request or api_request;self.store=_Store(state_dir)
        self.instance=str(config.get('instance_id',''));self.region=str(config.get('region',''))
        if not self.instance or len(self.instance)>200 or any(c in self.instance for c in ('\r','\n','/','\\')):raise ProviderError('provider_instance_invalid')
        self.scope=hashlib.sha256((profile['origin']+'|'+self.instance+'|'+self.region).encode()).hexdigest()
        self.profile_digest=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
        self.credentials=config.get('credentials',{})
        if not isinstance(self.credentials,dict) or any(not isinstance(v,str) or not 1<=len(v)<=4096 or '\r' in v or '\n' in v for v in self.credentials.values()):raise ProviderError('provider_credentials_invalid')
        if credential_names(profile)-set(self.credentials):raise ProviderError('provider_credentials_required')
        parameters=config.get('parameters',{})
        if not isinstance(parameters,dict) or any(not NAME.fullmatch(str(k)) or k in RESERVED or not isinstance(v,(str,int)) or len(str(v))>512 for k,v in parameters.items()):raise ProviderError('provider_parameters_invalid')
        self.variables={**parameters,'instance_id':self.instance,'region':self.region}
        if set(profile.get('parameters',[]))-set(self.variables):raise ProviderError('provider_parameters_required')
    def _secret_template(self,value,variables):
        if not isinstance(value,str):raise ProviderError('provider_auth_template_invalid')
        # Substitute once: credential bytes are never parsed as template text.
        token=re.compile(r'\{(secret:)?([a-z][a-z0-9_]{0,63})\}')
        if '{' in token.sub('',value) or '}' in token.sub('',value):raise ProviderError('provider_auth_template_invalid')
        def replace(m):
            source=self.credentials if m[1] else variables
            if m[2] not in source:raise ProviderError('provider_auth_template_variable_missing')
            return str(source[m[2]])
        return token.sub(replace,value)
    def _call(self,spec,variables):
        method=spec['method'];path=render(spec['path'],variables,path=True)
        query=render(spec.get('query',{}),variables);body=render(spec.get('body'),variables)
        headers=render(spec.get('headers',{}),variables);headers.update({'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded' if spec.get('encoding')=='form' else 'application/json'})
        auth=self.profile['auth'];kind=auth['type']
        if kind=='bearer':headers['Authorization']='Bearer '+self.credentials[auth['credential']]
        elif kind=='header':headers[auth['name']]=auth.get('prefix','')+self.credentials[auth['credential']]
        elif kind=='query':query[auth['name']]=self.credentials[auth['credential']]
        elif kind=='basic':headers['Authorization']='Basic '+base64.b64encode((self.credentials[auth['username']]+':'+self.credentials[auth['password']]).encode()).decode()
        elif kind=='hmac':
            now=int(self.clock());v={**variables,'method':method,'path':path,'timestamp':str(now),'timestamp_ms':str(now*1000),'date':time.strftime('%Y-%m-%d',time.gmtime(now)),'nonce':secrets.token_hex(12)}
            for name,value in auth.get('query',{}).items():query[name]=self._secret_template(value,v)
            raw='' if body is None else (urlencode(body) if spec.get('encoding')=='form' else json.dumps(body,separators=(',',':'),sort_keys=True))
            v.update(query=urlencode(sorted(query.items())),body=raw,body_sha256=hashlib.sha256(raw.encode()).hexdigest(),body_sha1=hashlib.sha1(raw.encode()).hexdigest())
            key=(auth.get('key_prefix','')+self.credentials[auth['credential']]).encode()
            for step in auth.get('key_steps',[]):key=hmac.new(key,render(step,v).encode(),auth['algorithm']).digest()
            digest=hmac.new(key,render(auth['canonical'],v).encode(),auth['algorithm']).digest();v['signature']=digest.hex() if auth['encoding']=='hex' else base64.b64encode(digest).decode()
            for name,value in auth.get('headers',{}).items():headers[name]=self._secret_template(value,v)
            if auth.get('signature_query'):query[auth['signature_query']]=v['signature']
        url=self.profile['origin']+path+('?' +urlencode(sorted(query.items())) if query else '')
        try:return self.request(method,url,body,headers)
        except ProviderError:raise
        except Exception:raise ProviderError('provider_transport_failed') from None
    def _capture(self,spec,result):
        output={}
        for name,path in spec.get('capture',{}).items():
            value=pointer(result,path)
            if not isinstance(value,(str,int)) or len(str(value))>512 or any(c in str(value) for c in ('/','\\','\r','\n','..')):raise ProviderError('provider_capture_value_invalid')
            output[name]=value
        return output
    def _read(self):
        spec=self.profile['read'];result=self._call(spec,self.variables)
        if str(pointer(result,spec['identity']))!=self.instance:raise ProviderError('provider_instance_identity_mismatch')
        return _ipv4(pointer(result,spec['address'])),self._capture(spec,result)
    def get_inbound_addresses(self):return {'A':self._read()[0]}
    def _journal(self):
        j=self.store.read('transaction.json',{})
        if j and (j.get('scope')!=self.scope or j.get('profile_digest')!=self.profile_digest):raise ProviderError('provider_transaction_scope_changed')
        return j
    def pending(self):return bool(self._journal())
    def _save(self,j):j['updated_at']=int(self.clock());self.store.write('transaction.json',j)
    def _reconcile(self,action,variables):
        spec=action.get('reconcile')
        if not spec:return None
        data=self._call(spec['request'],variables)
        if spec.get('select'):
            select=spec['select'];rows=pointer(data,select['path'])
            if not isinstance(rows,list) or len(rows)>1000:raise ProviderError('provider_reconcile_rows_invalid')
            expected=render(select['equals'],variables);rows=[r for r in rows if str(pointer(r,select['where']))==expected]
            if not rows:return None
            if len(rows)!=1:raise ProviderError('provider_reconcile_ambiguous')
            data=rows[0]
        for path,value in spec.get('expect',{}).items():
            if str(pointer(data,path))!=str(render(value,variables)):return None
        return self._capture(spec,data)
    def _steps(self,j,rollback=False):
        actions=self.profile.get('rollback',[]) if rollback else self.profile['actions'];key='rollback_index' if rollback else 'index';sent='rollback_sent' if rollback else 'sent';ack='rollback_ack' if rollback else 'ack'
        while j[key]<len(actions):
            action=actions[j[key]]
            if j.get(sent):
                if j.get(ack):result={}
                else:
                    result=self._reconcile(action,j['variables'])
                    if result is None:
                        current,_=self._read();expected=j['old_ip'] if rollback else j['variables'].get('new_ip')
                        if j[key]==len(actions)-1 and expected and current==expected and not action.get('capture'):result={}
                        else:return False
            else:
                j[sent]=True;self._save(j)
                try:
                    response=self._call(action['request'],j['variables'])
                    result=self._capture(action,response)
                    j['async_accepted']=getattr(response,'http_status',200)==202
                except Exception:return False
            j['variables'].update(result);j[ack]=True;self._save(j)
            if action.get('operation')=='ip_allocate':
                ledger=self.store.read('ledger.json',{'attempts':[],'finished':{}});owned=ledger.setdefault('owned',{})
                ident=str(j['variables']['resource_id']);owned.setdefault(ident,{'incident':j['incident'],'created_at':int(self.clock())})
                self.store.write('ledger.json',ledger)
            wait=action.get('wait')
            if wait:
                response=self._call(wait['request'],j['variables'])
                if any(str(pointer(response,path))!=str(render(expected,j['variables'])) for path,expected in wait['expect'].items()):return False
            elif j.get('async_accepted') and j[key]!=len(actions)-1:
                # HTTP202 is acceptance, never proof that an allocated resource is ready.
                return False
            elif action.get('reconcile'):
                reconciled=self._reconcile(action,j['variables'])
                if reconciled is None:return False
                for name,value in reconciled.items():
                    if name in j['variables'] and j['variables'][name]!=value:raise ProviderError('provider_reconciled_identity_changed')
                j['variables'].update(reconciled)
            j[key]+=1;j[sent]=False;j[ack]=False;j['async_accepted']=False;self._save(j)
        return True
    def _finish(self,j,status,code):
        result={'status':status,'code':code,'incident':j['incident'],'addresses':{'A':j['old_ip'] if status=='rolled_back' else j['new_ip']}}
        ledger=self.store.read('ledger.json',{'attempts':[],'finished':{}});ledger['finished'][j['incident']]=result
        ledger['finished']=dict(list(ledger['finished'].items())[-100:]);self.store.write('ledger.json',ledger);self.store.remove('transaction.json');return result
    def _rollback(self,j,update_dns):
        if not self.profile.get('rollback'):return {'status':'deferred','code':'provider_rollback_api_unavailable'}
        if not self._steps(j,True):return {'status':'pending','code':'provider_rollback_reconciliation_pending'}
        if self._read()[0]!=j['old_ip']:return {'status':'pending','code':'provider_rollback_address_pending'}
        if j.get('dns_attempted') and update_dns(j['old_ip']) is not True:return {'status':'pending','code':'provider_dns_rollback_pending'}
        return self._finish(j,'rolled_back',j.get('failure','provider_recovery_failed'))
    def _assess_ledger(self,ledger):
        """Local eligibility for a new transaction; never requests or reserves an IP."""
        blockers=[];required=[];details={}
        def block(code,field=None):
            if code not in blockers:blockers.append(code)
            if field and field not in required:required.append(field)
        for field in ('auto_rotate','allow_downtime'):
            if self.config.get(field) is not True:block('provider_rotation_not_authorized',field)
        if (not isinstance(ledger,dict) or not isinstance(ledger.get('attempts',[]),list)
                or not isinstance(ledger.get('finished',{}),dict) or not isinstance(ledger.get('owned',{}),dict)
                or any(type(t) not in (int,float) or not math.isfinite(t) for t in ledger.get('attempts',[]))):
            return {'automatic_rotation_ready':False,'recovery_mode':'assisted','blockers':['provider_ledger_invalid'],'required_configuration':[],'recent_attempts':[]}
        recent=[t for t in ledger.get('attempts',[]) if t>self.clock()-86400]
        maximum=self.config.get('max_attempts_per_day',1)
        details['attempts_last_24_hours']=len(recent)
        if type(maximum) is not int or not 1<=maximum<=3:block('provider_attempt_limit_invalid','max_attempts_per_day')
        elif len(recent)>=maximum:
            block('provider_daily_attempt_limit')
            details['next_attempt_at']=int(sorted(recent)[len(recent)-maximum]+86400)+1
        budget=self.config.get('max_cost_per_rotation',0)
        budget_valid=type(budget) in (int,float) and math.isfinite(budget) and 0<=budget<=100
        if not budget_valid:block('provider_budget_invalid','max_cost_per_rotation')
        maximum_owned=self.config.get('max_owned_allocations',2)
        if type(maximum_owned) is not int or not 1<=maximum_owned<=10:block('provider_owned_limit_invalid','max_owned_allocations')
        allocations=sum(a['operation']=='ip_allocate' for a in self.profile['actions']);owned=len(ledger.get('owned',{}));peak=owned+allocations
        details.update(owned_allocations=owned,new_allocations=allocations,peak_owned_allocations=peak)
        if type(maximum_owned) is int and 1<=maximum_owned<=10 and peak>maximum_owned:block('provider_owned_allocation_limit','max_owned_allocations')
        cost=self.profile['cost'];estimated=cost['amount']*(744 if cost['billing_period']=='hour' else 1)
        if cost['billing_period']!='one_time':estimated*=max(1,peak)
        details['estimated_cost']={'amount':estimated,'currency':cost['currency'],'period':'one_time' if cost['billing_period']=='one_time' else 'projected_31_days'}
        if cost['amount']>0 and cost['currency']!=self.config.get('cost_currency'):block('provider_cost_budget_exceeded','cost_currency')
        if budget_valid and estimated>budget:block('provider_cost_budget_exceeded','max_cost_per_rotation')
        mode='automatic' if not blockers else 'waiting' if blockers==['provider_daily_attempt_limit'] else 'assisted'
        return {'automatic_rotation_ready':not blockers,'recovery_mode':mode,'blockers':blockers,'required_configuration':required,'recent_attempts':recent,**details}
    def local_preflight(self):
        """Status never substitutes for fault evidence or the live read before mutation."""
        try:
            journal=self._journal()
            if journal:
                return {'automatic_rotation_ready':False,'recovery_mode':'recovering','pending_recovery':True,'blockers':['provider_recovery_in_progress'],'required_configuration':[],'transaction_phase':journal.get('phase'),'assessment_scope':'local_configuration_and_ledger','requires_live_verification':True}
            result=self._assess_ledger(self.store.read('ledger.json',{'attempts':[],'finished':{}}))
            result.pop('recent_attempts',None)
            return {**result,'pending_recovery':False,'assessment_scope':'local_configuration_and_ledger','requires_live_verification':True}
        except ProviderError as error:
            # An unreadable journal is a recovery blocker, never advice to replace another IP.
            pending=(self.store.root/'transaction.json').exists()
            return {'automatic_rotation_ready':False,'recovery_mode':'recovering' if pending else 'assisted','pending_recovery':pending,'blockers':[str(error)],'required_configuration':[],'assessment_scope':'local_configuration_and_ledger','requires_live_verification':True}

    def rotate(self,incident_id,verify_ip,update_dns):
        try:
            incident=_safe_id(incident_id);j=self._journal()
            ledger=self.store.read('ledger.json',{'attempts':[],'finished':{}})
            if not j:
                if incident in ledger['finished']:return ledger['finished'][incident]
                assessment=self._assess_ledger(ledger)
                if assessment['blockers']:raise ProviderError(assessment['blockers'][0])
                recent=assessment['recent_attempts']
                old,captures=self._read();variables={**self.variables,**captures,'old_ip':old,'incident':incident}
                j={'scope':self.scope,'profile_digest':self.profile_digest,'incident':incident,'old_ip':old,'variables':variables,'phase':'actions','index':0,'rollback_index':0,'created_at':int(self.clock()),'dns_attempted':False}
                ledger['attempts']=recent+[int(self.clock())];self.store.write('ledger.json',ledger);self._save(j)
            if j['phase']=='rollback':return self._rollback(j,update_dns)
            if j['phase']=='actions':
                if not self._steps(j):return {'status':'deferred' if self.clock()-j['created_at']>900 else 'pending','code':'provider_action_reconciliation_pending'}
                j['phase']='read_new';self._save(j)
            if j['phase']=='read_new':
                current,_=self._read();expected=j['variables'].get('new_ip')
                if current==j['old_ip'] or (expected and current!=expected):return {'status':'deferred' if self.clock()-j['created_at']>900 else 'pending','code':'provider_new_address_pending'}
                j['new_ip']=current;j['phase']='verify';self._save(j)
            if self.clock()<j.get('next_verify_at',0):return {'status':'pending','code':'provider_candidate_verification_pending'}
            if verify_ip(j['new_ip']) is not True:
                j['verify_failures']=j.get('verify_failures',0)+1;j['next_verify_at']=int(self.clock())+30
                if j['verify_failures']>=3:j.update(phase='rollback',failure='provider_candidate_unreachable')
                self._save(j);return {'status':'pending','code':'provider_candidate_verification_pending'}
            j['dns_attempted']=True;self._save(j)
            if update_dns(j['new_ip']) is not True:
                j.update(phase='rollback',failure='provider_dns_commit_failed');self._save(j);return {'status':'pending','code':'provider_rollback_required'}
            return self._finish(j,'rotated','provider_ip_rotated')
        except ProviderError as error:
            # Do not inspect a corrupt journal again while handling its error.
            return {'status':'deferred' if locals().get('j') else 'failed','code':str(error)}
        except Exception:return {'status':'deferred','code':'provider_operation_failed'}


def contract_check(config,profile):
    """Execute candidate protocol with synthetic responses and negative identity cases.

    This validates interpretation/binding, not provider semantics or live writes.
    The subsequent real read-only probe remains mandatory before activation.
    """
    import tempfile
    old,new='8.8.8.8','1.1.1.1'
    def assigned(root,path,value):
        tokens=[x.replace('~1','/').replace('~0','~') for x in path[1:].split('/')]
        current=root
        for i,key in enumerate(tokens):
            last=i==len(tokens)-1
            if isinstance(current,list):
                if not key.isdigit() or int(key)>100:raise ProviderError('provider_selector_contract_unsupported')
                while len(current)<=int(key):current.append(None)
                if last:current[int(key)]=value;return
                if current[int(key)] is None:current[int(key)]=[] if tokens[i+1].isdigit() else {}
                current=current[int(key)]
            else:
                if last:current[key]=value;return
                current=current.setdefault(key,[] if tokens[i+1].isdigit() else {})
    safe=copy.deepcopy(config)
    cost=profile['cost'];allocations=sum(a['operation']=='ip_allocate' for a in profile['actions'])
    estimate=cost['amount']*(744 if cost['billing_period']=='hour' else 1)*(max(1,allocations) if cost['billing_period']!='one_time' else 1)
    if estimate>100:raise ProviderError('provider_cost_exceeds_supported_budget')
    safe.update(auto_rotate=True,allow_downtime=True,max_attempts_per_day=1,max_owned_allocations=max(2,allocations),max_cost_per_rotation=estimate,cost_currency=cost['currency'])
    safe['credentials']={name:'synthetic-credential-value' for name in credential_names(profile)}
    count={'mutations':0,'reads':0};current=[old];wrong=[False]
    variables={'instance_id':str(safe['instance_id']),'region':str(safe.get('region','')),'incident':_safe_id('synthetic-contract'),'old_ip':old,**safe.get('parameters',{})}
    variables.update({name:'synthetic-old-resource' for name in profile['read'].get('capture',{})})
    def matches(spec,url):
        parsed=urlsplit(url);query=dict(parse_qsl(parsed.query))
        return parsed.path==render(spec['path'],variables,path=True) and all(str(query.get(k))==str(v) for k,v in render(spec.get('query',{}),variables).items())
    def transport(method,url,payload,headers):
        result={}
        if method=='GET':
            count['reads']+=1
            if matches(profile['read'],url):
                assigned(result,profile['read']['identity'],'different-instance' if wrong[0] else str(safe['instance_id']))
                assigned(result,profile['read']['address'],current[0])
                for name,path in profile['read'].get('capture',{}).items():assigned(result,path,'synthetic-old-resource')
            else:
                selected=next((action[branch] for action in profile['actions'] for branch in ('reconcile','wait') if branch in action and matches(action[branch]['request'],url)),None)
                if selected is None:raise ProviderError('provider_synthetic_read_unmapped')
                row={}
                for name,path in selected.get('capture',{}).items():assigned(row,path,variables[name])
                for path,value in selected.get('expect',{}).items():assigned(row,path,render(value,variables))
                if selected.get('select'):
                    selection=selected['select'];assigned(row,selection['where'],render(selection['equals'],variables));assigned(result,selection['path'],[row])
                else:result=row
        else:
            index=count['mutations'];action=profile['actions'][index];count['mutations']+=1
            for name,path in action.get('capture',{}).items():
                value=new if name=='new_ip' else 'synthetic-new-resource';assigned(result,path,value);variables[name]=value
            if count['mutations']==len(profile['actions']):current[0]=new
        return result
    with tempfile.TemporaryDirectory(prefix='huarun-provider-contract-') as root:
        provider=GenericHTTPProvider(safe,profile,pathlib.Path(root)/'positive',request=transport,clock=lambda:100000)
        result=provider.rotate('synthetic-contract',lambda ip:ip==new,lambda ip:ip==new)
        if result.get('status')!='rotated' or count['mutations']!=len(profile['actions']):raise ProviderError('provider_synthetic_contract_failed')
        wrong[0]=True;before=count['mutations']
        negative=GenericHTTPProvider(safe,profile,pathlib.Path(root)/'negative',request=transport,clock=lambda:100000)
        result=negative.rotate('wrong-identity',lambda ip:True,lambda ip:True)
        if result.get('code')!='provider_instance_identity_mismatch' or count['mutations']!=before:raise ProviderError('provider_synthetic_identity_guard_failed')
    return {'schema_and_evidence':True,'synthetic_protocol_passed':True,'synthetic_identity_guard_passed':True,'live_write_tested':False}
