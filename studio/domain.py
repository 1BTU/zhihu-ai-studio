"""Workspace entities. Extra tables preserve legacy article and job schemas."""
import json,uuid,datetime
import providers

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def init(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,title TEXT NOT NULL,column_id TEXT,model TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS job_context(job_id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,model TEXT NOT NULL,column_id TEXT);
 CREATE TABLE IF NOT EXISTS article_context(article_id TEXT PRIMARY KEY,conversation_id TEXT,column_id TEXT,parent_id TEXT,model TEXT);
 CREATE TABLE IF NOT EXISTS trash(article_id TEXT PRIMARY KEY,previous_status TEXT NOT NULL,deleted_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS columns(id TEXT PRIMARY KEY,name TEXT NOT NULL,config TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
 ''')
 c.execute("INSERT OR IGNORE INTO conversations VALUES('legacy','此前的写作对话',NULL,'',?,?,0)",(now(),now()))
 c.execute("INSERT OR IGNORE INTO job_context SELECT id,'legacy','codex',NULL FROM jobs WHERE kind='chat'")
 c.execute("INSERT OR IGNORE INTO article_context SELECT m.article_id,COALESCE(x.conversation_id,'legacy'),x.column_id,NULL,x.model FROM messages m LEFT JOIN job_context x ON m.job_id=x.job_id WHERE m.role='assistant' AND m.article_id IS NOT NULL ORDER BY m.id DESC")
 if not c.execute('SELECT 1 FROM columns').fetchone():
  for cid,name,genre,style in [('technology','科技观察','commentary','交代新闻背景，以事实和具体使用场景讨论技术变化，不堆术语，不制造焦虑。'),('stories','人间故事','fiction','原创虚构情感故事，开篇明确标注虚构。通过人物行动和对话表现冲突，克制，不说教，不套用真人经历。')]:
   config={'genre':genre,'style':style,'notes':'','model':'','review_model':'','target':None,'auto':False}
   c.execute('INSERT INTO columns VALUES(?,?,?,?,?)',(cid,name,json.dumps(config,ensure_ascii=False),now(),now()))
def column(c,cid):
 row=c.execute('SELECT * FROM columns WHERE id=?',(cid,)).fetchone() if cid else None
 if cid and not row:raise ValueError('专栏不存在')
 return dict(row)|{'config':json.loads(row['config'])} if row else None
def conversation(c,cid):
 row=c.execute('SELECT * FROM conversations WHERE id=? AND archived=0',(cid,)).fetchone()
 if not row:raise ValueError('会话不存在或已归档')
 return dict(row)
def save_conversation(c,p):
 cid=p.get('id');old=conversation(c,cid) if cid else None
 title=str(p.get('title',old['title'] if old else '新的写作想法')).strip()[:100] or '新的写作想法'
 col=p.get('column_id',old['column_id'] if old else None) or None;column(c,col)
 model=providers.validate(p.get('model',old['model'] if old else ''))
 if cid:
  c.execute('UPDATE conversations SET title=?,column_id=?,model=?,updated_at=?,archived=? WHERE id=?',(title,col,model,now(),int(bool(p.get('archived',False))),cid))
 else:
  cid=uuid.uuid4().hex;c.execute('INSERT INTO conversations VALUES(?,?,?,?,?,?,0)',(cid,title,col,model,now(),now()))
 return cid
def save_column(c,p):
 cid=p.get('id');old=column(c,cid) if cid else None;cfg=old['config'].copy() if old else {}
 name=str(p.get('name',old['name'] if old else '')).strip()[:80]
 if not name:raise ValueError('请输入专栏名称')
 for k in ['genre','style','notes','model','review_model','auto']:
  if k in p:cfg[k]=p[k]
 if cfg.get('genre') not in ('fiction','commentary'):raise ValueError('请选择故事或观察评论')
 cfg['style']=str(cfg.get('style',''))[:4000];cfg['notes']=str(cfg.get('notes',''))[:12000]
 cfg['model']=providers.validate(cfg.get('model',''));cfg['review_model']=providers.validate(cfg.get('review_model',''));cfg['auto']=bool(cfg.get('auto',False))
 if 'target' in p:
  target=p['target']
  if target:
   row=c.execute("SELECT value FROM meta WHERE key='zhihu_columns'").fetchone();known=json.loads(row[0]).get('columns',[]) if row else []
   target=next((x for x in known if x['id']==target),None)
   if not target:raise ValueError('请先同步并选择当前账号实际可管理的知乎专栏')
  cfg['target']=target or None
 cid=cid or uuid.uuid4().hex
 c.execute('INSERT INTO columns VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,config=excluded.config,updated_at=excluded.updated_at',(cid,name,json.dumps(cfg,ensure_ascii=False),now(),now()))
 return cid

def state(c):
 cols=[dict(x)|{'config':json.loads(x['config'])} for x in c.execute('SELECT * FROM columns ORDER BY created_at')]
 conv=[dict(x) for x in c.execute('SELECT * FROM conversations WHERE archived=0 ORDER BY updated_at DESC')]
 return {'columns':cols,'conversations':conv,'models':providers.public()}

def trash(c,ids,restore=False):
 if not isinstance(ids,list) or not 1<=len(ids)<=100 or any(not isinstance(x,str) for x in ids):raise ValueError('请选择1–100篇草稿')
 c.execute('BEGIN IMMEDIATE')
 for aid in set(ids):
  a=c.execute('SELECT * FROM articles WHERE id=?',(aid,)).fetchone()
  if not a:raise ValueError('草稿不存在')
  if restore:
   row=c.execute('SELECT previous_status FROM trash WHERE article_id=?',(aid,)).fetchone()
   if a['status']!='deleted' or not row:raise ValueError('该草稿不在回收站')
   c.execute('UPDATE articles SET status=?,updated_at=? WHERE id=?',(row[0],now(),aid));c.execute('DELETE FROM trash WHERE article_id=?',(aid,))
  else:
   if a['status']!='ready':raise ValueError('仅可删除未发布且未在写入中的本地成稿')
   if c.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') AND json_extract(payload,'$.article_id')=?",(aid,)).fetchone():raise ValueError('草稿仍有关联任务，请完成后再清理')
   c.execute('INSERT INTO trash VALUES(?,?,?)',(aid,a['status'],now()));c.execute("UPDATE articles SET status='deleted',updated_at=? WHERE id=?",(now(),aid))
 return {'count':len(set(ids))}
