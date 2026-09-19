from pathlib import Path
import json, re, html, hashlib, gzip, subprocess, sys

B=Path(__file__).resolve().parent; P=B/'public'
OLD=B.parent/'fanqiang-ar100-v1.1-2026-09-12/public'
data=json.loads((P/'data/guides.json').read_text(encoding='utf-8'))
guides=data['topics'];checks=[]
def check(name,ok):
    checks.append({'name':name,'passed':bool(ok)})
def schemas(raw):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>',raw,re.S)]
def faq_from_html(raw):
    return [x for d in schemas(raw) for x in d.get('@graph',[]) if x.get('@type')=='FAQPage'][0]['mainEntity']
check('ten_existing_topics',len(guides)==10)
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
check('official_docs_kept', 'href="https://xtls.github.io/"' in home and 'href="https://sing-box.sagernet.org/"' in home)
for rel in ('data/library.json','data/merlin-models.json','robots.txt','auth.md'):
    check(rel+': frozen_input_hash', hashlib.sha256((P/rel).read_bytes()).hexdigest()==json.loads((B/'content-invariants-v1.0.json').read_text(encoding='utf-8'))[rel])
check('llms_full_consistent',(P/'llms-full.txt').read_bytes()==(P/'ai/index.md').read_bytes())
check('no_editorial_probability_public',not any('largest_observed_intent_query' in (P/r).read_text(encoding='utf-8') for r in ('data/guides.json','index.html','ai/index.md')))
manifest=json.loads((B/'release-manifest-v1.4-2026-09-13.json').read_text(encoding='utf-8'))
for rel,digest in manifest.items():
    path=P/rel
    check(rel+': hash',hashlib.sha256(path.read_bytes()).hexdigest()==digest)
    if path.with_name(path.name+'.gz').exists():check(rel+': gzip',gzip.decompress(path.with_name(path.name+'.gz').read_bytes())==path.read_bytes())
validator=B.parents[1]/'tools/ilang_grammar_validator.py'
run=subprocess.run([sys.executable,'-X','utf8',str(validator),'--lint',*map(str,(P/'guides').glob('*.ilang')),'--strict','--json'],capture_output=True,text=True,encoding='utf-8',check=True)
lint=json.loads(run.stdout);check('all_engineering_books_valid',lint['errors']==0 and lint['warnings']==0)
out={'questions':len(seen),'home_questions':len(home_faq),'checks':checks,'lint':lint}
(B/'verification-content-v1.4-2026-09-13.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'questions':len(seen),'checks':len(checks),'failures':[c for c in checks if not c['passed']]},ensure_ascii=False))
assert all(c['passed'] for c in checks)
