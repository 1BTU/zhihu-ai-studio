import importlib.util,pathlib,tempfile,unittest
from unittest import mock
spec=importlib.util.spec_from_file_location('writing_studio',pathlib.Path(__file__).resolve().parents[1]/'studio/server.py');studio=importlib.util.module_from_spec(spec);spec.loader.exec_module(studio)
class StudioTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=pathlib.Path(self.temp.name)
  for k,v in [('DATA',self.path),('DB',self.path/'test.sqlite3')]:
   p=mock.patch.object(studio,k,v);p.start();self.addCleanup(p.stop)
  studio.init()
 def test_publication_requires_current_explicit_request(self):
  self.assertTrue(studio.may_publish('发布这篇'));self.assertTrue(studio.may_publish('写好以后发布到知乎'))
  for t in ['不要发布','先不发布','可以发布吗？','能否发布','讨论一下发布流程怎么设计','请修改一下文章']:self.assertFalse(studio.may_publish(t))
 def test_sync_requests_are_coalesced(self):
  self.assertEqual(studio.enqueue('sync',{}),studio.enqueue('sync',{}))
 def test_duplicate_publish_queue_rejected(self):
  studio.enqueue('publish',{'article_id':'draft-a'})
  with self.assertRaisesRegex(ValueError,'正在发布'):studio.enqueue('publish',{'article_id':'draft-a'})
 def test_published_article_not_submitted_again(self):
  with studio.database() as c:c.execute("INSERT INTO articles VALUES('a','title','body','{}','https://zhuanlan.zhihu.com/p/123','published','已发布','chat',?, ?,NULL)",(studio.now(),studio.now()))
  with mock.patch.object(studio,'command') as command:result=studio.publish_article('a',self.path)
  command.assert_not_called();self.assertIn('没有重复提交',result['answer'])
 def test_missing_review_blocks_external_actions(self):
  with studio.database() as c:c.execute("INSERT INTO articles VALUES('a','title','body','{}',NULL,'ready','内部审稿通过','chat',?, ?,?)",(studio.now(),studio.now(),str(self.path)))
  with mock.patch.object(studio,'command') as command:
   with self.assertRaisesRegex(RuntimeError,'审稿'):studio.publish_article('a',self.path)
  command.assert_not_called()
 def test_server_restart_does_not_retry_running_publish(self):
  jid=studio.enqueue('publish',{'article_id':'a'})
  with studio.database() as c:c.execute("UPDATE jobs SET status='running' WHERE id=?",(jid,))
  studio.init()
  with studio.database() as c:self.assertEqual(c.execute('SELECT status FROM jobs WHERE id=?',(jid,)).fetchone()[0],'failed')
 def test_metrics_time_uses_source_not_discovery(self):
  date=studio.content_time('发布于 10-21 15:45','fallback')
  self.assertTrue(date.endswith('07:45:00+00:00'));self.assertEqual(studio.content_time('未知','fallback'),'fallback')
 def test_evergreen_valid_but_daily_still_requires_fresh_event(self):
  a={'event_date':'2020-01-01','blocks':[{'type':'paragraph','text':'具体内容。'*250}],'sources':[{'url':'https://example.com/a'},{'url':'https://example.com/b'}]}
  with mock.patch.object(studio.daily.writing_wiki,'validate_plan'):
   studio.daily.validate_article(a,require_recent=False)
   with self.assertRaisesRegex(RuntimeError,'日期'):studio.daily.validate_article(a)
if __name__=='__main__':unittest.main()
