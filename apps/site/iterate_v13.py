from pathlib import Path
import json, html, hashlib, re

SITE='https://fanqiang.guide'
LIB='/guides/library.html'
MODELS='/guides/merlin-models.html'
ABOUT='/guides/about.html'
e=html.escape

def put(P,path,text):
    p=P/path;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(text.rstrip()+'\n',encoding='utf-8')

def iterate(P,page,guides,date):
    from catalog_v13 import build_catalog
    results=build_catalog(P,page)
    info=json.loads((P.parent/'content/client-comparison-v1.3-2026-09-12.json').read_text(encoding='utf-8'))
    rows=info['rows']
    def val(x): return '、'.join(x) if isinstance(x,list) else str(x)
    table_rows=[];md_rows=[]
    for r in rows:
        platform=val(r['platform']);arch=val(r['architecture'])
        client=val(r['client']);note=val(r['package_note'])
        checked=r['checked_at'];release=r['release_url']
        refs=' · '.join(f'<a href="{e(u,quote=True)}">依据 {i}</a>' for i,u in enumerate(r['source_urls'],1))
        mdrefs=' · '.join(f'[依据 {i}]({u})' for i,u in enumerate(r['source_urls'],1))
        table_rows.append(f'<tr><th scope="row">{e(platform)}<small>{e(arch)}</small></th><td>{e(client)}</td><td><a href="{e(release,quote=True)}">{e(client)} 官方发布入口 ↗</a></td><td>{e(note)}<small>来源核对：{e(checked)} · {refs}</small></td></tr>')
        md_rows.append('| '+' | '.join(x.replace('|','\\|').replace('\n',' ') for x in [platform+' / '+arch,client,f'[官方发布入口]({release})',note+'（核对：'+checked+'） '+mdrefs])+' |')
    comparison=f'<section id="client-comparison"><h2>按系统与架构找官方发布入口</h2><p>先找到你的系统与处理器架构，再查看发布说明中的对应附件。表内是官方项目入口，具体版本和文件名以发布页为准。</p><div class="comparison-scroll" role="region" aria-label="客户端系统与架构对照表，可横向滚动" tabindex="0"><table class="comparison-table"><caption>客户端选择与附件核对</caption><thead><tr><th scope="col">系统与架构</th><th scope="col">客户端</th><th scope="col">发布入口</th><th scope="col">附件核对</th></tr></thead><tbody>{"".join(table_rows)}</tbody></table></div><p><a href="{LIB}">按名称或分类检索全部工具 →</a></p></section>'
    comparison_md='\n\n## 按系统与架构找官方发布入口\n\n先找到系统与处理器架构，再核对官方发布页中的对应附件。\n\n| 系统与架构 | 客户端 | 发布入口 | 附件核对 |\n| --- | --- | --- | --- |\n'+'\n'.join(md_rows)+f'\n\n[代理工具与开源项目资料库]({SITE}{LIB})\n'
    ph=P/'guides/client-downloads.html';text=ph.read_text(encoding='utf-8')
    text=text.replace('<section id="section-1">',comparison+'<section id="section-1">',1)
    text=text.replace('<nav><a href="#section-1">','<nav><a href="#client-comparison">系统与架构选择表</a><a href="#section-1">',1)
    put(P,'guides/client-downloads.html',text)
    pm=P/'guides/client-downloads.md';md=pm.read_text(encoding='utf-8')
    pos=md.index('\n## ');put(P,'guides/client-downloads.md',md[:pos]+comparison_md+md[pos:])
    model_data=json.loads((P/'data/merlin-models.json').read_text(encoding='utf-8'))['items']
    picks=[r for r in model_data if r['model_exact'].upper() in {'RT-AX58U V1','RT-AX58U V2','RT-AX86U','RT-AX86U PRO','RT-AC68U','DSL-AC68U'}]
    labels={'current_listed':'来源列入支持','explicitly_unsupported':'来源明确不支持','unsupported':'来源明确不支持','not_supported':'来源明确不支持'}
    def claim(r):return labels.get(r['support_claim'],r['support_claim'])
    mt=[];mm=[]
    for r in picks:
        branch={'asuswrt-merlin':'Asuswrt-Merlin 原版','asuswrt-merlin-gnuton':'GNUton'}.get(r['firmware_entity_id'],r['firmware_entity_id'])
        mt.append(f'<tr><th scope="row">{e(r["model_exact"])}</th><td>{e(branch)}</td><td>{e(claim(r))}</td><td><a href="{e(r["source_url"],quote=True)}">查看支持来源 ↗</a><small>核对：{e(r["checked_at"])}</small></td></tr>')
        mm.append(f'| {r["model_exact"]} | {branch} | {claim(r)} | [来源]({r["source_url"]}) · {r["checked_at"]} |')
    model_section=f'<section id="model-lookup"><h2>梅林型号支持速查</h2><p>以下是部分容易混淆的型号。固件支持取自项目设备列表，插件环境需要单独核对；来源列入支持不表示本站完成了设备实测。</p><div class="comparison-scroll" role="region" aria-label="梅林型号支持对照表，可横向滚动" tabindex="0"><table class="comparison-table"><caption>完整型号与固件分支</caption><thead><tr><th scope="col">完整型号</th><th scope="col">固件分支</th><th scope="col">来源状态</th><th scope="col">来源与日期</th></tr></thead><tbody>{"".join(mt)}</tbody></table></div><a class="button button-primary" href="{MODELS}">查询全部 58 条型号记录 →</a></section>'
    ph=P/'guides/asus-merlin.html';s=ph.read_text(encoding='utf-8').replace('<section id="section-1">',model_section+'<section id="section-1">',1)
    s=s.replace('<nav><a href="#section-1">','<nav><a href="#model-lookup">型号支持速查</a><a href="#section-1">',1);put(P,'guides/asus-merlin.html',s)
    p=P/'guides/asus-merlin.md';s=p.read_text(encoding='utf-8');pos=s.index('\n## ')
    extra='\n\n## 梅林型号支持速查\n\n来源列入支持不表示本站设备实测；插件环境单独核对。\n\n| 完整型号 | 固件分支 | 来源状态 | 来源与日期 |\n| --- | --- | --- | --- |\n'+'\n'.join(mm)+f'\n\n[查询全部58条型号记录]({SITE}{MODELS})\n'
    put(P,'guides/asus-merlin.md',s[:pos]+extra+s[pos:])
    about_title='资料收录与核对方法'
    about_desc='Fanqiang Guide 的资料选取、来源核对、状态标注与纠错方式。'
    paragraphs=[('我们整理什么','Fanqiang Guide 整理客户端、代理核心、路由器固件与插件的公开资料，帮助读者确认项目身份、平台要求和官方来源。需要继续处理设备问题时，可把对应 I-Lang 工程书交给自己的 AI。'),('资料怎样核对','每条资料尽量保留第一方来源、核对日期和核对字段。已读第一方资料表示列出的字段经过来源核对；目录线索表示尚待进一步核对。来源页面列出的支持范围与实际设备测试分别记录。'),('更新日期表示什么','专题整理日期表示该页面内容的整理时间。工具与型号记录保留各自核对日期，页面更新不会自动提升记录状态。版本或来源发生变化时，应重新核对受影响字段。'),('如何反馈资料问题','若发现链接失效、平台信息有误或型号版本混淆，请通过公开仓库的 Issues 提供对应页面、项目名称和第一方依据。请勿在公开反馈里发送私密订阅、账号密码或设备密钥。')]
    body='<main id="main" class="wrap guide-main"><nav class="breadcrumbs" aria-label="面包屑"><a href="/">翻墙指南</a><span>/</span><span>'+about_title+'</span></nav><div class="guide-header"><h1>'+about_title+'</h1><p class="guide-meta">资料整理：Fanqiang Guide · '+date+'</p></div><div class="guide-body">'+''.join(f'<section><h2>{e(h)}</h2><p>{e(t)}</p></section>' for h,t in paragraphs)+f'<p><a href="https://github.com/JasperYubo/Fanqiang-Guide/issues">反馈资料问题 ↗</a> · <a href="{LIB}">浏览代理工具与开源项目资料库</a></p></div></main>'
    put(P,'guides/about.html',page(about_title+' | Fanqiang Guide',about_desc,ABOUT,body,[{'@type':'AboutPage','name':about_title,'url':SITE+ABOUT}],'/guides/about.md'))
    put(P,'guides/about.md','# '+about_title+'\n\n资料整理：Fanqiang Guide\n\n'+'\n\n'.join('## '+h+'\n\n'+t for h,t in paragraphs)+'\n\n[反馈资料问题](https://github.com/JasperYubo/Fanqiang-Guide/issues)')
    css='''
.comparison-scroll{overflow:auto;max-width:100%;border:1px solid #dce3ed;border-radius:10px;margin:18px 0}.comparison-table{border-collapse:collapse;width:100%;min-width:640px;font-size:13px}.comparison-table caption{text-align:left;padding:14px;font-weight:700;background:#eef3ff}.comparison-table th,.comparison-table td{padding:13px 14px;text-align:left;vertical-align:top;border-bottom:1px solid #e1e7f0;line-height:1.7}.comparison-table thead{background:#f5f7fb}.comparison-table small{display:block;color:#596b82;font-weight:400;margin-top:5px}.comparison-table a{color:#214fbd;text-decoration:underline}.site-search{margin-top:22px;max-width:590px}.site-search label{display:block;font-size:13px;font-weight:700;margin-bottom:9px}.site-search-row{display:flex;gap:8px}.site-search input{min-width:0;flex:1;border:1px solid #bdcbe1;border-radius:7px;padding:12px;font:inherit;background:#fff}.site-search button{border:0;cursor:pointer;white-space:nowrap}.site-search p{font-size:12px;color:#5c6e87;margin:8px 0}.site-search p a{color:#2858dc}.guide-meta a{color:#315792}.directory-entry{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:25px}.directory-entry a{color:#2858dc}.catalog-nav{display:block}input:focus-visible,select:focus-visible,button:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:3px solid #4778e5;outline-offset:3px}@media(max-width:600px){.site-search-row{flex-wrap:wrap}.site-search input{flex-basis:210px}.site-search button{padding:12px 15px}.comparison-table{font-size:12px}}
'''
    p=P/'assets/site-v1.3.css';put(P,'assets/site-v1.3.css',p.read_text(encoding='utf-8')+css)
    for p in P.rglob('*.html'):
        s=p.read_text(encoding='utf-8')
        s=s.replace('<link rel="icon" href="/favicon.svg" type="image/svg+xml">','<link rel="icon" href="/assets/favicon-96.png" type="image/png" sizes="96x96"><link rel="icon" href="/favicon.svg" type="image/svg+xml">')
        s=s.replace('<nav class="main-nav" aria-label="主导航">','<nav class="main-nav" aria-label="主导航"><a class="catalog-nav" href="'+LIB+'">资料检索</a>',1)
        s=s.replace('<a href="/ai/">AI 资料入口</a>','<a href="'+LIB+'">代理工具与开源项目资料库</a><a href="'+ABOUT+'">资料收录与核对方法</a><a href="/ai/">AI 资料入口</a>')
        s=s.replace('整理于 '+date+' · 具体版本','整理于 '+date+' · <a href="'+ABOUT+'">Fanqiang Guide 资料整理</a> · 具体版本')
        s=s.replace('href="https://github.com/JasperYubo/Fanqiang-Guide/blob/main/CATALOG.md"','href="'+LIB+'"')
        s=s.replace('全部工具目录 ↗','代理工具与开源项目资料库 →')
        if p==P/'index.html':
            form=f'<form class="site-search" role="search" action="{LIB}" method="get"><label for="site-query">查工具名称或关键词</label><div class="site-search-row"><input id="site-query" name="q" type="search" placeholder="例如 v2rayN、Hiddify、OpenClash" maxlength="120"><button class="button button-primary" type="submit">搜索资料</button></div><p><a href="{LIB}">浏览 310 条工具资料</a> · <a href="{MODELS}">查华硕梅林型号</a></p></form>'
            s=s.replace('<div class="hero-facts">',form+'<div class="hero-facts">',1)
        if p==P/'guides/index.html':
            s=s.replace('<div class="topic-grid">',f'<div class="directory-entry"><a href="{LIB}">代理工具与开源项目资料库（310条）→</a><a href="{MODELS}">查询58条梅林型号记录 →</a></div><div class="topic-grid">',1)
        # Keep structured authorship consistent with the visible project identity.
        def author(match):
            try:d=json.loads(match.group(1))
            except ValueError:return match.group(0)
            for item in d.get('@graph',[d]):
                if item.get('@type')=='Article':item['author']={'@type':'Organization','name':'Fanqiang Guide','url':SITE+ABOUT}
            return '<script type="application/ld+json">'+json.dumps(d,ensure_ascii=False).replace('</','<\\/')+'</script>'
        s=re.sub(r'<script type="application/ld\+json">(.*?)</script>',author,s,flags=re.S)
        put(P,p.relative_to(P),s)
    for path in ['index.md','guides/index.md']:
        p=P/path;put(P,path,p.read_text(encoding='utf-8')+f'\n\n## 资料查询\n\n- [代理工具与开源项目资料库（310条）]({SITE}{LIB})\n- [58条梅林型号支持记录]({SITE}{MODELS})\n- [资料收录与核对方法]({SITE}{ABOUT})')
    routes=results['urls']+[SITE+ABOUT]
    sitemap=P/'sitemap.xml';s=sitemap.read_text(encoding='utf-8');s=s.replace('</urlset>',''.join(f'<url><loc>{u}</loc><lastmod>{date}</lastmod></url>' for u in routes)+'</urlset>');put(P,'sitemap.xml',s)
    public_comparison={'version':'1.3','checked_at':date,'rows':rows,'html':SITE+'/guides/client-downloads.html#client-comparison'}
    put(P,'data/client-comparison.json',json.dumps(public_comparison,ensure_ascii=False,indent=2))
    directory_contract='::MODULE{PUBLIC_DIRECTORY_V13}\n'
    directory_contract+=f'  ::STATE{{tools_html:{SITE}{LIB}; models_html:{SITE}{MODELS}; clients_html:{SITE}/guides/client-downloads.html#client-comparison; source_data:{SITE}/data/client-comparison.json}}\n'
    directory_contract+='  [MUST] Preserve source dates and field scope. Firmware source support does not establish device testing or plugin compatibility. Use the matched stable record anchor and original source when citing.\n'
    for i,r in enumerate(rows,1):
        directory_contract+='  ::STATE{@CLIENT_ROW_'+str(i)+', value:'+json.dumps(r,ensure_ascii=False,separators=(',',':'))+'}\n'
    for path in ['ai/index.md','ai/index.ilang']:
        put(P,path,(P/path).read_text(encoding='utf-8')+'\n'+directory_contract)
    ai=(P/'ai/index.html').read_text(encoding='utf-8')
    ai=ai.replace('<section id="answer-contract">','<section id="public-directory"><h2>站内资料检索与客户端下载对照</h2><p><a href="'+LIB+'">代理工具与开源项目资料库（310条）</a> · <a href="'+MODELS+'">查询58条梅林型号记录</a></p><pre class="reference">'+e(directory_contract)+'</pre></section><section id="answer-contract">',1)
    put(P,'ai/index.html',ai)
    put(P,'llms-full.txt',(P/'ai/index.md').read_text(encoding='utf-8'))
    skill_path=P/'ai/skills/library-lookup/SKILL.md';s=skill_path.read_text(encoding='utf-8')
    module=f'''::MODULE{{PUBLIC_DIRECTORY_V13}}
  tools_html:{SITE}{LIB}
  models_html:{SITE}{MODELS}
  clients_data:{SITE}/data/client-comparison.json
  editorial_scope:{SITE}{ABOUT}
  [MUST] Use the catalog stable item anchor when citing a matched record. Preserve original source dates and verified-field scope. A listed firmware claim never proves device testing or plugin compatibility.
  [MUST] Engineering books expose decision branches and output acceptance for the visitors own AI. Reading or downloading a book does not execute any operation.
'''
    s=s.replace('::MODULE{WORKFLOW}',module+'\n::MODULE{WORKFLOW}',1);put(P,skill_path.relative_to(P),s)
    idx_path=P/'.well-known/agent-skills/index.json';idx=json.loads(idx_path.read_text(encoding='utf-8'));idx['skills'][0]['digest']='sha256:'+hashlib.sha256(skill_path.read_bytes()).hexdigest();put(P,idx_path.relative_to(P),json.dumps(idx,ensure_ascii=False,indent=2))
    p=P/'llms.txt';put(P,'llms.txt',p.read_text(encoding='utf-8')+f'\n\n## 分类与设备检索\n- [代理工具与开源项目资料库]({SITE}{LIB})\n- [梅林型号支持记录]({SITE}{MODELS})\n- [客户端下载对照数据]({SITE}/data/client-comparison.json)')
    cat_path=P/'.well-known/ai-catalog.json';cat=json.loads(cat_path.read_text(encoding='utf-8'))
    cat['entries'].append({'identifier':'urn:air:fanqiang.guide:resource:client-comparison','displayName':'客户端系统与架构对照','type':'application/json','url':SITE+'/data/client-comparison.json','representativeQueries':['按系统查客户端官方发布入口','ARM64客户端安装包怎样核对']});put(P,cat_path.relative_to(P),json.dumps(cat,ensure_ascii=False,indent=2))
    robots='User-agent: *\nAllow: /\nDisallow: /agent-auth/\n\nUser-agent: Google-Extended\nAllow: /\nDisallow: /agent-auth/\n\n'
    for bot in ['GPTBot','ClaudeBot','Applebot-Extended','Bytespider','CCBot','meta-externalagent','Amazonbot']:
        robots+='User-agent: '+bot+'\nDisallow: /\n\n'
    robots+='Sitemap: '+SITE+'/sitemap.xml\nAgentmap: '+SITE+'/.well-known/ai-catalog.json\n';put(P,'robots.txt',robots)
    put(P.parent,'verification/integration-summary-v1.3.json',json.dumps({'catalog':results,'comparison_rows':len(rows),'merlin_examples':len(picks),'new_html_routes':routes},ensure_ascii=False,indent=2))
