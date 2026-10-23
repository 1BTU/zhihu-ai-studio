import unittest,tempfile,pathlib
from unittest.mock import patch
import meme_crawl as crawl,wiki
class CrawlTests(unittest.TestCase):
 def test_extract_only_body_and_limit_excerpt(self):
  html='<h1 id="doctitle">浪漫过敏症</h1><div id="content-body"><div class="content_topp"><p>'+('原站释义内容'*40)+'</p></div></div><footer>不能收录页脚</footer>'
  e=crawl.parse('https://hddid.com/doc-view-1.html',html)
  self.assertEqual(e['name'],'浪漫过敏症');self.assertEqual(len(e['excerpt']),101);self.assertNotIn('页脚',e['excerpt']);self.assertIsNone(e['published_at'])
 def test_no_body_rejected(self):
  with self.assertRaises(ValueError):crawl.parse('https://hddid.com/doc-view-1.html','<h1 id="doctitle">标题</h1>')
 def test_dedup_and_exclusion_from_writing(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(wiki,'ROOT',pathlib.Path(tmp)):
   e={'name':'浪漫过敏症','excerpt':'原站释义','title':'浪漫过敏症','url':'https://hddid.com/doc-view-1.html','published_at':None}
   self.assertTrue(crawl.merge(e));self.assertFalse(crawl.merge(e));self.assertEqual(len(wiki.load_memes()),1);self.assertEqual(wiki.meme_search('浪漫'),[])
 def test_model_not_used(self):
  with patch.object(crawl.collect.providers,'run') as model:
   crawl.parse('https://hddid.com/doc-view-1.html','<h1 id="doctitle">词条</h1><div id="content-body"><div class="content_topp"><p>这是一份足够长的原站释义，直接读取不必模型生成。</p></div></div>');model.assert_not_called()
