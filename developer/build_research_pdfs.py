#!/usr/bin/env python3
"""Build the four research PDFs from their canonical JSON manuscripts on Linux."""
from pathlib import Path
from html import escape
import argparse,json,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
CSS="""@page{size:A4;margin:20mm 19mm 20mm}*{box-sizing:border-box}body{font-family:"Noto Sans SC","Noto Sans CJK SC",sans-serif;color:#172b43;font-size:10.25pt;line-height:1.62;margin:0}h1{font-size:22pt;line-height:1.38;margin:8mm 0 4mm;font-weight:700;letter-spacing:-.2pt}h2{font-size:13.4pt;line-height:1.45;margin:6mm 0 3mm;break-after:avoid}p{margin:0 0 3mm;orphans:3;widows:3}a{color:#215cbd;text-decoration:none;overflow-wrap:anywhere}.eyebrow{font-size:9pt;letter-spacing:1.6pt;color:#215cbd}.subtitle{font-size:12pt;line-height:1.45;color:#50627a}.byline{font-size:9pt;line-height:1.7;border-top:1px solid #ccd7e5;border-bottom:1px solid #ccd7e5;padding:3mm 0;margin:4mm 0}.abstract{font-size:10pt}.abstract-en{font-size:9pt;line-height:1.6;color:#334962}li{margin:0 0 2.8mm;orphans:2;widows:2}.references{font-size:8.6pt;line-height:1.6;list-style:none;padding:0}.references li{break-inside:avoid;margin:0 0 3mm}.refs-label{font-weight:600}.small{font-size:8.5pt;color:#50627a}.related{border-top:1px solid #ccd7e5;margin-top:2mm;padding-top:2mm}.lic{font-size:8pt;color:#50627a;margin-top:4mm}"""
def render(d,records):
 e=lambda v:escape(str(v),quote=True)
 by="; ".join(e(a["name"])+" · "+e(a.get("affiliation",""))+' · <a href="https://orcid.org/'+e(a["orcid"])+'">ORCID '+e(a["orcid"])+"</a>" for a in d["creators"])
 kind="技术报告" if d["type"]=="technicalreport" else "技术说明"
 body='<div class="eyebrow">FANQIANG GUIDE · RESEARCH</div><h1>'+e(d["title"])+'</h1><p class="subtitle">'+e(d["title_en"])+'</p><div class="byline">'+by+'<br>'+kind+' · v'+e(d["version"])+' · '+e(d["publication_date"])+'<br>DOI: <a href="https://doi.org/'+e(d["doi"])+'">'+e(d["doi"])+"</a></div>"
 if d.get("advisors"):body+='<p class="small">学术顾问：'+"；".join(e(a["name"])+' · ORCID '+e(a["orcid"]) for a in d["advisors"])+"</p>"
 body+='<h2>摘要</h2><p class="abstract">'+e(d["abstract"])+'</p><p class="abstract-en" lang="en">'+e(d.get("abstract_en",""))+"</p>"
 for s in d["sections"]:
  body+="<h2>"+e(s["title"])+"</h2>"
  body+="".join("<p>"+e(x)+"</p>" for x in s["paragraphs"])
  if s.get("items"):body+="<ul>"+"".join("<li>"+e(x)+"</li>" for x in s["items"])+"</ul>"
 body+='<h2>参考文献</h2><ol class="references">'
 for n,r in enumerate(d["references"],1):
  authors=r.get("authors","");authors="; ".join(authors) if isinstance(authors,list) else authors
  body+='<li><span class="refs-label">['+e(r.get("id",n))+"]</span> "+e(authors)+" ("+e(r.get("year",""))+"). "+e(r["title"])+'. <a href="'+e(r["url"])+'">'+e(r.get("doi",r["url"]))+"</a>."
  for a in r.get("author_identifiers",[]):body+='<br>引用作者 '+e(a["name"])+': <a href="https://orcid.org/'+e(a["orcid"])+'">ORCID '+e(a["orcid"])+"</a>."
  body+="</li>"
 body+="</ol>"
 if d.get("related_publications"):
  body+='<div class="related"><p class="small">配套技术文献：'
  for r in d["related_publications"]:
   other=records[r["slug"]];body+=e({'fanqiang-guide-system':'总报告','device-setup-protocol':'设备配置协议','router-package-matching':'路由器包匹配','local-diagnostics-consent':'诊断提交协议'}[r['slug']])+' · <a href="https://doi.org/'+e(r["doi"])+'">'+e(r["doi"])+"</a>； "
  body+="</p></div>"
 body+='<p class="lic">© 2026 Long Quan Zhu. MIT License. 项目：<a href="https://fanqiang.guide/">fanqiang.guide</a>。本报告以独立技术文献发布。</p>'
 return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>'+e(d["title"])+"</title><style>"+CSS+"</style></head><body>"+body+"</body></html>"
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("--playwright-module",required=True,help="Absolute path to an installed Playwright module")
 parser.add_argument("--output",type=Path,default=ROOT/"research/pdfs")
 parser.add_argument("--work",type=Path,required=True)
 args=parser.parse_args()
 data=json.loads((ROOT/"research/publications.json").read_text())
 rows=data["publications"];records={d["slug"]:d for d in rows}
 args.work.mkdir(parents=True,exist_ok=True);args.output.mkdir(parents=True,exist_ok=True)
 jobs=[]
 for d in rows:
  source=args.work/(d["slug"]+".html");source.write_text(render(d,records))
  jobs.append({"html":source.as_uri(),"pdf":str((args.output/(d["slug"]+".pdf")).resolve()),"doi":d["doi"]})
 config=args.work/"jobs.json";config.write_text(json.dumps(jobs))
 js=args.work/"render.mjs"
 js.write_text("""import {pathToFileURL} from 'node:url';import fs from 'node:fs';
const {chromium}=await import(pathToFileURL(process.argv[2]).href);
const jobs=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const browser=await chromium.launch({headless:true});
try{for(const job of jobs){const page=await browser.newPage();await page.goto(job.html);await page.evaluate(()=>document.fonts.ready);await page.pdf({path:job.pdf,format:'A4',printBackground:true,preferCSSPageSize:true,displayHeaderFooter:true,headerTemplate:'<div style="font-size:8px;color:#64748b;width:100%;text-align:right;margin-right:72px">DOI '+job.doi+'</div>',footerTemplate:'<div style="font-size:8px;color:#64748b;width:100%;text-align:center"><span class="pageNumber"></span> / <span class="totalPages"></span></div>'});await page.close();console.log(JSON.stringify({pdf:job.pdf}));}}finally{await browser.close();}
""")
 subprocess.run(["node",str(js),args.playwright_module,str(config)],check=True)
if __name__=="__main__":main()
