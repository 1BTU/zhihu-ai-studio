"""Public read-only projection; never expose the private workspace snapshot."""
import contextlib,json,pathlib,re,sqlite3
ROOT=pathlib.Path(__file__).resolve().parents[1]
PROFILE='https://www.zhihu.com/people/shuai-ge-8-87-44'

def rows(db,aid=None):
 with contextlib.closing(sqlite3.connect(f'file:{db}?mode=ro',uri=True,timeout=10)) as c:
  c.row_factory=sqlite3.Row
  sql="SELECT id,title,body,data,url,created_at FROM articles WHERE status='published'"
  params=()
  if aid is not None:sql+=' AND id=?';params=(aid,)
  return [dict(r) for r in c.execute(sql+' ORDER BY created_at DESC',params) if re.fullmatch(r'https://zhuanlan.zhihu.com/p/\d+',r['url'] or '')]

def parsed(row):
 try:return json.loads(row['data'])
 except (ValueError,TypeError):return {}

def media(row):
 result=[]
 for i,im in enumerate(parsed(row).get('illustrations',[])):
  url=im.get('url','')
  m=re.fullmatch(r'/studio/readings/([a-z0-9-]+)/([a-z0-9-]+\.(?:png|jpg|jpeg|webp))',url)
  if m and (ROOT/'private/readings'/m[1]/m[2]).is_file():
   result.append({'index':i,'src':f'/studio/api/guest/image/{row["id"]}/{i}','caption':str(im.get('caption','')),'before_block':max(0,int(im.get('before_block',0)))})
 return result

def image_path(db,aid,index):
 found=rows(db,aid)
 if not found or index not in {m['index'] for m in media(found[0])}:return None
 url=parsed(found[0])['illustrations'][index]['url']
 return ROOT/'private/readings'/pathlib.PurePosixPath(url).parts[-2]/pathlib.PurePosixPath(url).parts[-1]

def brief(row):
 data=parsed(row);category='故事' if data.get('genre')=='fiction' else data.get('category') or '随笔'
 images=media(row)
 return {'id':row['id'],'title':row['title'],'url':row['url'],'category':category,'date':row['created_at'][:10],
         'excerpt':row['body'].replace('\n',' ')[:115],'has_body':bool(row['body'] or data.get('blocks')),
         'cover':images[0]['src'] if images else None,'length':len(row['body'])}

def article(db,aid):
 found=rows(db,aid)
 if not found:return None
 row=found[0];data=parsed(row);blocks=[]
 for block in data.get('blocks',[]):
  if isinstance(block,dict) and isinstance(block.get('text'),str):blocks.append({'type':'heading' if block.get('type')=='heading' else 'paragraph','text':block['text']})
 if not blocks:blocks=[{'type':'paragraph','text':s} for s in row['body'].split('\n') if s.strip()]
 return {**brief(row),'blocks':blocks,'images':media(row)}

def snapshot(db):
 import wiki
 articles=[brief(r) for r in rows(db)]
 cards=[]
 for c in wiki.load():
  if not wiki.eligible(c)[0]:continue
  m=c.get('metrics',{});a=c.get('analysis',{})
  cards.append({'id':c['id'],'title':c['title'],'url':c['url'],'platform':c['platform'],'tags':c.get('tags',[]),
                'likes':m.get('likes'),'comments':m.get('comments'),'observed_at':m.get('observed_at'),
                'analysis':{k:a.get(k) for k in ['开头','推进','证据','结尾','可迁移','不可迁移','反馈解释假设','适用限制'] if a.get(k)}})
 return {'mode':'guest','can_use_ai':False,'profile_url':PROFILE,'author':'leon鸣','articles':articles,'references':cards,
         'policy':{'rule':'优先筛选有可核验互动反馈的样本，阅读全文后分析写法。互动数据提供参考，不能证明文章受欢迎的唯一原因。','metric_max_age_days':wiki.POLICY.get('metric_max_age_days')}}
