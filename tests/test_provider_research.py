import json,pathlib,sys,tempfile,unittest
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'studio'))
import providers

class ResearchTests(unittest.TestCase):
 def setup_run(self,deltas,limit=2):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);folder=pathlib.Path(tmp.name)
  schema=folder/'schema.json';schema.write_text(json.dumps({'type':'object','properties':{'status':{'enum':['ready','insufficient_sources']}},'required':['status'],'additionalProperties':False}))
  responses=[]
  for delta in deltas:
   r=mock.MagicMock();r.__enter__.return_value=r;r.status_code=200;r.iter_lines.return_value=iter(['data: '+json.dumps({'choices':[{'delta':delta,'finish_reason':'tool_calls' if 'tool_calls' in delta else 'stop'}]}),'data: [DONE]']);responses.append(r)
  post=mock.patch.object(providers.requests,'post',side_effect=responses).start();self.addCleanup(mock.patch.stopall)
  mock.patch.object(providers,'load',return_value={'providers':[{'id':'test','models':['model'],'base_url':'https://example.test','key':'placeholder','research_round_limit':limit}]}).start()
  mock.patch.object(providers,'tool',return_value={'items':[]}).start()
  return lambda:providers.run('test:model','只用真实资料',folder/'out.json',schema),folder,post
 def call(self,n):return {'tool_calls':[{'index':0,'id':str(n),'function':{'name':'wiki_search','arguments':'{"query":"测试"}'}}]}
 def test_research_limit_reserves_final_answer_without_forcing_articles(self):
  run,folder,post=self.setup_run([self.call(1),self.call(2),{'content':'{"status":"insufficient_sources"}'}])
  self.assertEqual(run()['status'],'insufficient_sources');self.assertEqual(post.call_count,3)
  self.assertNotIn('tools',post.call_args_list[-1].kwargs['json'])
  trace=json.loads((folder/'out.research.json').read_text());self.assertEqual(trace['research_rounds'],2);self.assertTrue(trace['finalizing']);self.assertEqual(len(trace['history']),2);self.assertEqual(trace['status'],'completed')
  self.assertEqual((folder/'out.research.json').stat().st_mode&0o777,0o600)
 def test_final_answer_still_has_two_format_repair_attempts(self):
  run,folder,post=self.setup_run([self.call(1),self.call(2),{'content':'bad'},{'content':'bad'},{'content':'{"status":"insufficient_sources"}'}])
  self.assertEqual(run()['status'],'insufficient_sources');self.assertEqual(post.call_count,5)
 def test_unexpected_tool_request_during_finalization_stops(self):
  run,folder,post=self.setup_run([self.call(1),self.call(2),self.call(3)])
  with self.assertRaisesRegex(RuntimeError,'整理阶段仍请求工具'):run()
  self.assertFalse((folder/'out.json').exists());self.assertEqual(json.loads((folder/'out.research.json').read_text())['status'],'unexpected_tool_call')

class MaterialPathTests(unittest.TestCase):
 def test_relative_project_and_wiki_paths_use_same_allowlist(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);folder=root/'reports/day';folder.mkdir(parents=True);(root/'writing-wiki/wiki').mkdir(parents=True)
   (root/'writing-wiki/README.md').write_text('rules');(root/'writing-wiki/wiki/index.md').write_text('index');(folder/'hotspots.json').write_text('{}');(root/'private').mkdir();(root/'private/key.json').write_text('secret')
   with mock.patch.object(providers,'ROOT',root):
    self.assertEqual(providers.tool('read_material',{'path':'writing-wiki/README.md'},folder),'rules')
    self.assertEqual(providers.tool('read_material',{'path':'wiki/index.md'},folder),'index')
    self.assertEqual(providers.tool('read_material',{'path':'hotspots.json'},folder),'{}')
    for name in ['private/key.json','../../private/key.json']:
     with self.assertRaises(ValueError):providers.tool('read_material',{'path':name},folder)
    (folder/'out.research.json').write_text('{}')
    with self.assertRaises(ValueError):providers.tool('read_material',{'path':'out.research.json'},folder)

if __name__=='__main__':unittest.main()
