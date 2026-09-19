from pathlib import Path
import json, re, html, hashlib, gzip, subprocess, sys

B=Path(__file__).resolve().parent; P=B/'public'
OLD=B.parent/'fanqiang-ar100-v1.1-2026-09-12/public'
data=json.loads((P/'data/guides.json').read_text(encoding='utf-8'))
guides=data['topics'];checks=[]
def check(name,ok):
    checks.append({'name':name,'passed':bool(ok)})
def stable_hash_matches(path, expected):
    payload=path.read_bytes()
    if hashlib.sha256(payload).hexdigest()==expected:return True
    if path.suffix.lower() not in {'.html','.txt','.md','.json','.xml','.js','.css','.ilang'}:return False
    normalized=payload.replace(b'\r\n',b'\n')
    candidates=(normalized,normalized.replace(b'\n',b'\r\n'))
    return any(hashlib.sha256(item).hexdigest()==expected for item in candidates)
def schemas(raw):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>',raw,re.S)]
def faq_from_html(raw):
    return [x for d in schemas(raw) for x in d.get('@graph',[]) if x.get('@type')=='FAQPage'][0]['mainEntity']
check('thirteen_topics',len(guides)==13)
seen=[]
for g in guides:
    stem='guides/'+g['slug'];raw=(P/(stem+'.html')).read_text(encoding='utf-8');md=(P/(stem+'.md')).read_text(encoding='utf-8');book=(P/(stem+'.ilang')).read_text(encoding='utf-8')
    structured=faq_from_html(raw)
    check(g['slug']+': faq_count_consistent',len(structured)==len(g['faq']))
    for i,f in enumerate(g['faq'],1):
        q=f['question'];seen.append(q)
        check(g['slug']+f': question_{i}',html.escape(q) in raw and html.escape(f['answer']) in raw and q in md and f['answer'] in md and q in book and f['answer'] in book and structured[i-1]['name']==q and structured[i-1]['acceptedAnswer']['text']==f['answer'] and f['url'].endswith('#question-'+str(i)) and f'id="question-{i}"' in raw and len(f['sources'])>0)
check('unique_question_intents_as_text',len(seen)==len(set(seen)))
home=(P/'index.html').read_text(encoding='utf-8');home_md=(P/'index.md').read_text(encoding='utf-8')
home_faq=faq_from_html(home)
check('eight_visible_home_answers',len(home_faq)==8 and all(html.escape(f['name']) in home and html.escape(f['acceptedAnswer']['text']) in home and f['name'] in home_md for f in home_faq))
check('homepage_topic_identity', '翻墙与科学上网工具指南 | Fanqiang Guide' in home and 'id="hero-title">翻墙与科学上网' in home)
check('homepage_ladder_term', '梯子' in home and '梯子' in home_md)
for slug in ('ladder-vpn-proxy','airport-subscription-nodes','router-guide'):
    relative='/guides/'+slug+'.html'
    check('homepage_new_topic_link:'+slug, 'href="'+relative+'"' in home and 'https://fanqiang.guide'+relative in home_md)
check('official_docs_kept', 'href="https://xtls.github.io/"' in home and 'href="https://sing-box.sagernet.org/"' in home)
for rel in ('data/library.json','data/merlin-models.json','robots.txt','auth.md'):
    check(rel+': frozen_input_hash', stable_hash_matches(P/rel,json.loads((B/'content-invariants-v1.0.json').read_text(encoding='utf-8'))[rel]))
check('llms_full_consistent',(P/'llms-full.txt').read_bytes()==(P/'ai/index.md').read_bytes())
check('no_editorial_probability_public',not any('largest_observed_intent_query' in (P/r).read_text(encoding='utf-8') for r in ('data/guides.json','index.html','ai/index.md')))
gsc_name='google35643466072986f6.html'
gsc_expected=b'google-site-verification: google35643466072986f6.html'
ga4_id='G-V0RLGGS7FB'
check('gsc_verification_exact',(P/gsc_name).read_bytes()==(B/'verification'/gsc_name).read_bytes()==gsc_expected)
check('sitemap_not_precompressed',not (P/'sitemap.xml.gz').exists())
for path in sorted(P.rglob('*.html')):
    if path.name==gsc_name:continue
    raw=path.read_text(encoding='utf-8')
    rel=path.relative_to(P).as_posix()
    check(rel+': ga4_once',raw.count('<!-- Google tag (gtag.js) -->')==1 and raw.count('googletagmanager.com/gtag/js?id='+ga4_id)==1 and raw.count("gtag('config', '"+ga4_id+"');")==1)
manifest=json.loads((B/'release-manifest-v1.4-2026-09-13.json').read_text(encoding='utf-8'))
for rel,digest in manifest.items():
    path=P/rel
    check(rel+': hash',stable_hash_matches(path,digest))
    if path.with_name(path.name+'.gz').exists():check(rel+': gzip',gzip.decompress(path.with_name(path.name+'.gz').read_bytes())==path.read_bytes())
validator=B.parents[1]/'tools/ilang_grammar_validator.py'
run=subprocess.run([sys.executable,'-X','utf8',str(validator),'--lint',*map(str,(P/'guides').glob('*.ilang')),'--strict','--json'],capture_output=True,text=True,encoding='utf-8',check=True)
lint=json.loads(run.stdout);check('all_engineering_books_valid',lint['errors']==0 and lint['warnings']==0)
out={'questions':len(seen),'home_questions':len(home_faq),'checks':checks,'lint':lint}
(B/'verification-content-v1.4-2026-09-13.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'questions':len(seen),'checks':len(checks),'failures':[c for c in checks if not c['passed']]},ensure_ascii=False))
assert all(c['passed'] for c in checks)
