#!/usr/bin/python3.11
"""Export a whitelisted read-only view of the local wiki for nginx."""
import fcntl
import datetime as dt
import json
import pathlib
import shutil
import wiki
import runtime

root=pathlib.Path(__file__).resolve().parent
out=runtime.WIKI_OUTPUT
out.mkdir(parents=True,exist_ok=True)
export_lock=(out/'.export.lock').open('a')
fcntl.flock(export_lock,fcntl.LOCK_EX)
cards=[]
for c in wiki.load():
    good,why=wiki.eligible(c);m=c.get('metrics',{})
    cards.append({k:c.get(k) for k in ('id','title','url','platform','author','tags','analysis','patterns','analysis_model','analysis_at','analysis_method')}|{
        'eligible':good,'reasons':why,
        'metrics':{k:m.get(k) for k in ('metric_label','likes','comments','observed_at')}})
docs=[]
for p in [wiki.ROOT/'wiki/reader-preferences.md',*sorted((wiki.ROOT/'wiki/patterns').glob('*.md'))]:
    content=p.read_text();docs.append({'title':content.splitlines()[0].lstrip('# '),'content':content})
data={'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'cards':cards,'documents':docs,
      'platforms':{k:v['label'] for k,v in wiki.POLICY['platforms'].items()},
      'policy':{k:v for k,v in wiki.POLICY.items() if k in ('platforms','metric_max_age_days','rule')}}
data['memes']=[{k:c.get(k) for k in ('id','name','title','meaning','origin_boundary','usage','avoid','example','tags','analysis_model','updated_at')}|{'heat_status':wiki.meme_status(c),'sources':[{k:s.get(k) for k in ('url','title','published_at','observed_at','retrieval','transport_verified')} for s in c.get('sources',[])]} for c in wiki.load_memes()]
collection_path=wiki.ROOT/'collection-status.json'
collection=json.loads(collection_path.read_text()) if collection_path.exists() else {}
data['collection']={k:collection.get(k) for k in ('status','model','started_at','finished_at','articles_added','memes_added','candidates_checked')}
config_path=root/'wiki-collect-config.json'
config=json.loads(config_path.read_text()) if config_path.exists() else {}
data['collection']['schedule']={k:config.get(k) for k in ('enabled','time','timezone','model','article_limit')}
for key,filename in [('meme_sites','meme-sites-status.json'),('daily_materials','daily-materials.json')]:
    path=wiki.ROOT/filename
    data[key]=json.loads(path.read_text()) if path.exists() else ([] if key=='meme_sites' else {})
agent_path=wiki.ROOT/'material-agent-status.json'
agent=json.loads(agent_path.read_text()) if agent_path.exists() else {}
data['material_agent']={k:agent.get(k) for k in ('agent','model','tools','status','started_at','finished_at','sites_checked','materials_added','memes_added')}
for name in ('index.html','app.js','style.css'):
    source=root/'server-site'/name;dest=out/name
    if not dest.exists() or source.read_bytes()!=dest.read_bytes():
        tmp=dest.with_suffix(dest.suffix+'.tmp');shutil.copyfile(source,tmp);tmp.chmod(0o644);tmp.replace(dest)
tmp=out/'data.json.tmp';tmp.write_text(json.dumps(data,ensure_ascii=False));tmp.chmod(0o644);tmp.replace(out/'data.json')
out.chmod(0o755)
print(json.dumps({'cards':len(cards),'eligible':sum(c['eligible'] for c in cards),'updated_at':data['updated_at']}))
