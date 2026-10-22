import importlib.util,json,pathlib,unittest
spec=importlib.util.spec_from_file_location('stream_adapter',pathlib.Path(__file__).resolve().parents[1]/'studio/streaming.py');stream=importlib.util.module_from_spec(spec);spec.loader.exec_module(stream)
class StreamTests(unittest.TestCase):
 def test_split_unicode_and_escape(self):
  self.assertEqual(stream.field_prefix('{"answer":"你好\\n世','answer'),'你好\n世')
  self.assertEqual(stream.field_prefix('{"answer":"a\\u4f','answer'),'a')
  self.assertEqual(stream.field_prefix('{"answer":"\\u4f60\\u597d"}','answer'),'你好')
 def test_private_reasoning_and_shell_output_never_emitted(self):
  seen=[];a=stream.PublicEvents(lambda k,v:seen.append((k,v)),'test')
  for method in ['item/reasoning/textDelta','item/reasoning/summaryTextDelta','item/commandExecution/outputDelta']:
   a.handle({'method':method,'params':{'delta':'PRIVATE_SECRET'}})
  a.handle({'method':'item/completed','params':{'item':{'type':'reasoning','text':'PRIVATE_SECRET'}}})
  self.assertEqual(seen,[])
 def test_public_progress_and_incremental_answer(self):
  seen=[];a=stream.PublicEvents(lambda k,v:seen.append((k,v)),'write')
  a.handle({'method':'item/started','params':{'item':{'id':'m','type':'agentMessage','phase':'final','text':''}}})
  for delta in ['{"answer":"你好','世界","action":"discuss"}']:
   a.handle({'method':'item/agentMessage/delta','params':{'itemId':'m','delta':delta}})
  a.handle({'method':'item/completed','params':{'item':{'id':'m','type':'agentMessage','phase':'final','text':'{"answer":"你好世界","action":"discuss"}'}}})
  answers=[v['text'] for k,v in seen if k=='answer'];self.assertEqual(answers[0],'你好');self.assertEqual(answers[-1],'你好世界');self.assertEqual(a.final['action'],'discuss')
 def test_structured_metadata_not_shown_as_response(self):
  text='{"answer":"好了","article":{"title":"题目","blocks":[{"type":"paragraph","text":"正文"}],"sources":[]},"writing_plan":{"secret":"PRIVATE"}}'
  self.assertEqual(stream.field_prefix(text,'answer'),'好了');self.assertEqual(stream.draft_prefix(text),'题目\n\n正文')
 def test_commentary_is_public_but_unlabelled_reasoning_is_not(self):
  seen=[];a=stream.PublicEvents(lambda k,v:seen.append((k,v)),'test')
  a.handle({'method':'item/completed','params':{'item':{'type':'agentMessage','id':'x','text':'检查资料中','phase':'commentary'}}})
  a.handle({'method':'item/completed','params':{'item':{'type':'agentMessage','id':'y','text':'unlabelled internal text'}}})
  self.assertEqual(len(seen),1);self.assertEqual(seen[0][0],'progress')
if __name__=='__main__':unittest.main()
