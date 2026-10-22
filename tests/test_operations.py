import unittest
from unittest.mock import patch
import operations
class OperationsTests(unittest.TestCase):
 def setUp(self):
  self.discovery={'details':[{'title':'问题的真实标题是什么？','url':'https://www.zhihu.com/question/123'}]}
  self.item={'kind':'answer','title':'问题的真实标题是什么？','target_url':'https://www.zhihu.com/question/123','body':'测试内容'*150,'reference_ids':['ref'],'sources':[{'url':'https://a.example'},{'url':'https://b.example'}]}
 def validate(self,items,history=[]):
  with patch('operations.wiki.load',return_value=[{'id':'ref'}]),patch('operations.wiki.eligible',return_value=(True,[])):
   operations.validate(items,self.discovery,history,{'answer_limit':2,'question_limit':1})
 def test_valid_answer(self):self.validate([self.item])
 def test_no_duplicate(self):
  with self.assertRaises(ValueError):self.validate([self.item,self.item])
  with self.assertRaises(ValueError):self.validate([self.item],[self.item])
 def test_unread_question_rejected(self):
  self.discovery['details']=[]
  with self.assertRaises(ValueError):self.validate([self.item])
 def test_changed_title_rejected(self):
  self.item['title']='改写了标题'
  with self.assertRaises(ValueError):self.validate([self.item])
 def test_missing_reference_rejected(self):
  self.item['reference_ids']=['unknown']
  with self.assertRaises(ValueError):self.validate([self.item])
