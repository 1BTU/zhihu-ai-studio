"""Feedback inbox, attachment validation, scheduling and reversible requests."""
import base64,datetime as dt,hashlib,io,json,pathlib,sqlite3,uuid
from zoneinfo import ZoneInfo
from PIL import Image,UnidentifiedImageError
ROOT=pathlib.Path(__file__).resolve().parents[1];DATA=ROOT/'private/feedback';DB=ROOT/'private/studio/studio.sqlite3'
Image.MAX_IMAGE_PIXELS=16000000

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def connect():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row;return c
def init(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,mode TEXT NOT NULL,status TEXT NOT NULL,due_at TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,summary TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',cancel_requested INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,attempts INTEGER NOT NULL DEFAULT 0);
 CREATE TABLE IF NOT EXISTS feedback_images(id TEXT PRIMARY KEY,feedback_id TEXT,name TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS feedback_events(id INTEGER PRIMARY KEY,feedback_id TEXT NOT NULL,created_at TEXT NOT NULL,message TEXT NOT NULL);
 ''')
 if 'attempts' not in [x[1] for x in c.execute('PRAGMA table_info(feedback)')]:c.execute('ALTER TABLE feedback ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0')
 DATA.mkdir(parents=True,exist_ok=True,mode=0o700);(DATA/'images').mkdir(exist_ok=True,mode=0o700)
def event(c,fid,text):c.execute('INSERT INTO feedback_events(feedback_id,created_at,message) VALUES(?,?,?)',(fid,now(),text))
def due(mode):
 stamp=dt.datetime.now(ZoneInfo('Asia/Shanghai'))
 if mode=='now':return stamp.astimezone(dt.timezone.utc).isoformat()
 morning=stamp.replace(hour=3,minute=0,second=0,microsecond=0)
 if morning<=stamp:morning+=dt.timedelta(days=1)
 return morning.astimezone(dt.timezone.utc).isoformat()
def upload(c,p):
 try:
  raw=base64.b64decode(p.get('data',''),validate=True)
  if not 0<len(raw)<=4*1024*1024:raise ValueError('每张图片不能超过4MB')
  with Image.open(io.BytesIO(raw)) as im:
   if im.format not in ('PNG','JPEG','WEBP'):raise ValueError('支持PNG、JPG、WebP图片')
   if im.width*im.height>16000000:raise ValueError('图片尺寸不能超过1600万像素')
   im.load();im.thumbnail((2400,2400));image=im.convert('RGB');output=io.BytesIO();image.save(output,'JPEG',quality=90)
 except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):raise ValueError('图片无法读取或尺寸过大') from None
 iid=uuid.uuid4().hex;path=DATA/'images'/(iid+'.jpg');path.write_bytes(output.getvalue());path.chmod(0o600)
 c.execute('INSERT INTO feedback_images VALUES(?,NULL,?,?,?)',(iid,str(p.get('name','截图'))[:120],str(path),now()))
 return {'id':iid,'url':'api/feedback/image/'+iid}
def get(c,fid):
 row=c.execute('SELECT * FROM feedback WHERE id=?',(fid,)).fetchone()
 if not row:raise ValueError('意见不存在')
 return dict(row)
def records(c):
 rows=[dict(x) for x in c.execute('SELECT * FROM feedback ORDER BY created_at DESC LIMIT 200')]
 for row in rows:
  row['images']=[{'id':i['id'],'name':i['name'],'url':'api/feedback/image/'+i['id']} for i in c.execute('SELECT id,name FROM feedback_images WHERE feedback_id=?',(row['id'],))]
  row['events']=[dict(x) for x in c.execute('SELECT created_at,message FROM feedback_events WHERE feedback_id=? ORDER BY id',(row['id'],))]
 return rows

def submit(c,p):
 title=str(p.get('title','')).strip();body=str(p.get('body','')).strip();mode=p.get('mode','night');images=p.get('images',[])
 if not 1<=len(title)<=100 or not 1<=len(body)<=12000:raise ValueError('请填写标题（最多100字）与问题描述（最多12000字）')
 if mode not in ('now','night'):raise ValueError('请选择立即或凌晨处理')
 if not isinstance(images,list) or len(images)>4 or len(set(images))!=len(images):raise ValueError('最多添加4张图片')
 c.execute('BEGIN IMMEDIATE');fid=p.get('id') or uuid.uuid4().hex
 if p.get('id'):
  old=get(c,fid)
  if old['status'] not in ('queued','scheduled','failed','attention','cancelled'):raise ValueError('正在修复或已上线的意见不能编辑，请先撤销或另提意见')
 for iid in images:
  im=c.execute('SELECT feedback_id FROM feedback_images WHERE id=?',(iid,)).fetchone()
  if not im or im[0] not in (None,fid):raise ValueError('图片不存在或已关联其他意见')
 status='queued' if mode=='now' else 'scheduled'
 c.execute('INSERT INTO feedback(id,title,body,mode,status,due_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,mode=excluded.mode,status=excluded.status,due_at=excluded.due_at,updated_at=excluded.updated_at,error=\'\',cancel_requested=0,attempts=0,revision=feedback.revision+1',(fid,title,body,mode,status,due(mode),now(),now()))
 c.execute('UPDATE feedback_images SET feedback_id=NULL WHERE feedback_id=?',(fid,))
 for iid in images:c.execute('UPDATE feedback_images SET feedback_id=? WHERE id=?',(fid,iid))
 event(c,fid,'已提交，等待立即处理' if mode=='now' else '已提交，安排在北京时间凌晨03:00处理')
 return {'id':fid}
def action(c,p):
 fid=p.get('id');action=p.get('action');c.execute('BEGIN IMMEDIATE');row=get(c,fid);status=row['status']
 if action=='cancel':
  if status in ('queued','scheduled','failed','attention'):status='cancelled'
  elif status in ('running','testing'):status='cancelling'
  else:raise ValueError('当前阶段不能撤回提交；上线完成后可选择撤销修复')
  c.execute('UPDATE feedback SET status=?,cancel_requested=1,updated_at=? WHERE id=?',(status,now(),fid));event(c,fid,'已请求撤销提交；尚未上线的修改将不部署')
 elif action=='undo':
  if status!='resolved':raise ValueError('只有已上线的修复可以撤销')
  c.execute("UPDATE feedback SET status='rollback_pending',updated_at=? WHERE id=?",(now(),fid));event(c,fid,'已请求撤销修复，等待核对版本并恢复')
 else:raise ValueError('未知操作')
 return {'id':fid}
