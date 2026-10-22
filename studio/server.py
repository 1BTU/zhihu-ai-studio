#!/usr/bin/python3.11
"""Private, loopback-only writing operations UI. Nginx supplies authentication."""
import contextlib,datetime as dt,fcntl,hashlib,json,mimetypes,os,pathlib,re,sqlite3,subprocess,sys,threading,time,uuid
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import daily,wiki,runtime
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from streaming import run_agent as realtime_agent
import auth,providers,domain,feedback
os.umask(0o077)
DATA=ROOT/'private/studio';DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'studio.sqlite3';FILES=pathlib.Path(__file__).parent
ORIGIN=runtime.ORIGIN;NODE=runtime.NODE
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def conn():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;return c
@contextlib.contextmanager
def database():
 c=conn()
 try:
  with c:yield c
 finally:c.close()
def init():
 with database() as c:
  c.executescript('''PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS articles(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',data TEXT NOT NULL DEFAULT '{}',url TEXT UNIQUE,status TEXT NOT NULL,review_status TEXT,origin TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,job_dir TEXT);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL,result TEXT,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,role TEXT NOT NULL,content TEXT NOT NULL,article_id TEXT,job_id TEXT,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS metrics(id INTEGER PRIMARY KEY,article_id TEXT NOT NULL,observed_at TEXT NOT NULL,views INTEGER,likes INTEGER,comments INTEGER,favorites INTEGER,raw TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS metric_article ON metrics(article_id,id);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS stream_events(id INTEGER PRIMARY KEY,job_id TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS stream_job ON stream_events(job_id,id);
''')
  domain.init(c)
  feedback.init(c)
  c.execute("UPDATE jobs SET status='failed',error='服务重启中断；请核对结果后重试，未自动重复发布',updated_at=? WHERE status='running'",(now(),))
def meta(key,value):
 with database() as c:c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(key,json.dumps(value,ensure_ascii=False)))
def message(role,text,article_id=None,job_id=None):
 with database() as c:c.execute('INSERT INTO messages(role,content,article_id,job_id,created_at) VALUES(?,?,?,?,?)',(role,text,article_id,job_id,now()))

def stream_event(jid,kind,payload):
 if kind not in ('progress','answer','draft','finished'):raise ValueError('无效实时事件')
 with database() as c:c.execute('INSERT INTO stream_events(job_id,kind,payload,created_at) VALUES(?,?,?,?)',(jid,kind,json.dumps(payload,ensure_ascii=False),now()))

def stream_state(jid):
 with database() as c:
  rows=c.execute('SELECT * FROM stream_events WHERE job_id=? ORDER BY id',(jid,)).fetchall()
 progress={};value={'progress':[],'answer':'','draft':''}
 for row in rows:
  payload=json.loads(row['payload'])
  if row['kind']=='progress':progress[payload['key']]={'id':row['id'],'time':row['created_at'],**payload}
  elif row['kind'] in ('answer','draft'):value[row['kind']]=payload['text']
 value['progress']=list(progress.values())[-80:]
 return value
def get_article(aid):
 with database() as c:r=c.execute('SELECT * FROM articles WHERE id=?',(aid,)).fetchone()
 if not r:raise ValueError('没有找到这篇文章')
 value=dict(r)
 with database() as c:context=c.execute('SELECT conversation_id,column_id,parent_id,model FROM article_context WHERE article_id=?',(aid,)).fetchone()
 if context:value.update(dict(context))
 return value
def ingest():
 """Import only local publication proofs, never arbitrary files or account secrets."""
 records=list((ROOT/'reports').glob('*/daily/draft-*-result.json'))+list((ROOT/'reports').glob('*/iphone-duo-manual/draft-result.json'))
 records+=list((ROOT/'reports').glob('*/daily/slots/*/draft-*-result.json'))
 records+=list((ROOT/'artifacts').glob('publish-verified.json'))
 for p in records:
  try:
   proof=json.loads(p.read_text());url=proof.get('publishedUrl') or proof.get('url','').removesuffix('/edit')
   if not proof.get('published') or not re.fullmatch(r'https://zhuanlan.zhihu.com/p/\d+',url):continue
   ap=p.parent/'article.json'
   if p.name.startswith('draft-') and p.name!='draft-result.json':ap=p.parent/f'article-{p.name.split("-")[1]}.json'
   article=json.loads(ap.read_text()) if ap.exists() else {}
   stamp=proof.get('verifiedAt') or proof.get('publishRequestedAt') or dt.datetime.fromtimestamp(p.stat().st_mtime,dt.timezone.utc).isoformat()
   aid='zhihu-'+url.rsplit('/',1)[1];title=proof.get('title') or article.get('title') or '知乎文章'
   with database() as c:
    c.execute('''INSERT INTO articles(id,title,body,data,url,status,review_status,origin,created_at,updated_at) VALUES(?,?,?,?,?,'published',?,'daily',?,?)
ON CONFLICT(url) DO UPDATE SET body=CASE WHEN articles.body='' THEN excluded.body ELSE articles.body END,data=CASE WHEN articles.data='{}' THEN excluded.data ELSE articles.data END''',(aid,title,article.get('body',''),json.dumps(article,ensure_ascii=False),url,proof.get('reviewStatus','已提交发布'),stamp,stamp))
   cp=p.parent/'column-context.json'
   if cp.exists():
    col=json.loads(cp.read_text())
    if col:
     with database() as c:
      row=c.execute('SELECT id FROM articles WHERE url=?',(url,)).fetchone()
      c.execute('INSERT OR IGNORE INTO article_context VALUES(?,NULL,?,NULL,?)',(row['id'],col['id'],col['config'].get('model','')))
  except (ValueError,KeyError,OSError):continue

def read_plans():
 today=dt.datetime.now(__import__('zoneinfo').ZoneInfo('Asia/Shanghai')).date()
 result=[]
 for date in (today,today+dt.timedelta(days=1)):
  p=ROOT/'reports'/str(date)/'daily/schedule.json'
  if p.exists():
   try:result.append(json.loads(p.read_text()))
   except ValueError:pass
 return result

def read_operations():
 result=[]
 for p in sorted((ROOT/'reports').glob('*/operations/state.json'),reverse=True)[:14]:
  try:result.append(json.loads(p.read_text()))
  except ValueError:pass
 return result

def snapshot():
 ingest()
 with database() as c:
  event_cursor=c.execute('SELECT COALESCE(MAX(id),0) FROM stream_events').fetchone()[0]
  articles=[dict(x) for x in c.execute('''SELECT a.*,m.observed_at,m.views,m.likes,m.comments,m.favorites FROM articles a LEFT JOIN metrics m ON m.id=(SELECT MAX(id) FROM metrics WHERE article_id=a.id) ORDER BY a.created_at DESC''')]
  for a in articles:
   article_data=json.loads(a['data']);a['preview_url']=article_data.get('preview_url');a['preview_only']=bool(article_data.get('preview_only'))
   a['excerpt']=a['body'][:150];a['has_body']=bool(a['body']);a.pop('body');a.pop('data');a.pop('job_dir')
  jobs=[dict(x) for x in c.execute('SELECT j.id,j.kind,j.status,j.result,j.error,j.created_at,j.updated_at,x.conversation_id,x.model,x.column_id FROM jobs j LEFT JOIN job_context x ON j.id=x.job_id ORDER BY j.created_at DESC LIMIT 100')]
  for j in jobs:
   j['result']=json.loads(j['result']) if j['result'] else None
   j['qr_ready']=j['kind']=='login' and j['status']=='running' and bool(list((DATA/j['id']).glob('login-qr-*.png')))
   if j['kind']=='chat':j['stream']=stream_state(j['id'])
  messages=[dict(x) for x in c.execute("SELECT m.*,COALESCE(x.conversation_id,'legacy') conversation_id FROM messages m LEFT JOIN job_context x ON x.job_id=m.job_id ORDER BY m.id")]
  workspace=domain.state(c)
  for a in articles:
   extra=c.execute('SELECT * FROM article_context WHERE article_id=?',(a['id'],)).fetchone()
   if extra:a.update(dict(extra))
  metadata={x['key']:json.loads(x['value']) for x in c.execute('SELECT * FROM meta')}
  history=[dict(x) for x in c.execute('''SELECT substr(datetime(observed_at,'+8 hours'),1,10) day,MAX(observed_at) observed_at FROM metrics GROUP BY day ORDER BY day DESC LIMIT 14''')]
  for h in history:
   rows=c.execute('''SELECT views,likes,comments,favorites FROM metrics WHERE id IN (SELECT MAX(id) FROM metrics WHERE substr(datetime(observed_at,'+8 hours'),1,10)=? GROUP BY article_id)''',(h['day'],)).fetchall()
   for k in ['views','likes','comments','favorites']:h[k]=sum(r[k] for r in rows if r[k] is not None)
   h['coverage']=len(rows)
 runs=[]
 for p in sorted((ROOT/'reports').glob('*/daily/state.json'),reverse=True)[:14]:
  try:
   d=json.loads(p.read_text());row={k:d.get(k) for k in ['date','completed_at','failed_at','error','notified','articles']}
   progress=p.parent/'progress.json'
   row['progress']=json.loads(progress.read_text()) if progress.exists() else None
   runs.append(row)
  except ValueError:pass
 cfg=json.loads((ROOT/'daily-config.json').read_text())
 return {**workspace,'event_cursor':event_cursor,'articles':articles,'jobs':jobs,'messages':messages,'meta':metadata,'history':list(reversed(history)),'runs':runs,'schedule':{'time':cfg['time'],'timezone':cfg['timezone'],'count':cfg['count'],'review_max_rounds':cfg['review_max_rounds'],'windows':cfg.get('windows',[]),'operations':cfg.get('operations',{}),'article_layout':cfg.get('article_layout',[]),'illustrations':cfg.get('illustrations',{})},'plans':read_plans(),'operations_runs':read_operations(),'updated_at':now()}

def enqueue(kind,payload):
 with database() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]>=8:raise ValueError('待处理任务较多，请稍后再试')
  if kind in ('sync','login') and (row:=c.execute("SELECT id FROM jobs WHERE kind=? AND status IN ('queued','running')",(kind,)).fetchone()):return row['id']
  if kind=='publish':
   if c.execute("SELECT 1 FROM jobs WHERE kind='publish' AND status IN ('queued','running') AND json_extract(payload,'$.article_id')=?",(payload['article_id'],)).fetchone():raise ValueError('这篇文章正在发布，请勿重复提交')
  if kind=='chat':
   conv=domain.conversation(c,payload.get('conversation_id','legacy'));col=domain.column(c,conv['column_id']);cfg=col['config'] if col else {}
   payload['conversation_id']=conv['id'];payload['column_id']=conv['column_id'];payload['column']=col
   payload['model']=providers.validate(payload.get('model') or conv['model'] or cfg.get('model') or providers.load()['default'])
   payload['review_model']=providers.validate(cfg.get('review_model') or providers.load()['review'] or payload['model'])
   if c.execute("SELECT 1 FROM jobs j JOIN job_context x ON j.id=x.job_id WHERE x.conversation_id=? AND j.status IN ('queued','running')",(conv['id'],)).fetchone():raise ValueError('当前会话仍在生成，请完成后继续，或新建会话')
  jid=uuid.uuid4().hex;c.execute('INSERT INTO jobs VALUES(?,?,\'queued\',?,NULL,NULL,?,?)',(jid,kind,json.dumps(payload,ensure_ascii=False),now(),now()))
  if kind=='chat':
   c.execute('INSERT INTO job_context VALUES(?,?,?,?)',(jid,payload['conversation_id'],payload['model'],payload['column_id']))
   c.execute("UPDATE conversations SET updated_at=?,title=CASE WHEN title='新的写作想法' THEN ? ELSE title END WHERE id=?",(now(),payload['message'].replace('\n',' ')[:28],payload['conversation_id']))
 return jid
@contextlib.contextmanager
def account_lock():
 with (ROOT/'private/daily.lock').open('a') as f:
  try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise RuntimeError('每日任务正在使用账号；请待其完成后重试')
  yield

def command(args,folder,env=None,timeout=240):
 result=subprocess.run(args,cwd=ROOT,env=env or daily.ENV,text=True,capture_output=True,timeout=timeout)
 (folder/'last-command.log').write_text(result.stdout+'\n'+result.stderr)
 if result.returncode:raise RuntimeError((result.stderr or result.stdout)[-700:] or '操作失败，详见任务日志')
 return result.stdout

def content_time(label, fallback):
 m=re.search(r'(?:(\d{4})-)?(\d{2})-(\d{2})(?:\s+(\d{2}):(\d{2}))?',label or '')
 if not m:return fallback
 current=dt.datetime.now(daily.ZoneInfo('Asia/Shanghai'))
 try:
  value=dt.datetime(int(m[1] or current.year),int(m[2]),int(m[3]),int(m[4] or 0),int(m[5] or 0),tzinfo=current.tzinfo)
  if not m[1] and value>current+dt.timedelta(days=1):value=value.replace(year=current.year-1)
  return value.astimezone(dt.timezone.utc).isoformat()
 except ValueError:return fallback

def sync_account(folder):
 with account_lock():raw=command([NODE,str(FILES/'sync-account.mjs')],folder)
 data=json.loads(raw);daily.save(folder/'metrics-proof.json',data)
 with database() as c:
  for a in data['articles']:
   aid='zhihu-'+a['url'].rsplit('/',1)[1]
   published_at=content_time(a.get('published_label'),data['observed_at'])
   c.execute('''INSERT INTO articles(id,title,body,data,url,status,review_status,origin,created_at,updated_at) VALUES(?,?,'','{}',?,'published',?,'account',?,?) ON CONFLICT(url) DO UPDATE SET review_status=excluded.review_status,created_at=excluded.created_at,updated_at=excluded.updated_at''',(aid,a['title'],a['url'],a['review_status'],published_at,data['observed_at']))
   row=c.execute('SELECT id FROM articles WHERE url=?',(a['url'],)).fetchone()
   m=a['metrics'];c.execute('INSERT INTO metrics(article_id,observed_at,views,likes,comments,favorites,raw) VALUES(?,?,?,?,?,?,?)',(row['id'],data['observed_at'],m['阅读'],m['赞同'],m['评论'],m['收藏'],json.dumps(a,ensure_ascii=False)))
 meta('sync',{'observed_at':data['observed_at'],'coverage':data['coverage'],'captured':len(data['articles']),'reported_count':data['reported_count'],'source':data['source']})
 meta('sync_error',None)
 return {'answer':f"同步了 {len(data['articles'])} 篇文章的页面数据。",'captured':len(data['articles'])}

def publish_article(aid,folder):
 a=get_article(aid)
 if json.loads(a['data']).get('preview_only'):raise ValueError('这篇图文稿尚未完成上传验证，请先完成草稿检查。')
 if a['status']=='published':return {'answer':'这篇文章已提交发布，没有重复提交。','article_id':aid,'url':a['url']}
 if a['status'] not in ('ready','publish_failed','publishing','writing'):raise ValueError('当前文章尚未通过审稿，不能发布')
 with database() as c:
  context=c.execute('SELECT column_id FROM article_context WHERE article_id=?',(aid,)).fetchone();col=domain.column(c,context['column_id']) if context and context['column_id'] else None
 if col and col['config'].get('target'):raise ValueError('该稿件绑定了知乎专栏；当前专栏定向发布尚未完成实账号验证，已停止，未发布到默认位置。请先联系维护者完成绑定验证。')
 article=json.loads(a['data']);daily.RUN=pathlib.Path(a['job_dir']);daily.validate_review(article)
 with account_lock():
  source=pathlib.Path(a['job_dir'])/'final-article.json';proofpath=pathlib.Path(a['job_dir'])/'draft-result.json'
  if a['status'] in ('writing','publishing') and not proofpath.exists():raise RuntimeError('上次草稿写入结果不确定，请核查知乎草稿箱；未重复创建')
  if not proofpath.exists():
   # Record before an external mutation, so an uncertain write never silently retries.
   with database() as c:c.execute("UPDATE articles SET status='writing',updated_at=? WHERE id=?",(now(),aid))
   if article.get('illustrations'):
    import article_images
    daily.save(source,article_images.prepare(article,pathlib.Path(a['job_dir'])))
   command([NODE,str(ROOT/'draft.mjs'),str(source)],folder,dict(daily.ENV,ZHIHU_RESULT_PATH=str(proofpath)),900)
  with database() as c:c.execute("UPDATE articles SET status='publishing',updated_at=? WHERE id=?",(now(),aid))
  command([NODE,str(ROOT/'publish.mjs'),str(source)],folder,dict(daily.ENV,ZHIHU_RESULT_PATH=str(proofpath),ZHIHU_PUBLISH_DIR=str(folder)),300)
  proof=json.loads(proofpath.read_text())
  if not proof.get('published') or not (proof.get('verifiedInCreatorCenter') or proof.get('verifiedByPublishedEditor')):raise RuntimeError('未取得知乎发布凭证')
 with database() as c:c.execute("UPDATE articles SET status='published',url=?,review_status=?,updated_at=? WHERE id=?",(proof['publishedUrl'],proof['reviewStatus'],now(),aid))
 return {'answer':f"已提交发布：{a['title']}。知乎状态：{proof['reviewStatus']}",'article_id':aid,'url':proof['publishedUrl']}

def read_article(aid,folder):
 a=get_article(aid)
 if not a['url'] or not re.fullmatch(r'https://zhuanlan.zhihu.com/p/\d+',a['url']):raise ValueError('没有可读取的知乎文章地址')
 with account_lock():result=json.loads(command([NODE,str(FILES/'read-article.mjs'),a['url']],folder))
 if result['title']!=a['title']:raise ValueError('知乎标题已变化，先同步账号数据后再读取')
 with database() as c:c.execute('UPDATE articles SET body=?,updated_at=? WHERE id=?',(result['body'],now(),aid))
 return {'answer':'已从知乎编辑器只读获取全文，没有修改原文。','article_id':aid}

def may_publish(text):
 # Only an explicit imperative in the current user request can cause publication.
 return bool(re.search(r'发布|发到知乎|发去知乎',text) and not re.search(r'别|不要|不发布|暂不|先不|能否|可以吗|能不能|如何|怎么|[?？]',text))

def job_stage(jid,text):
 with database() as c:c.execute("UPDATE jobs SET result=?,updated_at=? WHERE id=?",(json.dumps({'stage':text},ensure_ascii=False),now(),jid))
 stream_event(jid,'progress',{'key':'stage:'+text,'phase':'工作流程','text':text})

def chat(payload,folder,jid):
 selected=get_article(payload['article_id']) if payload.get('article_id') else None
 daily.RUN=folder
 daily.TODAY=dt.datetime.now(daily.ZoneInfo(daily.CFG['timezone'])).date()
 job_stage(jid,'采集热点与整理上下文')
 fetched=command([runtime.PYTHON,runtime.NEWS_FETCHER,'--source',daily.CFG['sources'],'--limit','10','--no-save'],folder)
 daily.save(folder/'hotspots.json',{'collected_at':now(),'items':json.loads(fetched)})
 cards=[c for c in wiki.load() if wiki.eligible(c)[0]]
 daily.save(folder/'writing-context.json',{'approved_cards':cards,'rules':wiki.POLICY})
 state=snapshot();daily.save(folder/'history.json',[{'title':a['title'],'url':a['url']} for a in state['articles'] if a['status']=='published'])
 context={'message':payload['message'],'selected_article':json.loads(selected['data']) if selected and selected['data']!='{}' else selected,'conversation':[m for m in state['messages'] if m['conversation_id']==payload.get('conversation_id','legacy')],'column':payload.get('column'),'operations':{'schedule':state['schedule'],'sync':state['meta'].get('sync'),'articles':state['articles']}}
 daily.save(folder/'context.json',context)
 prompt=(FILES/'chat-prompt.txt').read_text()+f'\n当前时间{now()}。本次context：{folder}/context.json；热点：{folder}/hotspots.json；范文：{folder}/writing-context.json。'
 job_stage(jid,'AI 检索材料、讨论或撰写初稿')
 def run_live(prompt,output,schema):
  model=payload['review_model'] if 'review-' in output.name else payload['model']
  if model!='codex':return providers.run(model,prompt,output,schema,lambda kind,value:stream_event(jid,kind,value))
  return realtime_agent(prompt,output,schema,lambda kind,value:stream_event(jid,kind,value),ROOT,daily.ENV)
 col=payload.get('column');fiction=bool(col and col['config'].get('genre')=='fiction' or selected and json.loads(selected['data']).get('genre')=='fiction')
 if fiction:prompt+='\n本次为原创虚构故事专栏，以context.column中的设定与人物资料为准。必须在首段明确标注原创虚构，不伪造真人经历。sources可以为空，不要求新闻背景和时效；仍须借鉴至少两篇合格范文的结构，不复制其情节。event_date为创作日期。'
 result=run_live(prompt,folder/'assistant.json',FILES/('fiction-chat-schema.json' if fiction else 'chat-schema.json'))
 action=result['action']
 if action=='publish':
  if not selected or not may_publish(payload['message']):return {'answer':'请选中要发布的已审稿文章，并明确说“发布这篇”，或使用文章旁的发布按钮。'}
  return publish_article(selected['id'],folder)
 if action in ('write','revise'):
  article=result.get('article')
  if not article:raise ValueError('AI没有返回完整成稿，请补充选题信息')
  daily.save(folder/'initial-article.json',article)
  if fiction:article['genre']='fiction'
  daily.validate_article(article,require_recent=False)
  # Every article, including a conversational revision, uses the same review gate.
  job_stage(jid,'独立编辑审核与修改')
  article=daily.review_article(article,1,require_recent=False,run_agent=run_live);daily.save(folder/'final-article.json',article)
  aid='draft-'+uuid.uuid4().hex
  with database() as c:c.execute("INSERT INTO articles VALUES(?,?,?,?,NULL,'ready','内部审稿通过','chat',?,?,?)",(aid,article['title'],article['body'],json.dumps(article,ensure_ascii=False),now(),now(),str(folder)))
  with database() as c:c.execute('INSERT INTO article_context VALUES(?,?,?,?,?)',(aid,payload.get('conversation_id','legacy'),payload.get('column_id'),selected['id'] if selected else None,payload['model']))
  if result['publish_after_review'] and may_publish(payload['message']):
   job_stage(jid,'成稿通过审阅，正在提交知乎')
   return publish_article(aid,folder)
  return {'answer':result['answer']+'\n\n独立审稿已通过，成稿已保存，可打开阅读、继续修改或发布。','article_id':aid}
 return {'answer':result['answer']}

def work():
 while True:
  try:
   ingest()
   with database() as c:
    row=c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
    if row:c.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?",(now(),row['id']))
   if not row:time.sleep(2);continue
   j=dict(row);folder=DATA/j['id'];folder.mkdir(exist_ok=True);payload=json.loads(j['payload'])
   try:
    if j['kind']=='sync':result=sync_account(folder)
    elif j['kind']=='columns':
     with account_lock():data=json.loads(command([NODE,str(FILES/'sync-columns.mjs')],folder))
     meta('zhihu_columns',data);result={'answer':f"已读取 {len(data['columns'])} 个可管理的知乎专栏"}
    elif j['kind']=='publish':result=publish_article(payload['article_id'],folder)
    elif j['kind']=='read':result=read_article(payload['article_id'],folder)
    elif j['kind']=='chat':result=chat(payload,folder,j['id'])
    elif j['kind']=='login':
     daily.RUN=folder
     with account_lock():daily.authenticate()
     result={'answer':'登录已恢复，可以同步数据或发布成稿。'}
    else:raise ValueError('未知任务')
    with database() as c:c.execute("UPDATE jobs SET status='done',result=?,updated_at=? WHERE id=?",(json.dumps(result,ensure_ascii=False),now(),j['id']))
    if j['kind'] in ('chat','publish','login'):message('assistant',result['answer'],result.get('article_id'),j['id'])
    if j['kind']=='chat':stream_event(j['id'],'finished',{'status':'done'})
   except Exception as e:
    error=str(e)[:1600]
    with database() as c:c.execute("UPDATE jobs SET status='failed',error=?,updated_at=? WHERE id=?",(error,now(),j['id']))
    if j['kind']=='sync':meta('sync_error',{'message':error,'at':now()})
    if j['kind'] in ('chat','publish','login'):message('assistant','操作未完成：'+error,None,j['id'])
    if j['kind']=='chat':stream_event(j['id'],'finished',{'status':'failed'})
  except Exception as e:print('worker:',str(e),flush=True);time.sleep(5)

def automatic_sync():
 while True:
  time.sleep(900)
  try:enqueue('sync',{})
  except Exception:pass

class Handler(BaseHTTPRequestHandler):
 def event_stream(self):
  cursor=max(int(parse_qs(urlparse(self.path).query).get('after',['0'])[0]),int(self.headers.get('Last-Event-ID','0')))
  self.send_response(200);self.send_header('Content-Type','text/event-stream; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Accel-Buffering','no');self.end_headers()
  deadline=time.monotonic()+50;ping=0
  try:
   self.wfile.write(b': connected\n\n');self.wfile.flush()
   while time.monotonic()<deadline:
    with database() as c:rows=c.execute('SELECT * FROM stream_events WHERE id>? ORDER BY id LIMIT 100',(cursor,)).fetchall()
    for row in rows:
     value={'job_id':row['job_id'],'kind':row['kind'],'created_at':row['created_at'],**json.loads(row['payload'])}
     self.wfile.write(('id: '+str(row['id'])+'\nevent: update\ndata: '+json.dumps(value,ensure_ascii=False)+'\n\n').encode());cursor=row['id']
    if time.monotonic()-ping>10:self.wfile.write(b': heartbeat\n\n');ping=time.monotonic()
    self.wfile.flush();time.sleep(.2)
  except (BrokenPipeError,ConnectionResetError):pass
 def log_message(self,fmt,*args):pass
 def reply(self,data,status=200,ctype='application/json; charset=utf-8'):
  body=json.dumps(data,ensure_ascii=False).encode() if ctype.startswith('application/json') else data
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
 def do_GET(self):
  try:
   path=urlparse(self.path).path
   if path=='/api/auth/check':return self.reply({'authenticated':auth.valid(self.headers)},200 if auth.valid(self.headers) else 401)
   if path in ('/login','/login/','/login.js','/style.css'):
    name={'/login':'login.html','/login/':'login.html','/login.js':'login.js','/style.css':'style.css'}[path];return self.reply((FILES/name).read_bytes(),ctype=mimetypes.guess_type(name)[0]+'; charset=utf-8')
   if not auth.valid(self.headers):
    if path.startswith('/api/'):return self.reply({'error':'登录已过期，请重新登录'},401)
    self.send_response(302);self.send_header('Location','/studio/login/?next='+__import__('urllib.parse',fromlist=['quote']).quote('/studio'+self.path,safe=''));self.end_headers();return
   if path.startswith('/readings/'):
    match=re.fullmatch(r'/readings/([a-z0-9-]+)/(index\.html|style\.css|cover\.png|dinner\.png|room\.png|story\.md)?',path)
    if not match:return self.reply({'error':'阅读页不存在'},404)
    target=ROOT/'private/readings'/match[1]/(match[2] or 'index.html')
    if not target.is_file():return self.reply({'error':'阅读页不存在'},404)
    return self.reply(target.read_bytes(),ctype=mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
   if path=='/api/feedback':
    with database() as c:items=feedback.records(c)
    return self.reply({'items':items})
   if path.startswith('/api/feedback/image/'):
    iid=path.rsplit('/',1)[1]
    with database() as c:row=c.execute('SELECT path FROM feedback_images WHERE id=?',(iid,)).fetchone()
    if not row:return self.reply({'error':'图片不存在'},404)
    return self.reply(pathlib.Path(row['path']).read_bytes(),ctype='image/jpeg')
   if path=='/api/wiki':return self.reply({'results':wiki.search(parse_qs(urlparse(self.path).query).get('q',[''])[0],8)})
   if path=='/api/events':return self.event_stream()
   if path=='/api/state':return self.reply(snapshot())
   if path.startswith('/api/article/'):
    aid=path.rsplit('/',1)[1];a=get_article(aid);data=json.loads(a['data']);a.pop('job_dir');a['data']=data
    return self.reply(a)
   if path.startswith('/api/qr/'):
    jid=path.rsplit('/',1)[1]
    if not re.fullmatch('[a-f0-9]{32}',jid):raise ValueError('无效任务')
    with database() as c:j=c.execute("SELECT 1 FROM jobs WHERE id=? AND kind='login' AND status='running'",(jid,)).fetchone()
    qr=sorted((DATA/jid).glob('login-qr-*.png')) if j else []
    if not qr:return self.reply({'error':'二维码尚未就绪'},404)
    return self.reply(qr[-1].read_bytes(),ctype='image/png')
   for_view=path.strip('/')
   if for_view in ('overview','articles','chat','jobs','columns','settings','feedback','operations'):
    return self.reply((FILES/'index.html').read_bytes(),ctype='text/html; charset=utf-8')
   allowed={'/':'index.html','/app.js':'app.js','/workspace.js':'workspace.js','/feedback.js':'feedback.js','/style.css':'style.css'}
   if path not in allowed:return self.reply({'error':'没有找到页面'},404)
   return self.reply((FILES/allowed[path]).read_bytes(),ctype=mimetypes.guess_type(allowed[path])[0]+'; charset=utf-8')
  except ValueError as e:self.reply({'error':str(e)},400)
  except Exception:self.reply({'error':'读取失败，请稍后刷新'},500)
 def do_POST(self):
  try:
   if self.headers.get('Origin')!=ORIGIN or self.headers.get('X-Requested-With')!='WritingStudio' or not self.headers.get('Content-Type','').startswith('application/json'):return self.reply({'error':'请求来源验证失败'},403)
   route=urlparse(self.path).path
   if route.startswith('/api/feedback') and not auth.valid(self.headers):return self.reply({'error':'请重新登录'},401)
   size=int(self.headers.get('Content-Length','0'))
   limit=6*1024*1024 if route=='/api/feedback/upload' else 2*1024*1024 if route=='/api/chat' else 50000
   if not 0<size<=limit:return self.reply({'error':'请求大小不合要求'},400)
   p=json.loads(self.rfile.read(size));route=urlparse(self.path).path
   if route=='/api/auth/login':
    value=auth.login(str(p.get('username',''))[:100],str(p.get('password',''))[:1000],self.headers.get('X-Real-IP',self.client_address[0]));self.send_response(200);self.send_header('Set-Cookie',auth.cookie(value));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}');return
   if not auth.valid(self.headers):return self.reply({'error':'请重新登录'},401)
   if route=='/api/auth/logout':
    auth.logout(self.headers);self.send_response(200);self.send_header('Set-Cookie',auth.cookie(''));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}');return
   if route=='/api/feedback/upload':
    with database() as c:result=feedback.upload(c,p)
    return self.reply(result)
   if route=='/api/feedback':
    with database() as c:result=feedback.submit(c,p)
    return self.reply(result)
   if route=='/api/feedback/action':
    with database() as c:result=feedback.action(c,p)
    return self.reply(result)
   if route in ('/api/drafts/trash','/api/drafts/restore'):
    with database() as c:result=domain.trash(c,p.get('ids'),route.endswith('/restore'))
    return self.reply(result)
   if route=='/api/conversations':
    with database() as c:cid=domain.save_conversation(c,p)
    return self.reply({'id':cid})
   if route=='/api/columns':
    with database() as c:cid=domain.save_column(c,p)
    return self.reply({'id':cid})
   if route=='/api/models':return self.reply(providers.configure(p))
   if route=='/api/model-defaults':return self.reply(providers.set_defaults(p))
   if route=='/api/columns/sync':jid=enqueue('columns',{})
   elif route=='/api/chat':
    text=p.get('message','').strip()
    if not text:raise ValueError('请输入想法或写作材料')
    aid=p.get('article_id')
    if aid:get_article(aid)
    jid=enqueue('chat',{'message':text,'article_id':aid,'conversation_id':p.get('conversation_id','legacy'),'model':p.get('model','')});message('user',text,aid,jid)
   elif route=='/api/sync':jid=enqueue('sync',{})
   elif route=='/api/login':jid=enqueue('login',{})
   elif route=='/api/read':
    a=get_article(p.get('article_id',''));jid=enqueue('read',{'article_id':a['id']})
   elif route=='/api/publish':
    a=get_article(p.get('article_id',''))
    if a['status'] not in ('ready','publish_failed','publishing','writing'):raise ValueError('请选择已通过内部审稿且尚未发布的文章')
    jid=enqueue('publish',{'article_id':a['id']});message('user','发布《'+a['title']+'》',a['id'],jid)
   else:return self.reply({'error':'没有找到操作'},404)
   self.reply({'job_id':jid},202)
  except (ValueError,TypeError,KeyError) as e:self.reply({'error':str(e)},400)
  except Exception:self.reply({'error':'请求未完成，请查看任务记录'},500)

if __name__=='__main__':
 auth.initialize();init();ingest()
 threading.Thread(target=work,daemon=True).start();threading.Thread(target=automatic_sync,daemon=True).start()
 print('Writing Studio listening on 127.0.0.1:27821',flush=True)
 ThreadingHTTPServer(('127.0.0.1',27821),Handler).serve_forever()
