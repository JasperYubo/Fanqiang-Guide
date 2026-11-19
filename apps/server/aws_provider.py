"""AWS EC2 Elastic IPv4 adapter using bounded SigV4 Query API requests.

Contract sources (checked 2026-11-18):
https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_AllocateAddress.html
https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_AssociateAddress.html
https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeAddresses.html
https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_ReleaseAddress.html
https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html

An existing Elastic IP is required for reversible automatic replacement. No
instance is stopped or destroyed. An unacknowledged allocation is reconciled by
its unique transaction tag; it is never blindly repeated. This module has API
contract/fault-injection tests; no live AWS-account verification is claimed.
"""
from __future__ import annotations
import datetime,hashlib,hmac,ipaddress,math,re,time
from pathlib import Path
from urllib.parse import urlencode,quote
from urllib.request import Request,build_opener
from urllib.error import HTTPError,URLError
import xml.etree.ElementTree as ET
from ip_provider import DigitalOceanRotator,ProviderError,_Store,_integer,_ipv4,NoRedirect

API_VERSION='2016-11-15'
MAX_RESPONSE=2*1024*1024
PUBLIC_IPV4_HOURLY_USD=0.005
MONTHLY_ESTIMATE_HOURS=744
PRICE_VERIFIED_ON='2026-11-18'
ACTIONS={'DescribeInstances','DescribeAddresses','AllocateAddress','AssociateAddress','DisassociateAddress','ReleaseAddress'}

def checked(value,pattern,code):
    if not isinstance(value,str) or not re.fullmatch(pattern,value):raise ProviderError(code)
    return value

def text(node,path,default=None):
    found=node.find(path)
    return found.text if found is not None and found.text is not None else default

def xml(raw,action):
    if not isinstance(raw,bytes) or len(raw)>MAX_RESPONSE or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ProviderError('provider_xml_invalid')
    try:root=ET.fromstring(raw)
    except ET.ParseError:raise ProviderError('provider_xml_invalid') from None
    for node in root.iter():node.tag=node.tag.split('}')[-1]
    if root.tag!=action+'Response':raise ProviderError('provider_xml_identity_invalid')
    return root

def signed_request(config,action,params,now):
    if action not in ACTIONS or not isinstance(params,dict) or any(not isinstance(k,str) or not isinstance(v,(str,int)) or isinstance(v,bool) for k,v in params.items()):raise ProviderError('provider_action_invalid')
    region=checked(config.get('region'),r'[a-z]{2}(?:-[a-z]+){1,3}-[1-9][0-9]?', 'provider_region_invalid')
    key=checked(config.get('access_key_id'),r'[A-Z0-9]{16,128}','provider_access_key_invalid')
    secret=checked(config.get('secret_access_key'),r'[A-Za-z0-9/+=]{20,256}','provider_secret_key_invalid')
    token=config.get('session_token','')
    if not isinstance(token,str) or len(token)>8192 or any(ord(c)<33 or ord(c)>126 for c in token):raise ProviderError('provider_session_token_invalid')
    host='ec2.'+region+('.amazonaws.com.cn' if region.startswith('cn-') else '.amazonaws.com')
    stamp=datetime.datetime.fromtimestamp(now,datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    date=stamp[:8]
    body=urlencode(sorted({**params,'Action':action,'Version':API_VERSION}.items()),quote_via=quote,safe='~').encode()
    headers={'content-type':'application/x-www-form-urlencoded; charset=utf-8','host':host,'x-amz-date':stamp}
    if token:headers['x-amz-security-token']=token
    keys=';'.join(sorted(headers));canonical_headers=''.join(k+':'+headers[k]+'\n' for k in sorted(headers))
    canonical='POST\n/\n\n'+canonical_headers+'\n'+keys+'\n'+hashlib.sha256(body).hexdigest()
    scope=date+'/'+region+'/ec2/aws4_request'
    tosign='AWS4-HMAC-SHA256\n'+stamp+'\n'+scope+'\n'+hashlib.sha256(canonical.encode()).hexdigest()
    signing=('AWS4'+secret).encode()
    for part in (date,region,'ec2','aws4_request'):signing=hmac.new(signing,part.encode(),hashlib.sha256).digest()
    signature=hmac.new(signing,tosign.encode(),hashlib.sha256).hexdigest()
    headers['authorization']='AWS4-HMAC-SHA256 Credential='+key+'/'+scope+', SignedHeaders='+keys+', Signature='+signature
    return Request('https://'+host+'/',data=body,method='POST',headers=headers)

class EC2API:
    def __init__(self,config,clock=time.time,opener=None):
        self.config=dict(config);self.clock=clock;self.opener=opener or build_opener(NoRedirect)
        signed_request(self.config,'DescribeAddresses',{},self.clock())
    def __call__(self,action,params):
        req=signed_request(self.config,action,params,self.clock())
        try:
            with self.opener.open(req,timeout=20) as response:raw=response.read(MAX_RESPONSE+1)
        except HTTPError as error:
            # Never expose response bodies, credential diagnostics or request headers.
            raise ProviderError('provider_aws_http_'+str(error.code)) from None
        except (URLError,OSError,TimeoutError):raise ProviderError('provider_aws_unavailable') from None
        return xml(raw,action)

class AWSElasticRotator(DigitalOceanRotator):
    def __init__(self,config,state_dir,request=None,clock=time.time):
        self.config=dict(config);self.clock=clock
        self.account=checked(config.get('account_id'),r'[0-9]{12}','provider_account_invalid')
        self.instance=checked(config.get('instance_id'),r'i-(?:[0-9a-f]{8}|[0-9a-f]{17})','provider_instance_invalid')
        self.region=checked(config.get('region'),r'[a-z]{2}(?:-[a-z]+){1,3}-[1-9][0-9]?','provider_region_invalid')
        self.eni=config.get('network_interface_id') or None
        if self.eni:checked(self.eni,r'eni-(?:[0-9a-f]{8}|[0-9a-f]{17})','provider_interface_invalid')
        self.private=config.get('private_ip_address') or None
        if self.private:
            try:
                if ipaddress.ip_address(self.private).version!=4:raise ValueError()
            except (ValueError,TypeError):raise ProviderError('provider_private_ip_invalid') from None
        self.scope='aws_eip:'+self.account+':'+self.region+':'+self.instance+':'+str(self.eni or 'primary')+':'+str(self.private or 'primary')
        self.request=request if request is not None else EC2API(config,clock=clock)
        self.store=_Store(Path(state_dir)/'aws_eip')
    def _droplet(self):
        root=self.request('DescribeInstances',{'InstanceId.1':self.instance})
        reservations=root.findall('reservationSet/item')
        matches=[]
        for reservation in reservations:
            for instance in reservation.findall('instancesSet/item'):
                matches.append((text(reservation,'ownerId'),instance))
        if len(matches)!=1:raise ProviderError('provider_instance_identity_or_state_mismatch')
        owner,node=matches[0]
        if owner!=self.account or text(node,'instanceId')!=self.instance or text(node,'instanceState/name')!='running' or not text(node,'vpcId'):raise ProviderError('provider_instance_identity_or_state_mismatch')
        # Only a selected ENI / private IP is eligible. Secondary IPs remain intact.
        interfaces=node.findall('networkInterfaceSet/item')
        choices=[i for i in interfaces if text(i,'networkInterfaceId')==self.eni] if self.eni else [i for i in interfaces if text(i,'attachment/deviceIndex')=='0']
        if len(choices)!=1:raise ProviderError('provider_interface_ambiguous')
        eni=choices[0];ident=text(eni,'networkInterfaceId')
        checked(ident,r'eni-(?:[0-9a-f]{8}|[0-9a-f]{17})','provider_interface_invalid')
        if text(eni,'ownerId')!=self.account or text(eni,'attachment/instanceId',self.instance)!=self.instance:raise ProviderError('provider_interface_owner_mismatch')
        private=self.private or text(eni,'privateIpAddress')
        choices=[a for a in eni.findall('privateIpAddressesSet/item') if text(a,'privateIpAddress')==private]
        if len(choices)!=1:raise ProviderError('provider_private_ip_ambiguous')
        try:
            if ipaddress.ip_address(private).version!=4:raise ValueError()
        except (ValueError,TypeError):raise ProviderError('provider_private_ip_invalid') from None
        public=text(choices[0],'association/publicIp')
        return {'id':self.instance,'eni':ident,'private':private,'public':public}
    def _ips(self):
        root=self.request('DescribeAddresses',{})
        rows=[]
        for node in root.findall('addressesSet/item'):
            if text(node,'domain')!='vpc':continue
            row={'ip':_ipv4(text(node,'publicIp')),'id':checked(text(node,'allocationId'),r'eipalloc-(?:[0-9a-f]{8}|[0-9a-f]{17})','provider_allocation_id_invalid'),
                 'association':text(node,'associationId'),'eni':text(node,'networkInterfaceId'),'private':text(node,'privateIpAddress'),
                 'instance':text(node,'instanceId'),'owner':text(node,'networkInterfaceOwnerId'),'border':text(node,'networkBorderGroup'),
                 'tags':{text(t,'key'):text(t,'value') for t in node.findall('tagSet/item')}}
            if row['association']:checked(row['association'],r'eipassoc-(?:[0-9a-f]{8}|[0-9a-f]{17})','provider_association_invalid')
            rows.append(row)
        if len(rows)>1000 or len({r['id'] for r in rows})!=len(rows) or len({r['ip'] for r in rows})!=len(rows):raise ProviderError('provider_ip_list_invalid')
        return rows
    def _get(self,ip):
        rows=[r for r in self._ips() if r['ip']==_ipv4(ip)]
        return rows[0] if rows else None
    @staticmethod
    def _assigned(value):
        if value is None or not value.get('association'):return None
        return value.get('instance') or value.get('eni') or 'associated'
    def _selected(self,rows,instance):
        return [r for r in rows if r['eni']==instance['eni'] and r['private']==instance['private'] and r['association']]
    def get_inbound_addresses(self):
        instance=self._droplet();bound=self._selected(self._ips(),instance)
        if len(bound)>1:raise ProviderError('provider_multiple_inbound_addresses')
        if bound:
            if bound[0]['owner']!=self.account:raise ProviderError('provider_interface_owner_mismatch')
            return {'A':bound[0]['ip']}
        if instance['public']:return {'A':_ipv4(instance['public'])}
        raise ProviderError('provider_public_ipv4_missing')
    def _authorization(self,ledger,rows):
        for key in ('auto_rotate','allow_reserved_ip_allocation','allow_downtime'):
            if self.config.get(key) is not True:raise ProviderError('provider_'+key+'_not_authorized')
        maximum=_integer(self.config.get('max_attempts_per_day',1),1,3,'provider_attempt_limit_invalid')
        limit=_integer(self.config.get('max_elastic_ips',5),2,50,'provider_address_limit_invalid')
        budget=self.config.get('max_monthly_ipv4_usd',20)
        if type(budget) not in (int,float) or not math.isfinite(budget) or not 0<budget<=1000:raise ProviderError('provider_budget_invalid')
        recent=[t for t in ledger['attempts'] if type(t) in (int,float) and t>self.clock()-86400]
        if len(recent)>=maximum:raise ProviderError('provider_daily_attempt_limit')
        if len(rows)+1>limit or (len(rows)+1)*PUBLIC_IPV4_HOURLY_USD*MONTHLY_ESTIMATE_HOURS>budget:raise ProviderError('provider_address_budget_exceeded')
        ledger['attempts']=recent+[int(self.clock())]
    def _adopt(self,journal,row):
        if (row['id'] in journal['before_ids'] or row['ip'] in journal['before_ips'] or row['association'] or row['tags'].get('huarun-transaction')!=journal['allocation_tag'] or row['tags'].get('huarun-instance')!=self.instance or row['border']!=journal['border']):raise ProviderError('provider_allocation_identity_invalid')
        journal.update(new_ip=row['ip'],new_id=row['id'],new_owned=True,phase='detach_old')
        self._save(journal)
        ledger=self._ledger();ledger['owned'][row['ip']]={'id':row['id'],'created_at':journal['created_at'],'incident':journal['incident']};self.store.write('ledger.json',ledger)
        return journal
    def _start(self,incident,ledger):
        instance=self._droplet();rows=self._ips();bound=self._selected(rows,instance)
        if len(bound)!=1:raise ProviderError('provider_existing_elastic_ip_required_for_rollback')
        old=bound[0]
        if old['owner']!=self.account or not old['border']:raise ProviderError('provider_old_ip_identity_invalid')
        self._authorization(ledger,rows)
        journal={'scope':self.scope,'incident':incident,'phase':'allocating','created_at':int(self.clock()),'old_ip':old['ip'],'old_id':old['id'],
                 'old_reserved':True,'old_owned':old['ip'] in ledger['owned'],'before_ips':[r['ip'] for r in rows],'before_ids':[r['id'] for r in rows],
                 'dns_attempted':False,'new_ip':None,'eni':instance['eni'],'private':instance['private'],'border':old['border'],
                 'allocation_tag':hashlib.sha256((self.scope+':'+incident).encode()).hexdigest()}
        self.store.write('ledger.json',ledger);self._save(journal)
        try:
            answer=self.request('AllocateAddress',{'Domain':'vpc','NetworkBorderGroup':old['border'],
                'TagSpecification.1.ResourceType':'elastic-ip','TagSpecification.1.Tag.1.Key':'huarun-transaction','TagSpecification.1.Tag.1.Value':journal['allocation_tag'],
                'TagSpecification.1.Tag.2.Key':'huarun-instance','TagSpecification.1.Tag.2.Value':self.instance})
            ident=text(answer,'allocationId');ip=text(answer,'publicIp')
            rows=[r for r in self._ips() if r['id']==ident and r['ip']==ip]
            if len(rows)!=1:raise ProviderError('provider_allocation_not_yet_visible')
            return self._adopt(journal,rows[0])
        except Exception:
            journal.update(phase='allocation_unknown',code='provider_allocation_requires_reconciliation');self._save(journal)
            return journal
    def _prepare_old(self,journal):
        # AssociateAddress replaces the old EIP while retaining its allocation.
        return True
    def _assignment(self,journal,ip,target,label):
        instance=self._droplet()
        if instance['eni']!=journal['eni'] or instance['private']!=journal['private']:raise ProviderError('provider_instance_address_changed')
        value=self._get(ip)
        expected=journal['new_id'] if ip==journal['new_ip'] else journal['old_id']
        if value is None or value['id']!=expected:raise ProviderError('provider_reserved_ip_disappeared')
        correct=value['eni']==journal['eni'] and value['private']==journal['private'] and value['owner']==self.account
        if value['association'] and not correct:raise ProviderError('provider_ip_assigned_elsewhere')
        matches=(not value['association']) if target is None else bool(value['association'] and correct)
        action=journal.get('action')
        if action:
            if action['ip']!=ip or action['target']!=target:raise ProviderError('provider_action_conflict')
            if matches:journal.pop('action');self._save(journal);return True
            journal['code']='provider_action_requires_reconciliation';self._save(journal);return False
        if matches:return True
        journal['action']={'ip':ip,'target':target,'label':label,'started_at':int(self.clock())};self._save(journal)
        try:
            if target is None:self.request('DisassociateAddress',{'AssociationId':value['association']})
            else:self.request('AssociateAddress',{'AllocationId':value['id'],'NetworkInterfaceId':journal['eni'],'PrivateIpAddress':journal['private'],'AllowReassociation':'false'})
            journal['action']['acknowledged']=True;self._save(journal)
        except Exception:journal['code']='provider_action_requires_reconciliation';self._save(journal)
        return False
    def _delete_created(self,journal,ip):
        ledger=self._ledger();owned=ledger['owned'].get(ip)
        expected=journal.get('new_id') if ip==journal.get('new_ip') and journal.get('new_owned') is True else owned.get('id') if isinstance(owned,dict) else None
        if not expected:raise ProviderError('provider_delete_not_owned')
        row=self._get(ip)
        if row is not None:
            if row['id']!=expected or row['association']:raise ProviderError('provider_delete_identity_or_assignment_mismatch')
            # Default-VPC ReleaseAddress also detaches: explicitly reject any attached resource first.
            self.request('ReleaseAddress',{'AllocationId':expected})
            if self._get(ip) is not None:return False
        ledger['owned'].pop(ip,None);self.store.write('ledger.json',ledger);return True
    def rotate(self,incident_id,verify_ip,update_dns):
        try:
            journal=self._journal()
            if journal and journal.get('phase') in ('allocating','allocation_unknown'):
                matches=[r for r in self._ips() if r['tags'].get('huarun-transaction')==journal['allocation_tag'] and r['tags'].get('huarun-instance')==self.instance]
                if len(matches)==1:self._adopt(journal,matches[0])
                else:return {'status':'deferred','code':'provider_allocation_requires_reconciliation'}
        except ProviderError as error:return {'status':'deferred','code':str(error)}
        except Exception:return {'status':'deferred','code':'provider_operation_failed'}
        return super().rotate(incident_id,verify_ip,update_dns)
