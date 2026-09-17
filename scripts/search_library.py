"""Portable local search; no server or API key required."""
import argparse,json,sqlite3,sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')
p=argparse.ArgumentParser()
p.add_argument('query');p.add_argument('--reviewed',action='store_true');p.add_argument('--kind');p.add_argument('--limit',type=int,default=15)
a=p.parse_args()
db=Path(__file__).resolve().parents[1]/'export'/'library-v0.1-2026-09-11.sqlite'
c=sqlite3.connect(f'file:{db.as_posix()}?mode=ro',uri=True)
terms=a.query.split()
sql='SELECT e.id,e.name,e.kind,e.status,e.json FROM entities e JOIN search s ON e.id=s.id WHERE '
conditions=[];params=[]
for term in terms:
    conditions.append('(s.name LIKE ? ESCAPE \'\\\' OR s.body LIKE ? ESCAPE \'\\\')')
    term=term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    params += ['%'+term+'%']*2
if a.reviewed:conditions.append('e.status=?');params.append('primary_reviewed')
if a.kind:conditions.append('e.kind=?');params.append(a.kind)
sql+=' AND '.join(conditions)+' ORDER BY CASE e.status WHEN \'primary_reviewed\' THEN 0 ELSE 1 END,e.name LIMIT ?'
params.append(a.limit)
for ident,name,kind,status,data in c.execute(sql,params):
    r=json.loads(data)
    print(json.dumps({'id':ident,'name':name,'kind':kind,'status':status,'summary':r['summary'],'sources':r['official_urls'] or r['discovery_sources']},ensure_ascii=False))
if not a.kind or a.kind=='hardware_compatibility':
    modelconds=[];modelparams=[]
    for term in terms:
        modelconds.append('search_text LIKE ? ESCAPE \'\\\'')
        modelparams.append('%'+term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    modelparams.append(a.limit)
    for row in c.execute('SELECT json FROM hardware_compatibility WHERE '+' AND '.join(modelconds)+' ORDER BY model LIMIT ?',modelparams):
        item=json.loads(row[0]);item['kind']='hardware_compatibility'
        print(json.dumps(item,ensure_ascii=False))
