import copy,datetime as dt,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
import wiki,wiki_collect as collect
class WikiCollectTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  self.patch=patch.object(wiki,'ROOT',self.root);self.patch.start();self.addCleanup(self.patch.stop)
  (self.root/'wiki/cards').mkdir(parents=True);(self.root/'catalog.json').write_text('[]')
 def test_interaction_gate(self):
  for likes,comments,expected in [(99,1000,False),(100,19,False),(100,20,True),(300,0,True)]:
   self.assertEqual(collect.qualifies({'likes':likes,'comments':comments}),expected)
 def test_article_dedup_and_evidence(self):
  source={'url':'https://sspai.com/post/999999','title':'test','author':'','text':'原文全文'*300,'likes':300,'comments':20,'observed_at':collect.stamp()}
  summary={'suitable':True,'tags':['生活'],'analysis':{k:'分析' for k in collect.ANALYSIS_KEYS}}
  self.assertTrue(collect.merge_card(source,summary,'deepseek:test'));self.assertFalse(collect.merge_card(source,summary,'deepseek:test'))
  card=wiki.load()[0];self.assertTrue(wiki.eligible(card)[0]);self.assertEqual(card['analysis_model'],'deepseek:test')
  proof=json.loads((self.root/card['metrics']['evidence_path']).read_text());self.assertNotIn('text',proof)
 def test_meme_evidence_required_and_sources_deduplicated(self):
  quote='这是报道中的测试梗，表示一种有明确语境的网络表达，不能凭空编造。'
  item={k:'说明' for k in ['meaning','origin_boundary','usage','avoid','example']};item.update(name='测试梗',evidence_quote=quote)
  source={'url':'https://www.chinanews.com/sh/2025/12-28/123.shtml','title':'原文','text':quote}
  self.assertEqual(collect.merge_memes(source,{'items':[item]},'deepseek:test'),1)
  self.assertEqual(collect.merge_memes(source,{'items':[item]},'deepseek:test'),0)
  wrong=copy.deepcopy(item);wrong['name']='编造的梗'
  self.assertEqual(collect.merge_memes(source,{'items':[wrong]},'deepseek:test'),0)
  self.assertEqual(len(wiki.load_memes()),1);self.assertEqual(wiki.meme_search('测试')[0]['name'],'测试梗')
 def test_heat_age_uses_source_date_not_refresh_time(self):
  card={'sources':[{'published_at':'2020-01-01','observed_at':collect.stamp()}]}
  self.assertIn('历史',wiki.meme_status(card))
  card['sources'][0]['published_at']=dt.datetime.now(dt.timezone.utc).date().isoformat()
  self.assertEqual(wiki.meme_status(card),'近期有报道')
 def test_source_hosts_and_dates(self):
  self.assertFalse(collect.trusted_meme_url('https://news.cn.evil.test/a'))
  self.assertFalse(collect.trusted_meme_url('http://www.news.cn/a'))
  self.assertTrue(collect.trusted_meme_url('https://www.news.cn/a'))
  self.assertEqual(collect.source_date('https://www.news.cn/book/20251212/id/c.html'),'2025-12-12')
  self.assertIsNone(collect.source_date('https://www.news.cn/a'))
