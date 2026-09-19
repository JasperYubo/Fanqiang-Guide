"""Apply the site's own answer selection to an already-built public site."""
import html, json, re

SITE='https://fanqiang.guide'
HOME_ORDER=['ladder-vpn-proxy','airport-subscription-nodes','router-guide','client-downloads','shadowrocket-platforms','free-nodes','v2rayn-guide','shadowrocket-qr']
e=html.escape

def write(P,path,text):
    (P/path).write_text(text.rstrip()+'\n',encoding='utf-8')

def fit_answers(P,guides,page,faq_schema):
    by_slug={g['slug']:g for g in guides}
    selected=[(by_slug[s],by_slug[s]['faq'][2 if s=='v2rayn-guide' else 0]) for s in HOME_ORDER]
    faqs=[f for g,f in selected]
    cards=[]
    for g,f in selected:
        sources=' · '.join(f'<a href="{e(s["url"],quote=True)}">{e(s["label"])}</a>' for s in f['sources'])
        cards.append(f'<article class="quick-answer"><h3>{e(f["question"])}</h3><p>{e(f["answer"])}</p><p class="sources">来源：{sources}</p><a class="text-link" href="{e(f["url"],quote=True)}">查看完整答案与资料 →</a></article>')
    section='<section class="section wrap" id="answers"><div class="section-heading"><div><p class="eyebrow">03 / 按问题找答案</p><h2>翻墙与科学上网常见问题</h2></div></div><div class="quick-answers">'+''.join(cards)+'</div></section>'
    p=P/'index.html';text=p.read_text(encoding='utf-8')
    start=text.index('<section class="section wrap" id="answers">')
    end=text.index('<section class="section wrap discovery-section" id="daily">',start)
    text=text[:start]+section+text[end:]
    def schema(match):
        data=json.loads(match.group(1))
        for i,node in enumerate(data.get('@graph',[])):
            if node.get('@type')=='FAQPage':data['@graph'][i]=faq_schema(faqs,SITE+'/#answers')
        return '<script type="application/ld+json">'+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+'</script>'
    text=re.sub(r'<script type="application/ld\+json">(.*?)</script>',schema,text,flags=re.S)
    write(P,'index.html',text)
    text=(P/'index.md').read_text(encoding='utf-8')
    start=text.index('## 科学上网工具常见问题');end=text.index('## 免费节点与代理来源归档',start)
    md=['## 翻墙与科学上网常见问题','']
    for g,f in selected:
        md += ['### '+f['question'],'',f['answer'],'','来源：'+'；'.join(f'[{s["label"]}]({s["url"]})' for s in f['sources']),'',f'[查看完整答案与资料]({f["url"]})','']
    write(P,'index.md',text[:start]+'\n'.join(md)+'\n'+text[end:])
    # Expose the already-visible questions in each guide's table of contents.
    for g in guides:
        path='guides/'+g['slug']+'.html';text=(P/path).read_text(encoding='utf-8')
        old='<a href="#questions">常见问题</a>'
        links=''.join(f'<a href="#question-{i}">{e(f["question"])}</a>' for i,f in enumerate(g['faq'],1))
        assert old in text
        text=text.replace(old,old+links,1)
        write(P,path,text)
    # The public navigation describes useful pages, never private planning data.
    nav=json.loads((P/'data/navigation.json').read_text(encoding='utf-8'))
    nav['answer_entries']=[{'question':f['question'],'url':f['url'],'topic':g['slug']} for g in guides for f in g['faq']]
    write(P,'data/navigation.json',json.dumps(nav,ensure_ascii=False,indent=2))
    text=(P/'llms.txt').read_text(encoding='utf-8')
    text+='\n\n## 常见问题直达\n'+'\n'.join(f'- [{f["question"]}]({f["url"]})' for g,f in selected)
    write(P,'llms.txt',text)
