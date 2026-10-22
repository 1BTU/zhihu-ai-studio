import copy,json,pathlib,tempfile,unittest
from unittest import mock
import daily

class DailyReviewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.run=pathlib.Path(self.tmp.name)
  self.patch=mock.patch.object(daily,'RUN',self.run);self.patch.start();self.addCleanup(self.patch.stop)
  self.cfg=mock.patch.dict(daily.CFG,{'count':1,'publish':True,'review_max_rounds':3,'article_layout':[]});self.cfg.start();self.addCleanup(self.cfg.stop)
  self.article={'title':'测试选题','topic_key':'test_event','category':'科技','event_date':str(daily.TODAY),'blocks':[{'type':'paragraph','text':'待核实的具体内容。'*110}],
   'sources':[{'title':'来源甲','date':str(daily.TODAY),'url':'https://example.com/a'},{'title':'来源乙','date':str(daily.TODAY),'url':'https://example.com/b'}],
   'tags':['科技'],'writing_plan':{'reader_question':'问题','thesis':'判断','references':[{'id':c['id'],'learn':'结构','adapt':'重新组织本次事实'} for c in daily.writing_wiki.load() if daily.writing_wiki.eligible(c)[0]][:2],
    'outline':['背景','证据','判断'],'strongest_objection':'反方','evidence_boundary':'不虚构','changes_after_review':'记录修改'}}
 def runner(self,verdicts):
  def run(prompt,output,schema):
   v=verdicts.pop(0);a=copy.deepcopy(self.article)
   if not verdicts:a['title']='审核后的标题'
   d={'verdict':v,'issues':[] if v=='approved' else ['尚需核实'],'changes':['补充事件背景'],'article':a}
   daily.save(output,d);return d
  return run
 def test_old_five_article_day_does_not_publish_again(self):
  self.assertTrue(daily.completed_for_today({'notified':True,'articles':[{'status':'published'}]*5}))
  self.assertFalse(daily.completed_for_today({'notified':False,'articles':[{'status':'published'}]}))
 def test_revision_then_approval_and_source_append_once(self):
  with mock.patch.object(daily,'agent',side_effect=self.runner(['revise','approved'])) as runner:
   a=daily.review_article(self.article,1)
  self.assertEqual(runner.call_count,2);self.assertEqual(a['editorial_review']['rounds'],2)
  self.assertEqual(a['title'],'审核后的标题');self.assertEqual(sum(b['text']=='参考资料' for b in a['blocks']),1)
  self.assertNotIn('body',self.article);daily.validate_review(a)
 def test_reject_stops(self):
  with mock.patch.object(daily,'agent',side_effect=self.runner(['reject'])):
   with self.assertRaisesRegex(RuntimeError,'审稿未通过'):daily.review_article(self.article,1)
 def test_round_limit_stops(self):
  with mock.patch.object(daily,'agent',side_effect=self.runner(['revise']*3)) as runner:
   with self.assertRaisesRegex(RuntimeError,'轮次上限'):daily.review_article(self.article,1)
  self.assertEqual(runner.call_count,3)
 def test_modified_body_or_blocks_cannot_publish(self):
  with mock.patch.object(daily,'agent',side_effect=self.runner(['approved'])):a=daily.review_article(self.article,1)
  for field in ['body','blocks']:
   b=copy.deepcopy(a)
   if field=='body':b['body']+='变更'
   else:b['blocks'][0]['text']+='变更'
   with self.assertRaisesRegex(RuntimeError,'版本不一致'):daily.validate_review(b)
 def test_missing_review_and_invalid_proof_blocked(self):
  with self.assertRaisesRegex(RuntimeError,'缺少独立审稿'):daily.validate_review(self.article)
  with mock.patch.object(daily,'agent',side_effect=self.runner(['approved'])):a=daily.review_article(self.article,1)
  a['editorial_review']['proof']='../outside.json'
  with self.assertRaisesRegex(RuntimeError,'路径无效'):daily.validate_review(a)
 def test_generate_single_article_with_cached_draft_runs_editor(self):
  daily.save(self.run/'generation.json',{'status':'ready','report':'来源报告','articles':[self.article]})
  with mock.patch.object(daily,'agent',side_effect=self.runner(['approved'])):
   data=daily.generate()
  self.assertEqual(len(data['articles']),1);self.assertEqual(data['workflow_version'],2)
  daily.validate_review(data['articles'][0])
 def test_three_articles_are_individually_reviewed(self):
  articles=[dict(copy.deepcopy(self.article),title='选题'+str(i),topic_key='topic_'+str(i)) for i in range(3)]
  daily.save(self.run/'generation.json',{'status':'ready','report':'来源报告','articles':articles})
  with mock.patch.dict(daily.CFG,{'count':3}),mock.patch.object(daily,'review_article',side_effect=lambda a,index:a) as review:
   data=daily.generate()
  self.assertEqual(len(data['articles']),3);self.assertEqual([call.args[1] for call in review.call_args_list],[1,2,3])
 def test_quota_increase_does_not_repeat_completed_day(self):
  with mock.patch.dict(daily.CFG,{'count':3}):
   self.assertTrue(daily.completed_for_today({'notified':True,'articles':[{'status':'published'}]}))
   self.assertFalse(daily.completed_for_today({'notified':False,'articles':[{'status':'published'}]}))
 def test_main_skips_completed_old_day_without_network(self):
  daily.save(self.run/'state.json',{'notified':True,'notification_mode':'publish','articles':[{'status':'published'}]*5})
  with mock.patch('sys.argv',['daily.py']),mock.patch.object(daily,'authenticate') as auth,mock.patch.object(daily,'email') as email,mock.patch.object(daily,'generate') as generate:
   daily.main()
  auth.assert_not_called();email.assert_not_called();generate.assert_not_called()

if __name__=='__main__':unittest.main()
