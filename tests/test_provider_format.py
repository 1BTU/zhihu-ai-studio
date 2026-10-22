import json,pathlib,sys,tempfile,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'studio'))
import providers
class FormatTests(unittest.TestCase):
 def run_responses(self,contents):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=pathlib.Path(temp.name)
  schema=root/'schema.json';schema.write_text(json.dumps({'type':'object','properties':{'answer':{'type':'string'}},'required':['answer'],'additionalProperties':False}))
  responses=[]
  for content in contents:
   response=mock.MagicMock();response.__enter__.return_value=response;response.status_code=200
   response.iter_lines.return_value=iter(['data: '+json.dumps({'choices':[{'delta':{'content':content},'finish_reason':'stop'}]}),'data: [DONE]']);responses.append(response)
  self.post=mock.patch.object(providers.requests,'post',side_effect=responses).start();self.addCleanup(mock.patch.stopall)
  mock.patch.object(providers,'load',return_value={'providers':[{'id':'deepseek','models':['test'],'base_url':'https://example.test','key':'test'}]}).start()
  events=[]
  return lambda **kwargs:providers.run('deepseek:test','输出JSON测试',root/'out.json',schema,lambda k,v:events.append((k,v)),**kwargs),root,events
 def test_summary_mode_disables_research_tools(self):
  run,root,events=self.run_responses(['{"answer":"summary"}'])
  self.assertEqual(run(research=False),{'answer':'summary'})
  self.assertNotIn('tools',self.post.call_args.kwargs['json'])
 def test_json_mode_and_bounded_format_correction(self):
  run,root,events=self.run_responses(['not json','{"answer":"ok"}']);self.assertEqual(run(),{'answer':'ok'})
  self.assertEqual(self.post.call_count,2);payloads=[x.kwargs['json'] for x in self.post.call_args_list]
  self.assertEqual(payloads[0]['response_format'],{'type':'json_object'});self.assertNotIn('tools',payloads[1]);self.assertIn('line',json.loads((root/'out.validation.json').read_text())[0]);self.assertTrue(any(v.get('phase')=='结果整理' for _,v in events))
 def test_invalid_output_stops_after_two_corrections(self):
  run,root,events=self.run_responses(['bad']*3)
  with self.assertRaisesRegex(RuntimeError,'2次纠错'):run()
  self.assertEqual(self.post.call_count,3);self.assertEqual((root/'out.invalid.txt').read_text(),'bad');self.assertFalse((root/'out.json').exists())

 def test_extra_closer_and_misplaced_mode_preserve_revise(self):
  value={'verdict':'revise','issues':['还需核实'],'article':{'writing_plan':{'content_mode':'hot'},'blocks':[{'text':'正文保留'}]}}
  result,repairs=providers.parse_model_json(json.dumps(value)+'}')
  self.assertEqual(result['verdict'],'revise');self.assertEqual(result['issues'],['还需核实'])
  self.assertEqual(result['article']['content_mode'],'hot');self.assertEqual(result['article']['blocks'],value['article']['blocks']);self.assertEqual(len(repairs),2)
 def test_premature_root_closure_rejoins_without_changing_review(self):
  result,repairs=providers.parse_model_json('{"verdict":"revise","issues":["核实"]},"article":{"title":"原稿"}}')
  self.assertEqual(result,{'verdict':'revise','issues':['核实'],'article':{'title':'原稿'}})
  self.assertEqual(len(repairs),1)
 def test_ambiguous_or_truncated_json_is_not_repaired(self):
  for raw in ['{"answer":"one"}{"answer":"two"}','{"answer":"a","answer":"b"}','{"answer":"incomplete"','{"answer":"ok"} explanation']:
   with self.subTest(raw=raw),self.assertRaises(ValueError):providers.parse_model_json(raw)
 def test_normalized_output_still_must_pass_schema(self):
  run,root,events=self.run_responses(['{"wrong":"x"}}','{"answer":"ok"}}'])
  self.assertEqual(run(),{'answer':'ok'});self.assertEqual(self.post.call_count,2)
  self.assertTrue((root/'out.normalization.json').exists());self.assertTrue((root/'out.invalid-1.txt').exists())

if __name__=='__main__':unittest.main()
