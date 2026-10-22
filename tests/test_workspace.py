import importlib.util,pathlib,tempfile,unittest,json
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('workspace_test_server',ROOT/'studio/server.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class WorkspaceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=pathlib.Path(self.temp.name)
  for k,v in [('DB',self.path/'db'),('DATA',self.path)]:
   patch=mock.patch.object(s,k,v);patch.start();self.addCleanup(patch.stop)
  s.init()
 def draft(self,aid='a',status='ready'):
  with s.database() as c:c.execute('INSERT INTO articles VALUES(?,?,?,?,NULL,?,?,?, ?,?,NULL)',(aid,'稿件','正文','{}',status,'已审稿','chat',s.now(),s.now()))
 def test_conversation_context_isolated_and_same_thread_serialized(self):
  with s.database() as c:a=s.domain.save_conversation(c,{'title':'甲'});b=s.domain.save_conversation(c,{'title':'乙'})
  ja=s.enqueue('chat',{'message':'甲','conversation_id':a});jb=s.enqueue('chat',{'message':'乙','conversation_id':b})
  with self.assertRaisesRegex(ValueError,'仍在生成'):s.enqueue('chat',{'message':'再问','conversation_id':a})
  with s.database() as c:
   self.assertEqual(c.execute('select conversation_id from job_context where job_id=?',(ja,)).fetchone()[0],a)
   self.assertEqual(c.execute('select conversation_id from job_context where job_id=?',(jb,)).fetchone()[0],b)
 def test_trash_restore_and_published_protection(self):
  self.draft();self.draft('b','published')
  with s.database() as c:s.domain.trash(c,['a'])
  self.assertEqual(s.get_article('a')['status'],'deleted')
  with self.assertRaises(ValueError):
   with s.database() as c:s.domain.trash(c,['b'])
  with s.database() as c:s.domain.trash(c,['a'],True)
  self.assertEqual(s.get_article('a')['status'],'ready')
 def test_bulk_delete_atomic_and_pending_protected(self):
  self.draft();self.draft('b','published')
  with self.assertRaises(ValueError):
   with s.database() as c:s.domain.trash(c,['a','b'])
  self.assertEqual(s.get_article('a')['status'],'ready')
  s.enqueue('publish',{'article_id':'a'})
  with self.assertRaisesRegex(ValueError,'关联任务'):
   with s.database() as c:s.domain.trash(c,['a'])
 def test_unknown_model_and_column_binding_rejected(self):
  with self.assertRaises(ValueError):
   with s.database() as c:s.domain.save_conversation(c,{'model':'fake:unknown'})
  with self.assertRaisesRegex(ValueError,'实际可管理'):
   with s.database() as c:s.domain.save_column(c,{'name':'测试','genre':'fiction','target':'unowned'})
 def test_model_key_never_in_public_settings(self):
  with mock.patch.object(s.providers,'load',return_value={'default':'codex','review':'','providers':[{'id':'test','key':'secret-value','models':[]}]}):
   self.assertNotIn('secret-value',json.dumps(s.providers.public()));self.assertNotIn('"key"',json.dumps(s.providers.public()))
 def test_tool_blocks_private_material_and_local_urls(self):
  with self.assertRaises(ValueError):s.providers.tool('read_material',{'path':str(ROOT/'private/wiki-web-access.json')},self.path)
  for url in ['https://127.0.0.1/','http://example.com','https://localhost/',s.ORIGIN+'/wiki/']:
   with self.assertRaises(ValueError):s.providers.public_url(url)
 def test_auth_login_logout_and_password_failure(self):
  salt='salt';password='test-password'
  with mock.patch.object(s.auth,'FILE',self.path/'auth.json'):
   s.auth.save({'username':'yc','salt':salt,'hash':s.auth.hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex(),'sessions':{}})
   with self.assertRaises(ValueError):s.auth.login('yc','bad','test')
   token=s.auth.login('yc',password,'test');headers={'Cookie':'lc_session='+token}
   self.assertTrue(s.auth.valid(headers));self.assertIn('HttpOnly',s.auth.cookie(token));s.auth.logout(headers);self.assertFalse(s.auth.valid(headers))
 def test_fiction_requires_label_and_hash_covers_genre(self):
  a={'event_date':str(s.daily.TODAY),'genre':'fiction','blocks':[{'text':'故事。'*400}],'sources':[]}
  with mock.patch.object(s.daily.writing_wiki,'validate_plan'):
   with self.assertRaisesRegex(RuntimeError,'虚构'):s.daily.validate_article(a)
   a['blocks'][0]['text']='原创虚构。'+a['blocks'][0]['text'];s.daily.validate_article(a)
  self.assertNotEqual(s.daily.article_fingerprint(a),s.daily.article_fingerprint({**a,'genre':None}))
 def test_fiction_schema_accepts_explicit_genre(self):
  schema=json.loads((ROOT/'fiction-review-schema.json').read_text())
  article_schema=next(x for x in schema['properties']['article']['anyOf'] if x.get('type')=='object')
  self.assertEqual(article_schema['properties']['genre']['enum'],['fiction'])
  self.assertEqual(article_schema['properties']['sources']['minItems'],0)

 def test_web_search_uses_standard_xml_parser(self):
  response=mock.Mock(text='<rss><channel><item><title>来源</title><link>https://example.com/a</link><description>摘要</description></item></channel></rss>')
  with mock.patch.object(s.providers.requests,'get',return_value=response):
   rows=s.providers.tool('search_web',{'query':'测试'},self.path)
  self.assertEqual(rows[0]['url'],'https://example.com/a')

if __name__=='__main__':unittest.main()
