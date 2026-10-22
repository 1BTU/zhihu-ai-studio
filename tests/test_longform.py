import copy,json,pathlib,tempfile,unittest
from unittest import mock
import daily,longform
class LongformTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=pathlib.Path(t.name)
  p=mock.patch.object(daily,'RUN',self.root);p.start();self.addCleanup(p.stop)
  self.article={'title':'测试长文','topic_key':'test','blocks':[{'type':'paragraph','text':'背景'}],'sources':[]}
 def runner(self,prompt,output,schema):
  if output.name.endswith('-plan.json'):return {'sections':[{'title':f'节{i}','purpose':'展开论证','facts':'已核实材料'} for i in range(6)]}
  return {'blocks':[{'type':'paragraph','text':'文'*2000}]}
 def test_expand_and_resume_without_duplicate_generation(self):
  with mock.patch.object(daily,'agent',side_effect=self.runner) as run:
   result=longform.expand(daily,self.article,1);self.assertEqual(longform.words(result),12000);self.assertEqual(run.call_count,7)
   longform.expand(daily,self.article,1);self.assertEqual(run.call_count,7)
 def test_changed_seed_does_not_reuse_old_chapters(self):
  with mock.patch.object(daily,'agent',side_effect=self.runner) as run:
   longform.expand(daily,self.article,1);changed=copy.deepcopy(self.article);changed['title']='新标题';longform.expand(daily,changed,1);self.assertEqual(run.call_count,14)
 def test_short_sections_do_not_pass(self):
  def run(prompt,output,schema):
   if output.name.endswith('-plan.json'):return self.runner(prompt,output,schema)
   return {'blocks':[{'type':'paragraph','text':'太短'}]}
  with mock.patch.object(daily,'agent',side_effect=run):
   with self.assertRaisesRegex(RuntimeError,'有效字数'):longform.expand(daily,self.article,1)
 def test_long_review_preserves_full_text_and_proof(self):
  article=copy.deepcopy(self.article);article['blocks']=[{'type':'paragraph','text':'文'*2000} for _ in range(6)]
  with mock.patch.object(daily,'validate_article'),mock.patch.object(daily,'agent',return_value={'verdict':'approved','issues':[],'changes':[{'index':2,'original':'文'*2000,'text':'改'*2000}]}):result=longform.review(daily,article,1)
  self.assertEqual(longform.words(result),12000);self.assertEqual(result['blocks'][2]['text'],'改'*2000);daily.validate_review(result)
 def test_review_cannot_shorten_below_target(self):
  article=copy.deepcopy(self.article);article['blocks']=[{'type':'paragraph','text':'文'*11000}]
  with mock.patch.object(daily,'validate_article'),mock.patch.object(daily,'agent',return_value={'verdict':'approved','issues':[],'changes':[{'index':0,'original':'文'*11000,'text':'短文'}]}):
   with self.assertRaisesRegex(RuntimeError,'10000'):longform.review(daily,article,1)
 def test_review_rejects_wrong_paragraph_even_if_index_is_valid(self):
  article=copy.deepcopy(self.article);article['blocks']=[{'type':'paragraph','text':'文'*11000}]
  with mock.patch.object(daily,'validate_article'),mock.patch.object(daily,'agent',return_value={'verdict':'approved','issues':[],'changes':[{'index':0,'original':'别的段落','text':'改'*11000}]}):
   with self.assertRaisesRegex(RuntimeError,'原文与段落位置不匹配'):longform.review(daily,article,1)
  self.assertEqual(article['blocks'][0]['text'],'文'*11000)
 def test_review_input_has_explicit_indices_without_polluting_final_blocks(self):
  article=copy.deepcopy(self.article);article['blocks']=[{'type':'paragraph','text':'文'*11000}]
  def review(prompt,output,schema):
   data=json.loads((self.root/'review-1-round-1-input.json').read_text());self.assertEqual(data['blocks'][0]['index'],0)
   return {'verdict':'approved','issues':[],'changes':[]}
  with mock.patch.object(daily,'validate_article'),mock.patch.object(daily,'agent',side_effect=review):result=longform.review(daily,article,1)
  self.assertNotIn('index',result['blocks'][0])
if __name__=='__main__':unittest.main()
