"""Deterministic dictionary ingestion: short attributed excerpts, no model calls."""
import datetime as dt,hashlib,json,pathlib,re,time,urllib.parse
import requests
from bs4 import BeautifulSoup
import wiki_collect as collect
ROOT=pathlib.Path(__file__).resolve().parent
RULES={'www.moyuoo.com':(r'/archives/\d+\.html','h1','.entry-content'),'hddid.com':(r'/doc-view-\d+\.html','#doctitle','#content-body .content_topp')}
def get_html(url):
 for _ in range(3):
  collect.providers.public_url(url)
  with requests.get(url,headers={'User-Agent':'WritingWiki/1.0 (reference collector)'},timeout=(10,15),allow_redirects=False,stream=True) as r:
   if r.status_code in (301,302,303,307,308):
    target=urllib.parse.urljoin(url,r.headers['Location'])
    if urllib.parse.urlsplit(target).hostname!=urllib.parse.urlsplit(url).hostname:raise ValueError('Cross-domain redirect')
    url=target;continue
   r.raise_for_status()
   if 'text/html' not in r.headers.get('Content-Type',''):raise ValueError('Not HTML')
   raw=b''
   for chunk in r.iter_content(16384):
    raw+=chunk
    if len(raw)>1500000:raise ValueError('Page too large')
   return raw
 raise ValueError('Too many redirects')
def parse(url,html):
 host=urllib.parse.urlsplit(url).hostname
 pattern,title_selector,body_selector=RULES[host]
 if not re.fullmatch(pattern,urllib.parse.urlsplit(url).path):raise ValueError('Not entry URL')
 soup=BeautifulSoup(html,'html.parser');title=soup.select_one(title_selector);bodies=soup.select(body_selector)
 if not title or not bodies:raise ValueError('Missing entry')
 name=re.sub(r'(是什么梗|是什么意思|是梗)[？?]?$', '',title.get_text(' ',strip=True)).strip()
 if not name or len(name)>80:raise ValueError('Invalid name')
 paragraphs=[]
 for body in bodies:
  for node in body(['script','style','form']):node.decompose()
  for p in body.select('p'):
   text=p.get_text(' ',strip=True)
   if text.startswith(('声明','关联科普','本站','版权','广告')):break
   if len(text)>=18:paragraphs.append(text)
 if not paragraphs:raise ValueError('No definition paragraph')
 text=paragraphs[0];excerpt=text[:100]+('…' if len(text)>100 else '')
 published=None;meta=soup.select_one('meta[property="article:published_time"]')
 if meta:
  try:published=dt.date.fromisoformat(meta.get('content','')[:10]).isoformat()
  except ValueError:pass
 return {'name':name,'excerpt':excerpt,'published_at':published,'url':url,'title':title.get_text(' ',strip=True)}
def merge(entry):
 normalized=re.sub(r'[\s，,。！？!?：:、]','',entry['name']).casefold()
 cid='raw-meme-'+hashlib.sha256(normalized.encode()).hexdigest()[:16]
 source={'url':entry['url'],'title':entry['title'],'published_at':entry['published_at'],'observed_at':collect.stamp(),'retrieval':'直接采集原站短摘录','quote':entry['excerpt']}
 with collect.catalog_lock():
  cards=collect.wiki.load_memes()
  if any(any(s['url']==entry['url'] for s in c.get('sources',[])) for c in cards):return False
  old=next((c for c in cards if c['id']==cid),None)
  if old:old['sources'].append(source)
  else:cards.append({'id':cid,'name':entry['name'],'title':entry['name'],'meaning':entry['excerpt'],'origin_boundary':'原站释义短摘录，未经事实核实；不代表已证实起源或当下流行。','usage':'使用前打开原文核实语境。','avoid':'未审核，不进入自动写作参考集。','example':'未生成例句。','ingestion_type':'raw','analysis_status':'unreviewed','analysis_model':None,'updated_at':collect.stamp(),'sources':[source],'tags':['原始词条','待核实']})
  collect.save(collect.wiki.ROOT/'memes.json',cards)
 return old is None

def run(limit=15):
 seeds=collect.read(ROOT/'meme-sites.json',[]);known={s['url'] for c in collect.wiki.load_memes() for s in c.get('sources',[])}
 status={'started_at':collect.stamp(),'mode':'直接采集，无模型调用','added':0,'checked':0,'errors':[]}
 for seed in seeds:
  host=urllib.parse.urlsplit(seed['url']).hostname
  if host not in RULES:continue
  try:
   soup=BeautifulSoup(get_html(seed['url']),'html.parser');urls=[]
   for a in soup.select('a[href]'):
    url=urllib.parse.urljoin(seed['url'],a['href']);u=urllib.parse.urlsplit(url)
    if u.hostname==host and re.fullmatch(RULES[host][0],u.path):urls.append(urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,'','')))
   pending=[u for u in dict.fromkeys(urls) if u not in known][:max(1,min(50,limit))]
   for url in pending:
    try:
     status['checked']+=1
     if merge(parse(url,get_html(url))):status['added']+=1
    except Exception as e:status['errors'].append({'url':url,'error':type(e).__name__})
    time.sleep(.4)
  except Exception as e:status['errors'].append({'url':seed['url'],'error':type(e).__name__})
 status['finished_at']=collect.stamp();collect.save(collect.wiki.ROOT/'raw-meme-status.json',status);return status
if __name__=='__main__':
 import fcntl,sys,subprocess
 folder=ROOT/'private/wiki-ingest';folder.mkdir(parents=True,exist_ok=True)
 with (folder/'collect.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  print(json.dumps(run(),ensure_ascii=False));subprocess.run([sys.executable,str(ROOT/'sync-web.py')],check=True)
