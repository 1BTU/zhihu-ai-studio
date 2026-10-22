#!/usr/bin/python3.11
"""Export a whitelisted read-only view of the local wiki for nginx."""
import datetime as dt
import json
import pathlib
import shutil
import wiki
import runtime

root=pathlib.Path(__file__).resolve().parent
out=runtime.WIKI_OUTPUT
out.mkdir(parents=True,exist_ok=True)
cards=[]
for c in wiki.load():
    good,why=wiki.eligible(c);m=c.get('metrics',{})
    cards.append({k:c.get(k) for k in ('id','title','url','platform','author','tags','analysis','patterns')}|{
        'eligible':good,'reasons':why,
        'metrics':{k:m.get(k) for k in ('metric_label','likes','comments','observed_at')}})
docs=[]
for p in [wiki.ROOT/'wiki/reader-preferences.md',*sorted((wiki.ROOT/'wiki/patterns').glob('*.md'))]:
    content=p.read_text();docs.append({'title':content.splitlines()[0].lstrip('# '),'content':content})
data={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'cards':cards,'documents':docs,
      'platforms':{k:v['label'] for k,v in wiki.POLICY['platforms'].items()},
      'policy':{k:v for k,v in wiki.POLICY.items() if k in ('platforms','metric_max_age_days','rule')}}
for name in ('index.html','app.js','style.css'):
    source=root/'server-site'/name;dest=out/name
    if not dest.exists() or source.read_bytes()!=dest.read_bytes():
        tmp=dest.with_suffix(dest.suffix+'.tmp');shutil.copyfile(source,tmp);tmp.chmod(0o644);tmp.replace(dest)
tmp=out/'data.json.tmp';tmp.write_text(json.dumps(data,ensure_ascii=False));tmp.chmod(0o644);tmp.replace(out/'data.json')
out.chmod(0o755)
print(json.dumps({'cards':len(cards),'eligible':sum(c['eligible'] for c in cards),'updated_at':data['updated_at']}))
