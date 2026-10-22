"""Fetch project-owned illustrations, checking bytes before browser upload."""
import pathlib,hashlib,requests,copy,re
from PIL import Image
import runtime
from urllib.parse import urlsplit
ROOT=pathlib.Path(__file__).resolve().parent

def prepare(article,folder):
 result=copy.deepcopy(article);directory=pathlib.Path(folder)/'images';directory.mkdir(parents=True,exist_ok=True)
 for i,image in enumerate(result.get('illustrations',[])):
  url=image.get('hosted_url','')
  base=runtime.IMAGE_BASE;parts=urlsplit(url)
  if base=='/' or not url.startswith(base) or parts.scheme!='https' or parts.query or parts.fragment or not re.fullmatch(r'[a-zA-Z0-9_./-]+\.(?:png|jpg|jpeg|webp)',url[len(base):]) or '..' in parts.path.split('/'):raise ValueError('配图不是已配置图床中的图片，请设置 IMAGE_HOST_BASE')
  target=directory/f'image-{i+1}{pathlib.PurePosixPath(url).suffix}'
  expected=image.get('hosted_sha256')
  if not expected:raise ValueError('配图缺少原图校验值')
  if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
   session=requests.Session();session.trust_env=False
   response=session.get(url,timeout=60);response.raise_for_status()
   if hashlib.sha256(response.content).hexdigest()!=expected:raise ValueError('图床图片与审阅原图不一致')
   temp=target.with_suffix('.tmp');temp.write_bytes(response.content)
   with Image.open(temp) as decoded:decoded.verify()
   temp.replace(target);target.chmod(0o600)
  image['local_path']=str(target.resolve())
 return result
