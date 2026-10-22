import copy, datetime as dt, unittest
from unittest.mock import patch
import daily

class ContentModeTests(unittest.TestCase):
 def article(self,mode):
  return {'content_mode':mode,'event_date':str(daily.TODAY-dt.timedelta(days=30)),
   'blocks':[{'type':'paragraph','text':'原创虚构故事。'+'人物走进了房间。'*120}],
   'sources':[]}
 def test_old_news_still_rejected_but_evergreen_date_allowed(self):
  a=self.article('hot');a['sources']=[{'url':'https://example.org/a'},{'url':'https://example.org/b'}]
  with patch.object(daily.writing_wiki,'validate_plan'):
   with self.assertRaisesRegex(RuntimeError,'日期'):daily.validate_article(a)
   a['content_mode']='evergreen';daily.validate_article(a)
 def test_fiction_needs_label_not_fake_sources(self):
  a=self.article('fiction')
  with patch.object(daily.writing_wiki,'validate_plan'):
   daily.validate_article(a)
   a['blocks'][0]['text']=a['blocks'][0]['text'].replace('原创虚构故事。','')
   with self.assertRaisesRegex(RuntimeError,'虚构'):daily.validate_article(a)
 def test_nonfiction_still_needs_sources_and_future_dates_rejected(self):
  a=self.article('evergreen')
  with patch.object(daily.writing_wiki,'validate_plan'):
   with self.assertRaisesRegex(RuntimeError,'来源不足'):daily.validate_article(a)
   a['content_mode']='fiction';a['event_date']=str(daily.TODAY+dt.timedelta(days=1))
   with self.assertRaisesRegex(RuntimeError,'日期'):daily.validate_article(a)
 def test_mode_is_part_of_review_fingerprint(self):
  a=self.article('fiction');b=copy.deepcopy(a);b['content_mode']='evergreen'
  self.assertNotEqual(daily.article_fingerprint(a),daily.article_fingerprint(b))

 def test_prepared_length_excludes_only_appended_sources(self):
  a=self.article('evergreen')
  a['sources']=[{'title':'source','url':'https://example.org/'+('x'*2000),'date':str(daily.TODAY)}]
  expected=sum(len(b['text']) for b in a['blocks'])
  prepared=daily.prepare_article(a)
  self.assertEqual(daily.prepared_body_length(prepared),expected)
  a['sources']=[]
  self.assertEqual(daily.prepared_body_length(daily.prepare_article(a)),expected)
