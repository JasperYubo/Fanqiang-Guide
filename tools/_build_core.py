"""Deterministic local knowledge-library build. Never performs network requests."""
import collections, copy, hashlib, json, re, sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

STAMP='v0.1-2026-09-11'
DATE='2026-09-11'
KINDS={'client':'客户端','core':'代理内核','protocol':'协议','transport':'传输与外层方案','concept':'基础机制',
 'firmware':'路由器固件','router_plugin':'路由器插件','package_ecosystem':'软件包生态',
 'deployment':'部署与运维工具','panel':'管理面板','rules':'分流规则','dns':'DNS工具',
 'subscription':'订阅与配置工具','browser_extension':'浏览器扩展','vpn':'VPN软件',
 'mesh':'组网工具','diagnostic':'诊断工具','library':'开发组件','directory':'资料目录','service':'网络服务','historical':'历史工具'}
STATUS={'primary_reviewed':'已读第一方资料','reference_only':'目录线索待核验','historical_reference':'历史资料待核验'}
INPUTS=['baseline.json','concepts.json','github-extra.json','routers.json','source-lists.json','baseline-reviewed.json','relationship-extra.json']

def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\r\n')

def jsonl(path,items):
    path.write_text(''.join(json.dumps(i,ensure_ascii=False)+'\n' for i in items),encoding='utf-8',newline='\r\n')

def unique(xs):
    return list(dict.fromkeys(x for x in xs if x is not None and x!=''))

def extract_urls(value):
    if isinstance(value,dict):
        return unique([u for v in value.values() for u in extract_urls(v)])
    if isinstance(value,list):
        return unique([u for v in value for u in extract_urls(v)])
    if isinstance(value,str) and re.fullmatch(r'https?://\S+',value):return [value]
    return []

def citation_urls(r):
    v=r['verification'];actual=v.get('evidence_urls',[])
    if not actual and v['status']=='primary_reviewed':
        ev=r.get('source_evidence',{})
        if isinstance(ev,dict) and ev.get('url'):actual=[ev['url']]
        sc=r.get('source_claims',{})
        if isinstance(sc,dict) and sc.get('readme_url'):actual=actual+[sc['readme_url']]
    return unique(actual) or r['official_urls'] or r['discovery_sources']

def key(text):
    return re.sub(r'[^\w]','',str(text).casefold())

def urlkey(url):
    if not url:return None
    p=urlsplit(url)
    path=p.path.rstrip('/')
    if p.hostname in ('github.com','www.github.com'):
        bits=path.strip('/').split('/')
        if len(bits)==2:return 'https://github.com/'+('/'.join(bits).removesuffix('.git')).lower()
    return urlunsplit((p.scheme.lower(),p.netloc.lower(),path,p.query,''))

def lists(record,field):
    value=record.get(field) or []
    return [value] if isinstance(value,str) else value

def normalize(r,origin):
    r=copy.deepcopy(r)
    assert re.fullmatch(r'[a-z0-9][a-z0-9-]*',r['id']),r['id']
    assert r['kind'] in KINDS,(r['id'],r['kind'])
    for f in ('aliases','platforms','ecosystems','official_urls','discovery_sources','tags','relations'):
        r[f]=lists(r,f)
    r.setdefault('source_claims',{})
    r.setdefault('compatibility',{'supported_models':None,'notes':None})
    r.setdefault('maintenance',{'status':'unknown','evidence_url':None})
    assert r['verification']['status'] in STATUS,r['id']
    if r['verification']['status']=='primary_reviewed' and 'reviewed_fields' not in r['verification']:
        r['verification']['reviewed_fields']=['name','kind','summary','official_urls']
    if r['verification']['status']=='primary_reviewed' and not r['verification'].get('evidence_urls'):
        r['verification']['evidence_urls']=citation_urls(r)
    assert r['official_urls'] or r['discovery_sources'],r['id']
    r['ingest_files']=[origin]
    r['schema_version']='0.1'
    r['updated_at']=DATE
    if key(r['name'])=='singbox' and r['kind']=='core':
        r['identity_notes']=['本条建模为 sing-box 核心平台。原参考目录混合核心与官方图形客户端信息，不能据平台数组推断各系统都有同等功能的 GUI；具体客户端应独立核验。']
    if r['id']=='shadow-tls':
        r['relations'].append({'predicate':'implements','target_name':'ShadowTLS 外层方案','evidence_url':'https://raw.githubusercontent.com/ihciah/shadow-tls/HEAD/README.md'})
    return r

def rank(r):return {'primary_reviewed':3,'reference_only':2,'historical_reference':1}[r['verification']['status']]

def merge(a,b,log):
    preferred=b if rank(b)>=rank(a) else a
    r=copy.deepcopy(preferred)
    r['id']=a['id']
    r['roles']=unique(a.get('roles',[a['kind']])+b.get('roles',[b['kind']]))
    r['identity_notes']=unique(a.get('identity_notes',[])+b.get('identity_notes',[]))
    r['verification_history']=a.get('verification_history',[a['verification']])+b.get('verification_history',[b['verification']])
    for f in ('aliases','official_urls','discovery_sources','tags','ingest_files'):
        r[f]=unique(a[f]+b[f])
    # Do not silently carry reference-only platform/core claims into a reviewed record.
    if rank(a)==rank(b):
        for f in ('platforms','ecosystems'):r[f]=unique(a[f]+b[f])
    if a['name']!=b['name']:r['aliases']=unique(r['aliases']+[a['name'],b['name']])
    r['aliases']=[x for x in r['aliases'] if x!=r['name']]
    r['merged_from_ids']=unique(a.get('merged_from_ids',[])+b.get('merged_from_ids',[])+[a['id'],b['id']])
    r['source_claim_sets']=a.get('source_claim_sets',[a.get('source_claims',{})])+b.get('source_claim_sets',[b.get('source_claims',{})])
    r['source_claim_sets']=[x for i,x in enumerate(r['source_claim_sets']) if x and x not in r['source_claim_sets'][:i]]
    # Relationship confidence is independent of the preferred record.
    rels=[]
    for orig in (a,b):
        for rel in orig['relations']:
            rel=copy.deepcopy(rel)
            rel.setdefault('verification_status',orig['verification']['status'])
            if rel not in rels:rels.append(rel)
    r['relations']=rels
    r['merge_history']=a.get('merge_history',[])+[{'incoming_id':b['id'],'incoming_file':b['ingest_files'],'selected_fields_from':preferred['ingest_files']}]
    for f in ('kind','repository','platforms'):
        if a.get(f)!=b.get(f):log.append({'id':r['id'],'field':f,'previous':a.get(f),'incoming':b.get(f),'selected':r.get(f)})
    return r

def build(source_dir, output_dir):
    source_dir=Path(source_dir)
    OUT=Path(output_dir)
    OUT.mkdir(parents=True,exist_ok=True)
    records={}; alternate_ids={}; changes=[]; inputs={}; input_hashes={}
    for filename in INPUTS:
        path=source_dir/filename
        if not path.is_file():raise ValueError('missing_required_input: '+filename)
        content=json.loads(path.read_text(encoding='utf-8-sig'))
        assert isinstance(content,list),filename
        inputs[filename]=len(content)
        input_hashes[filename]=hashlib.sha256(path.read_bytes()).hexdigest()
        for incoming in content:
            r=normalize(incoming,filename)
            existing=alternate_ids.get(r['id'],r['id']) if alternate_ids.get(r['id'],r['id']) in records else None
            if existing is None:
                matches=[]
                for ident,v in records.items():
                    # Never merge protocols/transports with tools sharing the same repository.
                    same_type=v['kind']==r['kind']
                    if same_type and (key(v['name'])==key(r['name']) or (r.get('repository') and urlkey(v.get('repository'))==urlkey(r['repository']))):matches.append(ident)
                assert len(matches)<=1,(r['id'],matches)
                existing=matches[0] if matches else None
            if existing:
                alternate_ids[r['id']]=existing
                records[existing]=merge(records[existing],r,changes)
            else:records[r['id']]=r
    rows=sorted(records.values(),key=lambda r:(list(KINDS).index(r['kind']),r['name'].casefold()))
    identities=collections.defaultdict(set)
    for r in rows:
        for value in [r['id'],r['name']]+r['aliases']+r.get('merged_from_ids',[]):identities[key(value)].add(r['id'])
    aliases={'xray':['Xray-core'],'mihomo':['Mihomo'],'clash':['Clash'],'singbox':['sing-box'],
        'tor':['tor-core'],'wireguard':['protocol-wireguard'],'shadowsocks':['protocol-shadowsocks']}
    edges=[]
    for r in rows:
        for rel in r['relations']:
            targets=identities.get(key(rel.get('target_name','')),set())
            if len(targets)!=1:
                for candidate in aliases.get(key(rel.get('target_name','')),[]):
                    targets=identities.get(key(candidate),set())
                    if len(targets)==1:break
            target=next(iter(targets)) if len(targets)==1 else None
            predicate=rel['predicate']
            if predicate=='uses_core' and target and records[target]['kind']=='protocol':predicate='uses_protocol'
            if predicate=='uses_core' and target and records[target]['kind']=='library':predicate='uses_library'
            e={'source_id':r['id'],'predicate':predicate,'target_id':target,'target_name':rel.get('target_name'),
                'evidence_url':rel.get('evidence_url'),'verification_status':rel.get('verification_status',r['verification']['status']),
                'resolution':'resolved' if target else 'unresolved'}
            if e not in edges:edges.append(e)
    sources={}
    for r in rows:
        urls=extract_urls(r)
        r['source_ids']=[]
        for u in urls:
            sid='src-'+hashlib.sha256(u.encode()).hexdigest()[:12]
            r['source_ids'].append(sid)
            s=sources.setdefault(sid,{'id':sid,'url':u,'host':urlsplit(u).netloc,'referenced_by':[],
                'observed_roles':[],'note':'作为来源或入口被记录；可访问性不等于内容经审校。'})
            s['referenced_by'].append(r['id'])
            role='declared_official_entry' if u in r['official_urls'] else 'retained_reference_or_snapshot'
            if u in citation_urls(r) and r['verification']['status']=='primary_reviewed':role='reviewed_scope_source'
            s['observed_roles']=unique(s['observed_roles']+[role])
    modelpath=source_dir/'merlin-model-matrix.json'
    models=json.loads(modelpath.read_text(encoding='utf-8-sig'))
    for m in models:
        u=m['source_url'];sid='src-'+hashlib.sha256(u.encode()).hexdigest()[:12]
        source=sources.setdefault(sid,{'id':sid,'url':u,'host':urlsplit(u).netloc,'referenced_by':[],'observed_roles':[],
            'note':'第一方型号支持清单，不代表刷机或插件实测。'})
        source['referenced_by'].append('compat:'+m['id'])
        source['observed_roles']=unique(source['observed_roles']+['hardware_support_list'])
    bysource={sid:s for sid,s in sources.items()}
    reviewed=[]; allchunks=[]
    cards=OUT/'cards'; cards.mkdir(exist_ok=True)
    expected_cards=set()
    for r in rows:
        status=STATUS[r['verification']['status']]
        field_scope=r['verification'].get('reviewed_fields',[])
        platform_label='平台（已核对）' if 'platforms' in field_scope else '平台线索（具体范围见核验说明）'
        ecosystem_label='生态（已核对）' if 'ecosystems' in field_scope else '生态线索（具体范围见核验说明）'
        lines=[f"# {r['name']}",'',f"条目 ID：{r['id']}  ",f"类型：{KINDS[r['kind']]}  ",f"资料状态：{status}  ",f"记录日期：{DATE}",'',r['summary'],'',
            f"别名线索：{'、'.join(r['aliases']) or '未记录'}",f"{platform_label}：{'、'.join(r['platforms']) or '未记录或不适用'}",
            f"{ecosystem_label}：{'、'.join(r['ecosystems']) or '未记录'}",'',
            '## 核验范围','',r['verification']['notes'],'',*r.get('identity_notes',[]),'',
            '价格、版本、热度等来源快照保留在结构化数据的 source_claims/source_claim_sets 中，未自动提升为已核验结论。','',
            '## 兼容性','',r['compatibility'].get('notes') or '未开展安装、硬件型号或网络效果测试。',
            f"具体支持型号：{json.dumps(r['compatibility'].get('supported_models'),ensure_ascii=False) if r['compatibility'].get('supported_models') is not None else '待核验'}",'',
            '## 项目关系','']
        relations=[e for e in edges if e['source_id']==r['id']]
        for e in relations:
            target=f"[{e['target_name']}]({e['target_id']}-{STAMP}.md)" if e['target_id'] else str(e['target_name'])+'（尚未关联到唯一条目）'
            lines.append(f"- {e['predicate']} → {target}；关系状态：{STATUS[e['verification_status']]}；[依据]({e['evidence_url']})")
        if not relations:lines.append('暂未建立经来源支持的关系。')
        lines+=['','## 来源','']
        if r['id']=='bannedbook-fanqiang':
            # This directory's search snapshots are discovery history, not card citations.
            lines.extend([
                '- [官方仓库 · bannedbook/fanqiang](https://github.com/bannedbook/fanqiang)',
                '- [已阅读的 README](https://raw.githubusercontent.com/bannedbook/fanqiang/HEAD/README.md)',
            ])
        else:
            for n,sid in enumerate(r['source_ids'],1):
                u=bysource[sid]['url'];lines.append(f'- [来源 {n} · {urlsplit(u).netloc}]({u})')
        text='\n'.join(lines)+'\n'
        filename=r['id']+'-'+STAMP+'.md'
        expected_cards.add(filename)
        (cards/filename).write_text(text,encoding='utf-8',newline='\r\n')
        # RAG excerpts exclude secondary platform/core metadata even on reviewed records.
        chunk_text='\n'.join([r['name'],r['summary'],f"类型：{KINDS[r['kind']]}",f"资料状态：{status}",
            '核验范围：'+r['verification']['notes'],*r.get('identity_notes',[]),
            '兼容性：'+(r['compatibility'].get('notes') or '具体设备与版本兼容性未核验'),
            '来源：'+' '.join(citation_urls(r))])
        chunk={'id':r['id']+':overview','entity_id':r['id'],'title':r['name'],'text':chunk_text,
            'metadata':{'kind':r['kind'],'verification_status':r['verification']['status'],'reviewed_fields':r['verification'].get('reviewed_fields',[]),
            'platforms':r['platforms'] if 'platforms' in field_scope else [],'ecosystems':r['ecosystems'] if 'ecosystems' in field_scope else [],
            'metadata_scope':'Only explicitly reviewed fields are populated','source_ids':r['source_ids'],'updated_at':DATE},'citations':citation_urls(r)}
        allchunks.append(chunk)
        if r['verification']['status']=='primary_reviewed':reviewed.append(chunk)
    for stale in cards.glob('*-'+STAMP+'.md'):
        if stale.name not in expected_cards:
            assert stale.resolve().parent==cards.resolve()
            stale.unlink()
    datafile=OUT/f'library-{STAMP}.json'
    dump(datafile,rows)
    jsonl(OUT/f'library-{STAMP}.jsonl',rows)
    jsonl(OUT/f'relationships-{STAMP}.jsonl',edges)
    jsonl(OUT/f'sources-{STAMP}.jsonl',sorted(sources.values(),key=lambda s:s['url']))
    jsonl(OUT/f'rag-all-{STAMP}.jsonl',allchunks)
    jsonl(OUT/f'rag-reviewed-{STAMP}.jsonl',reviewed)
    queue=[{'entity_id':r['id'],'name':r['name'],'kind':r['kind'],'status':r['verification']['status'],
        'next_action':'读取并核对第一方身份、用途、支持平台和维护说明；保留二手声明，变更后重新审校。',
        'candidate_sources':r['official_urls'] or r['discovery_sources'],'known_limits':r['verification']['notes']} for r in rows if r['verification']['status']!='primary_reviewed']
    jsonl(OUT/f'review-queue-{STAMP}.jsonl',queue)
    db=OUT/f'library-{STAMP}.sqlite'
    with closing(sqlite3.connect(db)) as conn:
        conn.executescript('DROP TABLE IF EXISTS entities; DROP TABLE IF EXISTS relations; DROP TABLE IF EXISTS sources; DROP TABLE IF EXISTS search; CREATE TABLE entities(id TEXT PRIMARY KEY,name TEXT,kind TEXT,status TEXT,json TEXT); CREATE TABLE relations(source_id TEXT,predicate TEXT,target_id TEXT,json TEXT); CREATE TABLE sources(id TEXT PRIMARY KEY,url TEXT,json TEXT); CREATE VIRTUAL TABLE search USING fts5(id UNINDEXED,name,body,tokenize="trigram");')
        for r in rows:
            conn.execute('INSERT INTO entities VALUES(?,?,?,?,?)',(r['id'],r['name'],r['kind'],r['verification']['status'],json.dumps(r,ensure_ascii=False)))
            searchbody=' '.join([r['summary']]+r['aliases']+r['platforms']+r['ecosystems']+r['tags']+[r['compatibility'].get('notes') or ''])
            conn.execute('INSERT INTO search VALUES(?,?,?)',(r['id'],r['name'],searchbody))
        for e in edges:conn.execute('INSERT INTO relations VALUES(?,?,?,?)',(e['source_id'],e['predicate'],e['target_id'],json.dumps(e,ensure_ascii=False)))
        for sid,s in sources.items():conn.execute('INSERT INTO sources VALUES(?,?,?)',(sid,s['url'],json.dumps(s,ensure_ascii=False)))
        modelpath=source_dir/'merlin-model-matrix.json'
        models=json.loads(modelpath.read_text(encoding='utf-8-sig'))
        conn.executescript('DROP TABLE IF EXISTS hardware_compatibility; CREATE TABLE hardware_compatibility(id TEXT PRIMARY KEY,model TEXT,firmware_id TEXT,search_text TEXT,json TEXT);')
        modelchunks=[]
        for m in models:
            assert m['firmware_entity_id'] in records,m
            assert m['tested'] is False,m
            modeltext=f"{m['vendor']} 华硕 {m['model_exact']} {m.get('hardware_revision') or ''} {m['firmware_entity_id']} {m['support_claim']} {m['notes']}"
            conn.execute('INSERT INTO hardware_compatibility VALUES(?,?,?,?,?)',(m['id'],m['model_exact'],m['firmware_entity_id'],modeltext,json.dumps(m,ensure_ascii=False)))
            modelchunks.append({'id':'compat:'+m['id'],'title':m['model_exact']+' / '+m['firmware_entity_id'],
                'text':modeltext+'\n这是固件项目支持列表的声明；本库未刷机实测，也未核验每个插件兼容性。',
                'metadata':{'kind':'hardware_compatibility','firmware_entity_id':m['firmware_entity_id'],'verification_status':'primary_list_reviewed','tested':False,'updated_at':DATE},
                'citations':[m['source_url']]})
        dump(OUT/f'merlin-model-matrix-{STAMP}.json',models)
        jsonl(OUT/f'merlin-model-matrix-{STAMP}.jsonl',models)
        jsonl(OUT/f'rag-compatibility-{STAMP}.jsonl',modelchunks)
        if modelpath.exists():input_hashes['merlin-model-matrix.json']=hashlib.sha256(modelpath.read_bytes()).hexdigest()
        conn.commit()
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    counts=collections.Counter(r['kind'] for r in rows)
    states=collections.Counter(r['verification']['status'] for r in rows)
    index=['# 网络工具知识库 '+STAMP,'',f'共 {len(rows)} 个独立条目。工具、固件、协议、机制、资料目录分类型计数；已读第一方资料 {len(reviewed)} 条。','',
        '“已读第一方资料”只覆盖条目所声明的核验范围，不代表实测稳定、安全或所有版本兼容。','',
        '入口：[使用说明](../README.md) · [梅林生态](../knowledge/merlin-guide-'+STAMP+'.md) · [分类与关系](../knowledge/taxonomy-'+STAMP+'.md)','',
        '| 类型 | 数量 |','|---|---:|']
    index += [f'| {KINDS[k]} | {v} |' for k,v in counts.items()]
    for kind in KINDS:
        subset=[r for r in rows if r['kind']==kind]
        if not subset:continue
        index+=['',f'## {KINDS[kind]}','', '| 名称 | 平台/生态 | 资料状态 |','|---|---|---|']
        for r in subset:
            field='platforms' if r['platforms'] else 'ecosystems'
            label='' if field in r['verification'].get('reviewed_fields',[]) else '（线索）'
            index.append(f"| [{r['name']}](cards/{r['id']}-{STAMP}.md) | {'、'.join(r[field])}{label if r[field] else ''} | {STATUS[r['verification']['status']]} |")
    (OUT/f'INDEX-{STAMP}.md').write_text('\n'.join(index)+'\n',encoding='utf-8',newline='\r\n')
    report={'date':DATE,'input_records':inputs,'input_hashes':input_hashes,'unique_entities':len(rows),'by_kind':dict(counts),'by_verification':dict(states),
        'source_urls':len(sources),'relationships':len(edges),'resolved_relationships':sum(e['resolution']=='resolved' for e in edges),
        'merge_field_differences':len(changes),'reviewed_rag_chunks':len(reviewed),'hardware_support_claims':len(models),'checks':{'unique_ids':len({r['id'] for r in rows})==len(rows),'sqlite_integrity':'ok'}}
    return report
