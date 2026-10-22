#!/usr/bin/python3.11
"""Small source-grounded writing wiki: refresh, compile, lint and retrieve."""
import argparse,collections,datetime as dt,hashlib,json,math,pathlib,re,sys,urllib.parse
import requests
from bs4 import BeautifulSoup
ROOT=pathlib.Path(__file__).resolve().parent/'writing-wiki'
POLICY=json.loads((ROOT/'policy.json').read_text())
def load():return json.loads((ROOT/'catalog.json').read_text())
def save(path,data):
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def eligible(card):
 reasons=[];m=card.get('metrics',{});p=POLICY['platforms'].get(card['platform'])
 if card.get('analysis_status')!='reviewed':reasons.append('结构分析未完成')
 if not card.get('full_text_read'):reasons.append('未确认读到全文')
 if not p:reasons.append('平台门槛未配置')
 if m.get('verification') not in ('live_dom','live_public_html'):reasons.append('缺少原页面指标证据')
 like=m.get('likes');comment=m.get('comments')
 if not isinstance(like,int) or like<0:reasons.append('支持数未知')
 elif p and not(like>=p['high_likes'] or like>=p['min_likes'] and isinstance(comment,int) and comment>=p['min_comments']):reasons.append('互动未达门槛')
 try:
  stamp=dt.datetime.fromisoformat(m['observed_at'].replace('Z','+00:00'));age=(dt.datetime.now(dt.timezone.utc)-stamp).total_seconds()/86400
  if age<-.01 or age>POLICY['metric_max_age_days']:reasons.append('互动证据已过期或日期异常')
 except (ValueError,KeyError,TypeError):reasons.append('观测时间缺失')
 proof=ROOT/m.get('evidence_path','missing')
 if not proof.is_file():reasons.append('证据文件缺失')
 else:
  evidence=json.loads(proof.read_text())
  for key in ('url','likes','comments','observed_at','verification'):
   expected=card['url'] if key=='url' else m.get(key)
   if evidence.get(key)!=expected:reasons.append('证据与记录不一致');break
 return not reasons,reasons

def refresh_sspai(card):
 url=card['url']
 if not re.fullmatch(r'https://sspai\.com/post/\d+',url):raise ValueError('非标准少数派文章URL')
 r=requests.get(url,timeout=25);r.raise_for_status();s=BeautifulSoup(r.text,'html.parser')
 charge=s.select_one('.article__bar__action--charge .article__bar__action__count');comments=s.select_one('.article__bar__action--comment .article__bar__action__count');body=s.select_one('.article-body')
 if not charge or not comments or not body:raise ValueError('公开页面缺少指标或全文，未猜测数字')
 if not charge.get_text(strip=True).isdigit() or not comments.get_text(strip=True).isdigit():raise ValueError('计数格式未知')
 stamp=dt.datetime.now(dt.timezone.utc).isoformat();content=body.get_text(' ',strip=True)
 proof={'platform':'sspai','url':url,'observed_at':stamp,'verification':'live_public_html','metric_label':'充电','likes':int(charge.get_text()),'comments':int(comments.get_text()),'body_length':len(content),'body_sha256':hashlib.sha256(content.encode()).hexdigest(),'evidence':{'likes_selector':'.article__bar__action--charge .article__bar__action__count','comments_selector':'.article__bar__action--comment .article__bar__action__count','likes_text':charge.get_text(),'comments_text':comments.get_text()}}
 name=f"raw/{card['id']}/{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json";p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(proof,f,ensure_ascii=False,indent=2)
 card['metrics']={k:proof[k] for k in ('observed_at','verification','metric_label','likes','comments')};card['metrics']['evidence_path']=name
 card['last_refresh_error']=None

def compile_wiki(cards):
 out=['# 写作参考索引','',f'编译时间：{dt.datetime.now().astimezone().isoformat()}','', '[使用规则](../README.md) · [读者偏好](reader-preferences.md) · [观察与重新解释](patterns/observation-reframe.md) · [反方与边界](patterns/objection-boundary.md)','', '|文章|平台|支持数（原名）|评论|状态|','|---|---|---:|---:|---|']
 for c in cards:
  ok,why=eligible(c);m=c.get('metrics',{});label=m.get('metric_label','未知')
  out.append(f"|[{c['title']}](cards/{c['id']}.md)|{c['platform']}|{m.get('likes','未知')}（{label}）|{m.get('comments','未知')}|{'可用' if ok else '候选：'+ '；'.join(why)}|")
  lines=[f"# {c['title']}",'',f"原文：{c['url']}",f"平台：{c['platform']}；作者：{c.get('author') or '见原文，未单独核实'}",f"互动：{m.get('likes','未知')} {label}；{m.get('comments','未知')} 评论；观测：{m.get('observed_at','未取得')}",f"状态：{'可用' if ok else '候选：'+'；'.join(why)}",'', '## 写作拆解']
  for k,v in c.get('analysis',{}).items():lines.extend(['',f'**{k}**：'+(' → '.join(v) if isinstance(v,list) else str(v))])
  lines+=['', '## 可追溯性',f"指标证据：[{m.get('evidence_path','尚无')}]({'../../'+m['evidence_path'] if m.get('evidence_path') else c['url']})",'', '关联：'+'、'.join(f'[{x}](../patterns/{x}.md)' for x in c.get('patterns',[]))]
  (ROOT/'wiki/cards'/f"{c['id']}.md").write_text('\n'.join(lines)+'\n')
 (ROOT/'wiki/index.md').write_text('\n'.join(out)+'\n')

def tokens(t):
 t=t.lower();words=re.findall(r'[a-z][a-z0-9_-]*',t)
 for run in re.findall(r'[\u4e00-\u9fff]+',t):
  words += [run[i:i+n] for n in (2,3) for i in range(max(0,len(run)-n+1))]
 return collections.Counter(words)

def load_memes():
 p=ROOT/'memes.json'
 return json.loads(p.read_text()) if p.exists() else []

def meme_status(card):
 dates=[]
 for source in card.get('sources',[]):
  try:dates.append(dt.date.fromisoformat(source.get('published_at') or ''))
  except ValueError:pass
 today=dt.datetime.now(dt.timezone.utc).date()
 return '近期有报道' if any(0<=(today-d).days<=30 for d in dates) else '历史收录 / 当前热度未核实'

def meme_search(query,limit=4):
 q=tokens(query);hits=[]
 for c in load_memes():
  if not c.get('sources'):continue
  text=tokens(' '.join(str(c.get(k,'')) for k in ('name','meaning','usage','avoid')))
  score=sum(text[t] for t in q)
  if score:hits.append({**c,'heat_status':meme_status(c),'score':score})
 return sorted(hits,key=lambda c:-c['score'])[:limit]

def validate_plan(article):
 plan=article.get('writing_plan',{})
 refs=plan.get('references',[])
 ids=[r.get('id') for r in refs]
 approved={c['id'] for c in load() if eligible(c)[0]}
 if len(set(ids))<POLICY['min_references_per_article'] or any(i not in approved for i in ids):
  raise ValueError('文章缺少至少2篇当前通过互动门槛的范文，未继续发布')
 if any(not r.get('learn') or not r.get('adapt') for r in refs):raise ValueError('缺少具体借鉴与迁移说明')
 if not all(plan.get(k) for k in ('reader_question','thesis','strongest_objection','evidence_boundary','changes_after_review')) or len(plan.get('outline',[]))<3:
  raise ValueError('写作计划缺少具体判断、提纲、边界或修改记录')
 return True

def search(query,limit=4):
 cards=[c for c in load() if eligible(c)[0]];qt=tokens(query);docs=[]
 for c in cards:
  # Themes and reader tensions weigh more than the title alone.
  text=' '.join([c['title'], ' '.join(c.get('tags',[]))*3,json.dumps(c.get('analysis',{}),ensure_ascii=False)])
  docs.append((c,tokens(text)))
 df=collections.Counter(t for _,d in docs for t in d)
 result=[]
 for c,d in docs:
  score=sum((1+math.log(1+d[t]))*math.log(1+(len(docs)+1)/(df[t]+.5)) for t in qt if d[t])
  if score<=0:continue
  result.append({'id':c['id'],'title':c['title'],'score':round(score,3),'url':c['url'],'metrics':c['metrics'],'tags':c.get('tags',[]),'analysis':c.get('analysis',{}),'card_path':str(ROOT/'wiki/cards'/f"{c['id']}.md")})
 return sorted(result,key=lambda x:(-x['score'],x['id']))[:limit]

def main():
 ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True)
 sp.add_parser('refresh');sp.add_parser('compile');sp.add_parser('lint')
 p=sp.add_parser('search');p.add_argument('--query',required=True);p.add_argument('--limit',type=int,default=4)
 p=sp.add_parser('import-proof');p.add_argument('--id',required=True);p.add_argument('--path',required=True)
 a=ap.parse_args();cards=load()
 if a.cmd=='search':
  hits=search(a.query,a.limit);print(json.dumps({'query':a.query,'results':hits},ensure_ascii=False,indent=2));return
 if a.cmd=='refresh':
  for c in cards:
   if c['platform']=='sspai':
    try:refresh_sspai(c)
    except Exception as ex:c['last_refresh_error']=str(ex)
  save(ROOT/'catalog.json',cards)
 if a.cmd=='import-proof':
  proof=pathlib.Path(a.path).resolve();rel=proof.relative_to(ROOT);d=json.loads(proof.read_text());c=next(c for c in cards if c['id']==a.id)
  if d['url']!=c['url'] or d['platform']!=c['platform']:raise ValueError('证据目标不匹配')
  c['metrics']={k:d[k] for k in ('observed_at','verification','metric_label','likes','comments')};c['metrics']['evidence_path']=str(rel);save(ROOT/'catalog.json',cards)
 compile_wiki(cards)
 states=[{'id':c['id'],'eligible':eligible(c)[0],'reasons':eligible(c)[1]} for c in cards]
 if a.cmd=='lint':
  ids=[c['id'] for c in cards]
  if len(ids)!=len(set(ids)):raise ValueError('重复卡片ID')
  for c in cards:
   for p in c.get('patterns',[]):
    if not (ROOT/'wiki/patterns'/f'{p}.md').exists():raise ValueError('失效写法链接：'+p)
  # Catch broken local Markdown links in the compiled wiki.
  for p in (ROOT/'wiki').rglob('*.md'):
   for link in re.findall(r'\]\(([^)]+)\)',p.read_text()):
    if not link.startswith(('https://','http://','#')) and not (p.parent/link).exists():raise ValueError('断链：'+str(p)+' -> '+link)
 print(json.dumps({'eligible':sum(s['eligible'] for s in states),'candidates':sum(not s['eligible'] for s in states),'states':states},ensure_ascii=False,indent=2))
if __name__=='__main__':
 import fcntl
 with (ROOT/'.catalog.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  main()
