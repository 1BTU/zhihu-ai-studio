import json,pathlib,sqlite3,sys,tempfile,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'studio'))
import guest
class GuestTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name);self.db=self.root/'test.db'
  with sqlite3.connect(self.db) as c:
   c.execute('CREATE TABLE articles(id,title,body,data,url,created_at,status)')
   for status in ['published','ready','deleted','draft']:
    c.execute('INSERT INTO articles VALUES(?,?,?,?,?,?,?)',(status,'Title','Public text',json.dumps({'secret':'PRIVATE_SECRET','prompt':'PRIVATE_PROMPT','blocks':[{'text':'Public text','type':'paragraph','secret':'PRIVATE_BLOCK'}]}),'https://zhuanlan.zhihu.com/p/123','2026-10-22',status))
 def test_only_published_articles_are_exposed(self):
  self.assertEqual([r['id'] for r in guest.rows(self.db)],['published'])
  for aid in ['ready','deleted','draft',"' OR 1=1 --"]:self.assertIsNone(guest.article(self.db,aid))
  value=json.dumps(guest.article(self.db,'published'));self.assertNotIn('PRIVATE_',value);self.assertNotIn('prompt',value)
 def test_image_allowlist_and_unpublication(self):
  folder=self.root/'private/readings/example';folder.mkdir(parents=True);(folder/'cover.png').write_bytes(b'image')
  data={'illustrations':[{'url':'/studio/readings/example/cover.png'},{'url':'/studio/readings/example/../../secret.png'},{'url':'https://external.test/image.png'}]}
  with sqlite3.connect(self.db) as c:c.execute('UPDATE articles SET data=? WHERE id=?',(json.dumps(data),'published'))
  with mock.patch.object(guest,'ROOT',self.root):
   self.assertEqual(len(guest.article(self.db,'published')['images']),1)
   self.assertEqual(guest.image_path(self.db,'published',0),folder/'cover.png')
   self.assertIsNone(guest.image_path(self.db,'published',1))
   with sqlite3.connect(self.db) as c:c.execute("UPDATE articles SET status='deleted' WHERE id='published'")
   self.assertIsNone(guest.image_path(self.db,'published',0))
 def test_reference_projection_omits_private_evidence(self):
  import wiki
  card={'id':'approved','title':'Reference','url':'https://example.com','platform':'test','metrics':{'likes':100,'proof':'PRIVATE_PROOF'},'analysis':{'开头':'Analysis','private':'PRIVATE_ANALYSIS'},'source_path':'PRIVATE_PATH'}
  with mock.patch.object(wiki,'load',return_value=[card,{**card,'id':'rejected'}]),mock.patch.object(wiki,'eligible',side_effect=lambda c:(c['id']=='approved',[])):
   data=guest.snapshot(self.db)
  self.assertFalse(data['can_use_ai']);self.assertEqual(len(data['references']),1);self.assertNotIn('PRIVATE_',json.dumps(data))
if __name__=='__main__':unittest.main()
