"""Single-account session authentication shared by studio and wiki."""
import hashlib,hmac,json,secrets,time,pathlib,threading
from http.cookies import SimpleCookie
ROOT=pathlib.Path(__file__).resolve().parents[1]
FILE=ROOT/'private/studio/auth.json'
LOCK=threading.Lock();ATTEMPTS={}
def initialize():
 if FILE.exists():return
 account=json.loads((ROOT/'private/wiki-web-access.json').read_text());salt=secrets.token_hex(24)
 data={'username':account['username'],'salt':salt,'hash':hashlib.pbkdf2_hmac('sha256',account['password'].encode(),salt.encode(),600000).hex(),'sessions':{}}
 FILE.write_text(json.dumps(data));FILE.chmod(0o600)
def save(data):
 tmp=FILE.with_suffix('.tmp');tmp.write_text(json.dumps(data));tmp.chmod(0o600);tmp.replace(FILE)
def token(headers):
 try:
  cookie=SimpleCookie();cookie.load(headers.get('Cookie',''));return cookie['lc_session'].value
 except (KeyError,ValueError):return ''
def valid(headers):
 value=token(headers)
 if not value:return False
 with LOCK:
  data=json.loads(FILE.read_text());expiry=data['sessions'].get(hashlib.sha256(value.encode()).hexdigest(),0)
 return expiry>time.time()
def login(username,password,ip):
 with LOCK:
  now=time.time();attempts=[t for t in ATTEMPTS.get(ip,[]) if t>now-900]
  if len(attempts)>=10:raise ValueError('尝试次数较多，请15分钟后重试')
  data=json.loads(FILE.read_text());hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),data['salt'].encode(),600000).hex()
  if not (hmac.compare_digest(username.encode(),data['username'].encode()) and hmac.compare_digest(hashed,data['hash'])):
   ATTEMPTS[ip]=attempts+[now];raise ValueError('账号或密码不正确')
  ATTEMPTS.pop(ip,None);value=secrets.token_urlsafe(48)
  data['sessions']={k:v for k,v in data['sessions'].items() if v>now}
  data['sessions'][hashlib.sha256(value.encode()).hexdigest()]=now+30*86400;save(data);return value
def logout(headers):
 with LOCK:
  data=json.loads(FILE.read_text());data['sessions'].pop(hashlib.sha256(token(headers).encode()).hexdigest(),None);save(data)
def cookie(value):return 'lc_session='+value+'; Path=/; Max-Age='+('2592000' if value else '0')+'; Secure; HttpOnly; SameSite=Lax'
